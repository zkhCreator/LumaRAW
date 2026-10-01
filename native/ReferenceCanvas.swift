// Purpose: native Reference/Active pairs with separate Fit/1:1 zoom and pan.
// Inputs: revision-bound frames, physical display scale and explicit role actions.
// Outputs: bounded viewport requests, active edits and catalog-photo drops only.
// Reuses engine previews and drawing/target overlays. Fit layout changes reuse
// pixels; this surface never edits the reference, resamples pixels or owns SQL.
import SwiftUI

struct ReferenceCanvas:View {
    @EnvironmentObject var s:Store
    @ObservedObject var renderer:ReferenceRenderer
    @Environment(\.displayScale) private var scale
    @FocusState private var keyboardFocus:Bool
    @State private var referenceDrag:CGSize = .zero
    @State private var activeDrag:CGSize = .zero
    @State private var capturedReference:ReferenceFrame?
    @State private var capturedActive:BeforeAfterFrame?

    var body:some View {
        VStack(spacing:8) {
            controls.padding(.horizontal,12).padding(.top,8)
            GeometryReader {geometry in
                let size=ComparisonLayout.paneSize(geometry.size,mode:s.referenceVertical ? .topBottom:.leftRight)
                Group {
                    if s.referenceVertical {
                        VStack(spacing:ComparisonLayout.gap) {referencePane(size);activePane(size)}
                    } else {
                        HStack(spacing:ComparisonLayout.gap) {referencePane(size);activePane(size)}
                    }
                }.onAppear {s.setReferencePane(canvasSize(size),scale:scale);s.updateReferenceRequest()}
                    .onChange(of:size) {_,value in s.setReferencePane(canvasSize(value),scale:scale);clearDrag()}
                    .onChange(of:scale) {_,value in s.setReferencePane(canvasSize(size),scale:value);clearDrag()}
            }.padding(12)
        }.background(Color(white:0.075))
            .focusable().focused($keyboardFocus).onTapGesture {keyboardFocus=true}
            .modifier(PhotoKeyboardShortcuts())
            .onKeyPress(.leftArrow) {s.navigateLoupe(-1);return .handled}
            .onKeyPress(.rightArrow) {s.navigateLoupe(1);return .handled}
            .onChange(of:s.referenceRequest) {_,_ in clearDrag()}
            .onChange(of:s.currentBeforeContext) {_,_ in clearDrag()}
            .onChange(of:s.referenceVertical) {_,_ in clearDrag()}
            .onDisappear {clearDrag();s.clearColorReadout()}
            .accessibilityElement(children:.contain).accessibilityLabel("Reference and Active photos")
    }

    private var controls:some View {
        HStack(spacing:8) {
            Picker("Reference layout",selection:$s.referenceVertical) {
                Text("Left/Right").tag(false);Text("Top/Bottom").tag(true)
            }.frame(width:160)
            Button {s.referenceLocked.toggle()} label:{Image(systemName:s.referenceLocked ? "lock.fill":"lock.open")}
                .accessibilityLabel(s.referenceLocked ? "Unlock reference photo":"Lock reference photo")
                .help("Keep the reference photo when switching modules")
            Button("Clear Reference") {s.clearReferencePhoto()}.disabled(s.referencePhoto==nil)
            Spacer(minLength:0)
            Button("Done") {Task {await s.startDevelop()}}
        }.controlSize(.small)
    }

    private func referencePane(_ size:CGSize)->some View {
        VStack(spacing:4) {
            HStack {
                Text("Reference").font(.caption.weight(.semibold))
                Text(s.referencePhoto?.displayName ?? "Choose a photo").font(.caption).lineLimit(1)
                Spacer(minLength:0)
                Picker("Reference zoom",selection:Binding(get:{s.referenceDetail},set:{s.setReferenceZoom($0)})) {
                    Text("Fit").tag(false);Text("1:1").tag(true)
                }.labelsHidden().frame(width:80).disabled(s.referencePhoto==nil)
            }.frame(height:24)
            ZStack {
                Color(white:0.06)
                if let error=s.referenceError ?? renderer.error {
                    VStack {Text(error).font(.caption);Button("Refresh Reference") {Task {await s.refreshReferencePhoto(force:true)}}}.padding()
                } else if let frame=renderer.frame,frame.request==s.referenceRequest {
                    image(frame.image,size:canvasSize(size),detail:s.referenceDetail,drag:referenceDrag)
                } else if renderer.loading {ProgressView("Loading reference…")}
                else {Text("Drag a photo here, or choose Set as Reference Photo in the filmstrip.").font(.callout).foregroundStyle(.secondary).multilineTextAlignment(.center).padding()}
            }.frame(width:size.width,height:canvasSize(size).height).clipped().contentShape(Rectangle())
                .onContinuousHover {phase in
                    if case .active(let location)=phase,referenceDrag == .zero,
                       let frame=renderer.frame,frame.request==s.referenceRequest {
                        s.hoverColors(point(location,image:frame.image,size:canvasSize(size),detail:s.referenceDetail),role:.reference)
                    } else {s.clearColorReadout()}
                }
                .gesture(DragGesture(minimumDistance:3).onChanged {value in
                    guard s.referenceDetail,!renderer.loading,let frame=renderer.frame,frame.request==s.referenceRequest else {return}
                    if capturedReference==nil {capturedReference=frame}
                    s.clearColorReadout()
                    referenceDrag=value.translation
                }.onEnded {value in
                    defer {clearDrag()}
                    if let frame=capturedReference {s.panReference(value.translation,scale:scale,frame:frame)}
                })
                .simultaneousGesture(SpatialTapGesture().onEnded {value in
                    guard let frame=renderer.frame,frame.request==s.referenceRequest,
                          let point=point(value.location,image:frame.image,size:canvasSize(size),detail:s.referenceDetail) else {return}
                    s.toggleReferenceZoom(at:point)
                })
                .dropDestination(for:CatalogPhotoDrag.self) {items,_ in s.dropReference(items,active:false)}
        }.frame(width:size.width,height:size.height).accessibilityElement(children:.contain)
            .accessibilityLabel("Reference: \(s.referencePhoto?.displayName ?? "No photo")")
    }

    private func activePane(_ size:CGSize)->some View {
        VStack(spacing:4) {
            HStack {
                Text(s.compare ? "Active (Before)":"Active").font(.caption.weight(.semibold))
                Text(s.photo?.displayName ?? "Choose a photo").font(.caption).lineLimit(1)
                Spacer(minLength:0)
                Button(s.compare ? "Show After":"Show Before") {s.setComparisonMode(s.compare ? .after:.before)}
            }.frame(height:24).controlSize(.small)
            ZStack {
                Color(white:0.06)
                if let photoImage=s.compare ? s.before:s.preview {
                    image(photoImage,size:canvasSize(size),detail:s.detail,drag:activeDrag).overlay {
                        if s.detail,!s.compare {
                            GeometryReader {geometry in
                                if s.curveTargetActive {CurveTargetOverlay(imageSize:photoImage.size,available:geometry.size,fitted:false)}
                                if s.mixerTargetActive {MixerTargetOverlay(imageSize:photoImage.size,available:geometry.size,fitted:false)}
                            }
                        }
                    }
                    if !s.compare,!s.detail {
                        if s.curveTargetActive {CurveTargetOverlay(imageSize:photoImage.size,available:canvasSize(size))}
                        if s.mixerTargetActive {MixerTargetOverlay(imageSize:photoImage.size,available:canvasSize(size))}
                        if !["view","curve","mixer"].contains(s.canvasTool) {
                            DrawingOverlay(image:photoImage,available:canvasSize(size))
                        }
                    }
                } else if s.rendering || s.loading {ProgressView("Loading active photo…")}
                if s.rendering {VStack {HStack {Spacer();ProgressView().controlSize(.small)};Spacer()}.padding(8)}
            }.frame(width:size.width,height:canvasSize(size).height).clipped().contentShape(Rectangle())
                .onContinuousHover {phase in
                    if case .active(let location)=phase,activeDrag == .zero,
                       let image=s.compare ? s.before:s.preview {
                        s.hoverColors(point(location,image:image,size:canvasSize(size),detail:s.detail),role:.active)
                    } else {s.clearColorReadout()}
                }
                .gesture(DragGesture(minimumDistance:3).onChanged {value in
                    guard s.detail,!s.rendering,!s.hasPendingEdits,let frame=s.activeViewportFrame,
                          frame.context==s.currentBeforeContext else {return}
                    if capturedActive==nil {capturedActive=frame}
                    s.clearColorReadout()
                    activeDrag=value.translation
                }.onEnded {value in
                    defer {clearDrag()}
                    if let frame=capturedActive {s.panReferenceActive(value.translation,scale:scale,frame:frame)}
                },including:s.canvasTool=="view" ? .all:.subviews)
                .simultaneousGesture(SpatialTapGesture().onEnded {value in
                    guard let image=s.compare ? s.before:s.preview,
                          let point=point(value.location,image:image,size:canvasSize(size),detail:s.detail) else {return}
                    s.toggleReferenceActiveZoom(at:point)
                })
                .dropDestination(for:CatalogPhotoDrag.self) {items,_ in s.dropReference(items,active:true)}
        }.frame(width:size.width,height:size.height).accessibilityElement(children:.contain)
            .accessibilityLabel("Active: \(s.photo?.displayName ?? "No photo")")
    }

    private func canvasSize(_ pane:CGSize)->CGSize {CGSize(width:pane.width,height:max(1,pane.height-28))}

    private func point(_ location:CGPoint,image:NSImage,size:CGSize,detail:Bool)->CGPoint? {
        let pixels=image.representations.first
        return ReferenceLayout.unitPoint(location,pixels:CGSize(width:pixels?.pixelsWide ?? 1,height:pixels?.pixelsHigh ?? 1),
                                         available:size,detail:detail,scale:scale)
    }

    private func image(_ image:NSImage,size:CGSize,detail:Bool,drag:CGSize)->some View {
        let pixels=image.representations.first
        let dimensions=CGSize(width:pixels?.pixelsWide ?? 1,height:pixels?.pixelsHigh ?? 1)
        // The same 26-point inset used by the shared drawing/target overlays.
        let available=detail ? size:CGSize(width:max(1,size.width-52),height:max(1,size.height-52))
        let rect=ComparisonLayout.imageRect(pixels:dimensions,available:available,detail:detail,scale:scale)
        return Image(nsImage:image).resizable().frame(width:rect.width,height:rect.height)
            .offset(drag).accessibilityHidden(true)
    }

    private func clearDrag() {referenceDrag = .zero;activeDrag = .zero;capturedReference=nil;capturedActive=nil}
}
