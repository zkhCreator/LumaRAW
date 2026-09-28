// Purpose: review, selection and explicit application of durable folder sync plans.
// Inputs: one catalog folder, bounded service pages and revision-bound actions.
// Outputs: progress, file/subfolder selection and refreshed native library state.
// No SQL, filesystem scans, metadata parsing or original writes. Closing retains
// a plan; cancelled/uncertain application is read back, never automatically retried.
import SwiftUI

struct FolderSyncPlan {
    let values: [String:Any]
    var id: Int { number("id") }
    var revision: Int { number("revision") }
    var state: String { text("state") }
    var active: Bool { ["planning","scanning","ready","verifying","interrupted"].contains(state) }
    func number(_ key: String) -> Int { values[key] as? Int ?? 0 }
    func text(_ key: String) -> String { values[key] as? String ?? "" }
    func count(_ kind: String,selected: Bool=false) -> Int {
        (values[selected ? "selected_counts":"counts"] as? [String:Int])?[kind] ?? 0
    }
}

struct FolderSyncItem: Identifiable {
    let id: Int
    let path: String
    let state: String
    let selected: Bool
    let photos: Int
    let patch: [String:Any]
    let clock: [String:Any]
    let notes: [String]
    let error: String
    var selectable: Bool { ["new","missing","updated"].contains(state) }
    var folder: String { URL(fileURLWithPath:path).deletingLastPathComponent().path }
    var metadataKeys: [String] { patch.keys.sorted() + ["taken","camera"].filter { clock[$0] != nil } }
    func label(_ key: String) -> String {
        ["keyword_paths":"Keywords","color_label":"Color Label","flag":"Flag","taken":"Capture Time","camera":"Camera"][key] ?? key.capitalized
    }
    func value(_ key: String) -> String {
        if key == "keyword_paths",let paths=patch[key] as? [[String]] { return paths.map{$0.joined(separator:" | ")}.joined(separator:", ") }
        if key == "flag",let flag=patch[key] as? Int { return flag == -1 ? "Rejected":flag == 1 ? "Picked":"Unflagged" }
        if key == "taken",let micros=clock["taken_us"] as? Int64 {
            let remainder=(micros % 1_000_000 + 1_000_000) % 1_000_000
            let seconds=(micros-remainder)/1_000_000
            let formatter=DateFormatter()
            formatter.locale=Locale(identifier:"en_US_POSIX");formatter.timeZone=TimeZone(secondsFromGMT:0)
            formatter.dateFormat="yyyy-MM-dd HH:mm:ss"
            var fraction=String(format:"%06lld",remainder)+(clock["taken_submicro"] as? String ?? "")
            while fraction.last == "0" { fraction.removeLast() }
            let suffix=clock["capture_clock"] as? String == "utc" ? " UTC":" (camera clock)"
            return formatter.string(from:Date(timeIntervalSince1970:Double(seconds)))+(fraction.isEmpty ? "":"."+fraction)+suffix
        }
        return String(describing:patch[key] ?? clock[key] ?? "")
    }
    init?(_ row: [String:Any]) {
        guard let id=row["id"] as? Int,let path=row["path"] as? String,let state=row["state"] as? String else { return nil }
        self.id=id;self.path=path;self.state=state;selected=(row["selected"] as? Int ?? 0) != 0
        photos=row["catalog_photos"] as? Int ?? 0;patch=row["patch"] as? [String:Any] ?? [:]
        clock=row["clock"] as? [String:Any] ?? [:]
        notes=row["notes"] as? [String] ?? [];error=row["error"] as? String ?? ""
    }
}

@MainActor final class FolderSyncModel: ObservableObject {
    let folder: LibraryFolder?
    @Published var plan: FolderSyncPlan?
    @Published var items: [FolderSyncItem]=[]
    @Published var kind="changes"
    @Published var offset=0
    @Published var total=0
    @Published var loading=true
    @Published var busy=false
    @Published var cancelling=false
    @Published var error: String?
    @Published var importNew=true
    @Published var removeMissing=false
    @Published var scanMetadata=true
    @Published var readMetadata=true
    private var generation=0
    private var adopted: Set<Int>=[]
    var canScan: Bool { !busy && !loading && ["planning","interrupted"].contains(plan?.state ?? "") }
    var canApply: Bool { !busy && !loading && plan?.state == "ready" && plan?.count("error") == 0 }
    init(folder: LibraryFolder?) { self.folder=folder }

    func receive(_ result: [String:Any]) {
        guard let values=result["plan"] as? [String:Any] else { plan=nil;items=[];total=0;offset=0;return }
        let next=FolderSyncPlan(values:values)
        if let previous=plan,previous.id == next.id {
            guard next.revision >= previous.revision else { return }
            if next.revision == previous.revision && next.number("checked") < previous.number("checked") { return }
        }
        plan=next;items=(result["items"] as? [[String:Any]] ?? []).compactMap(FolderSyncItem.init)
        total=result["total"] as? Int ?? 0;offset=result["offset"] as? Int ?? 0
        if next.number("scan_metadata") == 0 { readMetadata=false }
    }

    func reload(offset: Int=0) async {
        guard !busy else { return }
        generation+=1;let token=generation;loading=true;error=nil
        var params: [String:Any]=["kind":kind,"offset":offset]
        if let plan { params["plan_id"]=plan.id }
        defer { if token == generation { loading=false } }
        do {
            let result=try await Backend.call("get_folder_sync",params)
            if token == generation { receive(result) }
        } catch { if token == generation { self.error=error.localizedDescription } }
    }

    func prepare(revision: Int) async {
        guard let folder,!busy,!loading,plan?.active != true else { return }
        generation+=1;let token=generation;busy=true;error=nil;kind="changes";offset=0
        defer { if token == generation { busy=false } }
        do {
            let result=try await Backend.call("prepare_folder_sync",["folder_id":folder.id,"expected_revision":revision,"scan_metadata":scanMetadata])
            if token == generation { receive(result);readMetadata=scanMetadata }
        } catch { if token == generation { self.error=error.localizedDescription } }
    }

    func scan() async {
        guard canScan else { return }
        generation+=1;let token=generation;busy=true;error=nil;kind="changes";offset=0
        defer { if token == generation { busy=false } }
        do {
            while let captured=plan,["planning","interrupted"].contains(captured.state),token == generation,!Task.isCancelled {
                let result=try await Backend.call("scan_folder_sync",["plan_id":captured.id,"expected_revision":captured.revision])
                guard token == generation else { return }
                receive(result)
            }
        } catch { if token == generation { self.error=error.localizedDescription } }
    }

    func select(_ selected: Bool,kind requested: String,item: FolderSyncItem?=nil,folder: String?=nil) async {
        guard !busy,!loading,let captured=plan,captured.state == "ready" else { return }
        generation+=1;let token=generation;busy=true;error=nil
        let page=offset;let filter=kind
        defer { if token == generation { busy=false } }
        var params: [String:Any]=["plan_id":captured.id,"expected_revision":captured.revision,"selected":selected,"kind":requested]
        if let item { params["item_ids"]=[item.id] }
        if let folder { params["folder"]=folder }
        do {
            _=try await Backend.call("select_folder_sync_items",params)
            let result=try await Backend.call("get_folder_sync",["plan_id":captured.id,"kind":filter,"offset":page])
            if token == generation { receive(result) }
        } catch { if token == generation { self.error=error.localizedDescription } }
    }

    private func adopt(using store: Store) async {
        guard let plan,plan.state == "applied",!adopted.contains(plan.id) else { return }
        adopted.insert(plan.id)
        let selected=store.selected
        await store.refreshCollections();await store.refreshFolders(reset:true);await store.refresh()
        if let selected,store.selected == selected { await store.load(selected) }
        store.message="Synchronized folder · \(plan.number("imported")) imported · \(plan.number("removed")) catalog photos removed · \(plan.number("modified")) metadata updates"
    }

    func apply(using store: Store) async {
        guard canApply,let captured=plan else { return }
        generation+=1;let token=generation;busy=true;error=nil
        let options: [String:Any]=["plan_id":captured.id,"expected_revision":captured.revision,"import_new":importNew,
                                  "remove_missing":removeMissing,"read_metadata":readMetadata]
        defer { if token == generation { busy=false } }
        guard await store.flushEdits(),token == generation else { return }
        let polling=Task { [weak self] in
            while !Task.isCancelled {
                do { try await Task.sleep(nanoseconds:400_000_000) } catch { return }
                guard let self,self.generation == token else { return }
                if let result=try? await Backend.call("get_folder_sync",["plan_id":captured.id,"kind":self.kind,"offset":self.offset]),
                   self.generation == token,!Task.isCancelled { self.receive(result) }
            }
        }
        defer { polling.cancel() }
        do {
            let result=try await Backend.call("apply_folder_sync",options)
            guard token == generation else { return }
            receive(result);await adopt(using:store)
        } catch {
            guard token == generation else { return }
            self.error=error.localizedDescription
            if let result=try? await Backend.call("get_folder_sync",["plan_id":captured.id]),token == generation {
                receive(result);await adopt(using:store)
            }
        }
    }

    func cancel(using store: Store) async {
        guard let captured=plan,captured.active,!cancelling else { return }
        generation+=1;let token=generation;busy=true;loading=false;cancelling=true;error=nil
        defer { if token == generation { busy=false;cancelling=false } }
        do {
            let result=try await Backend.call("cancel_folder_sync",["plan_id":captured.id])
            guard token == generation else { return }
            receive(result);await adopt(using:store)
        } catch {
            guard token == generation else { return }
            self.error=error.localizedDescription
            if let result=try? await Backend.call("get_folder_sync",["plan_id":captured.id]),token == generation {
                receive(result);await adopt(using:store)
            }
        }
    }

    func invalidate() { generation+=1 }
}

struct FolderSyncSheet: View {
    @EnvironmentObject var s: Store
    @Environment(\.dismiss) private var dismiss
    @StateObject private var model: FolderSyncModel
    init(folder: LibraryFolder?) { _model=StateObject(wrappedValue:FolderSyncModel(folder:folder)) }
    var body: some View {
        VStack(alignment:.leading,spacing:14) {
            Text("Synchronize Folder").font(.title2)
            ScrollView {
                VStack(alignment:.leading,spacing:12) {
                    Text("Review this folder and all subfolders before updating the catalog. Files remain in their current locations.")
                    if let folder=model.folder { Text("Selected folder: \(folder.path)").font(.caption).textSelection(.enabled) }
                    if let plan=model.plan {
                        Text(plan.text("path")).textSelection(.enabled)
                        if plan.active {
                            if plan.text("phase") == "directories" {
                                ProgressView("Discovering folders · \(plan.number("directories_done")) of \(plan.number("directory_count")) visited")
                            } else {
                                ProgressView(value:Double(plan.number(plan.state == "verifying" ? "checked":"scanned")),total:Double(max(1,plan.number("file_count"))))
                                Text("\(plan.state == "verifying" ? "Verifying":"Scanned") \(plan.number(plan.state == "verifying" ? "checked":"scanned")) of \(plan.number("file_count")) originals")
                            }
                        }
                        Text("\(plan.count("new")) new · \(plan.count("missing")) missing · \(plan.count("updated")) changed · \(plan.count("error")) scan errors")
                        if plan.count("with_notes")>0 {
                            Text("\(plan.count("with_notes")) originals contain metadata notes. Review All Files for unsupported fields or Adobe Develop settings.").font(.caption).foregroundStyle(.secondary)
                        }
                        if plan.state == "ready" {
                            Toggle("Import New Photos (\(plan.count("new",selected:true)) selected)",isOn:$model.importNew).disabled(model.busy || model.loading)
                            Toggle("Remove Missing Photos From Catalog (\(plan.count("missing",selected:true)) originals)",isOn:$model.removeMissing)
                                .disabled(model.busy || model.loading || plan.count("missing")==0)
                            if model.removeMissing {
                                Text("This removes selected missing originals and all their virtual copies, edits, snapshots and collection memberships from the catalog. Existing export receipts are preserved.").font(.callout).foregroundStyle(.orange)
                            }
                            Toggle("Read Scanned Metadata Updates",isOn:$model.readMetadata).disabled(model.busy || model.loading || plan.number("scan_metadata")==0)
                            Text("Supported titles, captions, copyright, ratings, labels and keywords replace matching fields on originals. Virtual-copy descriptions and Develop edits stay independent.").font(.caption).foregroundStyle(.secondary)
                        }
                        if !plan.text("error").isEmpty { Text(plan.text("error")).foregroundStyle(.red).textSelection(.enabled) }
                        if plan.state == "applied" { Label("Imported \(plan.number("imported")) · Removed \(plan.number("removed")) · Read metadata for \(plan.number("modified"))",systemImage:"checkmark.circle") }
                        if plan.state == "cancelled" { Text("Plan cancelled. The catalog is unchanged.") }
                        if plan.state == "failed" { Text("Synchronization failed. The catalog is unchanged.") }
                        Picker("Review Files",selection:$model.kind) {
                            Text("Changes").tag("changes");Text("New").tag("new");Text("Missing").tag("missing")
                            Text("Changed").tag("updated");Text("Errors").tag("error");Text("All Files").tag("all")
                        }.disabled(model.busy || model.loading).onChange(of:model.kind) { _,_ in Task { await model.reload() } }
                        if ["new","missing","updated"].contains(model.kind),plan.state == "ready" {
                            HStack {
                                Button("Select All") { Task { await model.select(true,kind:model.kind) } }
                                Button("Select None") { Task { await model.select(false,kind:model.kind) } }
                            }.disabled(model.busy || model.loading)
                        }
                        LazyVStack(alignment:.leading,spacing:10) {
                            ForEach(model.items) { item in
                                HStack(alignment:.top) {
                                    if item.selectable {
                                        Toggle("Include \(URL(fileURLWithPath:item.path).lastPathComponent)",isOn:Binding(get:{item.selected},set:{ value in
                                            Task { await model.select(value,kind:item.state,item:item) }
                                        })).labelsHidden().disabled(model.busy || model.loading || model.plan?.state != "ready")
                                    }
                                    VStack(alignment:.leading,spacing:3) {
                                        Text(item.path).textSelection(.enabled)
                                        Text(item.state.capitalized+(item.photos>1 ? " · \(item.photos) catalog photos":"")).foregroundStyle(.secondary)
                                        if !item.metadataKeys.isEmpty {
                                            DisclosureGroup("Review Metadata") {
                                                ForEach(item.metadataKeys,id:\.self) { key in
                                                    Text("\(item.label(key)): \(item.value(key).isEmpty ? "(empty)":item.value(key))").textSelection(.enabled)
                                                }
                                            }
                                        }
                                        ForEach(item.notes,id:\.self) { Text($0).foregroundStyle(.secondary) }
                                        if !item.error.isEmpty { Text(item.error).foregroundStyle(.red) }
                                    }.font(.caption)
                                }.contextMenu {
                                    if item.selectable {
                                        Button("Select This Folder and Subfolders") { Task { await model.select(true,kind:item.state,folder:item.folder) } }
                                        Button("Deselect This Folder and Subfolders") { Task { await model.select(false,kind:item.state,folder:item.folder) } }
                                    }
                                }
                            }
                        }
                        if model.total>60 {
                            HStack {
                                Button("Previous") { Task { await model.reload(offset:max(0,model.offset-60)) } }.disabled(model.offset==0)
                                Text("\(model.offset+1)–\(min(model.offset+60,model.total)) of \(model.total)")
                                Button("Next") { Task { await model.reload(offset:model.offset+60) } }.disabled(model.offset+60>=model.total)
                            }.font(.caption).disabled(model.busy || model.loading)
                        }
                    } else if model.folder == nil && !model.loading { Text("Select a folder in the sidebar to start synchronization.") }
                    if model.plan?.active != true && model.folder != nil {
                        Toggle("Scan For Metadata Updates",isOn:$model.scanMetadata).disabled(model.busy || model.loading)
                    }
                    if let error=model.error { Text(error).foregroundStyle(.red).textSelection(.enabled) }
                    if model.loading { ProgressView("Reading saved plan…") }
                }.frame(maxWidth:.infinity,alignment:.leading)
            }.frame(maxHeight:580)
            HStack {
                if model.folder != nil && model.plan?.active != true {
                    Button("Start Scan") { Task {
                        await s.refreshFolders();await model.prepare(revision:s.folderRevision)
                        if model.canScan { await model.scan() }
                    } }.disabled(model.busy || model.loading)
                }
                if model.plan?.active == true {
                    Button("Cancel Plan",role:.destructive) { Task { await model.cancel(using:s) } }.disabled(model.cancelling)
                }
                Spacer()
                Button("Refresh") { Task { await model.reload(offset:model.offset) } }.disabled(model.busy || model.loading)
                Button("Close",role:.cancel) { dismiss() }.keyboardShortcut(.cancelAction).disabled(model.busy)
                if model.canScan { Button("Continue Scanning") { Task { await model.scan() } } }
                Button("Synchronize") { Task { await model.apply(using:s) } }.buttonStyle(.borderedProminent).disabled(!model.canApply)
            }
        }.padding(24).frame(width:740)
            .interactiveDismissDisabled(model.busy)
            .task { await model.reload() }
            .onDisappear { model.invalidate() }
    }
}
