// Purpose: native shortcut/Painter workflows and pure pointer geometry evidence.
// Inputs: five generated photos, fresh catalog/presets and real engine IPC.
// Outputs: bounded strokes, retained selection, all-or-nothing failures and immediate
// metadata readback. Geometry checks do not dispatch mouse or keyboard events.
import AppKit
import Combine
import Foundation

@main struct NativePainterRegression {
    @MainActor static func main() async {
        _ = NSApplication.shared
        let s=Store()
        var checks: [String:Bool]=[:]
        func check(_ value: Bool,_ name: String) throws {
            checks[name]=value
            if !value { throw EngineFailure(message:name) }
        }
        func read(_ id: Int) async throws -> Photo { Photo(try await Backend.call("get_photo",["photo_id":id]))! }
        do {
            let rect=CGRect(x:20,y:20,width:20,height:20)
            try check(painterIntersects(rect,from:CGPoint(x:0,y:30),to:CGPoint(x:70,y:30)),"coalesced_horizontal_drag_hits_crossed_thumbnail")
            try check(painterIntersects(rect,from:CGPoint(x:30,y:0),to:CGPoint(x:30,y:70)),"coalesced_vertical_drag_hits_crossed_thumbnail")
            try check(painterIntersects(rect,from:CGPoint(x:0,y:0),to:CGPoint(x:70,y:70)),"diagonal_drag_hits_crossed_thumbnail")
            try check(!painterIntersects(rect,from:CGPoint(x:0,y:0),to:CGPoint(x:50,y:10)),"drag_outside_thumbnail_does_not_paint")
            try check(painterIntersects(rect,from:CGPoint(x:30,y:30),to:CGPoint(x:30,y:30)) && !painterIntersects(rect,from:.zero,to:.zero),"stationary_click_requires_thumbnail_hit")
            try check(!painterIntersects(.zero,from:.zero,to:CGPoint(x:30,y:30)),"zero_size_thumbnail_cannot_be_painted")
            let paths=ProcessInfo.processInfo.environment["LUMARAW_TEST_FIXTURES"]!.components(separatedBy:"|")
            let original=try Data(contentsOf:URL(fileURLWithPath:paths[0]))
            await s.importPaths(paths);s.thumbnailRenderer.request([]);s.cancelMainPreview()
            try check(s.keywordShortcut?.ids.isEmpty == true,"empty_keyword_shortcut_initialized")
            s.setPainting(true)
            try check(!s.beginPainterStroke(erase:false) && s.error?.contains("Set a keyword shortcut") == true,"empty_keyword_painter_fails_before_stroke")
            s.error=nil
            try check(await s.saveKeywordShortcut(ids:[],additions:["Places | Coast","Portrait"],revision:s.keywordShortcut!.revision),"native_configures_multiple_shortcut_keywords")
            let shortcutIDs=s.keywordShortcut!.ids
            try check(shortcutIDs.count == 2 && s.keywordShortcut?.page.items.count == 2,"shortcut_exposes_complete_ids_and_paths")
            s.selection=[1,2];s.selected=1;await s.load(1);await s.refreshKeywords()
            let selection=s.selection,firstRevision=s.photo!.revision
            try check(s.beginPainterStroke(erase:false),"keyword_stroke_begins")
            s.touchPainterPhotos([3,3,4,999])
            try check(s.painterTouched == [3,4] && s.painterStroke?.ids == [3,4],"stroke_deduplicates_hits_and_ignores_unknown_ids")
            var repeatedPublications=0
            let observer=s.$painterTouched.dropFirst().sink { _ in repeatedPublications+=1 }
            for _ in 0..<1000 { s.touchPainterPhotos([3,4]) }
            observer.cancel()
            try check(repeatedPublications == 0,"repeated_pointer_hits_do_not_republish_identical_highlights")
            try check(try await read(3).keywordIDs.isEmpty,"drag_highlight_does_not_commit_before_mouse_up")
            await s.endPainterStroke()?.value
            let third=try await read(3),fourth=try await read(4)
            try check(third.keywordIDs == shortcutIDs && fourth.keywordIDs == shortcutIDs && third.metadataRevision == 1,"mouse_up_adds_all_keywords_once_per_touched_photo")
            try check(s.selection == selection && s.selected == 1 && s.photo?.keywordIDs.isEmpty == true,"painting_unselected_thumbnails_preserves_selection")
            try check(s.painterTouched.isEmpty && s.painterStroke == nil && !s.painterBusy && !s.keywordBusy,"completed_stroke_releases_transient_state")
            try check(s.beginPainterStroke(erase:true),"option_keyword_erasure_begins")
            s.touchPainterPhotos([3]);await s.endPainterStroke()?.value
            let erased=try await read(3),retained=try await read(4)
            try check(erased.keywordIDs.isEmpty && retained.keywordIDs == shortcutIDs,"erasure_only_removes_shortcut_from_touched_photo")
            s.setPainting(false)
            await s.applyKeywordShortcut()?.value
            let gridFirst=try await read(1),gridSecond=try await read(2)
            try check(gridFirst.keywordIDs == shortcutIDs && gridSecond.keywordIDs == shortcutIDs,"put_away_shortcut_applies_to_grid_selection")
            s.develop=true
            await s.applyKeywordShortcut(erase:true)?.value
            let active=try await read(1),inactive=try await read(2)
            try check(active.keywordIDs.isEmpty && inactive.keywordIDs == shortcutIDs,"shortcut_uses_active_photo_in_develop")
            try check(s.photo?.revision == firstRevision,"painter_and_shortcut_preserve_native_recipe_revision")
            s.develop=false;s.setPainting(true);s.painterKind="rating";s.painterRating=4
            try check(s.beginPainterStroke(erase:false),"rating_stroke_begins")
            s.touchPainterPhotos([1,5]);await s.endPainterStroke()?.value
            let rated=try await read(5)
            try check(s.photo?.rating == 4 && rated.rating == 4,"rating_paints_and_refreshes_active_inspector_immediately")
            s.painterKind="flag";s.painterFlag = -1
            _=s.beginPainterStroke(erase:false);s.touchPainterPhotos([1,2]);await s.endPainterStroke()?.value
            let flagged=try await read(2)
            try check(s.photo?.flag == -1 && flagged.flag == -1,"flag_paints_and_refreshes_active_inspector_immediately")
            s.painterKind="label";s.painterLabel="purple"
            _=s.beginPainterStroke(erase:false);s.touchPainterPhotos([1,4]);await s.endPainterStroke()?.value
            let labeled=try await read(4)
            try check(s.photo?.colorLabel == "purple" && labeled.colorLabel == "purple","label_paints_selected_and_unselected_targets")
            s.painterLabel="none"
            _=s.beginPainterStroke(erase:false);s.touchPainterPhotos([1]);await s.endPainterStroke()?.value
            try check(s.photo?.colorLabel == "none","explicit_none_clears_label")
            let fifthBefore=try await read(5)
            _=s.beginPainterStroke(erase:false);s.touchPainterPhotos([5]);s.setPainting(false)
            let cancelled=try await read(5)
            try check(s.endPainterStroke() == nil && cancelled.metadataRevision == fifthBefore.metadataRevision,"cancel_discards_unsubmitted_stroke")
            s.setPainting(true);_=s.beginPainterStroke(erase:false);s.touchPainterPhotos([5]);s.search="changed source"
            try check(s.endPainterStroke() == nil && s.painterTouched.isEmpty,"source_change_cannot_commit_old_stroke")
            s.search="";s.painterKind="rating";s.painterRating=1
            _=s.beginPainterStroke(erase:false);let obsolete=s.painterStroke!.id
            _=s.beginPainterStroke(erase:false);s.touchPainterPhotos([4]);s.cancelPainterStroke(id:obsolete)
            try check(s.painterTouched == [4] && s.painterStroke != nil,"deferred_layout_cancellation_does_not_clear_new_stroke")
            let current=s.painterStroke!.id;s.cancelPainterStroke(id:current)
            try check(s.painterStroke == nil && s.painterTouched.isEmpty,"matching_layout_cancellation_discards_pending_stroke")
            _=s.beginPainterStroke(erase:false);s.touchPainterPhotos([4,5])
            let stale=try await read(4)
            _=try await Backend.call("edit_metadata",["targets":[["photo_id":4,"expected_metadata_revision":stale.metadataRevision]],"patch":["title":"External"]])
            await s.endPainterStroke()?.value
            let rolledBack=try await read(5)
            try check(s.error?.contains("conflict") == true && rolledBack.metadataRevision == fifthBefore.metadataRevision,"one_stale_target_rolls_back_entire_stroke")
            try check(!s.painterBusy && !s.keywordBusy && s.painterStroke == nil,"failed_stroke_is_not_retried_or_retained")
            s.error=nil;await s.refreshKeywords()
            let captured=s.keywordShortcut!
            _=try await Backend.call("set_keyword_shortcut",["keyword_ids":[],"keyword_additions":["External Shortcut"],"expected_revision":captured.revision])
            try check(!(await s.saveKeywordShortcut(ids:shortcutIDs,revision:captured.revision)) && s.error?.contains("changed") == true,"stale_shortcut_editor_cannot_overwrite_external_changes")
            s.error=nil;await s.refreshKeywords()
            let root=s.keywordPages[0]!.items.first { $0.name == "Portrait" }!
            await s.useKeywordShortcut(root)
            try check(s.keywordShortcut?.ids == [root.id],"keyword_list_action_sets_shortcut_by_identity")
            try check(try Data(contentsOf:URL(fileURLWithPath:paths[0])) == original,"painter_preserves_original_bytes")
            print(String(data:try JSONSerialization.data(withJSONObject:["ok":true,"checks":checks,
                "desktop_ui":"NOT_VERIFIED","pointer_keyboard_dispatch":"NOT_VERIFIED"],options:[.prettyPrinted,.sortedKeys]),encoding:.utf8)!)
            exit(0)
        } catch {
            print(String(data:try! JSONSerialization.data(withJSONObject:["ok":false,"checks":checks,
                "error":error.localizedDescription,"store_error":s.error ?? ""],options:.prettyPrinted),encoding:.utf8)!)
            exit(1)
        }
    }
}
