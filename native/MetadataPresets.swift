// Purpose: captured metadata preset editors, scoped application and Painter state.
// Inputs: bounded portable pages and local forms. Outputs: explicit metadata-only
// commands and refreshed metadata receipts. No recipe adoption, XMP or SQL.
// External refresh never rebases a draft/stroke. Only a successful own application
// advances that same loaded Painter capture to its acknowledged vocabulary token.
import Foundation

struct MetadataPresetItem: Identifiable {
    let id: String
    let name: String
    let fieldCount: Int
    init?(_ row: [String:Any]) {
        guard let id=row["id"] as? String,let name=row["name"] as? String else { return nil }
        self.id=id;self.name=name;fieldCount=row["field_count"] as? Int ?? 0
    }
}

struct MetadataPresetSelection {
    let preset: MetadataPresetItem
    let revision: String
}

struct MetadataPresetPage {
    let revision: String
    let items: [MetadataPresetItem]
    let fields: [MetadataField]
    let total: Int
    let offset: Int
    let local: Bool
    init?(_ result: [String:Any]) {
        guard let revision=result["revision"] as? String else { return nil }
        self.revision=revision
        items=(result["presets"] as? [[String:Any]] ?? []).compactMap(MetadataPresetItem.init)
        fields=(result["fields"] as? [[String:Any]] ?? []).compactMap { MetadataField($0) }
        total=result["total"] as? Int ?? 0;offset=result["offset"] as? Int ?? 0
        local=result["store_with_catalog"] as? Bool ?? false
    }
}

struct MetadataPresetEditorSource: Identifiable {
    let id=UUID()
    let original: MetadataPresetItem?
    let revision: String
    let fields: [MetadataField]
    let values: [String:Any]
    let checked: Set<String>
}

extension Store {
    var canApplyMetadataPreset: Bool {
        !metadataPresetBusy && !painterBusy && !keywordBusy && !browsing && !loading && !actionPhotoIDs.isEmpty
    }
    var painterMetadataPresetName: String {
        (painterStroke?.configuration.value as? MetadataPresetSelection)?.preset.name ?? painterMetadataPreset?.preset.name ?? "Choose a preset"
    }
    func refreshMetadataSchema() async {
        guard iptcFields.isEmpty else { return }
        do {
            let result=try await Backend.call("metadata_schema")
            iptcFields=(result["iptc_fields"] as? [[String:Any]] ?? []).compactMap { MetadataField($0,prefix:"iptc.") }
        } catch { self.error=error.localizedDescription }
    }
    func refreshMetadataPresets(_ query: [String:Any]?=nil) async {
        guard !metadataPresetBusy else { return }
        if let query { metadataPresetQuery=query }
        metadataPresetReadGeneration+=1;let token=metadataPresetReadGeneration
        do {
            let result=try await Backend.call("list_metadata_presets",metadataPresetQuery)
            guard token == metadataPresetReadGeneration,!metadataPresetBusy else { return }
            metadataPresetPage=MetadataPresetPage(result)
        } catch { if token == metadataPresetReadGeneration { self.error=error.localizedDescription } }
    }
    func prepareMetadataPresetEditor(_ selection: MetadataPresetSelection?=nil,fromPhoto: Bool=false) async {
        metadataPresetEditorGeneration+=1;let token=metadataPresetEditorGeneration
        guard !metadataPresetBusy else { return }
        if metadataPresetPage == nil { await refreshMetadataPresets() }
        guard let page=metadataPresetPage else { return }
        var patch: [String:Any]=[:]
        let revision=selection?.revision ?? page.revision
        do {
            if let selection {
                let result=try await Backend.call("get_metadata_preset",["preset_id":selection.preset.id,"expected_revision":revision])
                guard let row=result["preset"] as? [String:Any],let saved=row["patch"] as? [String:Any] else { return }
                patch=saved
            } else if fromPhoto {
                guard let id=selected else { return }
                let row=try await Backend.call("get_photo",["photo_id":id])
                guard let source=Photo(row) else { return }
                var keywords=source.keywords
                if source.keywordsDeferred {
                    keywords=[]
                    var offset=0
                    repeat {
                        let result=try await Backend.call("get_photo_keywords",["photo_id":id,"expected_metadata_revision":source.metadataRevision,"offset":offset])
                        let page=KeywordPathPage(result)
                        keywords.append(contentsOf:page.items.map(\.path));offset+=20
                        if offset>=page.total { break }
                    } while offset<100
                }
                guard selected == id else { return }
                patch=["title":source.title,"caption":source.caption,"copyright":source.copyright,"rating":source.rating,
                       "color_label":source.colorLabel,"keywords":keywords,"iptc":source.iptc]
            }
            guard token == metadataPresetEditorGeneration else { return }
            let values=MetadataDraft.flatten(patch)
            let checked=selection == nil ? Set(page.fields.filter { $0.filled(values[$0.key]) }.map(\.key)):Set(values.keys)
            metadataPresetEditor=MetadataPresetEditorSource(original:selection?.preset,revision:revision,fields:page.fields,values:values,checked:checked)
        } catch { if token == metadataPresetEditorGeneration { self.error=error.localizedDescription } }
    }
    func saveMetadataPreset(_ source: MetadataPresetEditorSource,name: String,patch: [String:Any]) async -> Bool {
        guard !metadataPresetBusy else { return false }
        metadataPresetBusy=true;metadataPresetReadGeneration+=1
        defer { metadataPresetBusy=false }
        var params: [String:Any]=["name":name,"patch":patch,"expected_revision":source.revision]
        if let original=source.original { params["preset_id"]=original.id }
        do {
            let result=try await Backend.call("save_metadata_preset",params)
            metadataPresetQuery=[:];metadataPresetPage=MetadataPresetPage(result)
            message="Saved metadata preset \(name)"
            return true
        } catch { self.error=error.localizedDescription;return false }
    }
    @discardableResult func metadataPresetAction(_ action: String,revision: String,values: [String:Any]) async -> Bool {
        guard !metadataPresetBusy else { return false }
        metadataPresetBusy=true;metadataPresetReadGeneration+=1
        defer { metadataPresetBusy=false }
        do {
            let result=try await Backend.call("metadata_preset_action",values.merging(["action":action,"expected_revision":revision]) { _,new in new })
            metadataPresetQuery=[:];metadataPresetPage=MetadataPresetPage(result)
            return true
        } catch { self.error=error.localizedDescription;return false }
    }
    func loadPainterMetadataPreset(_ selection: MetadataPresetSelection) {
        cancelPainterStroke();painterMetadataPreset=selection;painterKind="metadata_preset"
        showMetadataPresets=false;setPainting(true)
    }
    @discardableResult func applyMetadataPreset(_ selection: MetadataPresetSelection) -> Task<Void,Never>? {
        guard canApplyMetadataPreset else { return nil }
        let ids=actionPhotoIDs,targets=photos.filter { ids.contains($0.id) }
        guard targets.count == ids.count else { return nil }
        return submitMetadataPreset(targets:targets,selection:selection)
    }
    @discardableResult func submitMetadataPreset(targets: [Photo],selection: MetadataPresetSelection) -> Task<Void,Never>? {
        guard !metadataPresetBusy,!painterBusy,!keywordBusy,!targets.isEmpty else { return nil }
        let params: [String:Any]=["preset_id":selection.preset.id,"expected_revision":selection.revision,
            "targets":targets.map { ["photo_id":$0.id,"expected_metadata_revision":$0.metadataRevision,"expected_rating":$0.rating] }]
        cancelPainterStroke();metadataPresetBusy=true;painterBusy=true;keywordBusy=true;metadataPresetReadGeneration+=1
        return Task {
            defer { metadataPresetBusy=false;painterBusy=false;keywordBusy=false }
            do {
                let result=try await Backend.call("apply_metadata_preset",params)
                metadataPresetQuery=[:];metadataPresetPage=MetadataPresetPage(result)
                if painterMetadataPreset?.preset.id == selection.preset.id,painterMetadataPreset?.revision == selection.revision,
                   let revision=result["revision"] as? String {
                    painterMetadataPreset=MetadataPresetSelection(preset:selection.preset,revision:revision)
                }
                await refresh();await refreshKeywords();await refreshKeywordPhoto(includeCulling:true)
                message="Applied \(selection.preset.name) to \(targets.count) photos; \((result["updated"] as? [Int] ?? []).count) changed"
            } catch { self.error=error.localizedDescription }
        }
    }
}
