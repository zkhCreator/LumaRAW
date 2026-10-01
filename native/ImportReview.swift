// Purpose: captured Add import reviews and bounded preview scheduling for Mac.
// Inputs: explicit source choices, service plans/pages and client generations.
// Outputs: checked selections, resumable scans and one explicit apply command.
// No filesystem scanning, SQL, image processing or automatic mutation replay.
// Closing preserves a plan; an uncertain apply is read back before any next action.
import AppKit
import Foundation

struct ImportPlan {
    let values: [String:Any]
    var id: Int { number("id") }
    var revision: Int { number("revision") }
    var state: String { text("state") }
    var active: Bool { ["planning","scanning","ready","verifying","interrupted"].contains(state) }
    var ready: Bool { state == "ready" }
    var skipDuplicates: Bool { number("skip_duplicates") != 0 }
    func number(_ key: String) -> Int { values[key] as? Int ?? 0 }
    func text(_ key: String) -> String { values[key] as? String ?? "" }
    func count(_ key: String) -> Int { (values["counts"] as? [String:Int])?[key] ?? 0 }
}

struct ImportItem: Identifiable {
    let id: Int
    let path: String
    let name: String
    let state: String
    let selected: Bool
    let eligible: Bool
    let bytes: Int64
    let error: String
    let hasNotes: Bool
    init?(_ row: [String:Any]) {
        guard let id=row["id"] as? Int,let path=row["path"] as? String,let name=row["name"] as? String,
              let state=row["state"] as? String else { return nil }
        self.id=id;self.path=path;self.name=name;self.state=state
        selected=(row["selected"] as? Int ?? 0) != 0;eligible=row["eligible"] as? Bool ?? false
        bytes=(row["bytes"] as? NSNumber)?.int64Value ?? 0
        error=row["error"] as? String ?? "";hasNotes=(row["has_notes"] as? Int ?? 0) != 0
    }
}

@MainActor final class ImportReviewModel: ObservableObject,Identifiable {
    let id=UUID()
    @Published var sources: [String]
    @Published var includeSubfolders=true
    @Published var initialSkipDuplicates=true
    @Published var plan: ImportPlan?
    @Published var items: [ImportItem]=[]
    @Published var kind="all"
    @Published var sort="name"
    @Published var descending=false
    @Published var offset=0
    @Published var total=0
    @Published var busy=false
    @Published var loading=false
    @Published var cancelling=false
    @Published var error: String?
    @Published var images: [Int:NSImage]=[:]
    @Published var previewErrors: [Int:String]=[:]
    @Published var focused: Int?
    @Published var loupe=false
    @Published var detail: NSImage?
    @Published var detailLoading=false
    @Published var detailError: String?
    @Published var processingEditor: ImportProcessingEditor?
    private let previewClient=UUID().uuidString
    private let detailClient=UUID().uuidString
    private var previewGeneration=0
    private var detailGeneration=0
    private var readGeneration=0
    private var previewTask: Task<Void,Never>?
    private var detailTask: Task<Void,Never>?
    private var closed=false
    private var delivered: Set<Int>=[]
    var onApplied: ((Int)->Void)?
    var canScan: Bool { !busy && !loading && (plan == nil || plan?.active == false || ["planning","interrupted"].contains(plan?.state ?? "")) }
    var canApply: Bool { !busy && !loading && plan?.ready == true && (plan?.number("selected_count") ?? 0)>0 }
    init(sources: [String]=[]) { self.sources=sources }

    func receive(_ result: [String:Any]) {
        guard !closed,let values=result["plan"] as? [String:Any] else { return }
        let next=ImportPlan(values:values)
        if let previous=plan,previous.id == next.id {
            guard next.revision>=previous.revision else { return }
            if next.revision == previous.revision && next.number("checked")<previous.number("checked") { return }
            let oldKey=(previous.values["processing"] as? [String:Any])?["develop_key"] as? String
            let newKey=(next.values["processing"] as? [String:Any])?["develop_key"] as? String
            if oldKey != newKey { images=[:];detail=nil }
        }
        plan=next;items=(result["items"] as? [[String:Any]] ?? []).compactMap(ImportItem.init)
        total=result["total"] as? Int ?? 0;offset=result["offset"] as? Int ?? 0
        if !items.contains(where:{$0.id == focused}) { focused=items.first?.id }
        if next.state == "applied",delivered.insert(next.id).inserted { onApplied?(next.number("imported")) }
    }

    func load(initial: Bool=false) async {
        readGeneration+=1;let token=readGeneration;loading=true
        defer { if token == readGeneration { loading=false } }
        var params: [String:Any]=["kind":kind,"offset":offset,"sort":sort,"descending":descending]
        if let plan { params["plan_id"]=plan.id }
        do {
            let result=try await Backend.call("get_import",params)
            guard token == readGeneration,!closed else { return }
            if initial,let values=result["plan"] as? [String:Any],!ImportPlan(values:values).active {
                // A previous completed import is history, not this newly opened dialog.
                return
            }
            receive(result);refreshPreviews()
            if initial,plan?.active == true,!sources.isEmpty {
                error="An unfinished import review is open. Finish or cancel it before scanning the newly selected sources."
            }
        } catch { if token == readGeneration,!closed { self.error=error.localizedDescription } }
    }

    func scan() async {
        guard canScan else { return }
        busy=true;error=nil;stopPreviews();readGeneration+=1
        defer { busy=false }
        do {
            if plan?.active != true {
                guard !sources.isEmpty else { throw EngineFailure(message:"Choose photos or folders first") }
                kind="all";offset=0
                receive(try await Backend.call("prepare_import",["paths":sources,"include_subfolders":includeSubfolders,"skip_duplicates":initialSkipDuplicates]))
            }
            while !closed,let captured=plan,["planning","interrupted"].contains(captured.state) {
                receive(try await Backend.call("scan_import",["plan_id":captured.id,"expected_revision":captured.revision]))
            }
            if !closed { await load() }
        } catch { self.error=error.localizedDescription;if !closed { await load() } }
    }

    func select(_ selected: Bool,ids: [Int]?=nil) async {
        guard !busy,!loading,let captured=plan,captured.ready else { return }
        if ids == nil,(["existing","error"].contains(kind) || kind == "selected" && selected) { return }
        var params: [String:Any]=["plan_id":captured.id,"expected_revision":captured.revision,"selected":selected]
        if let ids { params["item_ids"]=ids }
        else if ["new","duplicate"].contains(kind) { params["kind"]=kind }
        await mutate("select_import_items",params)
    }

    func skipDuplicates(_ value: Bool) async {
        guard !busy,!loading,let captured=plan,captured.ready else { return }
        await mutate("set_import_options",["plan_id":captured.id,"expected_revision":captured.revision,"skip_duplicates":value])
    }

    private func mutate(_ method: String,_ params: [String:Any]) async {
        busy=true;error=nil;readGeneration+=1;stopPreviews()
        defer { busy=false }
        do { receive(try await Backend.call(method,params));await load() }
        catch { self.error=error.localizedDescription }
    }

    func apply() async {
        guard canApply,let captured=plan else { return }
        await mutate("apply_import",["plan_id":captured.id,"expected_revision":captured.revision])
        // If the reply was lost, inspect the receipt. Do not retry apply.
        if error != nil,!closed { await load() }
    }

    func cancel() async {
        guard !cancelling,let captured=plan,captured.active else { return }
        cancelling=true;stopPreviews()
        defer { cancelling=false }
        do { receive(try await Backend.call("cancel_import",["plan_id":captured.id])) }
        catch { self.error=error.localizedDescription }
    }

    func browse(kind: String?=nil,offset: Int=0) async {
        guard !busy else { return }
        if let kind { self.kind=kind };self.offset=offset
        await load()
    }

    func refreshPreviews() {
        previewGeneration+=1;let token=previewGeneration;previewTask?.cancel()
        guard let captured=plan,captured.ready,!closed else { images=[:];return }
        let targets=items.filter{!["pending","error"].contains($0.state)}
        images=images.filter { key,_ in targets.contains(where:{$0.id == key}) };previewErrors=[:]
        previewTask=Task { [weak self] in
            guard let self else { return }
            _=try? await Backend.call("cancel_preview",["client_id":previewClient,"generation":token])
            for item in targets {
                guard !Task.isCancelled,!closed,token == previewGeneration else { return }
                if images[item.id] != nil { continue }
                do {
                    let result=try await Backend.call("preview_import_item",["plan_id":captured.id,"item_id":item.id,
                        "expected_revision":captured.revision,"client_id":previewClient,"generation":token])
                    guard !Task.isCancelled,!closed,token == previewGeneration else { return }
                    if result["item_id"] as? Int == item.id,result["source"] as? String == item.path,
                       let path=result["thumbnail"] as? String {
                        let loaded=await PreviewImageLoader.load(path)
                        guard !Task.isCancelled,!closed,token==previewGeneration else {return}
                        if let image=loaded {images[item.id]=image}
                    }
                } catch { if token == previewGeneration,!closed { previewErrors[item.id]=error.localizedDescription } }
            }
        }
        refreshDetail()
    }

    func focus(_ item: ImportItem,detail: Bool=false) {
        focused=item.id;if detail { loupe=true };refreshDetail()
    }

    func refreshDetail() {
        detailGeneration+=1;let token=detailGeneration;detailTask?.cancel();detail=nil;detailError=nil;detailLoading=false
        let captured=plan,item=items.first{$0.id == focused}
        detailTask=Task { [weak self] in
            guard let self else { return }
            _=try? await Backend.call("cancel_preview",["client_id":detailClient,"generation":token])
            guard loupe,!closed,let captured,captured.ready,let item,!["pending","error"].contains(item.state) else { return }
            detailLoading=true
            defer { if token == detailGeneration { detailLoading=false } }
            do {
                let result=try await Backend.call("preview_import_item",["plan_id":captured.id,"item_id":item.id,
                    "expected_revision":captured.revision,"client_id":detailClient,"generation":token,"detail":true])
                guard !Task.isCancelled,!closed,token == detailGeneration else { return }
                let loaded=await PreviewImageLoader.load(result["preview"] as? String)
                guard !Task.isCancelled,!closed,token==detailGeneration else {return}
                self.detail=loaded
            } catch { if token == detailGeneration,!closed { detailError=error.localizedDescription } }
        }
    }

    private func stopPreviews() {
        previewGeneration+=1;detailGeneration+=1;previewTask?.cancel();detailTask?.cancel()
        let preview=previewGeneration,detail=detailGeneration
        Task {
            _=try? await Backend.call("cancel_preview",["client_id":previewClient,"generation":preview])
            _=try? await Backend.call("cancel_preview",["client_id":detailClient,"generation":detail])
        }
    }

    func invalidate() { closed=true;readGeneration+=1;stopPreviews() }
}

extension Store {
    func reviewImport(_ paths: [String]=[]) async {
        guard await flushEdits() else { return }
        if let current=importReview {
            guard !paths.isEmpty else { return }
            guard current.plan?.active != true,!current.busy else {
                current.error="Finish or cancel this import review before adding sources";return
            }
            for path in paths where !current.sources.contains(path) { current.sources.append(path) }
            return
        }
        let model=ImportReviewModel(sources:paths)
        model.onApplied={ [weak self] count in
            guard let self else { return }
            self.message="Imported \(count) photos"
            Task { await self.finishImport(count) }
        }
        importReview=model
    }
    func reviewImportProviders(_ providers: [NSItemProvider]) async {
        var paths: [String]=[]
        for provider in providers {
            let value: String?=await withCheckedContinuation { continuation in
                provider.loadItem(forTypeIdentifier:"public.file-url",options:nil) { item,_ in
                    let url=(item as? URL) ?? (item as? Data).flatMap { URL(dataRepresentation:$0,relativeTo:nil) }
                    continuation.resume(returning:url?.path)
                }
            }
            if let value { paths.append(value) }
        }
        if !paths.isEmpty { await reviewImport(paths) }
    }
}
