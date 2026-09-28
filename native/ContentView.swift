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
                CollectionsSidebar()
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
                ToolbarItem(placement:.primaryAction){Button{ s.importPanel() }label:{Label("Import",systemImage:"plus")}.help("Import photos or folders ⌘I")}
                ToolbarItem(placement:.principal){if s.workspace=="library"{Picker("View",selection:$s.develop){Image(systemName:"square.grid.2x2").tag(false);Image(systemName:"slider.horizontal.3").tag(true)}.pickerStyle(.segmented).frame(width:100)}}
                ToolbarItemGroup(placement:.primaryAction){
                    if s.workspace=="library" {
                        Button{s.compare.toggle()}label:{Label("Before and After",systemImage:"rectangle.lefthalf.inset.filled")}.disabled(s.photo==nil).help("Before / After \\")
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
            Button("OK",role:.cancel){s.error=nil}
        } message:{Text(s.error ?? "")}
        .sheet(isPresented:$s.showExport){ExportSheet()}
        .sheet(isPresented:$s.showVersions){VersionsSheet()}
        .sheet(isPresented:$s.showRecipe){RecipeSheet()}
        .sheet(isPresented:$s.showSync){SyncSheet()}
        .sheet(isPresented:$s.showCalibration){CalibrationSheet()}
        .sheet(isPresented:$s.showCollectionEditor){CollectionEditor(original:s.editingCollection)}
        .sheet(isPresented:$s.showLibraryFilters){LibraryFilterSheet(draft:LibraryFilterDraft(s.libraryFilters))}
        .sheet(isPresented:$s.showMetadataEditor){MetadataEditor(targets:s.metadataTargets)}
        .onDrop(of:[UTType.fileURL],isTargeted:nil){providers in
            for provider in providers {provider.loadItem(forTypeIdentifier:UTType.fileURL.identifier,options:nil){item,_ in
                if let data=item as? Data,let url=URL(dataRepresentation:data,relativeTo:nil){Task{@MainActor in await s.importPaths([url.path])}}
            }};return true
        }
    }
    func side(_ title:String,_ symbol:String,_ mode:String)->some View {
        Button {s.mode=mode;s.collectionID=nil;s.workspace="library";s.offset=0;Task{await s.refresh()}} label:{
            HStack{Label(title,systemImage:symbol);Spacer();if s.mode==mode && s.collectionID==nil && s.workspace=="library"{Image(systemName:"checkmark").font(.caption).foregroundStyle(.tint)}}
        }.accessibilityAddTraits(s.mode==mode && s.collectionID==nil && s.workspace=="library" ? .isSelected:[])
    }
    var workspace:some View {
        VStack(spacing:0){
            HStack {
                VStack(alignment:.leading,spacing:3){Text(s.develop ? (s.photo?.name ?? "Develop") : "Photo Library").font(.headline).lineLimit(1);Text(s.develop ? (s.metadata["camera"] as? String ?? "") : "\(s.total) photos · Selected: \(s.selection.count)").font(.caption).foregroundStyle(.secondary)}
                Spacer()
                if s.develop {
                    Menu {
                        Button("Browse"){s.canvasTool="view"}
                        Button("Split Before and After"){s.splitCompare.toggle();s.compare=false;s.canvasTool="view";s.detail=false}
                        Button("Draw Freeform Crop"){s.canvasTool="crop";s.detail=false;s.compare=false;s.splitCompare=false}
                        Button("Draw Radial Mask"){s.canvasTool="radial";s.detail=false;s.compare=false;s.splitCompare=false}
                        Button("Draw Gradient Mask"){s.canvasTool="linear";s.detail=false;s.compare=false;s.splitCompare=false}
                        Button("Draw Brush Mask"){s.canvasTool="brush";s.detail=false;s.compare=false;s.splitCompare=false}
                    } label:{Label(s.canvasTool=="view" ? "Tools":"Drawing",systemImage:s.canvasTool=="crop" ? "crop":"paintbrush.pointed")}
                    Picker("Zoom",selection:$s.detail){Text("Fit").tag(false);Text("1:1 Detail").tag(true)}.frame(width:155).onChange(of:s.detail){_,_ in s.render()}
                } else {
                    TextField("Search photos and metadata",text:$s.search).textFieldStyle(.roundedBorder).frame(width:220).onSubmit{s.offset=0;Task{await s.refresh()}}
                    Button{Task{await s.refreshCollections();await s.refresh()}}label:{Image(systemName:"arrow.clockwise")}.help("Refresh Library")
                }
            }.padding(.horizontal,20).padding(.vertical,12)
            Divider()
            if !s.develop {
                LibraryToolbar()
                Divider()
            }
            if s.total==0 {empty}
            else if s.develop {PhotoCanvas();filmstrip}
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
        }description:{Text(filtered ? "This view has no photos. Adjust the filters or add photos to this collection." : "Import Nikon NEF or other photos to begin non-destructive editing.\nYou can also drag a photo folder into this window.")}
        actions:{
            if filtered { Button("Show All Photos"){s.mode="all";s.collectionID=nil;s.libraryFilters=[:];s.search="";s.offset=0;Task{await s.refresh()}} }
            else { Button("Import Photos…"){s.importPanel()}.buttonStyle(.borderedProminent).controlSize(.large) }
        }
    }
    var filtered: Bool { s.mode != "all" || s.collectionID != nil || !s.libraryFilters.isEmpty || !s.search.isEmpty }
    var gallery:some View {
        ScrollView {
            LazyVGrid(columns:[GridItem(.adaptive(minimum:175,maximum:245),spacing:18)],spacing:20) {
                ForEach(s.photos){p in
                    VStack(alignment:.leading,spacing:8){
                        ZStack(alignment:.bottomTrailing){
                            Rectangle().fill(.black.opacity(0.9))
                            if let im=s.thumbnails[p.id]{Image(nsImage:im).resizable().aspectRatio(contentMode:.fit).padding(5)}
                            else{Image(systemName:"photo").font(.largeTitle).foregroundStyle(.secondary).frame(maxWidth:.infinity,maxHeight:.infinity)}
                            if p.flag != 0 {Image(systemName:p.flag==1 ? "flag.fill":"xmark.circle.fill").padding(7).foregroundStyle(p.flag==1 ? .yellow:.gray)}
                        }.frame(height:145).clipShape(RoundedRectangle(cornerRadius:7)).overlay(RoundedRectangle(cornerRadius:7).stroke(s.selection.contains(p.id) ? Color.accentColor:.clear,lineWidth:3))
                        HStack(spacing:6){
                            if p.colorLabel != "none" {Circle().fill(LibraryLabels.color(p.colorLabel)).frame(width:8,height:8).accessibilityLabel("\(p.colorLabel) label")}
                            Text(p.name).font(.callout).lineLimit(1)
                        }
                        HStack(spacing:2){ForEach(0..<5){i in Image(systemName:i<p.rating ? "star.fill":"star").font(.system(size:9)).foregroundStyle(i<p.rating ? Color.yellow:Color.secondary.opacity(0.4))};Spacer();Text(URL(fileURLWithPath:p.path).pathExtension.uppercased()).font(.caption2).foregroundStyle(.secondary)}
                    }.contentShape(Rectangle())
                    .onTapGesture(count:2){s.choose(p.id);s.develop=true}
                    .onTapGesture {s.choose(p.id,extend:NSEvent.modifierFlags.contains(.command) || NSEvent.modifierFlags.contains(.shift))}
                    .accessibilityElement(children:.combine).accessibilityLabel("\(p.name), \(p.rating) \(p.rating == 1 ? "star" : "stars")")
                    .accessibilityAddTraits(.isButton).accessibilityAction{s.choose(p.id);s.develop=true}
                    .contextMenu {Button("Develop"){s.choose(p.id);s.develop=true};Button("Show in Finder"){NSWorkspace.shared.activateFileViewerSelecting([URL(fileURLWithPath:p.path)])}}
                }
            }.padding(24)
        }.background(Color(nsColor:.underPageBackgroundColor))
        .focusable()
        .onKeyPress(.rightArrow){moveSelection(1);return .handled}
        .onKeyPress(.leftArrow){moveSelection(-1);return .handled}
        .onKeyPress(.return){s.develop=true;return .handled}
    }
    func moveSelection(_ delta:Int){
        guard !s.photos.isEmpty else{return}
        let index=s.photos.firstIndex(where:{$0.id==s.selected}) ?? 0
        s.choose(s.photos[min(s.photos.count-1,max(0,index+delta))].id)
    }
    var filmstrip:some View {
        ScrollView(.horizontal){HStack(spacing:10){ForEach(s.photos){p in Button{s.choose(p.id,extend:NSEvent.modifierFlags.contains(.command))}label:{
            VStack(spacing:4){Group{if let im=s.thumbnails[p.id]{Image(nsImage:im).resizable().aspectRatio(contentMode:.fit)}else{Image(systemName:"photo")}}.frame(width:88,height:62).background(.black.opacity(0.8)).clipShape(RoundedRectangle(cornerRadius:4)).overlay(RoundedRectangle(cornerRadius:4).stroke(s.selection.contains(p.id) ? Color.accentColor:.clear,lineWidth:2));Text(p.name).font(.system(size:9)).lineLimit(1).frame(width:88)}
        }.buttonStyle(.plain).accessibilityLabel(p.name)}}.padding(12)}.frame(height:109).background(.bar)
    }
}

struct PhotoCanvas:View {
    @EnvironmentObject var s:Store
    var body:some View {
        GeometryReader {geo in
            ZStack {
                Color(white:0.075)
                if let image=s.compare ? s.before:s.preview {
                    if s.detail {
                        ScrollView([.horizontal,.vertical]) {
                            let scale=NSScreen.main?.backingScaleFactor ?? 2
                            let pixels=image.representations.first
                            Image(nsImage:image).resizable().frame(width:CGFloat(pixels?.pixelsWide ?? 1600)/scale,height:CGFloat(pixels?.pixelsHigh ?? 1100)/scale)
                                .frame(minWidth:geo.size.width,minHeight:geo.size.height)
                        }
                    } else {
                        Image(nsImage:image).resizable().aspectRatio(contentMode:.fit).padding(26)
                        if s.splitCompare,!s.compare,let baseline=s.before {
                            Image(nsImage:baseline).resizable().aspectRatio(contentMode:.fit).padding(26)
                                .mask(alignment:.leading){Rectangle().frame(width:geo.size.width*s.splitPosition)}
                            Rectangle().fill(.white.opacity(0.85)).frame(width:2).position(x:geo.size.width*s.splitPosition,y:geo.size.height/2)
                            VStack{Spacer();HStack{Text("Before");Slider(value:$s.splitPosition,in:0...1).accessibilityLabel("Before and after divider");Text("After")}.font(.caption).padding(9).background(.ultraThinMaterial,in:Capsule()).frame(width:280).padding(.bottom,14)}
                        }
                        if s.canvasTool != "view",!s.compare {DrawingOverlay(image:image,available:geo.size)}
                    }
                } else if s.rendering {ProgressView("Developing…").tint(.white).foregroundStyle(.white)}
                else {Text("Select a photo to start editing").foregroundStyle(.gray)}
                VStack {HStack{if s.compare{Text("Before").font(.caption.weight(.medium)).padding(8).background(.ultraThinMaterial,in:Capsule())};Spacer();if s.rendering && s.preview != nil{ProgressView().controlSize(.small).padding(8).background(.ultraThinMaterial,in:Circle())}};Spacer()}.padding(16)
            }
            .accessibilityLabel(s.compare ? "Photo before editing":"Photo after editing")
            .accessibilityValue(s.photo?.name ?? "No photo selected")
        }
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
