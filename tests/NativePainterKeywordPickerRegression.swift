// Purpose: multi-set Painter draft, cancellation and stale-read IPC regression.
// Inputs: generated photos and isolated preset/catalog stores. Outputs: assertions
// about local choices, identity-safe confirmation and preserved photo metadata.
// No rendered picker, pointer/keyboard event dispatch or VoiceOver acceptance.
import AppKit
import Foundation

@main struct NativePainterKeywordPickerRegression {
    @MainActor static func main() async {
        _=NSApplication.shared
        let s=Store();var checks: [String:Bool]=[:]
        func check(_ value: Bool,_ name: String) throws {
            checks[name]=value;if !value { throw EngineFailure(message:name) }
        }
        func preset(_ name: String,_ slots: [String]) async throws -> String {
            let state=try await Backend.call("list_keyword_sets")
            let saved=try await Backend.call("save_keyword_set",["name":name,
                "slots":slots+Array(repeating:"",count:9-slots.count),"expected_revision":state["revision"]!])
            return (saved["selected"] as! [String:Any])["id"] as! String
        }
        func read(_ id: Int) async throws -> Photo { Photo(try await Backend.call("get_photo",["photo_id":id]))! }
        do {
            await s.importPaths(ProcessInfo.processInfo.environment["LUMARAW_TEST_FIXTURES"]!.components(separatedBy:"|"))
            s.thumbnailRenderer.request([]);s.cancelMainPreview()
            let first=try await preset("First",["Shared","Places | Coast"])
            let second=try await preset("Second",["Shared","Portrait"])
            let before=try await read(1),initial=s.keywordShortcut!.revision
            s.choosePainterKeywordSets()
            try check(s.painterKeywordPicker == nil,"put_away_painter_does_not_open_chooser")
            s.setPainting(true);s.choosePainterKeywordSets()
            let model=s.painterKeywordPicker!;await model.start()
            try check(model.page?.state.selected.id == second && model.chosen.isEmpty,"chooser_starts_from_active_preset_without_implicit_choices")
            try check(!s.beginPainterStroke(erase:false),"modal_chooser_prevents_painting")
            model.selectAll();model.selectAll()
            try check(model.chosen.count == 2,"select_all_deduplicates_repeated_slots")
            await model.load(setID:first);model.selectAll()
            try check(model.chosen.map(\.path) == ["Shared","Portrait","Places | Coast"],"choices_accumulate_across_sets_in_selection_order")
            let state=try await Backend.call("list_keyword_sets")
            let unchanged=try await read(1)
            try check((state["selected"] as! [String:Any])["id"] as? String == second && unchanged.metadataRevision == before.metadataRevision,"browsing_does_not_select_presets_or_tag_photos")
            model.toggle(model.chosen[0])
            try check(model.chosen.map(\.path) == ["Portrait","Places | Coast"],"remove_choice_preserves_other_sets")
            model.invalidate();s.painterKeywordPicker=nil
            let cancelled=try await Backend.call("get_keyword_shortcut")
            let cancelledSave=await model.save(using:s)
            try check(cancelled["revision"] as? String == initial && !cancelledSave,"cancel_cannot_write_shortcut")
            s.choosePainterKeywordSets();let saved=s.painterKeywordPicker!;await saved.start()
            saved.selectAll();await saved.load(setID:first);saved.selectAll()
            try check(await saved.save(using:s),"confirm_loads_multiple_keywords_atomically")
            let after=try await read(1)
            try check(s.keywordShortcut?.ids.count == 3 && after.metadataRevision == before.metadataRevision && after.revision == before.revision,"loading_creates_vocabulary_without_touching_photo_or_recipe")
            saved.invalidate();s.painterKeywordPicker=nil
            await s.applyKeywordShortcut(ids:[1])?.value
            s.choosePainterKeywordSets();let recent=s.painterKeywordPicker!;await recent.start();await recent.load(setID:"recent")
            recent.selectAll()
            try check(Set(recent.chosen.compactMap(\.keywordID)) == Set(s.keywordShortcut!.ids),"recent_choices_retain_catalog_identities")
            try check(await recent.save(using:s),"recent_identity_choices_load_shortcut")
            recent.invalidate();s.painterKeywordPicker=nil
            s.choosePainterKeywordSets();let stale=s.painterKeywordPicker!;await stale.start();stale.selectAll()
            _=try await preset("External",["Changed"])
            await stale.load(setID:first)
            try check(stale.error?.contains("changed") == true && !stale.canSave,"changed_presets_fail_visibly_without_rebasing_draft")
            stale.invalidate();s.painterKeywordPicker=nil
            s.choosePainterKeywordSets();let staleShortcut=s.painterKeywordPicker!;await staleShortcut.start();staleShortcut.selectAll()
            _=try await Backend.call("set_keyword_shortcut",["keyword_ids":[],"expected_revision":staleShortcut.shortcutRevision!])
            let staleSaved=await staleShortcut.save(using:s)
            let externalShortcut=try await Backend.call("get_keyword_shortcut")
            try check(!staleSaved && staleShortcut.error?.contains("changed") == true && (externalShortcut["keyword_ids"] as? [Int])?.isEmpty == true,"stale_chooser_confirmation_preserves_external_shortcut")
            s.error=nil;staleShortcut.invalidate();s.painterKeywordPicker=nil
            s.choosePainterKeywordSets();let obsolete=s.painterKeywordPicker!;obsolete.invalidate();await obsolete.start()
            try check(obsolete.page == nil && !obsolete.canSave,"dismissed_chooser_cannot_adopt_late_initial_read")
            s.painterKeywordPicker=nil;s.choosePainterKeywordSets();let inFlight=s.painterKeywordPicker!
            let pending=Task { await inFlight.start() }
            await Task.yield();inFlight.invalidate();await pending.value
            try check(inFlight.page == nil && !inFlight.loading && !inFlight.canSave,"in_flight_initial_reply_does_not_reopen_dismissed_chooser")
            s.painterKeywordPicker=nil;s.choosePainterKeywordSets();let limited=s.painterKeywordPicker!;await limited.start()
            for i in 0..<100 { limited.toggle(PainterKeywordChoice(keywordID:nil,path:"Choice \(i)")) }
            limited.selectAll()
            try check(limited.chosen.count == 100 && limited.error?.contains("100") == true,"select_all_over_capacity_keeps_entire_existing_draft")
            limited.clear();try check(limited.chosen.isEmpty && !limited.canSave,"clear_choices_disables_empty_confirmation")
            s.setPainting(false)
            try check(s.painterKeywordPicker == nil && !limited.canSave,"putting_painter_away_invalidates_chooser")
            print(String(data:try JSONSerialization.data(withJSONObject:["ok":true,"checks":checks,
                "desktop_ui":"NOT_VERIFIED","shift_dispatch":"NOT_VERIFIED"],options:[.prettyPrinted,.sortedKeys]),encoding:.utf8)!)
            exit(0)
        } catch {
            print(String(data:try! JSONSerialization.data(withJSONObject:["ok":false,"checks":checks,
                "error":error.localizedDescription,"store_error":s.error ?? ""],options:.prettyPrinted),encoding:.utf8)!)
            exit(1)
        }
    }
}
