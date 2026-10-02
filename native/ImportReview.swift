// Purpose: captured Add/Copy import reviews and bounded preview scheduling for Mac.
// Inputs: explicit source choices, service plans/pages and client generations.
// Outputs: checked selections, resumable scans and one explicit apply command.
// No filesystem scanning, SQL, image processing or automatic mutation replay.
// Closing preserves a plan; an uncertain apply is read back before any next action.
// Optional second copies retain original state independently of import naming.
// Preset choices are revision-bound; explicit rescans atomically replace ready plans.
// Counter-dependent naming stays bound to the sequence revision captured by the plan.
// Date-folder format is a separate captured Copy option; legacy presets default to year/date.
// Focused Loupe requests are generation-bound, with Import-local Fit and 1:1 viewport state.
import AppKit
import Foundation

struct ImportPlan {
    let values: [String:Any]
    var id: Int { number("id") }
    var revision: Int { number("revision") }
    var state: String { text("state") }
    var active: Bool { ["planning","scanning","ready","verifying","interrupted"].contains(state) }
    var ready: Bool { state == "ready" }
    var isCopy: Bool { text("mode") == "copy" }
    var copy: [String:Any] { values["copy"] as? [String:Any] ?? [:] }
    var backup: [String:Any]? { copy["backup"] as? [String:Any] }
    var sequence: [String:Any]? { values["sequence"] as? [String:Any] }
    var primaryCopied: Int { (copy["copied"] as? Int ?? 0)-(backup?["copied"] as? Int ?? 0) }
    var primaryTransferCount: Int { (copy["transfer_count"] as? Int ?? 0)-(backup?["transfer_count"] as? Int ?? 0) }
    var interruptedCopy: Bool { isCopy && state == "interrupted" && ["copying","copy_preparing"].contains(text("phase")) }
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
    let destination: String
    let secondDestination: String
    init?(_ row: [String:Any]) {
        guard let id=row["id"] as? Int,let path=row["path"] as? String,let name=row["name"] as? String,
              let state=row["state"] as? String else { return nil }
        self.id=id;self.path=path;self.name=name;self.state=state
        selected=(row["selected"] as? Int ?? 0) != 0;eligible=row["eligible"] as? Bool ?? false
        bytes=(row["bytes"] as? NSNumber)?.int64Value ?? 0
        error=[row["error"] as? String ?? "",row["naming_error"] as? String ?? "",row["backup_error"] as? String ?? ""].filter{!$0.isEmpty}.joined(separator:" · ")
        hasNotes=(row["has_notes"] as? Int ?? 0) != 0
        destination=row["destination"] as? String ?? ""
        secondDestination=row["second_destination"] as? String ?? ""
    }
}

@MainActor final class ImportReviewModel: ObservableObject,Identifiable {
    let id=UUID()
    @Published var sources: [String]
    @Published var includeSubfolders=true
    @Published var initialSkipDuplicates=true
    @Published var mode="add"
    @Published var destination=""
    @Published var organization="flat"
    @Published var dateFormat="year_date"
    @Published var subfolder=""
    @Published var makeSecondCopy=false
    @Published var secondCopyDestination=""
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
    @Published var loupeViewport=ImportLoupeViewport()
    @Published var detailFrame: ImportLoupeFrame?
    @Published var detailLoading=false
    @Published var detailError: String?
    @Published var processingEditor: ImportProcessingEditor?
    @Published var namingEditor: ImportNamingEditor?
    @Published var presetEditor: ImportPresetEditor?
    @Published var presetChoice: [String:Any]?
    @Published var presetName=""
    private let previewClient=UUID().uuidString
    private let detailClient=UUID().uuidString
    private var previewGeneration=0
    private var detailGeneration=0
    private var loupeWidthPixels=0
    private var loupeHeightPixels=0
    private var loupeDisplayScale=1.0
    private var loupeResizeInvalidated=false
    private var readGeneration=0
    private var previewTask: Task<Void,Never>?
    private var detailTask: Task<Void,Never>?
    private var closed=false
    private var delivered: Set<Int>=[]
    private let detailCall: (String,[String:Any]) async throws -> [String:Any]
    var onApplied: ((Int)->Void)?
    var canScan: Bool { !busy && !loading && plan?.interruptedCopy != true && (plan == nil || plan?.active == false || ["planning","interrupted"].contains(plan?.state ?? "")) }
    var canApply: Bool { !busy && !loading && plan?.ready == true && (plan?.number("selected_count") ?? 0)>0 }
    var canResumeCopy: Bool { !busy && !loading && plan?.interruptedCopy == true }
    init(sources: [String]=[],detailCall: @escaping (String,[String:Any]) async throws -> [String:Any] = Backend.call) {
        self.sources=sources;self.detailCall=detailCall
    }

    func receive(_ result: [String:Any]) {
        guard !closed,let values=result["plan"] as? [String:Any] else { return }
        let next=ImportPlan(values:values)
        let previousFocus=focused
        var discardDetail=false
        if let previous=plan,previous.id == next.id {
            guard next.revision>=previous.revision else { return }
            if next.revision == previous.revision && next.number("checked")<previous.number("checked") { return }
            let oldKey=(previous.values["processing"] as? [String:Any])?["develop_key"] as? String
            let newKey=(next.values["processing"] as? [String:Any])?["develop_key"] as? String
            if oldKey != newKey { images=[:];discardDetail=true }
            if next.revision != previous.revision { discardDetail=true }
        } else if plan?.id != next.id || plan?.revision != next.revision {
            discardDetail=true
        }
        plan=next;items=(result["items"] as? [[String:Any]] ?? []).compactMap(ImportItem.init)
        total=result["total"] as? Int ?? 0;offset=result["offset"] as? Int ?? 0
        if !items.contains(where:{$0.id == focused}) { focused=items.first?.id }
        if previousFocus != focused {
            loupeViewport=ImportLoupeViewport()
            discardDetail=true
        }
        if !next.ready { discardDetail=true }
        if discardDetail { discardLoupeFrame() }
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
                var params: [String:Any]=["paths":sources,"include_subfolders":includeSubfolders,"skip_duplicates":initialSkipDuplicates,"mode":mode]
                if let presetChoice { params["preset"]=presetChoice }
                if mode == "copy" {
                    guard !destination.isEmpty else { throw EngineFailure(message:"Choose a Copy destination") }
                    params["destination"]=destination;params["organization"]=organization
                    params["date_format"]=dateFormat;params["subfolder"]=subfolder
                    params["second_copy_destination"]=NSNull()
                    if makeSecondCopy {
                        guard !secondCopyDestination.isEmpty else { throw EngineFailure(message:"Choose a second-copy destination") }
                        params["second_copy_destination"]=secondCopyDestination
                    }
                }
                receive(try await Backend.call("prepare_import",params))
            }
            while !closed,let captured=plan,["planning","interrupted"].contains(captured.state) {
                receive(try await Backend.call("scan_import",["plan_id":captured.id,"expected_revision":captured.revision]))
            }
            if !closed { await load() }
        } catch { self.error=error.localizedDescription;if !closed { await load() } }
    }

    func openPresets() {
        guard !busy,!loading,plan?.active != true || plan?.ready == true else {return}
        let editor=ImportPresetEditor(plan:plan)
        editor.onUse={ [weak self,weak editor] value in
            guard let self else {return false}
            let result=await self.usePreset(value)
            if !result {editor?.error=self.error}
            return result
        }
        presetEditor=editor
    }

    func usePreset(_ value:[String:Any]) async -> Bool {
        guard !busy,!loading,!closed,let key=value["id"] as? String,let revision=value["revision"] as? Int else {return false}
        let choice: [String:Any]=["preset_id":key,"expected_revision":revision]
        error=nil
        if let captured=plan,captured.active {
            guard captured.ready else {return false}
            busy=true;readGeneration+=1;stopPreviews()
            do {
                receive(try await Backend.call("restart_import_with_preset",["plan_id":captured.id,"expected_revision":captured.revision,"preset":choice]))
                guard !closed else {busy=false;return false}
                kind="all";offset=0;busy=false
                // Dismiss the preset sheet immediately so the parent exposes Cancel.
                Task { [weak self] in await self?.scan() }
                return true
            } catch {
                self.error=error.localizedDescription;busy=false
                // Inspect an uncertain receipt; never automatically repeat a restart.
                if let latest=try? await Backend.call("get_import") {receive(latest)}
                await load();return false
            }
        }
        guard let options=value["options"] as? [String:Any] else {return false}
        mode=options["mode"] as? String ?? "add";includeSubfolders=options["include_subfolders"] as? Bool ?? true
        initialSkipDuplicates=options["skip_duplicates"] as? Bool ?? true
        destination=options["destination"] as? String ?? "";organization=options["organization"] as? String ?? "flat"
        dateFormat=options["date_format"] as? String ?? "year_date"
        subfolder=options["subfolder"] as? String ?? "";secondCopyDestination=options["second_copy_destination"] as? String ?? ""
        makeSecondCopy = !secondCopyDestination.isEmpty;presetChoice=choice;presetName=value["name"] as? String ?? ""
        return true
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

    func setBackup(_ destination: String?) async {
        guard !busy,!loading,let captured=plan,captured.ready,captured.isCopy else { return }
        await mutate("set_import_backup",["plan_id":captured.id,"expected_revision":captured.revision,
            "destination":destination.map{$0 as Any} ?? NSNull()])
    }

    private func mutate(_ method: String,_ params: [String:Any]) async {
        busy=true;error=nil;readGeneration+=1;stopPreviews()
        let poll: Task<Void,Never>? = (plan?.isCopy == true && ["apply_import","resume_import_copy"].contains(method)) ? Task { [weak self] in
            while !Task.isCancelled {
                do { try await Task.sleep(nanoseconds:500_000_000) } catch { return }
                guard let self,!closed,let captured=plan else { return }
                if let result=try? await Backend.call("get_import",["plan_id":captured.id]),!Task.isCancelled { receive(result) }
            }
        } : nil
        defer { poll?.cancel();busy=false }
        do { receive(try await Backend.call(method,params));await load() }
        catch { self.error=error.localizedDescription }
    }

    func apply() async {
        guard canApply,let captured=plan else { return }
        var params: [String:Any]=["plan_id":captured.id,"expected_revision":captured.revision]
        if let sequence=captured.sequence,let revision=sequence["revision"] as? Int {
            params["expected_sequence_revision"]=revision
        }
        await mutate("apply_import",params)
        // If the reply was lost, inspect the receipt. Do not retry apply.
        if error != nil,!closed { await load() }
    }

    func resumeCopy() async {
        guard canResumeCopy,let captured=plan else { return }
        await mutate("resume_import_copy",["plan_id":captured.id,"expected_revision":captured.revision])
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
        if focused != item.id { loupeViewport=ImportLoupeViewport() }
        focused=item.id;if detail { loupe=true };refreshDetail()
    }

    var currentLoupeRequest: ImportLoupeRequest? {
        guard let plan,let item=items.first(where:{$0.id == focused}),plan.ready,
              !["pending","error"].contains(item.state) else { return nil }
        let oneToOne=loupeViewport.zoom == 1
        if oneToOne && (loupeWidthPixels<=0 || loupeHeightPixels<=0) { return nil }
        return ImportLoupeRequest(planID:plan.id,revision:plan.revision,itemID:item.id,source:item.path,
            viewport:loupeViewport,width:oneToOne ? loupeWidthPixels:0,height:oneToOne ? loupeHeightPixels:0)
    }

    var currentLoupeFrame: ImportLoupeFrame? {
        guard let request=currentLoupeRequest,let frame=detailFrame,frame.request == request else { return nil }
        return frame
    }

    var loupePixelSize: (width:Int,height:Int) { (loupeWidthPixels,loupeHeightPixels) }

    func setLoupeViewportSize(_ size: CGSize,displayScale: Double) {
        let scale=displayScale.isFinite && displayScale>0 ? displayScale:1
        let width=max(1,min(2048,Int((Double(size.width)*scale).rounded())))
        let height=max(1,min(1536,Int((Double(size.height)*scale).rounded())))
        let pixelSizeChanged=width != loupeWidthPixels || height != loupeHeightPixels
        if !pixelSizeChanged && scale == loupeDisplayScale {
            if loupeResizeInvalidated { loupeResizeInvalidated=false;if loupeViewport.zoom == 1 { refreshDetail() } }
            return
        }
        loupeWidthPixels=width;loupeHeightPixels=height;loupeDisplayScale=scale
        let needsRender=loupeResizeInvalidated
        loupeResizeInvalidated=false
        if (pixelSizeChanged || needsRender) && loupeViewport.zoom == 1 { refreshDetail() }
    }

    func invalidateLoupeViewportForResize() {
        guard loupeViewport.zoom == 1 else { return }
        detailGeneration+=1;let token=detailGeneration;detailTask?.cancel();detailTask=nil
        detailFrame=nil;detailError=nil;detailLoading=false
        guard !loupeResizeInvalidated else { return }
        loupeResizeInvalidated=true
        Task { _=try? await detailCall("cancel_preview",["client_id":detailClient,"generation":token]) }
    }

    func setLoupeZoom(_ zoom: Double) {
        let value=zoom >= 0.5 ? 1.0:0.0
        guard value != loupeViewport.zoom else { return }
        loupeViewport.zoom=value
        refreshDetail()
    }

    func finishLoupePan(_ translation: CGSize,displayScale: Double,from request: ImportLoupeRequest) {
        guard request.viewport.zoom == 1,request == currentLoupeRequest,
              let frame=detailFrame,frame.request == request,let roi=frame.roi,
              frame.fullWidth>0,frame.fullHeight>0 else { return }
        let scale=displayScale.isFinite && displayScale>0 ? displayScale:loupeDisplayScale
        let x=(roi.x+roi.width/2)/Double(frame.fullWidth)
            - Double(translation.width)*scale/(request.viewport.zoom*Double(frame.fullWidth))
        let y=(roi.y+roi.height/2)/Double(frame.fullHeight)
            - Double(translation.height)*scale/(request.viewport.zoom*Double(frame.fullHeight))
        loupeViewport.move(
            x:ImportLoupeViewport.clampedCenter(x,viewportPixels:request.width,fullPixels:frame.fullWidth),
            y:ImportLoupeViewport.clampedCenter(y,viewportPixels:request.height,fullPixels:frame.fullHeight))
        refreshDetail()
    }

    func refreshDetail() {
        loupeResizeInvalidated=false
        detailGeneration+=1;let token=detailGeneration;detailTask?.cancel();detailError=nil;detailLoading=false
        detailFrame=nil
        let captured=plan,item=items.first{$0.id == focused},request=currentLoupeRequest
        detailTask=Task { [weak self] in
            guard let self else { return }
            _=try? await detailCall("cancel_preview",["client_id":detailClient,"generation":token])
            guard loupe,!closed,let captured,captured.ready,let item,let request,
                  request == currentLoupeRequest else { return }
            detailLoading=true
            defer { if token == detailGeneration { detailLoading=false } }
            do {
                var params=request.params
                params["client_id"]=detailClient;params["generation"]=token
                let result=try await detailCall("preview_import_item",params)
                guard !Task.isCancelled,!closed,token == detailGeneration else { return }
                guard result["plan_id"] as? Int == captured.id,result["item_id"] as? Int == item.id,
                      result["revision"] as? Int == captured.revision,result["source"] as? String == item.path,
                      request == currentLoupeRequest else {
                    throw EngineFailure(message:"The import preview no longer matches this review")
                }
                let loaded=await PreviewImageLoader.load(result["preview"] as? String)
                guard !Task.isCancelled,!closed,token==detailGeneration else {return}
                guard request == currentLoupeRequest,let loaded,
                      let frame=ImportLoupeFrame(result:result,image:loaded,request:request) else {
                    throw EngineFailure(message:"The import preview frame is invalid")
                }
                detailFrame=frame
            } catch { if token == detailGeneration,!closed { detailError=error.localizedDescription } }
        }
    }

    private func discardLoupeFrame() {
        loupeResizeInvalidated=false
        detailGeneration+=1;let token=detailGeneration;detailTask?.cancel();detailTask=nil
        detailFrame=nil;detailError=nil;detailLoading=false
        Task { _=try? await detailCall("cancel_preview",["client_id":detailClient,"generation":token]) }
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
