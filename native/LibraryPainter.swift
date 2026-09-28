// Purpose: persistent keyword shortcuts and bounded native Painter stroke state.
// Inputs: captured shortcut/metadata revisions, explicit settings and thumbnail IDs.
// Outputs: one atomic service command per mouse-up or selected-photo shortcut.
// No pointer geometry, SQL or pixel edits. A stroke never selects photos, retries
// stale writes, or follows a changed source/page. Pending strokes can be cancelled.
import Foundation

struct KeywordShortcut {
    let revision: String
    let keywordRevision: Int
    let ids: [Int]
    let page: KeywordPathPage
    init?(_ result: [String:Any]) {
        guard let revision=result["revision"] as? String,let ids=result["keyword_ids"] as? [Int],
              let keywordRevision=result["keyword_revision"] as? Int else { return nil }
        self.revision=revision;self.ids=ids;self.keywordRevision=keywordRevision
        page=KeywordPathPage(result)
    }
}

struct KeywordShortcutEditorSource: Identifiable {
    let id=UUID()
    let shortcut: KeywordShortcut
}

struct PainterConfiguration {
    let kind: String
    let value: Any?
    let erase: Bool
    let shortcutRevision: String?
    var parameters: [String:Any] {
        var result: [String:Any]=["kind":kind,"erase":erase]
        if let value { result["value"]=value }
        if let shortcutRevision { result["expected_shortcut_revision"]=shortcutRevision }
        return result
    }
}

struct PainterStroke {
    let id=UUID()
    let source: String
    let configuration: PainterConfiguration
    let photos: [Int:Photo]
    var ids: [Int]=[]
}

extension Store {
    var painterInGrid: Bool { workspace == "library" && !develop && libraryView == .grid }
    var painterCanReceive: Bool {
        painterEnabled && painterInGrid && !painterBusy && !keywordBusy &&
            painterKeywordPicker == nil && shortcutEditor == nil
    }
    var painterSource: String {
        let filters=(try? JSONSerialization.data(withJSONObject:libraryFilters,options:.sortedKeys)).flatMap { String(data:$0,encoding:.utf8) } ?? ""
        return [workspace,String(develop),String(describing:libraryView),mode,String(collectionID ?? 0),
            String(folderID ?? 0),String(includeSubfolders),String(offset),search,filters,librarySort,
            String(sortDescending),String(showStacks),photos.map { String($0.id) }.joined(separator:",")].joined(separator:"\n")
    }

    func refreshKeywordShortcut() async {
        guard !painterBusy else { return }
        shortcutReadGeneration+=1;let token=shortcutReadGeneration
        do {
            let result=try await Backend.call("get_keyword_shortcut")
            guard token == shortcutReadGeneration,!painterBusy else { return }
            keywordShortcut=KeywordShortcut(result)
        } catch { if token == shortcutReadGeneration { self.error=error.localizedDescription } }
    }

    func prepareKeywordShortcut() async {
        guard painterKeywordPicker == nil,!painterBusy,!keywordBusy else { return }
        cancelPainterStroke()
        await refreshKeywordShortcut()
        if let shortcut=keywordShortcut { shortcutEditor=KeywordShortcutEditorSource(shortcut:shortcut) }
    }

    func saveKeywordShortcut(ids: [Int], additions: [String]=[], revision: String) async -> Bool {
        guard !keywordBusy,!painterBusy else { return false }
        cancelPainterStroke();painterBusy=true;keywordBusy=true;shortcutReadGeneration+=1
        defer { painterBusy=false;keywordBusy=false }
        do {
            let result=try await Backend.call("set_keyword_shortcut",["keyword_ids":ids,"keyword_additions":additions,"expected_revision":revision])
            guard let shortcut=KeywordShortcut(result) else { throw EngineFailure(message:"Incomplete keyword shortcut response") }
            keywordShortcut=shortcut
            await refresh();await refreshKeywords()
            message="Keyword shortcut contains \(shortcut.ids.count) keywords"
            return true
        } catch { self.error=error.localizedDescription;return false }
    }

    func useKeywordShortcut(_ keyword: LibraryKeyword) async {
        await refreshKeywordShortcut()
        guard let shortcut=keywordShortcut,shortcut.keywordRevision == keyword.revision else {
            error="Keyword list changed; refresh before choosing a shortcut";return
        }
        _=await saveKeywordShortcut(ids:[keyword.id],revision:shortcut.revision)
    }

    func setPainting(_ enabled: Bool) {
        cancelPainterStroke()
        painterEnabled=enabled && painterInGrid
        if !painterEnabled { painterKeywordPicker?.invalidate();painterKeywordPicker=nil }
    }

    func choosePainterKeywordSets() {
        guard painterCanReceive,painterKind == "keywords" else { return }
        cancelPainterStroke()
        painterKeywordPicker=PainterKeywordPickerModel()
    }

    func cancelPainterStroke(id: UUID?=nil) {
        if let id,painterStroke?.id != id { return }
        painterStroke=nil;painterTouched.removeAll()
    }

    func beginPainterStroke(erase: Bool) -> Bool {
        guard painterCanReceive else { return false }
        let value: Any?
        switch painterKind {
        case "rating": value=painterRating
        case "flag": value=painterFlag
        case "label": value=painterLabel
        default: value=nil
        }
        if painterKind == "keywords",keywordShortcut?.ids.isEmpty != false {
            error="Set a keyword shortcut before painting";return false
        }
        let configuration=PainterConfiguration(kind:painterKind,value:value,erase:painterKind == "keywords" && erase,
            shortcutRevision:painterKind == "keywords" ? keywordShortcut?.revision:nil)
        painterStroke=PainterStroke(source:painterSource,configuration:configuration,
            photos:Dictionary(uniqueKeysWithValues:photos.map { ($0.id,$0) }))
        painterTouched.removeAll()
        return true
    }

    func touchPainterPhotos(_ ids: [Int]) {
        guard var stroke=painterStroke,painterCanReceive,stroke.source == painterSource else {
            cancelPainterStroke();return
        }
        let previousCount=stroke.ids.count
        for id in ids where stroke.photos[id] != nil && !stroke.ids.contains(id) && stroke.ids.count<60 { stroke.ids.append(id) }
        guard stroke.ids.count != previousCount else { return }
        painterStroke=stroke;painterTouched=Set(stroke.ids)
    }

    @discardableResult func endPainterStroke() -> Task<Void,Never>? {
        guard let stroke=painterStroke else { return nil }
        cancelPainterStroke()
        guard stroke.source == painterSource,painterCanReceive,!stroke.ids.isEmpty else { return nil }
        return submitPaint(targets:stroke.ids.compactMap { stroke.photos[$0] },configuration:stroke.configuration)
    }

    @discardableResult func applyKeywordShortcut(ids: [Int]?=nil, erase: Bool=false) -> Task<Void,Never>? {
        guard let shortcut=keywordShortcut,!shortcut.ids.isEmpty else { return nil }
        let captured=ids ?? actionPhotoIDs,targets=photos.filter { captured.contains($0.id) }
        guard targets.count == captured.count else { return nil }
        return submitPaint(targets:targets,configuration:PainterConfiguration(kind:"keywords",value:nil,erase:erase,shortcutRevision:shortcut.revision))
    }

    private func submitPaint(targets: [Photo],configuration: PainterConfiguration) -> Task<Void,Never>? {
        guard !painterBusy,!keywordBusy,!targets.isEmpty else { return nil }
        painterBusy=true;keywordBusy=true;shortcutReadGeneration+=1
        var params=configuration.parameters
        params["targets"]=targets.map { ["photo_id":$0.id,"expected_metadata_revision":$0.metadataRevision] }
        return Task {
            defer { painterBusy=false;keywordBusy=false }
            do {
                let result=try await Backend.call("paint_library",params)
                if let reply=result["shortcut"] as? [String:Any],let shortcut=KeywordShortcut(reply) { keywordShortcut=shortcut }
                await refresh();await refreshKeywords();await refreshKeywordPhoto(includeCulling:true)
                message="\(configuration.erase ? "Removed":"Applied") \(configuration.kind) on \(targets.count) photos"
            } catch { self.error=error.localizedDescription }
        }
    }
}
