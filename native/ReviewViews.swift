// Purpose: native two-photo Compare and fitted multi-photo Survey surfaces.
// Inputs: Store selection and bounded review frames. Outputs: focus, candidate,
// rating/flag/label, zoom and pan actions. Deselect never deletes a catalog photo.
// Detail frames use physical screen scale; fitted survey images are not 1:1 views.
import AppKit
import SwiftUI

struct ReviewWorkspace: View {
    @EnvironmentObject var s: Store
    @ObservedObject var renderer: ReviewRenderer
    @FocusState private var keyboardFocus: Bool

    var body: some View {
        VStack(spacing:8) {
            HStack {
                Text(s.libraryView == .compare ? "Select & Candidate":"Survey · \(s.reviewPhotoIDs.count) photos")
                    .font(.headline)
                Spacer()
                Button { s.reviewNavigate(-1) } label: { Image(systemName:"chevron.left") }.help("Previous Photo")
                Button { s.reviewNavigate(1) } label: { Image(systemName:"chevron.right") }.help("Next Photo")
                Button("Done") { Task { await s.switchLibraryView(.loupe) } }
            }.padding(.horizontal,12).padding(.top,10)
            if s.libraryView == .compare { compareControls }
            GeometryReader { geometry in
                if s.reviewPhotoIDs.isEmpty {
                    ContentUnavailableView("Select Photos to Review",systemImage:"photo.on.rectangle",
                        description:Text("Select photos in the filmstrip or return to Grid."))
                } else if s.libraryView == .compare {
                    HStack(spacing:8) {
                        ForEach(s.reviewPhotoIDs,id:\.self) { id in
                            if let photo=s.photos.first(where: { $0.id == id }) {
                                ReviewPhotoCard(photo:photo,role:id == s.review.selectID ? "Select":"Candidate",renderer:renderer)
                            }
                        }
                        if s.reviewPhotoIDs.count == 1 {
                            Text("Select another candidate in the filmstrip")
                                .font(.callout).foregroundStyle(.secondary).frame(maxWidth:.infinity,maxHeight:.infinity)
                        }
                    }
                } else {
                    let ids=s.reviewPhotoIDs
                    let columns=min(ids.count,max(1,Int(ceil(sqrt(Double(ids.count)*geometry.size.width/max(1,geometry.size.height)/1.5)))))
                    let rows=(ids.count+columns-1)/columns
                    let width=max(1,(geometry.size.width-Double(columns-1)*8)/Double(columns))
                    let height=max(1,(geometry.size.height-Double(rows-1)*8)/Double(rows))
                    VStack(spacing:8) {
                        ForEach(0..<rows,id:\.self) { row in
                            HStack(spacing:8) {
                                ForEach(Array(ids.dropFirst(row*columns).prefix(columns)),id:\.self) { id in
                                    if let photo=s.photos.first(where: { $0.id == id }) {
                                        ReviewPhotoCard(photo:photo,role:nil,renderer:renderer,compact:width<240 || height<170)
                                            .frame(width:width,height:height)
                                    }
                                }
                            }.frame(maxWidth:.infinity)
                        }
                    }
                }
            }.padding(.horizontal,8).padding(.bottom,8)
        }
        .background(Color(nsColor:.underPageBackgroundColor))
        .focusable().focused($keyboardFocus)
        .onTapGesture { keyboardFocus=true }
        .modifier(PhotoKeyboardShortcuts())
        .onKeyPress(.leftArrow) { s.reviewNavigate(-1);return .handled }
        .onKeyPress(.rightArrow) { s.reviewNavigate(1);return .handled }
        .onKeyPress(.upArrow) { if s.libraryView == .compare { s.promoteReview();return .handled };return .ignored }
        .onKeyPress(.downArrow) { if s.libraryView == .compare { s.swapReview();return .handled };return .ignored }
        .onAppear { s.updateReviewRequests() }
        .onDisappear { renderer.stop() }
    }

    var compareControls: some View {
        VStack(spacing:6) {
            HStack(spacing:8) {
                Button { s.swapReview() } label: { Image(systemName:"arrow.left.arrow.right") }.help("Swap Select and Candidate")
                Button { s.promoteReview() } label: { Image(systemName:"arrow.up.to.line") }.help("Make Candidate the Select")
                Button {
                    s.review.linked.toggle()
                    if s.review.linked,let id=s.selected { s.review.synchronize(from:id);s.updateReviewRequests() }
                } label: { Image(systemName:s.review.linked ? "lock.fill":"lock.open") }
                    .help(s.review.linked ? "Linked zoom and pan":"Independent zoom and pan")
                    .accessibilityLabel(s.review.linked ? "Unlink zoom and pan":"Link zoom and pan")
                Button("Sync") { if let id=s.selected { s.review.synchronize(from:id);s.updateReviewRequests() } }
                Spacer(minLength:0)
                Picker("Zoom",selection:Binding(get:{viewport.zoom},set:{zoom in
                    guard let id=s.selected else { return }
                    var value=viewport;value.zoom=zoom;s.setReviewViewport(value,id:id)
                })) {
                    Text("Fit").tag(0.0);Text("50%").tag(0.5);Text("100%").tag(1.0);Text("200%").tag(2.0);Text("400%").tag(4.0)
                }.frame(width:140)
            }.controlSize(.small)
            if viewport.zoom > 0 {
                HStack {
                    Text("Pan").font(.caption)
                    Slider(value:center(horizontal:true),in:0...1,onEditingChanged:{ if !$0 { s.updateReviewRequests() } })
                        .accessibilityLabel("Horizontal viewport position")
                    Slider(value:center(horizontal:false),in:0...1,onEditingChanged:{ if !$0 { s.updateReviewRequests() } })
                        .accessibilityLabel("Vertical viewport position")
                }
            }
        }.padding(.horizontal,12)
    }

    var viewport: ReviewViewport { s.review.viewports[s.selected ?? -1] ?? ReviewViewport() }
    func center(horizontal: Bool) -> Binding<Double> {
        Binding(get:{horizontal ? viewport.cx:viewport.cy},set:{position in
            guard let id=s.selected else { return }
            var value=viewport
            if horizontal { value.cx=position } else { value.cy=position }
            s.setReviewViewport(value,id:id,render:false)
        })
    }
}

struct ReviewPhotoCard: View {
    @EnvironmentObject var s: Store
    let photo: Photo
    let role: String?
    @ObservedObject var renderer: ReviewRenderer
    var compact=false

    var body: some View {
        VStack(spacing:4) {
            if let role { Text(role).font(.caption.weight(.semibold)).padding(.top,5) }
            ReviewImage(photoID:photo.id,renderer:renderer)
            HStack(spacing:4) {
                if photo.colorLabel != "none" { Circle().fill(LibraryLabels.color(photo.colorLabel)).frame(width:7,height:7) }
                Text(photo.displayName).font(.caption).lineLimit(1)
                Spacer(minLength:0)
                if compact { actionsMenu }
                Button { s.deselectReviewPhoto(photo.id) } label: { Image(systemName:"xmark.circle") }
                    .buttonStyle(.plain).help("Remove from review, keep in library")
                    .accessibilityLabel("Deselect \(photo.displayName)")
            }.padding(.horizontal,6)
            if !compact {
                ViewThatFits(in:.horizontal) {
                    HStack(spacing:7) {
                        ForEach(1...5,id:\.self) { rating in
                            Button { rate(photo.rating == rating ? 0:rating) } label: {
                                Image(systemName:photo.rating >= rating ? "star.fill":"star").foregroundStyle(photo.rating >= rating ? Color.yellow:Color.secondary)
                            }.accessibilityLabel("Rate \(photo.displayName) \(rating) stars")
                        }
                        Button { flag(photo.flag == 1 ? 0:1) } label: { Image(systemName:photo.flag == 1 ? "flag.fill":"flag") }
                            .accessibilityLabel("Pick \(photo.displayName)")
                        Button { flag(photo.flag == -1 ? 0:-1) } label: { Image(systemName:photo.flag == -1 ? "xmark.square.fill":"xmark.square") }
                            .accessibilityLabel("Reject \(photo.displayName)")
                        labelMenu
                    }.buttonStyle(.plain).fixedSize()
                    actionsMenu
                }.padding(.bottom,6)
            }
        }
        .frame(maxWidth:.infinity,maxHeight:.infinity)
        .background(Color(nsColor:.controlBackgroundColor))
        .overlay(RoundedRectangle(cornerRadius:5).stroke(s.selected == photo.id ? Color.accentColor:Color.secondary.opacity(0.25),lineWidth:s.selected == photo.id ? 2:1))
        .contentShape(Rectangle())
        .onTapGesture { s.activateReviewPhoto(photo.id) }
        .contextMenu { menuItems }
        .accessibilityElement(children:.contain)
        .accessibilityLabel("\(role ?? "Survey photo"): \(photo.displayName)")
        .accessibilityAddTraits(s.selected == photo.id ? .isSelected:[])
    }

    var actionsMenu: some View { Menu { menuItems } label: { Image(systemName:"ellipsis.circle") }.menuStyle(.borderlessButton).fixedSize() }
    @ViewBuilder var menuItems: some View {
        ForEach(0...5,id:\.self) { value in Button(value == 0 ? "Clear Rating":"\(value) Stars") { rate(value) } }
        Divider()
        Button("Pick") { flag(1) };Button("Reject") { flag(-1) };Button("Clear Flag") { flag(0) }
        labelMenu
        Button("Remove from Review") { s.deselectReviewPhoto(photo.id) }
    }
    var labelMenu: some View {
        Menu("Color Label") {
            ForEach(LibraryLabels.names,id:\.self) { name in
                Button(name.capitalized) {
                    s.activateReviewPhoto(photo.id)
                    Task { _=await s.saveMetadata(targets:[photo],patch:["color_label":name]) }
                }
            }
        }.menuStyle(.borderlessButton).labelsHidden()
    }
    func rate(_ value: Int) { s.activateReviewPhoto(photo.id);Task { await s.ratePhotos([photo.id],patch:["rating":value]) } }
    func flag(_ value: Int) { s.activateReviewPhoto(photo.id);Task { await s.ratePhotos([photo.id],patch:["flag":value]) } }
}

struct ReviewImage: View {
    @EnvironmentObject var s: Store
    let photoID: Int
    @ObservedObject var renderer: ReviewRenderer
    @Environment(\.displayScale) private var displayScale
    @State private var drag: CGSize = .zero

    var viewport: ReviewViewport { s.libraryView == .compare ? s.review.viewports[photoID] ?? ReviewViewport():ReviewViewport() }
    var body: some View {
        GeometryReader { geometry in
            ZStack {
                Color(white:0.07)
                if let frame=renderer.frames[photoID] {
                    if frame.request.viewport.zoom > 0 {
                        Image(nsImage:frame.image).resizable()
                            .frame(width:Double(frame.width)*frame.request.viewport.zoom/displayScale,
                                   height:Double(frame.height)*frame.request.viewport.zoom/displayScale)
                            .offset(drag)
                    } else { Image(nsImage:frame.image).resizable().aspectRatio(contentMode:.fit).padding(4) }
                } else if let error=renderer.errors[photoID] {
                    VStack { Image(systemName:"exclamationmark.triangle");Text(error).font(.caption).lineLimit(3)
                        Button("Retry") { s.updateReviewRequests(force:true) }
                    }.foregroundStyle(.white).padding(8)
                } else { ProgressView().controlSize(.small).tint(.white) }
            }.frame(width:geometry.size.width,height:geometry.size.height).clipped()
                .contentShape(Rectangle())
                .gesture(DragGesture(minimumDistance:3).onChanged { value in
                    if viewport.zoom > 0 { drag=value.translation }
                }.onEnded { value in
                    defer { drag = .zero }
                    guard viewport.zoom > 0,let frame=renderer.frames[photoID] else { return }
                    s.activateReviewPhoto(photoID)
                    var position=viewport
                    position.move(x:position.cx-value.translation.width*displayScale/(position.zoom*Double(frame.fullWidth)),
                                  y:position.cy-value.translation.height*displayScale/(position.zoom*Double(frame.fullHeight)))
                    s.setReviewViewport(position,id:photoID)
                })
                .onAppear { if s.libraryView == .compare { s.setReviewPaneSize(geometry.size,scale:displayScale) } }
                .onChange(of:geometry.size) { _,size in if s.libraryView == .compare { s.setReviewPaneSize(size,scale:displayScale) } }
                .onChange(of:displayScale) { _,scale in if s.libraryView == .compare { s.setReviewPaneSize(geometry.size,scale:scale) } }
        }
        .accessibilityLabel(viewport.zoom > 0 ? "Full-resolution comparison viewport":"Fitted review preview")
    }
}
