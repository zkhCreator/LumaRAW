// Purpose: native import source options, thumbnail checks and focused Loupe review.
// Inputs: one bounded ImportReviewModel page. Outputs: explicit scan, selection,
// duplicate policy, Add/Copy import and cancellation commands. No filesystem traversal,
// original writes or AI choices. Closing retains unfinished plans for later review.
// Second-copy choices/progress are explicit; backups retain source names and bytes.
// Presets are source-neutral; ready-review replacement uses explicit rescan.
import SwiftUI
import AppKit

struct ImportReviewSheet: View {
    @ObservedObject var model: ImportReviewModel
    @Environment(\.dismiss) private var dismiss
    @State private var thumbnailSize=150.0
    @State private var showCopies=false
    var body: some View {
        content.task { await model.load(initial:true) }.onDisappear { model.invalidate() }
            .interactiveDismissDisabled(model.busy)
            .sheet(item:$model.processingEditor) { ImportProcessingSheet(model:$0) }
            .sheet(item:$model.namingEditor) { ImportNamingSheet(model:$0) }
            .sheet(item:$model.presetEditor) { ImportPresetSheet(model:$0) }
            .sheet(isPresented:$showCopies) { if let plan=model.plan { ImportCopyReceipts(planID:plan.id) } }
    }
    var content: some View {
        VStack(alignment:.leading,spacing:14) {
            HStack {
                VStack(alignment:.leading,spacing:4) {
                    Text("Import Photos").font(.title2)
                    Text("Review photographs before adding or copying them").foregroundStyle(.secondary)
                }
                Spacer()
                Button("Choose Sources…") { chooseSources() }.disabled(model.busy || model.loading || model.plan?.active == true)
            }
            if model.plan?.active != true {
                VStack(alignment:.leading,spacing:8) {
                    Picker("Import Method",selection:$model.mode) {
                        Text("Add").tag("add");Text("Copy").tag("copy")
                    }.pickerStyle(.segmented).frame(width:220)
                    if model.mode == "copy" {
                        HStack {
                            Button("Choose Destination…") { chooseDestination() }
                            Text(model.destination.isEmpty ? "Choose an existing folder":model.destination).font(.caption).lineLimit(1).help(model.destination)
                        }
                        HStack {
                            Picker("Organize",selection:$model.organization) {
                                Text("Into One Folder").tag("flat")
                                Text("By Original Folders").tag("source")
                                Text("By Date (YYYY/YYYY-MM-DD)").tag("date")
                            }.frame(width:350)
                            TextField("Into Subfolder (optional)",text:$model.subfolder).frame(maxWidth:260)
                        }
                        HStack {
                            Toggle("Make a Second Copy To",isOn:$model.makeSecondCopy)
                            if model.makeSecondCopy {
                                Button("Choose Folder…") { chooseSecondDestination(ready:false) }
                                Text(model.secondCopyDestination.isEmpty ? "Choose an existing folder":model.secondCopyDestination)
                                    .font(.caption).lineLimit(1).help(model.secondCopyDestination)
                            }
                            Spacer()
                        }
                    }
                    Text(model.sources.isEmpty ? "Choose files or folders to review.":"\(model.sources.count) sources selected")
                    ForEach(Array(model.sources.prefix(3).enumerated()),id:\.offset) { _,path in Text(path).font(.caption).lineLimit(1).help(path) }
                    Toggle("Include Subfolders",isOn:$model.includeSubfolders)
                    Toggle("Don't Import Suspected Duplicates",isOn:$model.initialSkipDuplicates)
                    Text("Duplicates require the same original filename, capture time and file size. Unknown capture time is never replaced by file modification time.")
                        .font(.caption).foregroundStyle(.secondary)
                }.disabled(model.busy || model.loading)
            }
            if let plan=model.plan {
                if plan.isCopy {
                    HStack {
                        Text("Copy to \(plan.copy["destination"] as? String ?? "")").font(.caption).lineLimit(1)
                        Spacer()
                        Text("\(plan.primaryCopied) of \(plan.primaryTransferCount) main files copied").font(.caption)
                        Button("Transfer Details…") { showCopies=true }
                    }
                    if let backup=plan.backup {
                        HStack {
                            let path=(backup["destination"] as? String ?? "")+"/"+(backup["subfolder"] as? String ?? "")
                            Text("Second copy: \(path)").font(.caption).lineLimit(1).help(path)
                            Spacer()
                            Text("\(backup["copied"] as? Int ?? 0) of \(backup["transfer_count"] as? Int ?? 0) backed up").font(.caption)
                            if plan.ready {
                                Button("Change…") { chooseSecondDestination(ready:true) }.disabled(model.busy || model.loading)
                                Button("Disable") { Task { await model.setBackup(nil) } }.disabled(model.busy || model.loading)
                            }
                        }
                        if backup["same_volume"] as? Bool == true {
                            Text("Both destinations are on the same filesystem volume. A separate drive provides protection against drive failure.")
                                .font(.caption).foregroundStyle(.secondary)
                        }
                    } else if plan.ready {
                        Button("Make a Second Copy To…") { chooseSecondDestination(ready:true) }.disabled(model.busy || model.loading)
                    }
                }
                HStack {
                    Text(plan.state.capitalized).fontWeight(.semibold)
                    Text("\(plan.number("scanned")) of \(plan.number("file_count")) scanned").foregroundStyle(.secondary)
                    if plan.state == "verifying" { Text("\(plan.number("checked")) verified").foregroundStyle(.secondary) }
                    Spacer()
                    if model.busy || model.loading { ProgressView().controlSize(.small) }
                }
                if !plan.text("error").isEmpty { Text(plan.text("error")).foregroundStyle(.red).textSelection(.enabled) }
                if plan.active {
                    HStack {
                        Button("Apply During Import…") { model.openProcessing() }.disabled(model.busy || model.loading || !plan.ready)
                        if plan.isCopy {
                            Button(plan.copy["renaming"] as? Bool == true ? "File Renaming: On…":"File Renaming…") { model.openNaming() }
                                .disabled(model.busy || model.loading || !plan.ready)
                        }
                        if let settings=plan.values["processing"] as? [String:Any] {
                            let names=[settings["develop_name"] as? String ?? "",settings["metadata_name"] as? String ?? ""].filter{!$0.isEmpty}
                            Text((names+[(settings["keyword_count"] as? Int ?? 0)>0 ? "Additional keywords":""]).filter{!$0.isEmpty}.joined(separator:" · "))
                                .font(.caption).foregroundStyle(.secondary).lineLimit(1)
                        }
                        Spacer()
                    }
                    HStack {
                        Picker("Show",selection:Binding(get:{model.kind},set:{value in Task { await model.browse(kind:value) }})) {
                            Text("All Photos").tag("all");Text("New Photos").tag("new");Text("Suspected Duplicates").tag("duplicate")
                            Text("Already Imported").tag("existing");Text("Errors").tag("error");Text("Checked Photos").tag("selected")
                        }.frame(width:245)
                        Picker("Sort",selection:Binding(get:{model.sort},set:{value in model.sort=value;Task { await model.browse() }})) {
                            Text("Filename").tag("name");Text("Capture Time").tag("captured");Text("Checked State").tag("checked");Text("File Type").tag("type")
                        }.frame(width:190)
                        Button { model.descending.toggle();Task { await model.browse() } } label: {
                            Image(systemName:model.descending ? "arrow.down":"arrow.up")
                        }.help("Reverse sort direction")
                        Spacer()
                        Picker("View",selection:$model.loupe) { Text("Grid").tag(false);Text("Loupe").tag(true) }
                            .labelsHidden().accessibilityLabel("Preview view")
                            .pickerStyle(.segmented).frame(width:130).onChange(of:model.loupe) { _,_ in model.refreshDetail() }
                    }.disabled(model.busy || model.loading || !plan.ready)
                    if model.loupe { loupe } else { grid }
                    HStack {
                        Button("Check All") { Task { await model.select(true) } }.disabled(["existing","error","selected"].contains(model.kind))
                        Button("Uncheck All") { Task { await model.select(false) } }.disabled(["existing","error"].contains(model.kind))
                        Spacer()
                        Toggle("Don't Import Suspected Duplicates",isOn:Binding(get:{plan.skipDuplicates},set:{value in Task { await model.skipDuplicates(value) }}))
                    }.disabled(model.busy || model.loading || !plan.ready)
                    HStack {
                        Text("\(plan.number("selected_count")) checked · \(ByteCountFormatter.string(fromByteCount:Int64(plan.number("selected_bytes")),countStyle:.file))")
                        Spacer()
                        if !model.loupe { Text("Thumbnails");Slider(value:$thumbnailSize,in:110...230).frame(width:115) }
                        Button("Previous") { Task { await model.browse(offset:max(0,model.offset-60)) } }.disabled(model.offset == 0)
                        Text(model.total == 0 ? "No photos":"\(model.offset+1)–\(min(model.offset+60,model.total)) of \(model.total)").font(.caption)
                        Button("Next") { Task { await model.browse(offset:model.offset+60) } }.disabled(model.offset+60>=model.total)
                    }.disabled(model.busy || model.loading)
                } else if plan.state == "applied" {
                    Label("Imported \(plan.number("imported")) photos",systemImage:"checkmark.circle.fill").foregroundStyle(.green)
                    Spacer()
                }
            } else { Spacer() }
            if let error=model.error { Text(error).font(.caption).foregroundStyle(.red).textSelection(.enabled) }
            Text((model.plan?.isCopy ?? (model.mode == "copy")) ?
                 "Copy preserves originals and copies associated XMP. Existing destinations are never overwritten. Cancelling keeps completed copies. Unknown capture dates use an Unknown Date folder.":
                 "Files stay in place. Supported embedded and sidecar descriptions are read into the catalog; existing catalog photos are preserved.")
                .font(.caption).foregroundStyle(.secondary)
            HStack {
                Button("Import Presets…") {model.openPresets()}.disabled(model.busy || model.loading || model.plan?.active == true && model.plan?.ready != true)
                let presetName=model.plan?.active == true ? model.plan?.text("preset_name") ?? "":model.presetName
                if !presetName.isEmpty {Text("Based on: \(presetName)").font(.caption).lineLimit(1)}
                if model.plan?.active != true,model.presetChoice != nil {
                    Button("Clear Preset") {model.presetChoice=nil;model.presetName=""}.disabled(model.busy || model.loading)
                }
                Spacer()
            }
            HStack {
                Button("Done") { dismiss() }.keyboardShortcut(.cancelAction).disabled(model.busy)
                if model.plan?.active == true {
                    Button(model.cancelling ? "Cancelling…":"Cancel Import Review",role:.destructive) { Task { await model.cancel() } }.disabled(model.cancelling)
                }
                Spacer()
                if model.plan?.interruptedCopy == true {
                    Button("Resume Copy") { Task { await model.resumeCopy() } }.disabled(!model.canResumeCopy)
                }
                if model.plan?.interruptedCopy != true {
                    Button(model.plan?.active == true ? "Resume Scan":"Scan Photos") { Task { await model.scan() } }
                        .disabled(!model.canScan || model.plan?.active != true && model.sources.isEmpty)
                }
                Button("Import Checked") { Task { await model.apply() } }.buttonStyle(.borderedProminent)
                    .keyboardShortcut(.defaultAction).disabled(!model.canApply)
            }
        }.padding(22).frame(minWidth:900,idealWidth:1060,minHeight:650,idealHeight:760)
    }
    var grid: some View {
        ScrollView {
            LazyVGrid(columns:[GridItem(.adaptive(minimum:thumbnailSize),spacing:10,alignment:.top)],spacing:12) {
                ForEach(model.items) { item in
                    VStack(alignment:.leading,spacing:7) {
                        ZStack {
                            Rectangle().fill(Color.black.opacity(0.2))
                            if let image=model.images[item.id] { Image(nsImage:image).resizable().scaledToFit().padding(5) }
                            else { Image(systemName:item.state == "error" ? "exclamationmark.triangle":"photo").foregroundStyle(.secondary) }
                        }.frame(height:thumbnailSize*0.68).contentShape(Rectangle())
                            .onTapGesture(count:2) { model.focus(item,detail:true) }
                            .onTapGesture { model.focus(item) }
                            .accessibilityLabel("Preview \(item.name)")
                        Toggle(isOn:Binding(get:{item.selected && item.eligible},set:{value in Task { await model.select(value,ids:[item.id]) }})) {
                            Text(item.name).lineLimit(1).font(.caption)
                        }.disabled(!item.eligible || model.busy || model.loading || model.plan?.ready != true)
                        Text(item.state == "existing" ? "Already imported":item.state == "duplicate" ? "Suspected duplicate":item.state.capitalized)
                            .font(.caption2).foregroundStyle(item.eligible ? Color.secondary:Color.orange)
                        if item.hasNotes { Text("Some metadata is unsupported").font(.caption2).foregroundStyle(.secondary) }
                        if !item.destination.isEmpty { Text("To: \(URL(fileURLWithPath:item.destination).lastPathComponent)").font(.caption2).lineLimit(2).help(item.destination) }
                        if !item.secondDestination.isEmpty { Text("Backup: \(URL(fileURLWithPath:item.secondDestination).lastPathComponent)").font(.caption2).lineLimit(2).help(item.secondDestination) }
                        if !item.error.isEmpty { Text(item.error).font(.caption2).foregroundStyle(.red).lineLimit(2) }
                        if let error=model.previewErrors[item.id] { Text(error).font(.caption2).foregroundStyle(.red).lineLimit(2) }
                    }.padding(8).background(RoundedRectangle(cornerRadius:7).fill(model.focused == item.id ? Color.accentColor.opacity(0.15):Color.clear))
                        .help(item.path)
                }
            }.padding(4)
        }.frame(maxWidth:.infinity,maxHeight:.infinity)
    }
    var loupe: some View {
        VStack(spacing:8) {
            ZStack {
                Rectangle().fill(Color.black.opacity(0.3))
                if let image=model.detail ?? model.focused.flatMap({model.images[$0]}) { Image(nsImage:image).resizable().scaledToFit().padding(10) }
                if model.detailLoading { ProgressView() }
            }.frame(maxWidth:.infinity,maxHeight:.infinity)
            if let item=model.items.first(where:{$0.id == model.focused}) {
                HStack {
                    Button("Previous Photo") { moveFocus(-1) }
                    Toggle(item.name,isOn:Binding(get:{item.selected && item.eligible},set:{value in Task { await model.select(value,ids:[item.id]) }}))
                        .disabled(!item.eligible || model.busy || model.loading || model.plan?.ready != true)
                    Button("Next Photo") { moveFocus(1) }
                }
                Text(item.path).font(.caption).textSelection(.enabled)
                if let error=model.detailError { Text(error).font(.caption).foregroundStyle(.red) }
            }
        }
    }
    func moveFocus(_ step: Int) {
        guard let index=model.items.firstIndex(where:{$0.id == model.focused}) else { return }
        let next=index+step
        if model.items.indices.contains(next) { model.focus(model.items[next]) }
    }
    func chooseSources() {
        let panel=NSOpenPanel();panel.canChooseFiles=true;panel.canChooseDirectories=true;panel.allowsMultipleSelection=true
        panel.prompt="Review";panel.message="Choose photographs or folders to review before importing"
        if panel.runModal() == .OK { model.sources=panel.urls.map(\.path) }
    }
    func chooseDestination() {
        let panel=NSOpenPanel();panel.canChooseFiles=false;panel.canChooseDirectories=true;panel.allowsMultipleSelection=false
        panel.prompt="Choose Destination";panel.message="Copies will be written here when you import the checked photographs"
        if panel.runModal() == .OK,let path=panel.url?.path { model.destination=path }
    }
    func chooseSecondDestination(ready: Bool) {
        let panel=NSOpenPanel();panel.canChooseFiles=false;panel.canChooseDirectories=true;panel.allowsMultipleSelection=false
        panel.prompt="Choose Backup Folder"
        panel.message="Keep an extra copy of the original files and XMP, using their original names, in a dated folder"
        if panel.runModal() == .OK,let path=panel.url?.path {
            if ready { Task { await model.setBackup(path) } }
            else { model.secondCopyDestination=path }
        }
    }
}
