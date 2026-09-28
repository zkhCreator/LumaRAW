// Purpose: bounded keyword hierarchy and captured-selection metadata actions.
// Inputs: portable tag pages, explicit forms and photo metadata revisions.
// Outputs: lazy tree state, mixed assignment indicators and catalog mutations.
// No SQL, original metadata writes or recipe adoption. Stale replies are ignored.
// Deferred list labels are presentation only; editors require complete details.
import Foundation

struct LibraryKeyword: Identifiable {
    let id: Int
    let name: String
    let path: String
    let parentID: Int?
    let synonyms: [String]
    let detailsDeferred: Bool
    let parentPath: String
    let hasChildren: Bool
    let photoCount: Int
    let selectedCount: Int
    let selection: [Int]
    let revision: Int
    let includeExport: Bool
    let exportContaining: Bool
    let exportSynonyms: Bool
    let isPerson: Bool
    init?(_ row: [String:Any], revision: Int, selection: [Int]) {
        guard let id=row["id"] as? Int,let name=row["name"] as? String else { return nil }
        self.id=id;self.name=name;self.revision=revision;self.selection=selection
        path=row["path"] as? String ?? row["path_preview"] as? String ?? name
        parentID=row["parent_id"] as? Int
        parentPath=row["parent_path"] as? String ?? ""
        detailsDeferred=row["details_deferred"] as? Bool ?? false
        synonyms=row["synonyms"] as? [String] ?? []
        includeExport=(row["include_export"] as? Int ?? 1) != 0
        exportContaining=(row["export_containing"] as? Int ?? 1) != 0
        exportSynonyms=(row["export_synonyms"] as? Int ?? 1) != 0
        isPerson=(row["is_person"] as? Int ?? 0) != 0
        hasChildren=row["has_children"] as? Bool ?? false
        photoCount=row["photo_count"] as? Int ?? 0;selectedCount=row["selected_count"] as? Int ?? 0
    }

    func resolved(_ result: [String:Any]) throws -> LibraryKeyword {
        guard result["keyword_revision"] as? Int == revision,
              let row=result["keyword"] as? [String:Any],row["id"] as? Int == id,
              row["details_deferred"] as? Bool == false,row["path"] is String,
              row["parent_path"] is String,row["synonyms"] is [String],
              let full=LibraryKeyword(row,revision:revision,selection:selection) else {
            throw EngineFailure(message:"Keyword details changed; refresh before editing")
        }
        return full
    }

    func complete() async throws -> LibraryKeyword {
        try resolved(await Backend.call("get_keyword",["keyword_id":id,"expected_revision":revision]))
    }
}

struct KeywordPage {
    let items: [LibraryKeyword]
    let offset: Int
    let total: Int
}

extension Store {
    var keywordSelectionKey: String { actionPhotoIDs.map(String.init).joined(separator:",") }

    func loadKeywordPage(parent: Int?, offset: Int=0) async {
        let key=parent ?? 0,query=keywordSearch,ids=actionPhotoIDs
        let token=(keywordPageGenerations[key] ?? 0)+1
        keywordPageGenerations[key]=token
        var params: [String:Any]=["offset":offset]
        if parent == nil { params["search"]=query } else { params["parent_id"]=parent }
        if !ids.isEmpty { params["photo_ids"]=ids }
        do {
            let result=try await Backend.call("list_keywords",params)
            guard keywordPageGenerations[key] == token,query == keywordSearch,ids == actionPhotoIDs else { return }
            if let parent,!expandedKeywords.contains(parent) { return }
            let revision=result["keyword_revision"] as? Int ?? 0
            let rows=(result["keywords"] as? [[String:Any]] ?? []).compactMap {
                LibraryKeyword($0,revision:revision,selection:ids)
            }
            for previous in keywordPages[key]?.items ?? [] where !rows.contains(where: { $0.id == previous.id }) {
                collapseKeyword(previous.id)
            }
            keywordPages[key]=KeywordPage(items:rows,offset:result["offset"] as? Int ?? 0,total:result["total"] as? Int ?? 0)
            keywordRevision=max(keywordRevision,revision)
        } catch {
            guard keywordPageGenerations[key] == token,query == keywordSearch,ids == actionPhotoIDs else { return }
            if let parent,error.localizedDescription == "Keyword does not exist" { collapseKeyword(parent);return }
            self.error=error.localizedDescription
        }
    }

    func refreshKeywords(reset: Bool=false) async {
        if reset {
            for id in Array(expandedKeywords) { collapseKeyword(id) }
            keywordPages.removeAll()
        }
        await loadKeywordPage(parent:nil,offset:reset ? 0:keywordPages[0]?.offset ?? 0)
        if keywordSearch.isEmpty {
            for id in expandedKeywords.sorted() {
                await loadKeywordPage(parent:id,offset:keywordPages[id]?.offset ?? 0)
            }
        }
        await refreshKeywordSets()
    }

    func scheduleKeywordSearch() {
        keywordSearchTask?.cancel()
        keywordSearchTask=Task {
            do { try await Task.sleep(nanoseconds:200_000_000) } catch { return }
            await refreshKeywords(reset:true)
        }
    }

    func collapseKeyword(_ id: Int) {
        keywordPageGenerations[id]=(keywordPageGenerations[id] ?? 0)+1
        for child in keywordPages[id]?.items ?? [] { collapseKeyword(child.id) }
        keywordPages.removeValue(forKey:id);expandedKeywords.remove(id)
    }

    func turnKeywordPage(parent: Int?, offset: Int) async {
        for child in keywordPages[parent ?? 0]?.items ?? [] { collapseKeyword(child.id) }
        await loadKeywordPage(parent:parent,offset:offset)
    }

    func editKeyword(_ original: LibraryKeyword?=nil, parent: LibraryKeyword?=nil) async {
        keywordEditorGeneration+=1
        let token=keywordEditorGeneration
        keywordEditorLoading=true
        showKeywordEditor=false
        editingKeyword=nil;newKeywordParent=nil
        let ids=actionPhotoIDs
        let targets=photos.filter { ids.contains($0.id) }
        let revision=original?.revision ?? parent?.revision ?? keywordRevision
        defer { if token == keywordEditorGeneration { keywordEditorLoading=false } }
        do {
            let full=try await (original ?? parent)?.complete()
            guard token == keywordEditorGeneration else { return }
            editingKeyword=original == nil ? nil:full
            newKeywordParent=original == nil ? full:nil
            keywordEditorTargets=targets
            keywordEditorRevision=revision
            showKeywordEditor=true
        } catch {
            guard token == keywordEditorGeneration else { return }
            self.error=error.localizedDescription
        }
    }

    func saveKeyword(name: String, synonyms: [String], parentID: Int?, original: LibraryKeyword?, revision: Int, targets: [Photo]=[], includeExport: Bool?=nil, exportContaining: Bool?=nil, exportSynonyms: Bool?=nil, isPerson: Bool?=nil) async -> Bool {
        guard !keywordBusy else { return false }
        guard original?.detailsDeferred != true else {
            error="Read complete keyword details before editing"
            return false
        }
        keywordBusy=true;defer { keywordBusy=false }
        var params: [String:Any]=["name":name,"synonyms":synonyms,
            "parent_id":parentID as Any? ?? NSNull(),"expected_revision":revision]
        if let original { params["keyword_id"]=original.id }
        if let includeExport { params["include_export"]=includeExport }
        if let exportContaining { params["export_containing"]=exportContaining }
        if let exportSynonyms { params["export_synonyms"]=exportSynonyms }
        if let isPerson { params["is_person"]=isPerson }
        if !targets.isEmpty { params["targets"]=targets.map { ["photo_id":$0.id,"expected_metadata_revision":$0.metadataRevision] } }
        do {
            _=try await Backend.call("save_keyword",params)
            await refresh();await refreshKeywords();await refreshKeywordPhoto()
            return true
        } catch { self.error=error.localizedDescription;await refreshKeywords();return false }
    }

    func changeKeyword(_ keyword: LibraryKeyword, action: String) async {
        let ids=actionPhotoIDs
        guard !keywordBusy,!ids.isEmpty,ids == keyword.selection else { return }
        let targets=photos.filter { ids.contains($0.id) }
        guard targets.count == ids.count else { return }
        keywordBusy=true;defer { keywordBusy=false }
        do {
            _=try await Backend.call("keyword_membership",["keyword_id":keyword.id,"expected_revision":keyword.revision,
                "action":action,"targets":targets.map { ["photo_id":$0.id,"expected_metadata_revision":$0.metadataRevision] }])
            await refresh();await refreshKeywords();await refreshKeywordPhoto()
            message="\(action == "add" ? "Added":"Removed") keyword for \(ids.count) photos"
        } catch { self.error=error.localizedDescription;await refreshKeywords() }
    }

    func deleteKeyword(_ keyword: LibraryKeyword) async {
        guard !keywordBusy else { return }
        keywordBusy=true;defer { keywordBusy=false }
        do {
            _=try await Backend.call("delete_keyword",["keyword_id":keyword.id,"expected_revision":keyword.revision])
            collapseKeyword(keyword.id)
            await refresh();await refreshKeywords();await refreshKeywordPhoto()
        } catch { self.error=error.localizedDescription;await refreshKeywords() }
    }

    func showKeywordPhotos(_ keyword: LibraryKeyword) async {
        sourceNavigationGeneration+=1;let token=sourceNavigationGeneration
        guard await flushEdits(),token == sourceNavigationGeneration else { return }
        folderID=nil;activeFolder=nil;collectionID=nil;activeCollection=nil
        mode="all";search="";libraryFilters=["keyword_id":keyword.id];showStacks=false
        workspace="library";develop=false;offset=0
        await refresh()
    }

    func refreshKeywordPhoto() async {
        guard let id=selected else { return }
        guard let row=try? await Backend.call("get_photo",["photo_id":id]),let fresh=Photo(row),
              selected == id,var current=photo,current.id == id,current.metadataRevision <= fresh.metadataRevision else { return }
        current.adoptLibraryPatch(["keywords":fresh.keywords,"title":fresh.title,"caption":fresh.caption,
            "keyword_ids":fresh.keywordIDs,"keyword_count":fresh.keywordCount,"keywords_deferred":fresh.keywordsDeferred,
            "copyright":fresh.copyright,"color_label":fresh.colorLabel,"copy_name":fresh.copyName],revision:fresh.metadataRevision)
        photo=current
    }
}
