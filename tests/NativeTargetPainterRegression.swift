// Purpose: captured-target collection Painter behavior against real engine IPC.
// Inputs: five generated photos and isolated catalog state. Outputs: assertions
// for gesture commit/cancel, fixed target revisions, refreshed membership and
// untouched photo edits. No pointer event dispatch or rendered UI acceptance.
import AppKit
import Foundation

@main struct NativeTargetPainterRegression {
    @MainActor static func main() async {
        _=NSApplication.shared
        let s=Store()
        var checks: [String:Bool]=[:]
        func check(_ value: Bool,_ name: String) throws {
            checks[name]=value
            if !value { throw EngineFailure(message:name) }
        }
        func members(_ id: Int) async throws -> Set<Int> {
            let result=try await Backend.call("list_photos",["collection_id":id,"stacked":false])
            return Set((result["photos"] as! [[String:Any]]).compactMap { $0["id"] as? Int })
        }
        func photo(_ id: Int) async throws -> Photo {
            Photo(try await Backend.call("get_photo",["photo_id":id]))!
        }
        do {
            let fixtures=ProcessInfo.processInfo.environment["LUMARAW_TEST_FIXTURES"]!.components(separatedBy:"|")
            let originals=try fixtures.map { try Data(contentsOf:URL(fileURLWithPath:$0)) }
            await s.importPaths(fixtures)
            s.thumbnailRenderer.request([]);s.cancelMainPreview()
            s.selection=[1,2];s.selected=1
            await s.load(1);await s.refreshCollections()
            let before=try await photo(1)
            s.painterKind="target_collection";s.setPainting(true)
            let state=s.collectionState!,quick=state.quick.id
            try check(s.keywordShortcut?.ids.isEmpty == true && s.beginPainterStroke(erase:false),"target_painter_works_without_keyword_shortcut")
            s.touchPainterPhotos([3,3,4,999])
            try check(s.painterTouched == [3,4] && s.painterStroke?.ids == [3,4],"target_stroke_deduplicates_only_visible_hits")
            try check(try await members(quick).isEmpty,"target_highlight_does_not_write_before_mouse_up")
            await s.endPainterStroke()?.value
            try check(s.collectionState?.members == [3,4] && s.collectionState?.target.revision == state.target.revision+1,"target_stroke_commits_once_and_refreshes_badges")
            try check(s.selection == [1,2] && s.selected == 1,"painting_unselected_targets_preserves_selection")
            _=s.beginPainterStroke(erase:false);s.touchPainterPhotos([3,4]);await s.endPainterStroke()?.value
            try check(try await members(quick) == [3,4],"painting_existing_members_adds_without_toggling")
            _=s.beginPainterStroke(erase:true);s.touchPainterPhotos([3]);await s.endPainterStroke()?.value
            try check(s.collectionState?.members == [4],"option_stroke_removes_only_touched_members")
            _=s.beginPainterStroke(erase:false);s.touchPainterPhotos([5]);s.cancelPainterStroke()
            try check(s.endPainterStroke() == nil,"cancel_discards_pending_target_stroke")
            try check(try await members(quick) == [4],"cancel_preserves_collection_members")
            let created=try await Backend.call("save_collection",["name":"Painter Target","kind":"regular"])
            let album=LibraryCollection(created)!
            await s.setTargetCollection(album)
            try check(s.beginPainterStroke(erase:false),"regular_collection_can_receive_stroke")
            s.touchPainterPhotos([1,5])
            let captured=s.collectionState!
            _=try await Backend.call("set_target_collection",["collection_id":NSNull(),"expected_revision":captured.revision])
            await s.refreshCollectionState()
            try check(s.painterTargetName == "Painter Target","pending_stroke_keeps_captured_destination_label")
            await s.endPainterStroke()?.value
            let oldMembers=try await members(album.id),newMembers=try await members(quick)
            try check(s.error?.contains("Target collection conflict") == true && oldMembers.isEmpty && newMembers == [4],"target_change_during_drag_never_retargets_or_replays")
            try check(!s.painterBusy && !s.keywordBusy && s.painterStroke == nil,"failed_target_stroke_releases_busy_state")
            s.error=nil;await s.setTargetCollection(album)
            _=s.beginPainterStroke(erase:false);s.touchPainterPhotos([1,5])
            let pending=s.collectionState!
            _=try await Backend.call("target_membership",["collection_id":album.id,"expected_state_revision":pending.revision,
                "expected_revision":pending.target.revision,"photo_ids":[2],"action":"add"])
            await s.endPainterStroke()?.value
            let externalMembers=try await members(album.id)
            try check(s.error?.contains("Collection conflict") == true && externalMembers == [2],"membership_change_rejects_whole_old_stroke")
            s.error=nil;await s.refreshCollectionState()
            _=s.beginPainterStroke(erase:false);s.touchPainterPhotos([1,5])
            _=try await Backend.call("edit_metadata",["targets":[["photo_id":1,"expected_metadata_revision":before.metadataRevision]],
                "patch":["title":"Independent metadata"]])
            await s.endPainterStroke()?.value
            let after=try await photo(1)
            try check(s.error == nil && s.collectionState?.members == [1,2,5] && after.title == "Independent metadata","membership_does_not_conflict_with_unrelated_metadata_edit")
            try check(after.revision == before.revision && after.metadataRevision == before.metadataRevision+1,"target_painter_does_not_write_photo_revisions")
            await s.openCollection(album)
            _=s.beginPainterStroke(erase:true);s.touchPainterPhotos([1,2,5]);await s.endPainterStroke()?.value
            try check(s.photos.isEmpty && s.total == 0 && s.selected == nil && s.collectionState?.members.isEmpty == true,"removing_from_visible_target_refreshes_empty_source")
            try check(try fixtures.map { try Data(contentsOf:URL(fileURLWithPath:$0)) } == originals,"target_painter_preserves_original_bytes")
            print(String(data:try JSONSerialization.data(withJSONObject:["ok":true,"checks":checks,
                "desktop_ui":"NOT_VERIFIED","option_pointer_dispatch":"NOT_VERIFIED"],options:[.prettyPrinted,.sortedKeys]),encoding:.utf8)!)
            exit(0)
        } catch {
            print(String(data:try! JSONSerialization.data(withJSONObject:["ok":false,"checks":checks,
                "error":error.localizedDescription,"store_error":s.error ?? ""],options:.prettyPrinted),encoding:.utf8)!)
            exit(1)
        }
    }
}
