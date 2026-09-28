// Purpose: export, history, batch, calibration and agent connection workflows.
// Inputs: explicit native panels and user-entered settings. Outputs: domain calls.
// Exports retain snapshots; app never overwrites an original or existing output.
// Calibration rectangles address full decoded sources before catalog/Develop edits.
import SwiftUI
import AppKit

struct ExportSheet:View {
    @EnvironmentObject var s:Store
    @Environment(\.dismiss) var dismiss
    @State private var format="tiff16"
    @State private var space="srgb"
    @State private var name="{stem}-Luma-{seq}"
    @State private var destination=""
    @State private var edge=0
    @State private var quality=96
    @State private var metadata="catalog"
    @State private var keywordHierarchy=false
    @State private var metadataPhoto: Int?
    @State private var submitting=false
    var body:some View {
        VStack(alignment:.leading,spacing:20){
            Text("Export Photos").font(.title2.weight(.semibold))
            Text("Save current adjustments to new files. Originals remain unchanged.").foregroundStyle(.secondary)
            Form {
                LabeledContent("Photo Count",value:"\(max(s.selection.count,1))")
                Picker("File Format",selection:$format){Text("16-bit TIFF").tag("tiff16");Text("JPEG").tag("jpeg")}
                Picker("Color Space",selection:$space){Text("sRGB").tag("srgb");Text("Display P3").tag("p3");Text("Adobe RGB").tag("adobe");Text("ProPhoto RGB").tag("prophoto")}
                Picker("Size",selection:$edge){Text("Full Size").tag(0);Text("Long Edge: 4096 px").tag(4096);Text("Long Edge: 2048 px").tag(2048);Text("Long Edge: 1280 px").tag(1280)}
                if format=="jpeg"{Stepper("JPEG Quality: \(quality)",value:$quality,in:1...100)}
                TextField("Filename Template",text:$name)
                Picker("Metadata",selection:$metadata) {
                    Text("None").tag("none");Text("Copyright Only").tag("copyright");Text("Catalog Descriptions and Keywords").tag("catalog")
                }
                Toggle("Write Keywords as Lightroom Hierarchy",isOn:$keywordHierarchy).disabled(metadata != "catalog")
                Text("Includes supported catalog fields and keyword export rules. Camera EXIF, GPS and Develop settings are not copied.").font(.caption).foregroundStyle(.secondary)
                Button("Preview Metadata for Active Photo…") { metadataPhoto=s.selected ?? s.selection.sorted().first }.disabled(s.selected == nil && s.selection.isEmpty)
                Text("Available: {stem} {seq} {width} {height} {space}").font(.caption).foregroundStyle(.secondary)
                HStack{Text(destination.isEmpty ? "Choose an export folder":destination).lineLimit(2).font(.callout).textSelection(.enabled);Spacer();Button("Choose…"){let panel=NSOpenPanel();panel.canChooseDirectories=true;panel.canChooseFiles=false;panel.canCreateDirectories=true;if panel.runModal() == .OK{destination=panel.url?.path ?? ""}}}
            }.formStyle(.grouped)
            HStack{Text("Existing files are preserved · ICC embedded").font(.caption).foregroundStyle(.secondary);Spacer();Button("Cancel"){dismiss()}.keyboardShortcut(.cancelAction);Button(submitting ? "Submitting…":"Add to Queue"){submitting=true;Task{await s.export(destination,format,["space":space,"max_edge":edge,"quality":quality,"name":name,"metadata":metadata,"keyword_hierarchy":keywordHierarchy]);submitting=false}}.buttonStyle(.borderedProminent).keyboardShortcut(.defaultAction).disabled(destination.isEmpty || submitting)}
        }.padding(24).frame(width:660)
            .sheet(isPresented:Binding(get:{metadataPhoto != nil},set:{if !$0 { metadataPhoto=nil }})) {
                if let metadataPhoto { ExportMetadataSheet(photoID:metadataPhoto,metadata:metadata,hierarchy:keywordHierarchy) }
            }
    }
}
struct QueueView:View {
    @EnvironmentObject var s:Store
    func state(_ job:[String:Any])->String{["pending":"Pending","running":"Exporting","done":"Completed","failed":"Failed","interrupted":"Interrupted","cancelled":"Cancelled"][job["state"] as? String ?? ""] ?? "Unknown"}
    var body:some View {
        VStack(alignment:.leading,spacing:18){
            HStack{VStack(alignment:.leading,spacing:5){Text("Export Queue").font(.largeTitle.weight(.semibold));Text(s.paused ? "Paused; the current photo will finish first":"One photo at a time · Each job uses its submitted edit snapshot").foregroundStyle(.secondary)};Spacer();Button(s.paused ? "Resume":"Pause"){s.queue(s.paused ? "resume":"pause")};Menu("Retry"){Button("Failed and Interrupted Jobs"){s.queue("retry")};Button("Cancelled Jobs"){s.queue("retry_cancelled")}}}
            if s.jobs.isEmpty{ContentUnavailableView("No Export Jobs Yet",systemImage:"square.and.arrow.up",description:Text("Select photos, then press ⇧⌘E to export."))}
            else{List(Array(s.jobs.enumerated()),id:\.offset){_,job in
                HStack(spacing:14){Image(systemName:job["state"] as? String == "done" ? "checkmark.circle.fill":"photo").foregroundStyle(job["state"] as? String == "done" ? .green:.secondary).font(.title2)
                    VStack(alignment:.leading,spacing:4){Text(URL(fileURLWithPath:job["source"] as? String ?? "").lastPathComponent).font(.headline);Text("\(state(job)) · \(job["format"] as? String ?? "")").font(.caption).foregroundStyle(.secondary);if let e=job["error"] as? String,!e.isEmpty{Text(e).font(.caption).foregroundStyle(.red)}}
                    Spacer()
                    if let output=job["output"] as? String,!output.isEmpty{Button("Show File"){NSWorkspace.shared.activateFileViewerSelecting([URL(fileURLWithPath:output)])}}
                    if ["pending","running"].contains(job["state"] as? String ?? ""){Button("Cancel"){s.queue("cancel",job["id"] as? Int)}}
                    if ["failed","interrupted","cancelled"].contains(job["state"] as? String ?? ""){Button("Retry"){s.queue(job["state"] as? String == "cancelled" ? "retry_cancelled":"retry",job["id"] as? Int)}}
                }.padding(.vertical,7)
            }.listStyle(.inset)}
            Text("Showing the latest 60 jobs. Interrupted jobs require an explicit retry; check the destination for any completed output first.").font(.caption).foregroundStyle(.secondary)
        }.padding(28).task{await s.refreshJobs()}
    }
}
struct VersionsSheet:View {
    @EnvironmentObject var s:Store
    @Environment(\.dismiss) var dismiss
    @State private var name="New Version"
    var body:some View {
        VStack(alignment:.leading,spacing:16){Text("Snapshots").font(.title2.weight(.semibold));HStack{TextField("Version Name",text:$name);Button("Save Current Adjustments"){Task{await s.saveVersion(name)}}.disabled(name.trimmingCharacters(in:.whitespaces).isEmpty)}
            List(Array(s.versions.enumerated()),id:\.offset){_,row in HStack{Text(row["name"] as? String ?? "Version");Spacer();Button("Restore"){if let id=row["id"] as? Int{Task{await s.restoreVersion(id);dismiss()}}}}}
            HStack{Text("Shared by master and copies · Restoring keeps undo history").font(.caption).foregroundStyle(.secondary);Spacer();Button("Done"){dismiss()}.keyboardShortcut(.cancelAction)}
        }.padding(24).frame(width:480,height:360).task{await s.readVersions()}
    }
}
struct RecipeSheet:View {
    @EnvironmentObject var s:Store
    @Environment(\.dismiss) var dismiss
    @State private var text=""
    @State private var issue=""
    var body:some View{
        VStack(alignment:.leading,spacing:14){Text("Full Recipe").font(.title2.weight(.semibold));Text("Edit custom curve points, brush paths, and precise values. The engine validates changes before applying them.").font(.callout).foregroundStyle(.secondary);TextEditor(text:$text).font(.system(.body,design:.monospaced)).border(.separator).frame(minHeight:400);if !issue.isEmpty{Text(issue).foregroundStyle(.red)};HStack{Spacer();Button("Cancel"){dismiss()}.keyboardShortcut(.cancelAction);Button("Apply"){do{guard let data=text.data(using:.utf8),let patch=try JSONSerialization.jsonObject(with:data) as? [String:Any] else{throw EngineFailure(message:"Enter a JSON object")};s.apply(patch);dismiss()}catch{issue=error.localizedDescription}}.buttonStyle(.borderedProminent)}}.padding(24).frame(width:650).onAppear{if let data=try? JSONSerialization.data(withJSONObject:s.recipe,options:[.prettyPrinted,.sortedKeys]),let value=String(data:data,encoding:.utf8){text=value}}
    }
}
struct SyncSheet:View {
    @EnvironmentObject var s:Store
    @Environment(\.dismiss) var dismiss
    @State private var groups:Set<String>=["White Balance","Light","Color","Tone Curve","Detail"]
    let all=["White Balance","Light","Color","Tone Curve","Detail","Lens","Composition","Local Masks","Camera Profile","LUT"]
    var body:some View{VStack(alignment:.leading,spacing:18){Text("Sync Adjustments").font(.title2.weight(.semibold));Text("Copy selected adjustments from \(s.photo?.name ?? "the current photo") to \(max(0,s.selection.count-1)) other photos.").foregroundStyle(.secondary);ForEach(all,id:\.self){g in Toggle(g,isOn:Binding(get:{groups.contains(g)},set:{if $0{groups.insert(g)}else{groups.remove(g)}}))};HStack{Spacer();Button("Cancel"){dismiss()};Button("Sync"){Task{await s.sync(Array(groups).sorted())}}.buttonStyle(.borderedProminent).disabled(groups.isEmpty || s.selection.count<2)}}.padding(24).frame(width:480)}
}
struct CalibrationSheet:View {
    @EnvironmentObject var s:Store
    @Environment(\.dismiss) var dismiss
    @State private var reference=""
    @State private var name="Camera Chart Profile"
    @State private var lighting="Daylight"
    @State private var sourceRect="0, 0, 1, 1"
    @State private var referenceRect="0, 0, 1, 1"
    @State private var report=""
    @State private var busy=false
    @State private var profile:[String:Any]=[:]
    var body:some View {
        VStack(alignment:.leading,spacing:16){Text("Fit Camera Profile").font(.title2.weight(.semibold));Text("The current RAW and reference image must contain a 6 × 4 chart in the same orientation. Use normalized 0–1 bounds. The fit is specific to this camera and lighting.").foregroundStyle(.secondary)
            Text("Chart bounds use the full source after EXIF orientation, before catalog rotation, flips or Develop adjustments.").font(.caption).foregroundStyle(.secondary)
            Form{TextField("Profile Name",text:$name);TextField("Lighting",text:$lighting);HStack{Text(reference.isEmpty ? "Choose a reference image":URL(fileURLWithPath:reference).lastPathComponent);Spacer();Button("Choose…"){let p=NSOpenPanel();if p.runModal() == .OK{reference=p.url?.path ?? ""}}};TextField("RAW Chart: Left, Top, Right, Bottom",text:$sourceRect);TextField("Reference Chart: Left, Top, Right, Bottom",text:$referenceRect)}
            if !report.isEmpty{ScrollView{Text(report).font(.system(.caption,design:.monospaced)).textSelection(.enabled)}.frame(height:150)}
            Text("Fit error describes this data only. It does not establish Nikon NX Studio equivalence or accuracy under other lighting.").font(.caption).foregroundStyle(.secondary)
            HStack{Button("Close"){dismiss()};Spacer();if busy{ProgressView().controlSize(.small)};Button("Fit"){Task{await calibrate()}}.disabled(reference.isEmpty || busy);Button("Apply Profile"){s.set("camera_profile",profile);dismiss()}.buttonStyle(.borderedProminent).disabled(profile.isEmpty)}
        }.padding(24).frame(width:580)
    }
    func calibrate() async {
        guard let p=s.photo else{return};busy=true;defer{busy=false}
        do{let a=sourceRect.split(separator:",").compactMap{Double($0.trimmingCharacters(in:.whitespaces))};let b=referenceRect.split(separator:",").compactMap{Double($0.trimmingCharacters(in:.whitespaces))};let r=try await Backend.call("calibrate_camera",["photo_id":p.id,"reference":reference,"source_rect":a,"reference_rect":b,"name":name,"lighting":lighting]);profile=r["profile"] as? [String:Any] ?? [:];if let data=try? JSONSerialization.data(withJSONObject:r,options:[.prettyPrinted,.sortedKeys]){report=String(data:data,encoding:.utf8) ?? ""}}catch{report=error.localizedDescription}
    }
}
struct AgentView:View {
    @EnvironmentObject var s:Store
    var config:String {
        let data:[String:Any]=["mcpServers":["lumaraw":["command":Backend.executable,"args":["--mcp","--catalog",Backend.catalog]]]]
        return String(data:(try? JSONSerialization.data(withJSONObject:data,options:[.prettyPrinted,.sortedKeys,.withoutEscapingSlashes])) ?? Data(),encoding:.utf8) ?? ""
    }
    var body:some View {
        ScrollView{VStack(alignment:.leading,spacing:24){Label("Bring Your Agent into the Darkroom",systemImage:"terminal").font(.largeTitle.weight(.semibold));Text("The app, MCP, and CLI share one local catalog service. Keep editing while your agent organizes photos, applies adjustments, and submits batch exports.").font(.title3).foregroundStyle(.secondary)
            GroupBox("MCP stdio Configuration"){VStack(alignment:.leading,spacing:12){Text(config).font(.system(.callout,design:.monospaced)).textSelection(.enabled).frame(maxWidth:.infinity,alignment:.leading);Button("Copy Configuration"){NSPasteboard.general.clearContents();NSPasteboard.general.setString(config,forType:.string)}}.padding(10)}
            HStack(spacing:20){Label("Local Communication",systemImage:"desktopcomputer");Label("Read-Only Originals",systemImage:"lock");Label("Edit Conflict Detection",systemImage:"arrow.triangle.branch")}.font(.callout)
            Text("Suggested Workflow").font(.headline)
            Text("1. Read the photo and its current revision\n2. Submit a partial recipe patch and inspect the preview\n3. Enqueue exports with a unique request_key\n4. Check job results and actual output paths").lineSpacing(9)
            Button("Open Agent Skill"){let url=Bundle.main.resourceURL!.appendingPathComponent("skills/lumaraw/SKILL.md");NSWorkspace.shared.open(url)}
            Text("No account or API key is required. Copy this configuration into your client; this app does not modify other app settings.").font(.caption).foregroundStyle(.secondary)
        }.padding(36).frame(maxWidth:850,alignment:.leading)}
    }
}
struct SettingsView:View {
    @EnvironmentObject var s:Store
    var body:some View {
        Form {
            Section("Acceleration"){
                Picker("Image Processing",selection:$s.computeBackend){Text("Auto (Prefer Metal)").tag("auto");Text("CPU").tag("cpu");Text("Metal (Report Failures)").tag("metal")}
                    .onChange(of:s.computeBackend){_,value in Task{do{_=try await Backend.call("settings",["compute_backend":value]);await s.refreshMemory()}catch{s.error=error.localizedDescription}}}
                Text(s.processingSummary).font(.caption).foregroundStyle(.secondary)
                Text("Metal accelerates grading and color conversion. RAW unpacking, demosaicing, and some filters use the CPU.").font(.caption).foregroundStyle(.secondary)
            }
            Section("Processing"){Slider(value:$s.budget,in:256...16384,step:256){Text("Image Worker Budget")}onEditingChanged:{if !$0{Task{do{_=try await Backend.call("settings",["budget_mb":Int(s.budget)]);await s.refreshMemory()}catch{s.error=error.localizedDescription}}}};Text("Configured limit: \(Int(s.budget)) MB · Effective budget: \(s.effectiveBudget) MB").font(.caption).foregroundStyle(.secondary)
                Text("Available memory: about \(Int(s.availableMemory)) MB. Each job uses the lower of the configured limit and 70% of available memory. RSS is sampled, not a system hard limit.").font(.caption).foregroundStyle(.secondary)
                Button("Refresh Memory Status"){Task{await s.refreshMemory()}}}
            Section("Keyword Sets") {
                Toggle("Store Keyword Sets with This Catalog",isOn:Binding(get:{s.keywordSets?.storeWithCatalog ?? false},set:{value in
                    Task { _=await s.keywordSetAction("storage",storeWithCatalog:value) }
                })).disabled(s.keywordSets == nil || s.keywordSetBusy)
                Text("New sets use the selected location. Existing sets are kept in their original location. Shared sets are available to other catalogs.").font(.caption).foregroundStyle(.secondary)
            }
            Section("Develop Presets") {
                Toggle("Store Develop Presets with This Catalog",isOn:Binding(get:{s.developPresetPage?.local ?? false},set:{value in
                    if let page=s.developPresetPage { Task { await s.developPresetAction("storage",revision:page.revision,values:["store_with_catalog":value]) } }
                })).disabled(s.developPresetPage == nil || s.developPresetBusy)
                Text("Shared presets are available to other catalogs. Switching storage keeps existing presets in their original location.").font(.caption).foregroundStyle(.secondary)
            }
            Section("Library"){Text(Backend.catalog).font(.caption).textSelection(.enabled);Button("Show in Finder"){NSWorkspace.shared.open(URL(fileURLWithPath:Backend.catalog))}}
            Section("Background Service") {
                Button(s.connectingService ? "Connecting…":"Connect with This Version") { Task { await s.activateCurrentService() } }.disabled(s.connectingService)
                Text("If another build is connected, switch when image processing is idle. Submitted exports and the queue's pause setting are preserved.").font(.caption).foregroundStyle(.secondary)
                if !s.serviceConnectionMessage.isEmpty { Text(s.serviceConnectionMessage).font(.caption) }
            }
            Section("Color"){Text("Non-destructive editing leaves originals unchanged. NEF decoding uses LibRaw; HE / HE* support and camera-specific color require testing.").font(.callout).foregroundStyle(.secondary)}
        }.formStyle(.grouped).padding(12).task{await s.refreshMemory();await s.refreshKeywordSets();await s.refreshDevelopPresets()}
    }
}
