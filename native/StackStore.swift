// Purpose: native stack presentation and captured, revision-checked actions.
// Inputs: a bounded page's scoped stack fields and explicit user selection.
// Outputs: portable service commands and refreshed visible rows. No SQL/pixels.
// Stack metadata stays separate from photo recipes and their edit revisions.
import Foundation

struct PhotoStack {
    let id: Int
    let count: Int
    let top: Int
    let ordinal: Int?
    let collapsed: Bool
    var badgeValue: Int? { collapsed ? count:ordinal }
    var memberDescription: String {
        ordinal.map { "Photo \($0) of \(count)" } ?? "Position unavailable in stack of \(count) photos"
    }
    var visibilityAction: String { collapsed ? "Expand stack":"Collapse stack" }
    init?(_ row: [String:Any]) {
        guard let id=row["stack_id"] as? Int,let top=row["stack_top"] as? Int else { return nil }
        self.id=id;self.top=top;count=row["stack_count"] as? Int ?? 0
        ordinal=row["stack_ordinal"] as? Int
        collapsed=(row["stack_collapsed"] as? Int ?? 0) != 0
    }
}

extension Store {
    var canStack: Bool {
        workspace == "library" && !develop && showStacks && !stackBusy && !browsing &&
        (collectionID == nil || ["regular","quick"].contains(activeCollection?.kind ?? ""))
    }

    func adoptStacks(_ result: [String:Any]) {
        stackRevision=result["stack_revision"] as? Int ?? stackRevision
        photoStacks=Dictionary(uniqueKeysWithValues:(result["photos"] as? [[String:Any]] ?? []).compactMap { row in
            guard let id=row["id"] as? Int,let stack=PhotoStack(row) else { return nil }
            return (id,stack)
        })
    }

    func changeStack(_ action: String, ids requested: [Int]?=nil) async {
        let wanted=Set(requested ?? actionPhotoIDs)
        let ids=photos.map(\.id).filter { wanted.contains($0) }
        let source=collectionID
        let folder=folderID
        let revision=stackRevision
        let active=selected
        let focus=(action == "collapse" || action == "toggle") ? ids.first.flatMap { photoStacks[$0]?.top } : active
        guard canStack,!ids.isEmpty else { return }
        stackBusy=true
        defer { stackBusy=false }
        guard await flushEdits() else { return }
        do {
            var params: [String:Any] = ["action":action,"photo_ids":ids,"expected_revision":revision]
            if let source { params["collection_id"]=source }
            if action == "group",let active,ids.contains(active) { params["active_id"]=active }
            _=try await Backend.call("stack_photos",params)
            await refreshCollections()
            let stillHere=collectionID == source && folderID == folder && selected == active
            await refresh()
            if stillHere,collectionID == source,folderID == folder,let focus,photos.contains(where: { $0.id == focus }) { choose(focus) }
            message="Updated photo stacks"
        } catch { self.error=error.localizedDescription }
    }

    func setStackVisibility(collapsed: Bool) async {
        guard canStack else { return }
        var params: [String:Any] = ["collapsed":collapsed,"expected_revision":stackRevision]
        if let collectionID { params["collection_id"]=collectionID }
        else if let folder=activeFolder,folder.id == folderID {
            params["folder"]=folder.path;params["include_subfolders"]=includeSubfolders
        }
        else if let folder=libraryFilters["folder"] as? String { params["folder"]=folder }
        stackBusy=true
        defer { stackBusy=false }
        guard await flushEdits() else { return }
        do {
            _=try await Backend.call("set_stack_visibility",params)
            await refreshCollections();await refresh()
            message=collapsed ? "Collapsed stacks in this source":"Expanded stacks in this source"
        } catch { self.error=error.localizedDescription }
    }
}
