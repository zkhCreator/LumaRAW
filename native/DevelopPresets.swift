// Purpose: bounded Develop preset browsing, captured editors and batch workflows.
// Inputs: portable preset pages, selected photo revisions and explicit UI actions.
// Outputs: persistent preset commands, refreshed photos and captured Painter state.
// No SQL, asset I/O or grading. Refresh never rebases an open editor or loaded
// Painter preset; stale writes remain visible and are never automatically retried.
import Foundation

struct DevelopPresetItem: Identifiable {
    let id: String
    let name: String
    let groupID: String
    let group: String
    let favorite: Bool
    let builtin: Bool
    let fieldCount: Int
    init?(_ row: [String:Any]) {
        guard let id=row["id"] as? String,let name=row["name"] as? String,
              let groupID=row["group_id"] as? String,let group=row["group_name"] as? String else { return nil }
        self.id=id;self.name=name;self.groupID=groupID;self.group=group
        favorite=(row["favorite"] as? NSNumber)?.boolValue ?? false
        builtin=(row["builtin"] as? NSNumber)?.boolValue ?? false
        fieldCount=row["field_count"] as? Int ?? 0
    }
}

struct DevelopPresetGroup: Identifiable {
    let id: String
    let name: String
    let visible: Bool
    let builtin: Bool
    init?(_ row: [String:Any]) {
        guard let id=row["id"] as? String,let name=row["name"] as? String else { return nil }
        self.id=id;self.name=name
        visible=(row["visible"] as? NSNumber)?.boolValue ?? false
        builtin=(row["builtin"] as? NSNumber)?.boolValue ?? false
    }
}

struct DevelopPresetSelection {
    let preset: DevelopPresetItem
    let revision: String
}

struct DevelopPresetPage {
    let revision: String
    let items: [DevelopPresetItem]
    let groups: [DevelopPresetGroup]
    let fieldGroups: [String:[String]]
    let fields: [String]
    let total: Int
    let offset: Int
    let groupTotal: Int
    let groupOffset: Int
    let local: Bool
    init?(_ result: [String:Any]) {
        guard let revision=result["revision"] as? String else { return nil }
        self.revision=revision
        items=(result["presets"] as? [[String:Any]] ?? []).compactMap(DevelopPresetItem.init)
        groups=(result["groups"] as? [[String:Any]] ?? []).compactMap(DevelopPresetGroup.init)
        fieldGroups=result["field_groups"] as? [String:[String]] ?? [:]
        fields=result["fields"] as? [String] ?? []
        total=result["total"] as? Int ?? 0;offset=result["offset"] as? Int ?? 0
        groupTotal=result["group_total"] as? Int ?? 0;groupOffset=result["group_offset"] as? Int ?? 0
        local=result["store_with_catalog"] as? Bool ?? false
    }
}

struct DevelopPresetEditorSource: Identifiable {
    let id=UUID()
    let photo: Photo
    let revision: String
    let original: DevelopPresetItem?
    let fieldGroups: [String:[String]]
    let fields: Set<String>
}

extension Store {
    var canApplyDevelopPreset: Bool {
        !developPresetBusy && !orientationBusy && !painterBusy && !hasPendingEdits && !loading && !browsing && !actionPhotoIDs.isEmpty
    }
    var painterPresetName: String {
        (painterStroke?.configuration.value as? DevelopPresetSelection)?.preset.name ?? painterDevelopPreset?.preset.name ?? "Choose a preset"
    }

    func refreshDevelopPresets(_ query: [String:Any]?=nil) async {
        guard !developPresetBusy else { return }
        if let query { developPresetQuery=query }
        developPresetReadGeneration+=1;let token=developPresetReadGeneration
        do {
            let result=try await Backend.call("list_develop_presets",developPresetQuery)
            guard token == developPresetReadGeneration,!developPresetBusy else { return }
            developPresetPage=DevelopPresetPage(result)
        } catch { if token == developPresetReadGeneration { self.error=error.localizedDescription } }
    }

    func prepareDevelopPresetEditor(_ selection: DevelopPresetSelection?=nil) async {
        developPresetEditorGeneration+=1;let token=developPresetEditorGeneration
        guard !developPresetBusy,!orientationBusy,let id=selected,await flushEdits(),selected == id,let current=photo else { return }
        if developPresetPage == nil { await refreshDevelopPresets() }
        guard let page=developPresetPage else { return }
        let revision=selection?.revision ?? page.revision
        var fields=Set(["White Balance","Light","Color","Presence","Black & White Mix","Tone Curve","Color Grading"].flatMap { page.fieldGroups[$0] ?? [] })
        if let selection {
            do {
                let result=try await Backend.call("get_develop_preset",["preset_id":selection.preset.id,"expected_revision":revision])
                guard let row=result["preset"] as? [String:Any],let patch=row["patch"] as? [String:Any] else { return }
                fields=Set(patch.keys)
            } catch { self.error=error.localizedDescription;return }
        }
        guard token == developPresetEditorGeneration,selected == id,photo?.revision == current.revision else { return }
        developPresetEditor=DevelopPresetEditorSource(photo:current,revision:revision,original:selection?.preset,
            fieldGroups:page.fieldGroups,fields:fields)
    }

    func saveDevelopPreset(_ source: DevelopPresetEditorSource,name: String,group: String,fields: Set<String>,policy: String) async -> Bool {
        guard !developPresetBusy else { return false }
        developPresetBusy=true;developPresetReadGeneration+=1
        defer { developPresetBusy=false }
        var params: [String:Any]=["photo_id":source.photo.id,"expected_photo_revision":source.photo.revision,
            "expected_revision":source.revision,"name":name,"group_name":group,"fields":fields.sorted(),"duplicate_policy":policy]
        if let original=source.original { params["preset_id"]=original.id }
        do {
            let result=try await Backend.call("save_develop_preset",params)
            developPresetQuery=[:];developPresetPage=DevelopPresetPage(result)
            message="Saved Develop preset \(name)"
            return true
        } catch { self.error=error.localizedDescription;return false }
    }

    @discardableResult func developPresetAction(_ action: String,revision: String,values: [String:Any]) async -> Bool {
        guard !developPresetBusy else { return false }
        developPresetBusy=true;developPresetReadGeneration+=1
        defer { developPresetBusy=false }
        do {
            let result=try await Backend.call("develop_preset_action",values.merging(["action":action,"expected_revision":revision]) { _,new in new })
            developPresetQuery=[:];developPresetPage=DevelopPresetPage(result)
            return true
        } catch { self.error=error.localizedDescription;return false }
    }

    func loadPainterDevelopPreset(_ selection: DevelopPresetSelection) {
        cancelPainterStroke()
        painterDevelopPreset=selection;painterKind="develop_preset"
        showDevelopPresets=false
        setPainting(true)
    }

    @discardableResult func applyDevelopPreset(_ selection: DevelopPresetSelection) -> Task<Void,Never>? {
        guard canApplyDevelopPreset else { return nil }
        let ids=actionPhotoIDs,targets=photos.filter { ids.contains($0.id) }
        guard ids.count == targets.count else { return nil }
        return submitDevelopPreset(targets:targets,selection:selection)
    }

    @discardableResult func submitDevelopPreset(targets: [Photo],selection: DevelopPresetSelection) -> Task<Void,Never>? {
        guard !developPresetBusy,!orientationBusy,!painterBusy,!hasPendingEdits,!targets.isEmpty else { return nil }
        let params: [String:Any]=["preset_id":selection.preset.id,"expected_revision":selection.revision,
            "targets":targets.map { ["photo_id":$0.id,"expected_revision":$0.revision] }]
        cancelPainterStroke();developPresetBusy=true;developPresetReadGeneration+=1;cancelMainPreview()
        return Task {
            defer { developPresetBusy=false }
            do {
                let result=try await Backend.call("apply_develop_preset",params)
                let changed=result["updated"] as? [Int] ?? []
                await refresh()
                if let id=selected,changed.contains(id) { await load(id) }
                else { render() }
                message="Applied \(selection.preset.name) to \(targets.count) photos; \(changed.count) changed"
            } catch { self.error=error.localizedDescription }
        }
    }
}
