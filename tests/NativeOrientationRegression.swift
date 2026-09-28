// Purpose: catalog orientation workflows against real native-to-engine IPC.
// Inputs: generated photos and isolated catalog. Outputs: scope, captured gesture,
// stale-write, independent undo and preview-coordinate assertions. Original files
// remain unchanged. No desktop pointer/shortcut dispatch or visual acceptance.
import AppKit
import Foundation

@main struct NativeOrientationRegression {
    @MainActor static func main() async {
        _=NSApplication.shared
        let s=Store()
        var checks: [String:Bool]=[:]
        func check(_ value: Bool,_ name: String) throws {
            checks[name]=value
            if !value { throw EngineFailure(message:name) }
        }
        func photo(_ id: Int) async throws -> Photo {
            Photo(try await Backend.call("get_photo",["photo_id":id]))!
        }
        func until(_ condition: () -> Bool) async throws {
            for _ in 0..<600 {
                if condition() { return }
                try await Task.sleep(nanoseconds:25_000_000)
            }
            throw EngineFailure(message:"Orientation preview timed out")
        }
        do {
            let fixtures=ProcessInfo.processInfo.environment["LUMARAW_TEST_FIXTURES"]!.components(separatedBy:"|")
            let originals=try fixtures.map { try Data(contentsOf:URL(fileURLWithPath:$0)) }
            await s.importPaths(fixtures)
            s.selection=[1,2];s.selected=1;await s.load(1)
            let before=try await photo(1)
            let task=s.orientSelection("rotate_right")
            try check(task != nil && s.orientationBusy && s.orientSelection("flip_horizontal") == nil,"orientation_acquires_busy_state_before_async_dispatch")
            await task?.value
            let one=try await photo(1),two=try await photo(2),three=try await photo(3)
            try check(one.orientation == 1 && two.orientation == 1 && three.orientation == 0,"grid_rotates_all_selected_only")
            try check(one.revision == before.revision+1 && one.metadataRevision == before.metadataRevision,"orientation_uses_visual_revision_only")
            try check(s.photo?.orientation == 1 && s.photos.first(where:{$0.id == 2})?.orientation == 1,"active_photo_and_grid_refresh_after_rotation")
            try check(s.orientationState?.actionID != nil && !s.orientationBusy,"batch_undo_receipt_adopted_and_busy_released")
            try await until { s.previewGeometry?.orientation == 1 && !s.rendering }
            try check(s.previewGeometry?.photoID == 1 && s.previewGeometry?.revision == one.revision && s.previewGeometry?.detail == false,"fitted_preview_geometry_matches_current_photo_revision")
            try await until { s.thumbnailRenderer.frames[1]?.target.revision == one.revision }
            let thumb=s.thumbnailRenderer.frames[1]!.image.size
            try check(thumb.height>thumb.width,"developed_thumbnail_follows_rotated_dimensions")
            for mode in [LibraryViewMode.loupe,.compare,.survey] {
                await s.switchLibraryView(mode)
                if s.selected != 1 { s.selected=1;await s.load(1) }
                let other=try await photo(2)
                await s.orientSelection("rotate_left")?.value
                let after=try await photo(2)
                try check(after.orientation == other.orientation && after.revision == other.revision,"\(mode)_orientation_targets_only_active_photo")
                if s.isMultiReview {
                    let active=try await photo(1)
                    try await until { s.reviewRenderer.frames[1]?.revision == active.revision && s.reviewRenderer.loading.isEmpty }
                    let frame=s.reviewRenderer.frames[1]!
                    try check(frame.fullWidth == (active.orientation % 2 == 1 ? 100:160) &&
                        frame.fullHeight == (active.orientation % 2 == 1 ? 160:100),"\(mode)_refreshes_oriented_preview_dimensions")
                }
            }
            await s.switchLibraryView(.grid)
            s.selection=[1,2];s.selected=1;await s.load(1)
            s.set("exposure",0.7)
            try check(s.orientSelection("rotate_right") == nil,"pending_develop_edits_block_orientation_without_rebasing")
            try check(await s.flushEdits(),"develop_edits_finish_normally")
            let edited=try await photo(1)
            await s.orientSelection("flip_horizontal")?.value
            let flipped=try await photo(1)
            try check(flipped.recipe["exposure"] as? Double == 0.7,"flip_preserves_develop_recipe")
            _=try await Backend.call("edit_photo",["photo_id":1,"expected_revision":flipped.revision,"patch":["exposure":0]])
            await s.undoOrientation()?.value
            let restored=try await photo(1)
            try check(restored.orientation == edited.orientation && (restored.recipe["exposure"] as? Double) == 0,"orientation_undo_preserves_later_develop_edits")
            s.painterKind="orientation";s.painterOrientationAction="rotate_right";s.setPainting(true)
            let target=try await photo(3)
            try check(s.beginPainterStroke(erase:true) && !s.painterSupportsErasing,"rotation_painter_works_without_keyword_shortcut_or_erase")
            s.touchPainterPhotos([3,3,4,999]);s.painterOrientationAction="flip_vertical"
            try check(s.painterTouched == [3,4],"rotation_painter_deduplicates_visible_targets")
            try check(try await photo(3).revision == target.revision,"rotation_stroke_does_not_write_before_mouse_up")
            await s.endPainterStroke()?.value
            let painted=try await photo(3)
            try check(painted.orientation == 1 && painted.revision == target.revision+1,"rotation_stroke_uses_captured_action_once")
            try check(s.selection == [1,2] && s.selected == 1,"painting_unselected_photos_preserves_selection")
            _=s.beginPainterStroke(erase:false);s.touchPainterPhotos([3]);s.cancelPainterStroke()
            let cancelled=s.endPainterStroke(),afterCancel=try await photo(3)
            try check(cancelled == nil && afterCancel.revision == painted.revision,"cancel_discards_rotation_stroke")
            _=s.beginPainterStroke(erase:false);s.touchPainterPhotos([3,4])
            let untouched=try await photo(4)
            _=try await Backend.call("edit_photo",["photo_id":3,"expected_revision":painted.revision,"patch":["contrast":12]])
            await s.endPainterStroke()?.value
            let afterConflict=try await photo(4)
            try check(s.error?.contains("Orientation edit conflict") == true && afterConflict.revision == untouched.revision,"stale_painter_visual_revision_rejects_entire_batch")
            try check(!s.orientationBusy && s.painterStroke == nil,"failed_rotation_releases_busy_state_without_replay")
            s.error=nil;await s.refresh();await s.load(1)
            let oldState=s.orientationState!
            let external=try await photo(5)
            _=try await Backend.call("orient_photos",["targets":[["photo_id":5,"expected_revision":external.revision]],"action":"rotate_left"])
            await s.undoOrientation()?.value
            try check(s.error?.contains("Orientation history changed") == true && s.orientationState?.revision == oldState.revision,"stale_undo_does_not_adopt_or_undo_another_clients_action")
            s.error=nil;await s.refreshOrientationState()
            await s.undoOrientation()?.value
            try check(try await photo(5).orientation == external.orientation,"refreshed_explicit_undo_restores_latest_batch")
            let expected=[CGPoint(x:0.2,y:0.7),CGPoint(x:0.3,y:0.2),CGPoint(x:0.8,y:0.3),CGPoint(x:0.7,y:0.8),
                          CGPoint(x:0.8,y:0.7),CGPoint(x:0.3,y:0.8),CGPoint(x:0.2,y:0.3),CGPoint(x:0.7,y:0.2)]
            for orientation in 0..<8 {
                let point=CGPoint(x:0.2,y:0.7),displayed=PhotoOrientation.forward(point,orientation:orientation)
                let canonical=PhotoOrientation.inverse(displayed,orientation:orientation)
                try check(hypot(displayed.x-expected[orientation].x,displayed.y-expected[orientation].y)<1e-10 &&
                    hypot(canonical.x-point.x,canonical.y-point.y)<1e-10,"display_and_mask_coordinates_orientation_\(orientation)")
                let box=[0.1,0.2,0.7,0.9]
                let visible=PhotoOrientation.box(box,orientation:orientation)
                let restored=PhotoOrientation.box(visible,orientation:orientation,inverse:true)
                try check(zip(box,restored).allSatisfy { abs($0-$1)<1e-10 },"crop_bounds_round_trip_orientation_\(orientation)")
                try check(PhotoOrientation.ratio("4:5",orientation:orientation) == (orientation % 2 == 1 ? "5:4":"4:5") &&
                    PhotoOrientation.ratio("original",orientation:orientation) == "original","crop_ratio_follows_display_orientation_\(orientation)")
            }
            try check(try fixtures.map { try Data(contentsOf:URL(fileURLWithPath:$0)) } == originals,"orientation_preserves_original_bytes")
            print(String(data:try JSONSerialization.data(withJSONObject:["ok":true,"checks":checks,
                "desktop_ui":"NOT_VERIFIED","pointer_and_shortcut_dispatch":"NOT_VERIFIED"],options:[.prettyPrinted,.sortedKeys]),encoding:.utf8)!)
            exit(0)
        } catch {
            print(String(data:try! JSONSerialization.data(withJSONObject:["ok":false,"checks":checks,
                "error":error.localizedDescription,"store_error":s.error ?? ""],options:.prettyPrinted),encoding:.utf8)!)
            exit(1)
        }
    }
}
