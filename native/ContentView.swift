// Purpose: native three-column photo workspace using system navigation and controls.
// Inputs: bounded Store presentation data. Outputs: explicit user actions.
// Canvas displays ICC-tagged previews; it never claims monitor calibration.
import SwiftUI
import AppKit
import UniformTypeIdentifiers

struct ContentView: View {
    @EnvironmentObject var s:Store
    var body: some View {
        NavigationSplitView {
            List {
                Section("Library") {
                    side("All Photos","photo.on.rectangle","all")
                    side("Previous Import","square.and.arrow.down","previous_import")
                    side("Picks","flag","keepers")
                    side("3 Stars and Up","star","stars")
                    side("Rejected","xmark.circle","rejects")
                }
                Section("Organize") {
                    side("Duplicates","square.on.square","duplicates")
                    side("Missing Originals","externaldrive.badge.exclamationmark","missing")
                    Button {s.workspace="exports"} label:{Label("Export Queue",systemImage:"square.and.arrow.up")}
                    Button {s.workspace="agent"} label:{Label("Agent Connection",systemImage:"terminal")}
                }
                FoldersSidebar()
                CollectionsSidebar()
                KeywordsSidebar()
                KeywordSetsSidebar()
                Section {
                    Button {s.libraryAction("index_library")} label:{Label("Update Library Index",systemImage:"arrow.triangle.2.circlepath")}.disabled(s.busy)
                    Button {s.backup()} label:{Label("Back Up Library…",systemImage:"externaldrive")}
                }
            }.listStyle(.sidebar)
                .navigationTitle("LumaRAW")
                .navigationSplitViewColumnWidth(min:215,ideal:240,max:300)
                .safeAreaInset(edge:.bottom){VStack(alignment:.leading,spacing:6){Label("Local Darkroom",systemImage:"internaldrive").font(.callout);Text("\(s.total) photos · Originals are read-only").font(.caption).foregroundStyle(.secondary)}.frame(maxWidth:.infinity,alignment:.leading).padding()}
        } detail: {
            Group {
                if s.workspace=="exports" {QueueView()}
                else if s.workspace=="agent" {AgentView()}
                else {workspace}
            }
            .toolbar {
                if let recovery=s.whiteBalanceEditRecovery {
                    ToolbarItem(placement:.primaryAction) {
                        Button("Resolve Unsaved Adjustments") {s.error=recovery.message}
                    }
                }
                ToolbarItem(placement:.primaryAction){Button{ s.importPanel() }label:{Label("Import",systemImage:"plus")}.help("Import photos or folders ⌘I")}
                ToolbarItem(placement:.principal){if s.workspace=="library"{Picker("Module",selection:Binding(get:{s.develop},set:{value in Task {if value {await s.startDevelop()} else {await s.switchLibraryView(s.libraryView)}}})){Image(systemName:"square.grid.2x2").tag(false);Image(systemName:"slider.horizontal.3").tag(true)}.pickerStyle(.segmented).frame(width:100)}}
                ToolbarItemGroup(placement:.primaryAction){
                    if s.workspace=="library" {
                        if s.develop {
                            Button("Reference View") {Task {await s.startReferenceView()}}.help("Reference View · Shift-R")
                            BeforeAfterMenu()
                        }
                        Button{s.showInspector.toggle()}label:{Label("Inspector",systemImage:"sidebar.right")}
                        Button{s.showExport=true}label:{Label("Export",systemImage:"square.and.arrow.up")}.disabled(s.selected==nil)
                    }
                }
            }
        }
        .inspector(isPresented:Binding(get:{s.showInspector && s.workspace=="library"},set:{s.showInspector=$0})) {
            InspectorView().inspectorColumnWidth(min:310,ideal:340,max:420)
        }
        .alert("Unable to Complete Action",isPresented:Binding(get:{s.error != nil},set:{if !$0{s.error=nil}})) {
            if s.serviceUpgradeNeeded {
                Button("Connect with This Version") { Task { await s.activateCurrentService() } }
                    .disabled(s.connectingService)
            }
            if let recovery=s.whiteBalanceEditRecovery {
                Button("Discard Unsaved Adjustments and Reload",role:.destructive) {
                    Task {await s.discardWhiteBalancePendingEdits(recovery)}
                }
                Button("Keep Draft",role:.cancel) {s.error=nil}
            } else {
                Button("OK",role:.cancel){s.error=nil}
            }
        } message:{Text(s.error ?? "")}
        .alert("Exit Reference View to Crop?",isPresented:Binding(get:{s.referenceCropPhotoID != nil},set:{if !$0 {s.referenceCropPhotoID=nil}})) {
            Button("Continue") {s.confirmReferenceCrop()}
            Button("Cancel",role:.cancel) {s.referenceCropPhotoID=nil}
        } message:{Text("The Crop tool uses the full Develop view. Your reference photo remains available when you return.")}
        .sheet(isPresented:$s.showExport){ExportSheet()}
        .sheet(item:$s.importReview){ImportReviewSheet(model:$0)}
        .sheet(isPresented:$s.showVersions){VersionsSheet()}
        .modifier(SnapshotNamePresentation())
        .sheet(isPresented:$s.showRecipe){RecipeSheet()}
        .sheet(isPresented:$s.showSync){SyncSheet()}
        .sheet(isPresented:$s.showCalibration){CalibrationSheet()}
        .sheet(isPresented:$s.showDevelopPresets){DevelopPresetBrowser()}
        .sheet(isPresented:$s.showMetadataPresets){MetadataPresetBrowser()}
        .sheet(isPresented:$s.showCollectionEditor){CollectionEditor(original:s.editingCollection,kind:s.newCollectionKind,parentID:s.newCollectionParent)}
        .sheet(isPresented:$s.showQuickSave){if let source=s.quickSaveSource {QuickCollectionSheet(source:source)}}
        .sheet(isPresented:$s.showLibraryFilters){LibraryFilterSheet(draft:LibraryFilterDraft(s.libraryFilters))}
        .sheet(isPresented:$s.showCopyRemoval){VirtualCopyRemovalSheet(targets:s.copyRemovalTargets)}
        .sheet(isPresented:$s.showMetadataEditor){MetadataEditor(targets:s.metadataTargets)}
        .sheet(isPresented:$s.showKeywordEditor){KeywordEditor(original:s.editingKeyword,parent:s.newKeywordParent,revision:s.keywordEditorRevision,targets:s.keywordEditorTargets)}
        .sheet(isPresented:$s.showAutoStack){if let source=s.autoStackSource {AutoStackSheet(source:source)}}
        .sheet(isPresented:$s.showFolderRelocation){FolderRelocationSheet(folder:s.relocationFolder)}
        .sheet(isPresented:$s.showFolderSync){FolderSyncSheet(folder:s.syncFolder)}
        .sheet(item:$s.shortcutEditor){KeywordShortcutEditor(source:$0)}
        .sheet(item:$s.painterKeywordPicker){PainterKeywordPicker(model:$0)}
        .onChange(of:s.workspace) { _,_ in if !s.isMultiReview {s.reviewRenderer.stop()} else {s.updateReviewRequests()} }
        .onChange(of:s.develop) { _,value in if value {s.reviewRenderer.stop()} }
        .onChange(of:s.curveTargetActive) {_,active in
            if !active {s.cancelCurveTarget();s.curveTargetFrame=nil}
            else if s.curveTargetFrame == nil {s.render()}
        }
        .onChange(of:s.curveTargetContext) {_,_ in if s.curveTargetGesture != nil {s.cancelCurveTarget()}}
        .onChange(of:s.mixerTargetActive) {_,active in
            if !active {s.cancelMixerTarget();s.mixerTargetFrame=nil}
            else if s.mixerTargetFrame == nil {s.render()}
        }
        .onChange(of:s.curveTargetContext) {_,_ in if s.mixerTargetGesture != nil {s.cancelMixerTarget()}}
        .onChange(of:s.activeMixerComponent) {_,_ in if s.mixerTargetGesture != nil {s.cancelMixerTarget()}}
        .onChange(of:s.painterSource) { _,_ in s.cancelPainterStroke();if !s.painterInGrid { s.setPainting(false) } }
        .onDrop(of:[UTType.fileURL],isTargeted:nil){providers in
            Task { await s.reviewImportProviders(providers) };return true
        }
    }
    func side(_ title:String,_ symbol:String,_ mode:String)->some View {
        Button {Task{await s.openLibraryMode(mode)}} label:{
            HStack{Label(title,systemImage:symbol);Spacer();if s.mode==mode && s.collectionID==nil && s.folderID==nil && s.workspace=="library"{Image(systemName:"checkmark").font(.caption).foregroundStyle(.tint)}}
        }.accessibilityAddTraits(s.mode==mode && s.collectionID==nil && s.folderID==nil && s.workspace=="library" ? .isSelected:[])
    }
    var workspace:some View {
        VStack(spacing:0){
            HStack {
                VStack(alignment:.leading,spacing:3){Text(s.develop ? (s.photo?.displayName ?? "Develop") : "Photo Library").font(.headline).lineLimit(1);Text(s.develop ? (s.metadata["camera"] as? String ?? "") : "\(s.total) photos · Selected: \(s.selection.count)").font(.caption).foregroundStyle(.secondary)}
                Spacer()
                if s.develop {
                    Menu {
                        Button("Browse"){s.canvasTool="view"}
                        Button("Targeted Tone Curve"){s.setCurveTargeting(true)}.disabled(!s.canEditPointCurves || s.hasPendingEdits)
                        Menu("Targeted Color Mixer") {
                            if s.recipe["monochrome"] as? Bool ?? false {
                                Button("Black & White Mix") {s.setMixerTargeting("bw")}
                            } else {
                                Button("Hue") {s.setMixerTargeting("hue")}
                                Button("Saturation") {s.setMixerTargeting("sat")}
                                Button("Luminance") {s.setMixerTargeting("lum")}
                            }
                        }.disabled(!s.canEditPointCurves || s.hasPendingEdits)
                        Button("Split Before and After"){s.setComparisonMode(s.comparisonMode == .leftRightSplit ? .after:.leftRightSplit)}
                        Button("Draw Freeform Crop"){s.requestCropTool()}
                        Button("Draw Radial Mask"){s.canvasTool="radial";s.detail=false;s.compare=false;s.splitCompare=false}
                        Button("Draw Gradient Mask"){s.canvasTool="linear";s.detail=false;s.compare=false;s.splitCompare=false}
                        Button("Draw Brush Mask"){s.canvasTool="brush";s.detail=false;s.compare=false;s.splitCompare=false}
                    } label:{Label(s.canvasTool=="view" ? "Tools":(s.canvasTool=="curve" ? "Tone Curve":(s.canvasTool=="mixer" ? "Color Mixer":"Drawing")),systemImage:["curve","mixer"].contains(s.canvasTool) ? "scope":(s.canvasTool=="crop" ? "crop":"paintbrush.pointed"))}
                    Picker(s.isReferenceView ? "Active zoom":"Zoom",selection:$s.detail){Text("Fit").tag(false);Text("1:1 Detail").tag(true)}.frame(width:155).onChange(of:s.detail){_,_ in s.render()}
                } else {
                    if s.libraryView == .loupe {
                        Picker("Zoom",selection:$s.detail){Text("Fit").tag(false);Text("1:1 Detail").tag(true)}.frame(width:155).onChange(of:s.detail){_,_ in s.render()}
                    }
                    TextField("Search photos and metadata",text:$s.search).textFieldStyle(.roundedBorder).frame(width:220).onSubmit{s.offset=0;Task{await s.refresh()}}
                    Button{Task{await s.refreshCollections();await s.refresh();s.updateReviewRequests(force:true)}}label:{Image(systemName:"arrow.clockwise")}.help("Refresh Library")
                }
            }.padding(.horizontal,20).padding(.vertical,12)
            Divider()
            if !s.develop {
                LibraryToolbar()
                PainterToolbar()
                Picker("Library View",selection:Binding(get:{s.libraryView},set:{view in Task {await s.switchLibraryView(view)}})) {
                    ForEach(LibraryViewMode.allCases,id:\.self) { view in Label(view.title,systemImage:view.symbol).tag(view) }
                }.pickerStyle(.segmented).padding(.horizontal,20).padding(.bottom,8)
                Divider()
            }
            if s.total==0 {empty}
            else if s.develop {
                if s.isReferenceView {ReferenceCanvas(renderer:s.referenceRenderer)} else {PhotoCanvas()}
                filmstrip
            }
            else if s.isMultiReview {ReviewWorkspace(renderer:s.reviewRenderer);filmstrip}
            else if s.libraryView == .loupe {PhotoCanvas();filmstrip}
            else {gallery}
            Divider()
            HStack {
                if s.busy || s.rendering || s.editing {ProgressView().controlSize(.small)}
                Text(s.editing ? "Saving adjustments…":s.message).lineLimit(1)
                Spacer()
                Button{ s.offset=max(0,s.offset-60);Task{await s.refresh()} }label:{Image(systemName:"chevron.left")}.disabled(s.offset==0)
                Text("\(s.offset+min(1,s.total))–\(min(s.offset+60,s.total)) / \(s.total)").monospacedDigit()
                Button{ s.offset+=60;Task{await s.refresh()} }label:{Image(systemName:"chevron.right")}.disabled(s.offset+60>=s.total)
            }.font(.caption).foregroundStyle(.secondary).padding(.horizontal,16).padding(.vertical,9)
        }
    }
    var empty:some View {
        ContentUnavailableView {
            Label(filtered ? "No Matching Photos":"Your Next Great Photo",systemImage:filtered ? "line.3.horizontal.decrease.circle":"camera.aperture")
        }description:{Text(filtered ? "This view has no photos. Choose another source or adjust the filters." : "Import Nikon NEF or other photos to begin non-destructive editing.\nYou can also drag a photo folder into this window.")}
        actions:{
            if filtered { Button("Show All Photos"){Task{await s.openLibraryMode("all",clearFilters:true)}} }
            else { Button("Import Photos…"){s.importPanel()}.buttonStyle(.borderedProminent).controlSize(.large) }
        }
    }
    var filtered: Bool { s.mode != "all" || s.collectionID != nil || s.folderID != nil || !s.libraryFilters.isEmpty || !s.search.isEmpty }
    var gallery:some View {
        ScrollView {
            LazyVGrid(columns:[GridItem(.adaptive(minimum:175,maximum:245),spacing:18)],spacing:20) {
                ForEach(s.photos){p in
                    VStack(alignment:.leading,spacing:8){
                        ZStack(alignment:.bottomTrailing){
                            Rectangle().fill(.black.opacity(0.9))
                            if let im=s.thumbnails[p.id]{Image(nsImage:im).resizable().aspectRatio(contentMode:.fit).padding(5)}
                            else{Image(systemName:s.thumbnailErrors[p.id] == nil ? "photo":"exclamationmark.triangle").font(.largeTitle).foregroundStyle(.secondary).frame(maxWidth:.infinity,maxHeight:.infinity)}
                            if p.flag != 0 {Image(systemName:p.flag==1 ? "flag.fill":"xmark.circle.fill").padding(7).foregroundStyle(p.flag==1 ? .yellow:.gray)}
                        }.overlay(alignment:.topLeading){StackBadge(photoID:p.id).padding(4)}.overlay(alignment:.bottomLeading){VirtualCopyBadge(photo:p).padding(6)}.overlay(alignment:.topTrailing){TargetCollectionBadge(photoID:p.id).padding(6)}.frame(height:145).clipShape(RoundedRectangle(cornerRadius:7)).overlay(RoundedRectangle(cornerRadius:7).stroke(s.painterTouched.contains(p.id) ? Color.orange:s.selection.contains(p.id) ? Color.accentColor:.clear,lineWidth:3))
                            .anchorPreference(key:PainterThumbnailAnchors.self,value:.bounds) { [p.id:$0] }
                        HStack(spacing:6){
                            if p.colorLabel != "none" {Circle().fill(LibraryLabels.color(p.colorLabel)).frame(width:8,height:8).accessibilityLabel("\(p.colorLabel) label")}
                            Text(p.displayName).font(.callout).lineLimit(1)
                        }
                        HStack(spacing:2){ForEach(0..<5){i in Image(systemName:i<p.rating ? "star.fill":"star").font(.system(size:9)).foregroundStyle(i<p.rating ? Color.yellow:Color.secondary.opacity(0.4))};Spacer();Text(URL(fileURLWithPath:p.path).pathExtension.uppercased()).font(.caption2).foregroundStyle(.secondary)}
                    }.contentShape(Rectangle())
                    .onTapGesture(count:2){s.choose(p.id);Task {await s.switchLibraryView(.loupe)}}
                    .onTapGesture {s.choose(p.id,extend:NSEvent.modifierFlags.contains(.command),range:NSEvent.modifierFlags.contains(.shift))}
                    .help(s.thumbnailErrors[p.id] ?? p.displayName)
                    .accessibilityElement(children:.combine).accessibilityLabel("\(p.displayName), \(p.rating) \(p.rating == 1 ? "star" : "stars")")
                    .accessibilityAddTraits(.isButton).accessibilityAction{s.choose(p.id);Task {await s.switchLibraryView(.loupe)}}
                    .draggable(s.libraryPhotoDrag(p.id))
                    .contextMenu {ReferencePhotoAction(photoID:p.id);StackActions(photoID:p.id);VirtualCopyActions(photo:p);PhotoFolderAction(photo:p);PhotoKeywordShortcutActions(photoID:p.id);Divider();Button("Develop"){s.choose(p.id);Task {await s.startDevelop()}};Button("Show in Finder"){NSWorkspace.shared.activateFileViewerSelecting([URL(fileURLWithPath:p.path)])}}
                }
            }.padding(24).overlayPreferenceValue(PainterThumbnailAnchors.self) { anchors in
                GeometryReader { geometry in
                    PainterPointerLayer(rectangles:anchors.mapValues { geometry[$0] })
                        .frame(width:geometry.size.width,height:geometry.size.height)
                }
            }
        }.background(Color(nsColor:.underPageBackgroundColor))
        .focusable()
        .modifier(PhotoKeyboardShortcuts())
        .onKeyPress(.rightArrow){moveSelection(1);return .handled}
        .onKeyPress(.leftArrow){moveSelection(-1);return .handled}
        .onKeyPress(.return){Task {await s.switchLibraryView(.loupe)};return .handled}
        .onKeyPress(characters:CharacterSet(charactersIn:"a")){press in
            if press.modifiers.contains(.command) {s.selectAllVisible();return .handled}
            return .ignored
        }
    }
    func moveSelection(_ delta:Int){
        guard !s.photos.isEmpty else{return}
        let index=s.photos.firstIndex(where:{$0.id==s.selected}) ?? 0
        s.choose(s.photos[min(s.photos.count-1,max(0,index+delta))].id,range:NSEvent.modifierFlags.contains(.shift))
    }
    var filmstrip:some View {
        ScrollView(.horizontal){HStack(spacing:10){ForEach(s.photos){p in Button{s.choose(p.id,extend:NSEvent.modifierFlags.contains(.command),range:NSEvent.modifierFlags.contains(.shift))}label:{
            VStack(spacing:4){Group{if let im=s.thumbnails[p.id]{Image(nsImage:im).resizable().aspectRatio(contentMode:.fit)}else{Image(systemName:s.thumbnailErrors[p.id] == nil ? "photo":"exclamationmark.triangle")}}.frame(width:88,height:62).overlay(alignment:.topLeading){StackBadge(photoID:p.id).padding(4)}.overlay(alignment:.bottomLeading){VirtualCopyBadge(photo:p)}.overlay(alignment:.topTrailing){TargetCollectionBadge(photoID:p.id).font(.caption2)}.background(.black.opacity(0.8)).clipShape(RoundedRectangle(cornerRadius:4)).overlay(RoundedRectangle(cornerRadius:4).stroke(s.selection.contains(p.id) ? Color.accentColor:.clear,lineWidth:2));Text(p.displayName).font(.system(size:9)).lineLimit(1).frame(width:88)}
        }.buttonStyle(.plain).help(s.thumbnailErrors[p.id] ?? p.displayName).accessibilityLabel(p.displayName).draggable(s.referenceDrag(p.id)).contextMenu{ReferencePhotoAction(photoID:p.id);StackActions(photoID:p.id);VirtualCopyActions(photo:p);PhotoFolderAction(photo:p);PhotoKeywordShortcutActions(photoID:p.id)}}}.padding(12)}.frame(height:109).background(.bar).modifier(PhotoKeyboardShortcuts())
    }
}

struct PhotoCanvas:View {
    @EnvironmentObject var s:Store
    @Environment(\.displayScale) private var displayScale
    @FocusState private var keyboardFocus: Bool
    var body:some View {
        GeometryReader {geo in
            ZStack {
                Color(white:0.075)
                if s.develop,s.comparisonMode.isPaired {
                    BeforeAfterCanvas()
                } else if let image=s.develop && s.compare ? s.before:s.preview {
                    if s.detail {
                        ScrollView([.horizontal,.vertical]) {
                            let scale=displayScale
                            let pixels=image.representations.first
                            Image(nsImage:image).resizable().frame(width:CGFloat(pixels?.pixelsWide ?? 1600)/scale,height:CGFloat(pixels?.pixelsHigh ?? 1100)/scale)
                                .overlay {
                                    GeometryReader {frame in
                                        Color.clear.contentShape(Rectangle())
                                            .modifier(ColorReadoutHover(imageSize:image.size,available:frame.size,fitted:false))
                                    }
                                    if s.curveTargetActive {
                                        GeometryReader {frame in CurveTargetOverlay(imageSize:image.size,available:frame.size,fitted:false)}
                                    }
                                    if s.mixerTargetActive {
                                        GeometryReader {frame in MixerTargetOverlay(imageSize:image.size,available:frame.size,fitted:false)}
                                    }
                                    if s.whiteBalanceTargetActive && !s.compare {
                                        GeometryReader {frame in WhiteBalanceTargetOverlay(imageSize:image.size,available:frame.size,
                                            fitted:false,role:"active",after:true)}
                                    }
                                }
                                .frame(minWidth:geo.size.width,minHeight:geo.size.height)
                        }
                    } else {
                        Image(nsImage:image).resizable().aspectRatio(contentMode:.fit).padding(26)
                        if s.develop,s.canvasTool=="view" {
                            Color.clear.contentShape(Rectangle())
                                .modifier(ColorReadoutHover(imageSize:image.size,available:geo.size))
                        }
                        if s.curveTargetActive {CurveTargetOverlay(imageSize:image.size,available:geo.size)}
                        if s.mixerTargetActive {MixerTargetOverlay(imageSize:image.size,available:geo.size)}
                        if s.whiteBalanceTargetActive && !s.compare {
                            WhiteBalanceTargetOverlay(imageSize:image.size,available:geo.size,fitted:true,role:"active",after:true)
                        }
                        if s.develop,!["view","curve","mixer","white-balance"].contains(s.canvasTool),!s.compare {DrawingOverlay(image:image,available:geo.size)}
                    }
                } else if s.rendering {ProgressView("Developing…").tint(.white).foregroundStyle(.white)}
                else {Text("Select a photo to start editing").foregroundStyle(.gray)}
                VStack {HStack{if s.compare{Text("Before · \(s.beforeLabel)").font(.caption.weight(.medium)).padding(8).background(.ultraThinMaterial,in:Capsule())};Spacer();if s.rendering && s.preview != nil{ProgressView().controlSize(.small).padding(8).background(.ultraThinMaterial,in:Circle())}};Spacer()}.padding(16)
            }
            .accessibilityLabel(s.develop && s.comparisonMode.isPaired ? "Before and After comparison":(s.compare ? "Photo before editing":"Photo after editing"))
            .accessibilityValue(s.photo?.displayName ?? "No photo selected")
        }
        .focusable().focused($keyboardFocus)
        .onTapGesture { keyboardFocus=true }
        .modifier(PhotoKeyboardShortcuts())
        .onChange(of:s.canvasTool) {_,tool in s.whiteBalanceCanvasToolDidChange(tool)}
        .onChange(of:s.comparisonMode) {_,mode in s.whiteBalanceComparisonDidChange(mode)}
        .onDisappear {s.cancelWhiteBalanceSelector()}
        .onKeyPress(.escape) {
            if s.whiteBalanceTargetActive || s.whiteBalanceSampling || s.whiteBalanceArming {s.cancelWhiteBalanceSelector();return .handled}
            if s.mixerTargetActive {
                if s.mixerTargetGesture != nil {s.cancelMixerTarget()} else {s.setMixerTargeting(nil)}
                return .handled
            }
            guard s.curveTargetActive else {return .ignored}
            if s.curveTargetGesture != nil {s.cancelCurveTarget()} else {s.setCurveTargeting(false)}
            return .handled
        }
        .onKeyPress(.upArrow) {
            if s.mixerTargetActive {s.nudgeMixerTarget(1);return .handled}
            guard s.curveTargetActive else {return .ignored};s.nudgeCurveTarget(1);return .handled
        }
        .onKeyPress(.downArrow) {
            if s.mixerTargetActive {s.nudgeMixerTarget(-1);return .handled}
            guard s.curveTargetActive else {return .ignored};s.nudgeCurveTarget(-1);return .handled
        }
        .onKeyPress(.leftArrow) { s.navigateLoupe(-1);return .handled }
        .onKeyPress(.rightArrow) { s.navigateLoupe(1);return .handled }
    }
}

struct HistogramView:View {
    let data:[[Double]]
    var body:some View {
        Canvas {context,size in
            let colors:[Color]=[.red,.green,.blue]
            for (channel,values) in data.enumerated() where channel<3 && !values.isEmpty {
                let top=max(values.max() ?? 1,1);var path=Path();path.move(to:CGPoint(x:0,y:size.height))
                for (i,v) in values.enumerated(){path.addLine(to:CGPoint(x:Double(i)/Double(max(1,values.count-1))*size.width,y:size.height-pow(v/top,0.5)*size.height))}
                path.addLine(to:CGPoint(x:size.width,y:size.height));path.closeSubpath();context.fill(path,with:.color(colors[channel].opacity(0.32)))
            }
        }.frame(height:72).background(Color.black.opacity(0.1),in:RoundedRectangle(cornerRadius:5)).accessibilityLabel("RGB Histogram")
    }
}
