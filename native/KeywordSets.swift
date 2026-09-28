// Purpose: nine-slot keyword preset state and captured photo application.
// Inputs: bounded portable preset pages, transient drafts and metadata revisions.
// Outputs: explicit save/select/delete/storage actions and additive assignments.
// No SQL or platform storage paths. Drafts survive refresh of the same selection;
// changing preset or storage discards them. Stale writes never retry automatically.
import Foundation

struct KeywordSetName: Identifiable {
    let id: String
    let name: String
}

struct KeywordSetState {
    let revision: String
    let items: [KeywordSetName]
    let selected: KeywordSetName
    let slots: [String]
    let offset: Int
    let total: Int
    let storeWithCatalog: Bool
    init?(_ result: [String:Any]) {
        guard let revision=result["revision"] as? String,
              let selected=result["selected"] as? [String:Any],let id=selected["id"] as? String,
              let name=selected["name"] as? String,let slots=selected["slots"] as? [String],slots.count == 9 else { return nil }
        self.revision=revision;self.selected=KeywordSetName(id:id,name:name);self.slots=slots
        items=(result["sets"] as? [[String:Any]] ?? []).compactMap { row in
            guard let id=row["id"] as? String,let name=row["name"] as? String else { return nil }
            return KeywordSetName(id:id,name:name)
        }
        offset=result["offset"] as? Int ?? 0;total=result["total"] as? Int ?? 0
        storeWithCatalog=result["store_with_catalog"] as? Bool ?? false
    }
}

extension Store {
    var keywordSetSlots: [String] { keywordSetDraft ?? keywordSets?.slots ?? Array(repeating:"",count:9) }

    func adoptKeywordSets(_ result: [String:Any], discardDraft: Bool=false) throws {
        guard let state=KeywordSetState(result) else { throw EngineFailure(message:"Incomplete keyword set response") }
        if discardDraft || state.selected.id != keywordSets?.selected.id || state.storeWithCatalog != keywordSets?.storeWithCatalog {
            keywordSetDraft=nil
            keywordSetDraftRevision=nil
        }
        keywordSets=state
    }

    func refreshKeywordSets(offset: Int?=nil) async {
        guard !keywordSetBusy else { return }
        keywordSetGeneration+=1;let token=keywordSetGeneration
        do {
            let result=try await Backend.call("list_keyword_sets",["offset":offset ?? keywordSets?.offset ?? 0])
            guard token == keywordSetGeneration,!keywordSetBusy else { return }
            try adoptKeywordSets(result)
        } catch { if token == keywordSetGeneration { self.error=error.localizedDescription } }
    }

    func saveKeywordSet(name: String, slots: [String], id: String?, revision: String) async -> Bool {
        guard !keywordSetBusy else { return false }
        keywordSetBusy=true;keywordSetGeneration+=1;defer { keywordSetBusy=false }
        var params: [String:Any]=["name":name,"slots":slots,"expected_revision":revision]
        if let id { params["set_id"]=id }
        do {
            try adoptKeywordSets(await Backend.call("save_keyword_set",params),discardDraft:true)
            return true
        } catch { self.error=error.localizedDescription;return false }
    }

    func keywordSetAction(_ action: String, id: String?=nil, storeWithCatalog: Bool?=nil, revision: String?=nil) async -> Bool {
        guard !keywordSetBusy,let state=keywordSets else { return false }
        keywordSetBusy=true;keywordSetGeneration+=1;defer { keywordSetBusy=false }
        var params: [String:Any]=["action":action,"expected_revision":revision ?? state.revision]
        if let id { params["set_id"]=id }
        if let storeWithCatalog { params["store_with_catalog"]=storeWithCatalog }
        do {
            try adoptKeywordSets(await Backend.call("keyword_set_action",params),discardDraft:true)
            return true
        } catch { self.error=error.localizedDescription;return false }
    }

    func changeKeywordSetDraft(_ slots: [String], revision: String) -> Bool {
        guard let state=keywordSets,state.selected.id != "recent",state.revision == revision,slots.count == 9 else {
            error="Keyword sets changed; reopen the editor"
            return false
        }
        keywordSetDraft=slots.map { $0.trimmingCharacters(in:.whitespacesAndNewlines) }
        keywordSetDraftRevision=revision
        return true
    }

    func canApplyKeywordSlot(_ slot: Int) -> Bool {
        (1...9).contains(slot) && !keywordSetBusy && !keywordBusy && keywordSets != nil &&
            !actionPhotoIDs.isEmpty && !keywordSetSlots[slot-1].isEmpty
    }

    func applyKeywordSlot(_ slot: Int) async {
        guard canApplyKeywordSlot(slot),let state=keywordSets else { return }
        let ids=actionPhotoIDs,targets=photos.filter { ids.contains($0.id) }
        guard targets.count == ids.count else { return }
        keywordSetBusy=true;keywordBusy=true;keywordSetGeneration+=1
        defer { keywordSetBusy=false;keywordBusy=false }
        var params: [String:Any]=["slot":slot,"expected_revision":keywordSetDraftRevision ?? state.revision,
            "targets":targets.map { ["photo_id":$0.id,"expected_metadata_revision":$0.metadataRevision] }]
        if let draft=keywordSetDraft { params["draft_slots"]=draft }
        do {
            try adoptKeywordSets(await Backend.call("apply_keyword_set",params))
            if keywordSetDraft != nil { keywordSetDraftRevision=keywordSets?.revision }
            await refresh();await refreshKeywords();await refreshKeywordPhoto()
            message="Applied keyword to \(ids.count) photos"
        } catch { self.error=error.localizedDescription }
    }
}
