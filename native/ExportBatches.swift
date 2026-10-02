// Purpose: revision-bound native state and payloads for multi-preset export batches.
// Inputs: bounded preset pages, captured preset settings and explicit queue receipts.
// Outputs: immutable batch requests and paged batch history/detail reads.
// This layer does not change preset options, process pixels, or poll batch history.
import Foundation
import SwiftUI

private func batchRowsEqual(_ lhs:[[String:Any]],_ rhs:[[String:Any]])->Bool {
    NSArray(array:lhs).isEqual(to:rhs)
}

struct ExportBatchPresetSnapshot: Identifiable, Equatable {
    let id: String
    let name: String
    let settings: ExportEffectiveSettings

    init?(_ row: [String: Any]) {
        guard let id=row["id"] as? String,
              let name=row["name"] as? String,
              let raw=row["settings"] as? [String:Any],
              let format=raw["format"] as? String,
              let options=raw["options"] as? [String:Any],
              raw["destination"] != nil else { return nil }
        let destination=raw["destination"] as? String
        if destination == nil && !(raw["destination"] is NSNull) { return nil }
        guard let settings=ExportEffectiveSettings(format:format,options:options,destination:destination) else {
            return nil
        }
        self.id=id;self.name=name;self.settings=settings
    }
}

struct ExportBatchPresetDraft: Identifiable {
    let snapshot: ExportBatchPresetSnapshot
    var destinationOverride=""
    var subfolder: String
    var filenameSuffix: String

    var id: String { snapshot.id }

    init(snapshot: ExportBatchPresetSnapshot) {
        self.snapshot=snapshot
        subfolder=Self.suggestedSubfolder(snapshot.name)
        filenameSuffix=snapshot.name
    }

    var resolvedDestination: String? {
        if !destinationOverride.trimmingCharacters(in:.whitespacesAndNewlines).isEmpty {
            return destinationOverride
        }
        return snapshot.settings.destination
    }

    func submissionEntry(parentMode: Bool) -> [String:Any]? {
        guard validationMessage(parentMode:parentMode)==nil else { return nil }
        if parentMode {
            guard Self.isValidFilenameComponent(subfolder,maximumBytes:255) else { return nil }
            return ["preset_id":snapshot.id,"subfolder":subfolder,"filename_suffix":filenameSuffix]
        }
        guard let destination=resolvedDestination,!destination.isEmpty else { return nil }
        var entry:[String:Any]=["preset_id":snapshot.id,"filename_suffix":filenameSuffix]
        if !destinationOverride.trimmingCharacters(in:.whitespacesAndNewlines).isEmpty {
            entry["destination"]=destination
        }
        return entry
    }

    static func isSingleComponent(_ value: String) -> Bool {
        !value.isEmpty && value != "." && value != ".."
            && !value.contains("/") && !value.contains("\\")
    }

    func validationMessage(parentMode:Bool)->String? {
        guard !filenameSuffix.trimmingCharacters(in:.whitespacesAndNewlines).isEmpty else {
            return "Enter a filename collision suffix."
        }
        guard Self.isValidFilenameComponent(filenameSuffix,maximumBytes:120) else {
            return "Use a path-safe suffix of at most 120 UTF-8 bytes."
        }
        if parentMode && !Self.isValidFilenameComponent(subfolder,maximumBytes:255) {
            return "Use a path-safe subfolder name of at most 255 UTF-8 bytes."
        }
        if !parentMode && (resolvedDestination?.isEmpty != false) {
            return "Choose an export folder for this preset."
        }
        return nil
    }

    static func isValidFilenameComponent(_ value:String,maximumBytes:Int)->Bool {
        guard isSingleComponent(value),let data=value.data(using:.utf8),data.count<=maximumBytes,
              let last=value.last,last != " ",last != "." else { return false }
        let forbidden=CharacterSet(charactersIn:"/\\<>:\"|?*")
        guard value.unicodeScalars.allSatisfy({ !CharacterSet.controlCharacters.contains($0) && !forbidden.contains($0) }) else { return false }
        let device=value.split(separator:".",maxSplits:1,omittingEmptySubsequences:false).first?.uppercased() ?? ""
        let reserved=["CON","PRN","AUX","NUL"] + (1...9).flatMap { ["COM\($0)","LPT\($0)"] }
        return !reserved.contains(device)
    }

    private static func suggestedSubfolder(_ value: String) -> String {
        let safe=value.replacingOccurrences(of:"/",with:"-")
            .replacingOccurrences(of:"\\",with:"-")
            .replacingOccurrences(of:":",with:"-")
            .trimmingCharacters(in:CharacterSet.whitespacesAndNewlines.union(CharacterSet(charactersIn:".")))
        return safe.isEmpty || safe == "." || safe == ".." ? "Export-\(UUID().uuidString.prefix(8))" : safe
    }
}

@MainActor final class ExportBatchPresetPickerModel: ObservableObject {
    @Published private(set) var page: ExportPresetPage?
    @Published var searchText=""
    @Published private(set) var selectedOrder:[String]=[]
    @Published private(set) var capturedRevision:String?
    @Published private(set) var loading=false
    @Published private(set) var loadingSettings=false
    @Published private(set) var stale=false
    @Published var error:String?
    private var listGeneration=0
    private var settingsGeneration=0
    private var pendingSearch=""

    var selectedIDs:Set<String> { Set(selectedOrder) }
    var canContinue:Bool { !stale && !loading && !loadingSettings && !selectedOrder.isEmpty }

    func refresh(offset requestedOffset:Int=0,search requestedSearch:String?=nil) async {
        guard !loading && !loadingSettings && !stale else { return }
        listGeneration+=1
        let token=listGeneration
        let search=requestedSearch ?? searchText
        let offset=max(0,requestedOffset)
        pendingSearch=search;loading=true
        defer { if listGeneration==token { loading=false } }
        do {
            let result=try await Backend.call("list_export_presets",["offset":offset,"search":search])
            guard token==listGeneration,pendingSearch==search else { return }
            guard let next=ExportPresetPage(result,search:search) else {
                error="The export preset list could not be read. Reload before continuing."
                return
            }
            if let capturedRevision,capturedRevision != next.revision {
                stale=true
                error="The export preset library changed. Reload and reselect presets before continuing."
                return
            }
            if capturedRevision == nil { capturedRevision=next.revision }
            page=next;searchText=search;error=nil
        } catch {
            if token==listGeneration { self.error=error.localizedDescription }
        }
    }

    @discardableResult func setSelected(_ id:String,_ selected:Bool)->Bool {
        guard !stale,!loading,!loadingSettings,
              page?.items.contains(where:{$0.id==id})==true else { return false }
        if selected {
            guard !selectedIDs.contains(id) else { return true }
            guard selectedOrder.count<30 else {
                error="Choose up to 30 presets for one batch."
                return false
            }
            selectedOrder.append(id)
        } else {
            selectedOrder.removeAll{$0==id}
        }
        error=nil
        return true
    }

    func clearSelection() {
        guard !loadingSettings else { return }
        selectedOrder=[];error=nil
    }

    func reloadAndClearSelection() async {
        listGeneration+=1;settingsGeneration+=1
        selectedOrder=[];capturedRevision=nil;page=nil;stale=false
        loading=false;loadingSettings=false;error=nil
        await refresh(offset:0,search:searchText)
    }

    func invalidateReads() {
        listGeneration+=1;settingsGeneration+=1
        loading=false;loadingSettings=false
    }

    func markStale(_ message:String) {
        listGeneration+=1;settingsGeneration+=1
        loading=false;loadingSettings=false;stale=true
        error=message
    }

    func captureSelectedSettings() async -> [ExportBatchPresetSnapshot]? {
        guard canContinue,selectedOrder.count<=30,let capturedRevision else { return nil }
        settingsGeneration+=1
        let token=settingsGeneration
        let listToken=listGeneration
        let ids=selectedOrder
        loadingSettings=true
        defer { if settingsGeneration==token { loadingSettings=false } }
        do {
            let result=try await Backend.call("get_export_presets",[
                "preset_ids":ids,"expected_revision":capturedRevision
            ])
            guard token==settingsGeneration,listToken==listGeneration,
                  ids==selectedOrder,self.capturedRevision==capturedRevision else { return nil }
            guard result["revision"] as? String==capturedRevision else {
                stale=true
                error="The export preset library changed. Reload and reselect presets before continuing."
                return nil
            }
            let rows=(result["presets"] as? [[String:Any]] ?? []).compactMap(ExportBatchPresetSnapshot.init)
            guard rows.count==ids.count,Set(rows.map(\.id))==Set(ids) else {
                error="One or more selected presets could not be captured. Reload and reselect them."
                return nil
            }
            let byID=Dictionary(uniqueKeysWithValues:rows.map{($0.id,$0)})
            error=nil
            return ids.compactMap{byID[$0]}
        } catch {
            if token==settingsGeneration {
                let message=error.localizedDescription
                if message.localizedCaseInsensitiveContains("changed") {
                    stale=true
                    self.error="The export preset library changed. Reload and reselect presets before continuing."
                } else { self.error=message }
            }
            return nil
        }
    }
}

struct ExportBatchPresetSubmission {
    let expectedRevision:String
    let entries:[ExportBatchPresetDraft]
    let parentDestination:String?

    var payloadPresets:[[String:Any]]? {
        let entries=entries.compactMap{$0.submissionEntry(parentMode:parentDestination != nil)}
        return entries.count==self.entries.count ? entries:nil
    }
}

enum ExportBatchSubmissionResult {
    case accepted(String)
    case rejected(String)
    case uncertain(String)
}

struct ExportBatchSummary: Identifiable, Equatable {
    let id:String
    let created:Double
    let photoCount:Int
    let presetCount:Int
    let queued:Int
    let revision:String
    let destinationMode:String
    let counts:[String:Int]
    var createdLabel:String {
        DateFormatter.localizedString(from:Date(timeIntervalSince1970:created),dateStyle:.medium,timeStyle:.short)
    }

    init?(_ row:[String:Any]) {
        guard let id=row["batch_id"] as? String,!id.isEmpty,
              let created=(row["created"] as? NSNumber)?.doubleValue ?? row["created"] as? Double,
              let photoCount=row["photo_count"] as? Int,
              let presetCount=row["preset_count"] as? Int,
              let queued=row["queued"] as? Int,
              let revision=row["revision"] as? String,
              let destinationMode=row["destination_mode"] as? String else { return nil }
        self.id=id;self.created=created;self.photoCount=photoCount;self.presetCount=presetCount
        self.queued=queued;self.revision=revision;self.destinationMode=destinationMode
        counts=Self.intMap(row["counts"] as? [String:Any] ?? [:])
    }

    static func intMap(_ raw:[String:Any])->[String:Int] {
        raw.compactMapValues { ($0 as? NSNumber)?.intValue ?? $0 as? Int }
    }
}

struct ExportBatchListPage: Equatable {
    let batches:[ExportBatchSummary]
    let total:Int
    let offset:Int
    let pageSize:Int

    init?(_ result:[String:Any]) {
        guard let total=result["total"] as? Int,
              let offset=result["offset"] as? Int,
              let pageSize=result["page_size"] as? Int,
              let rows=result["batches"] as? [[String:Any]] else { return nil }
        batches=rows.compactMap(ExportBatchSummary.init)
        self.total=total;self.offset=offset;self.pageSize=pageSize
    }
}

struct ExportBatchReceiptPage: Equatable {
    let batch:ExportBatchSummary
    let parentDestination:String?
    let presets:[[String:Any]]
    let jobs:[[String:Any]]
    let total:Int
    let offset:Int
    let pageSize:Int
    let counts:[String:Int]

    init?(_ result:[String:Any],expectedBatchID:String) {
        guard let rawBatch=result["batch"] as? [String:Any],
              let batch=ExportBatchSummary(rawBatch),batch.id==expectedBatchID,
              let presets=result["presets"] as? [[String:Any]],
              let jobs=result["jobs"] as? [[String:Any]],
              let total=result["total"] as? Int,
              let offset=result["offset"] as? Int,
              let pageSize=result["page_size"] as? Int,
              let rawCounts=result["counts"] as? [String:Any] else { return nil }
        self.batch=batch;parentDestination=rawBatch["parent_destination"] as? String
        self.presets=presets;self.jobs=jobs;self.total=total;self.offset=offset;self.pageSize=pageSize
        counts=ExportBatchSummary.intMap(rawCounts)
    }

    static func == (lhs:ExportBatchReceiptPage,rhs:ExportBatchReceiptPage)->Bool {
        lhs.batch==rhs.batch && lhs.parentDestination==rhs.parentDestination
            && batchRowsEqual(lhs.presets,rhs.presets) && batchRowsEqual(lhs.jobs,rhs.jobs)
            && lhs.total==rhs.total && lhs.offset==rhs.offset && lhs.pageSize==rhs.pageSize
            && lhs.counts==rhs.counts
    }
}

@MainActor final class ExportBatchHistoryModel: ObservableObject {
    typealias Command = @MainActor (String,[String:Any]) async throws -> [String:Any]
    @Published private(set) var page:ExportBatchListPage?
    @Published private(set) var receipt:ExportBatchReceiptPage?
    @Published private(set) var selectedBatchID:String?
    @Published private(set) var listLoading=false
    @Published private(set) var detailLoading=false
    @Published private(set) var actionBusy=false
    @Published var error:String?
    private var listGeneration=0
    private var detailGeneration=0
    private var sessionGeneration=0
    private let command:Command

    init(command:Command?=nil) {
        self.command=command ?? { method,params in try await Backend.call(method,params) }
    }

    @discardableResult func refresh(offset requestedOffset:Int?=nil,showActivity:Bool=true) async -> Bool {
        guard showActivity || (!listLoading && !actionBusy) else { return false }
        listGeneration+=1
        let token=listGeneration
        let offset=max(0,requestedOffset ?? page?.offset ?? 0)
        if showActivity { listLoading=true }
        defer { if token==listGeneration && showActivity { listLoading=false } }
        do {
            let result=try await command("list_export_batches",["offset":offset])
            guard token==listGeneration else { return false }
            guard let next=ExportBatchListPage(result) else {
                setError("The export batch list was incomplete. Reload to try again.")
                return false
            }
            if page != next { page=next }
            setError(nil)
            return true
        } catch {
            if token==listGeneration { setError(error.localizedDescription) }
            return false
        }
    }

    func open(_ batchID:String,offset:Int=0) async {
        sessionGeneration+=1
        selectedBatchID=batchID
        await loadDetail(batchID,offset:offset)
    }

    func showList() {
        sessionGeneration+=1
        detailGeneration+=1;selectedBatchID=nil;receipt=nil;detailLoading=false;setError(nil)
    }

    @discardableResult func loadDetail(_ batchID:String?=nil,offset:Int?=nil,showActivity:Bool=true) async -> Bool {
        guard showActivity || (!detailLoading && !actionBusy) else { return false }
        guard let id=batchID ?? selectedBatchID else { return false }
        detailGeneration+=1
        let token=detailGeneration
        let requestedOffset=max(0,offset ?? receipt?.offset ?? 0)
        if showActivity { detailLoading=true }
        defer { if token==detailGeneration && showActivity { detailLoading=false } }
        do {
            let result=try await command("get_export_batch",["batch_id":id,"offset":requestedOffset])
            guard token==detailGeneration,selectedBatchID==id else { return false }
            guard let next=ExportBatchReceiptPage(result,expectedBatchID:id) else {
                setError("The batch receipt was incomplete. Reload to try again.")
                return false
            }
            if receipt != next { receipt=next }
            setError(nil)
            return true
        } catch {
            if token==detailGeneration { setError(error.localizedDescription) }
            return false
        }
    }

    func perform(_ action:String,on batchID:String) async -> Bool {
        guard !actionBusy,selectedBatchID==batchID,
              ["cancel","retry","retry_cancelled"].contains(action) else { return false }
        let session=sessionGeneration
        actionBusy=true
        defer { actionBusy=false }
        do {
            _=try await command("queue_control",["action":action,"batch_id":batchID])
            guard session==sessionGeneration,selectedBatchID==batchID else { return true }
            let detailLoaded=await loadDetail(batchID,offset:receipt?.offset ?? 0)
            guard session==sessionGeneration,selectedBatchID==batchID else { return true }
            guard detailLoaded else { return false }
            let listLoaded=await refresh(offset:page?.offset ?? 0)
            guard session==sessionGeneration,selectedBatchID==batchID else { return true }
            guard listLoaded else { return false }
            setError(nil)
            return true
        } catch {
            if session==sessionGeneration { setError(error.localizedDescription) }
            return false
        }
    }

    func refreshVisibleQuietly() async {
        if selectedBatchID != nil { await loadDetail(showActivity:false) }
        else { await refresh(showActivity:false) }
    }

    private func setError(_ value:String?) {
        if error != value { error=value }
    }

    func invalidateReads() {
        sessionGeneration+=1
        listGeneration+=1;detailGeneration+=1
        listLoading=false;detailLoading=false
    }
}
