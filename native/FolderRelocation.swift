// Purpose: reviewable, resumable reconnection of a missing catalog folder tree.
// Inputs: an explicit replacement directory and revision-bound service plans.
// Outputs: bounded progress/issues, cancellation and refreshed native sources.
// No filesystem traversal, SQL, hashing or original writes. Closing retains the
// staged plan; applying requires an explicit action after the scan completes.
import SwiftUI
import AppKit

struct FolderRelocationPlan {
    let values: [String:Any]
    var id: Int { count("id") }
    var revision: Int { count("revision") }
    var state: String { text("state") }
    var active: Bool { ["planning","scanning","ready","verifying","interrupted"].contains(state) }
    func count(_ key: String) -> Int { values[key] as? Int ?? 0 }
    func text(_ key: String) -> String { values[key] as? String ?? "" }
}

@MainActor final class FolderRelocationModel: ObservableObject {
    let folder: LibraryFolder?
    @Published var plan: FolderRelocationPlan?
    @Published var items: [[String:Any]]=[]
    @Published var total=0
    @Published var offset=0
    @Published var busy=false
    @Published var loading=true
    @Published var cancelling=false
    @Published var error: String?
    private var generation=0
    private var adopted: Set<Int>=[]
    var canScan: Bool { !busy && !loading && ["planning","interrupted"].contains(plan?.state ?? "") }
    var canApply: Bool { !busy && !loading && plan?.state == "ready" && plan?.count("conflicts") == 0 }
    init(folder: LibraryFolder?) { self.folder=folder }

    func receive(_ result: [String:Any]) {
        guard let values=result["plan"] as? [String:Any] else { plan=nil;items=[];total=0;offset=0;return }
        let next=FolderRelocationPlan(values:values)
        if let previous=plan,previous.id == next.id {
            guard next.revision >= previous.revision else { return }
            if next.revision == previous.revision && next.count("checked") < previous.count("checked") { return }
        }
        plan=next;items=result["items"] as? [[String:Any]] ?? []
        total=result["total"] as? Int ?? 0;offset=result["offset"] as? Int ?? 0
    }

    func reload(offset: Int=0) async {
        guard !busy else { return }
        generation+=1;let token=generation;loading=true;error=nil
        var params: [String:Any]=["offset":offset]
        if let plan { params["plan_id"]=plan.id }
        defer { if token == generation { loading=false } }
        do {
            let result=try await Backend.call("get_folder_relocation",params)
            if token == generation { receive(result) }
        } catch { if token == generation { self.error=error.localizedDescription } }
    }

    func prepare(destination: String, revision: Int) async {
        guard !busy && !loading,plan?.active != true,let folder else { return }
        generation+=1;let token=generation;busy=true;error=nil
        do {
            let result=try await Backend.call("prepare_folder_relocation",["folder_id":folder.id,"destination":destination,"expected_revision":revision])
            guard token == generation else { return }
            receive(result)
        } catch { if token == generation { self.error=error.localizedDescription } }
        if token == generation { busy=false }
    }

    func scan() async {
        guard canScan else { return }
        generation+=1;let token=generation;busy=true;error=nil
        defer { if token == generation { busy=false } }
        do {
            while let captured=plan,["planning","interrupted"].contains(captured.state),token == generation,!Task.isCancelled {
                let result=try await Backend.call("scan_folder_relocation",["plan_id":captured.id,"expected_revision":captured.revision])
                guard token == generation else { return }
                receive(result)
            }
        } catch { if token == generation { self.error=error.localizedDescription } }
    }

    private func adopt(using store: Store) async {
        guard let plan,plan.state == "applied",!adopted.contains(plan.id) else { return }
        adopted.insert(plan.id)
        await store.adoptFolderRelocation(plan)
    }

    func apply(using store: Store) async {
        guard canApply,let captured=plan else { return }
        generation+=1;let token=generation;busy=true;error=nil
        defer { if token == generation { busy=false } }
        guard await store.flushEdits(),token == generation else { return }
        let polling=Task { [weak self] in
            while !Task.isCancelled {
                do { try await Task.sleep(nanoseconds:400_000_000) } catch { return }
                guard let self,self.generation == token else { return }
                if let result=try? await Backend.call("get_folder_relocation",["plan_id":captured.id]),self.generation == token,!Task.isCancelled {
                    self.receive(result)
                }
            }
        }
        defer { polling.cancel() }
        do {
            let result=try await Backend.call("apply_folder_relocation",["plan_id":captured.id,"expected_revision":captured.revision])
            guard token == generation else { return }
            receive(result);await adopt(using:store)
        } catch {
            guard token == generation else { return }
            self.error=error.localizedDescription
            // Read an uncertain mutation outcome; never retry the mutation.
            if let result=try? await Backend.call("get_folder_relocation",["plan_id":captured.id]),token == generation {
                receive(result);await adopt(using:store)
            }
        }
    }

    func cancel(using store: Store) async {
        guard let captured=plan,captured.active,!cancelling else { return }
        generation+=1;let token=generation;busy=true;loading=false;cancelling=true;error=nil
        defer { if token == generation { busy=false;cancelling=false } }
        do {
            let result=try await Backend.call("cancel_folder_relocation",["plan_id":captured.id])
            guard token == generation else { return }
            receive(result);await adopt(using:store)
        } catch {
            guard token == generation else { return }
            self.error=error.localizedDescription
            if let result=try? await Backend.call("get_folder_relocation",["plan_id":captured.id]),token == generation {
                receive(result);await adopt(using:store)
            }
        }
    }

    func invalidate() { generation+=1 }
}

extension Store {
    func adoptFolderRelocation(_ plan: FolderRelocationPlan) async {
        let navigation=sourceNavigationGeneration
        let previous=activeFolder
        let selectedID=selected
        let source=plan.text("source")
        if let previous,folderID == previous.id,previous.path == source || previous.path.hasPrefix(source+"/") {
            let result: [String:Any]?
            if let existing=try? await Backend.call("get_folder",["folder_id":previous.id]) { result=existing }
            else { result=try? await Backend.call("get_folder",["folder_id":plan.count("result_folder_id")]) }
            if navigation == sourceNavigationGeneration,folderID == previous.id,let result,let updated=LibraryFolder(result) {
                folderID=updated.id;activeFolder=updated;offset=0
            }
        }
        await refreshFolders(reset:true)
        await refresh()
        if let selectedID,selected == selectedID { await load(selectedID) }
        message="Reconnected \(plan.count("photo_count")) catalog photos · \(plan.count("missing")) originals still missing"
    }
}

struct FolderRelocationSheet: View {
    @EnvironmentObject var s: Store
    @Environment(\.dismiss) private var dismiss
    @StateObject private var model: FolderRelocationModel
    init(folder: LibraryFolder?) { _model=StateObject(wrappedValue:FolderRelocationModel(folder:folder)) }
    var body: some View {
        VStack(alignment:.leading,spacing:14) {
            Text("Find Missing Folder").font(.title2)
            Text("Reconnect this folder and its subfolders at their new location. Your edits, virtual copies, keywords and stacks stay in the catalog.").font(.callout)
            if let folder=model.folder { Text("Selected folder: \(folder.path)").font(.caption).textSelection(.enabled) }
            if let plan=model.plan {
                Text(plan.text("source")).textSelection(.enabled)
                Label(plan.text("destination"),systemImage:"arrow.turn.down.right").textSelection(.enabled)
                Text("\(plan.count("photo_count")) catalog photos · \(plan.count("physical_count")) originals · \(plan.count("folder_count")) folders")
                if plan.active {
                    ProgressView(value:Double(plan.count(plan.state == "verifying" ? "checked":"scanned")),total:Double(max(1,plan.count("physical_count"))))
                    Text(plan.state == "verifying" ? "Checking \(plan.count("checked")) of \(plan.count("physical_count")) originals before applying…" : "Scanned \(plan.count("scanned")) of \(plan.count("physical_count")) originals")
                }
                Text("\(plan.count("verified")) content verified · \(plan.count("unverified")) without an indexed hash · \(plan.count("missing")) missing · \(plan.count("conflicts")) conflicts")
                    .font(.caption).foregroundStyle(.secondary)
                if plan.count("unverified")>0 { Text("Originals without an indexed hash are matched by relative path. Confirm that you chose the correct folder.").font(.callout) }
                if plan.count("missing")>0 { Text("Missing originals will use the new paths and remain marked missing.").font(.callout) }
                if plan.count("merge_count")>0 { Text("\(plan.count("merge_count")) destination folders already exist in the catalog. Favorites are combined; existing destination color labels take precedence.").font(.callout) }
                if !plan.text("error").isEmpty { Text(plan.text("error")).foregroundStyle(.red).textSelection(.enabled) }
                if plan.state == "applied" { Label("Folder reconnected",systemImage:"checkmark.circle") }
                if plan.state == "cancelled" { Text("Plan cancelled. Catalog paths are unchanged.") }
                if plan.state == "failed" { Text("Relocation failed. Catalog paths are unchanged.") }
                if !model.items.isEmpty {
                    ScrollView {
                        LazyVStack(alignment:.leading,spacing:10) {
                            ForEach(Array(model.items.enumerated()),id:\.offset) { _,row in
                                VStack(alignment:.leading) {
                                    Text(row["destination"] as? String ?? "").textSelection(.enabled)
                                    Text((row["error"] as? String).flatMap{$0.isEmpty ? nil:$0} ?? "Original is missing").foregroundStyle(.secondary)
                                }.font(.caption)
                            }
                        }.frame(maxWidth:.infinity,alignment:.leading)
                    }.frame(maxHeight:140)
                }
                if model.total>60 {
                    HStack {
                        Button("Previous") { Task { await model.reload(offset:max(0,model.offset-60)) } }.disabled(model.busy || model.loading || model.offset==0)
                        Text("\(model.offset+1)–\(min(model.offset+60,model.total)) of \(model.total) issues")
                        Button("Next") { Task { await model.reload(offset:model.offset+60) } }.disabled(model.busy || model.loading || model.offset+60>=model.total)
                    }.font(.caption)
                }
            } else if let folder=model.folder { Text(folder.path).textSelection(.enabled) }
            else if !model.loading { Text("No folder relocation has been started. Select a missing folder in the Folders sidebar.") }
            if model.loading { ProgressView("Reading saved plan…") }
            if let error=model.error { Text(error).foregroundStyle(.red).textSelection(.enabled) }
            HStack {
                if model.folder != nil && model.plan?.active != true {
                    Button("Choose Replacement Folder…") { choose() }.disabled(model.busy || model.loading)
                }
                if model.plan?.active == true {
                    Button("Cancel Plan",role:.destructive) { Task { await model.cancel(using:s) } }.disabled(model.cancelling)
                }
                Spacer()
                Button("Refresh Plan") { Task { await model.reload(offset:model.offset) } }.disabled(model.busy || model.loading)
                Button("Close",role:.cancel) { dismiss() }.keyboardShortcut(.cancelAction).disabled(model.busy)
                if model.canScan { Button("Continue Scanning") { Task { await model.scan() } } }
                Button("Reconnect") { Task { await model.apply(using:s) } }.buttonStyle(.borderedProminent).disabled(!model.canApply)
            }
        }.padding(24).frame(width:680)
            .interactiveDismissDisabled(model.busy)
            .task { await model.reload() }
            .onDisappear { model.invalidate() }
    }
    private func choose() {
        let panel=NSOpenPanel();panel.canChooseDirectories=true;panel.canChooseFiles=false;panel.allowsMultipleSelection=false
        panel.prompt="Choose Folder";panel.message="Choose the new location of this missing folder. Files are not moved."
        guard panel.runModal() == .OK,let path=panel.url?.path else { return }
        Task {
            await s.refreshFolders()
            await model.prepare(destination:path,revision:s.folderRevision)
            if model.canScan { await model.scan() }
        }
    }
}
