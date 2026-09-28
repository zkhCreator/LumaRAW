// Purpose: native preset editing and captured batch/Painter behavior via real IPC.
// Inputs: generated photos and isolated catalog/preset storage. Outputs: selected
// field, scope, stale form/gesture, history and original-safety assertions. This
// does not verify rendered dialogs, mouse/keyboard dispatch or accessibility.
import AppKit
import Foundation

@main struct NativeDevelopPresetRegression {
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
        func exposure(_ photo: Photo) -> Double { (photo.recipe["exposure"] as? NSNumber)?.doubleValue ?? 0 }
        func choice(_ name: String) throws -> DevelopPresetSelection {
            guard let page=s.developPresetPage,let preset=page.items.first(where: { $0.name == name }) else {
                throw EngineFailure(message:"Preset not visible: \(name)")
            }
            return DevelopPresetSelection(preset:preset,revision:page.revision)
        }
        func edit(_ id: Int,_ patch: [String:Any]) async throws {
            let row=try await photo(id)
            _=try await Backend.call("edit_photo",["photo_id":id,"expected_revision":row.revision,"patch":patch])
        }
        do {
            let fixtures=ProcessInfo.processInfo.environment["LUMARAW_TEST_FIXTURES"]!.components(separatedBy:"|")
            let originals=try fixtures.map { try Data(contentsOf:URL(fileURLWithPath:$0)) }
            await s.importPaths(fixtures)
            try await edit(1,["exposure":1.25,"contrast":18])
            try await edit(2,["temperature":22,"crop":"4:5"])
            s.selected=1;s.selection=[1];await s.load(1);await s.refreshDevelopPresets()
            try check(s.developPresetPage?.items.count == 5 && s.developPresetPage?.local == false,"preset_library_starts_with_shared_builtin_group")
            await s.prepareDevelopPresetEditor()
            let draft=s.developPresetEditor!
            try check(draft.photo.id == 1 && draft.photo.revision == s.photo?.revision && draft.fields.contains("exposure"),"editor_captures_source_photo_and_settings")
            try check(await s.saveDevelopPreset(draft,name:"Exposure Only",group:"User Presets",fields:["exposure"],policy:"error"),"save_partial_preset")
            let afterSave=try await photo(1)
            try check(afterSave.revision == draft.photo.revision,"saving_preset_never_edits_source_photo")
            s.developPresetEditor=nil
            let preset=try choice("Exposure Only")
            s.selection=[2,3];s.selected=2;await s.refresh();await s.load(2)
            let task=s.applyDevelopPreset(preset)
            try check(task != nil && s.developPresetBusy && s.orientSelection("rotate_right") == nil,"preset_apply_acquires_busy_state_and_blocks_orientation")
            s.set("exposure",4)
            await task?.value
            let two=try await photo(2),three=try await photo(3)
            try check(exposure(two) == 1.25 && exposure(three) == 1.25,"grid_application_updates_all_selected")
            try check((two.recipe["temperature"] as? NSNumber)?.intValue == 22 && two.recipe["crop"] as? String == "4:5","unchecked_settings_survive_partial_preset")
            try check(!s.developPresetBusy && s.photo?.revision == two.revision && exposure(s.photo!) == 1.25,"active_inspector_refreshes_without_interleaved_slider_edit")
            await s.applyDevelopPreset(preset)?.value
            try check(try await photo(2).revision == two.revision,"reapplying_equal_preset_is_noop")
            await s.switchLibraryView(.loupe)
            try await edit(3,["exposure":-1])
            await s.refresh();await s.load(2)
            await s.applyDevelopPreset(preset)?.value
            try check(exposure(try await photo(3)) == -1,"loupe_applies_only_active_photo")
            await s.switchLibraryView(.grid)
            s.selected=1;s.selection=[1,2];await s.load(1)
            s.loadPainterDevelopPreset(preset)
            try check(s.painterKind == "develop_preset" && s.painterEnabled && s.beginPainterStroke(erase:true),"preset_painter_works_without_keyword_shortcut")
            s.touchPainterPhotos([4,4,5,999])
            try check(s.painterTouched == [4,5] && !s.painterSupportsErasing,"preset_painter_deduplicates_hits_and_has_no_erase_mode")
            try check(exposure(try await photo(4)) == 0,"preset_stroke_waits_for_mouse_up")
            s.painterDevelopPreset=try choice("Warm Film")
            try check(s.painterPresetName == "Exposure Only","pending_stroke_retains_captured_preset_label")
            await s.endPainterStroke()?.value
            let four=try await photo(4),five=try await photo(5)
            try check(exposure(four) == 1.25 && exposure(five) == 1.25,"pending_stroke_applies_captured_preset_once")
            try check(s.selection == [1,2] && s.selected == 1,"preset_painter_preserves_selection")
            s.loadPainterDevelopPreset(preset)
            _=s.beginPainterStroke(erase:false);s.touchPainterPhotos([4]);s.cancelPainterStroke()
            let cancelled=s.endPainterStroke(),afterCancel=try await photo(4)
            try check(cancelled == nil && afterCancel.revision == four.revision,"cancel_discards_preset_stroke")
            _=s.beginPainterStroke(erase:false);s.touchPainterPhotos([4,5])
            _=try await Backend.call("develop_preset_action",["action":"favorite","preset_id":preset.preset.id,
                "favorite":true,"expected_revision":preset.revision])
            await s.refreshDevelopPresets()
            await s.endPainterStroke()?.value
            let afterPresetConflict=try await photo(5)
            try check(s.error?.contains("presets or storage changed") == true && afterPresetConflict.revision == five.revision,"preset_change_during_drag_rejects_whole_stroke")
            try check(s.painterDevelopPreset?.revision == preset.revision,"list_refresh_never_rebases_loaded_painter_preset")
            s.error=nil
            let current=try choice("Exposure Only")
            s.loadPainterDevelopPreset(current)
            _=s.beginPainterStroke(erase:false);s.touchPainterPhotos([4,5])
            try await edit(4,["exposure":-2])
            await s.endPainterStroke()?.value
            let afterPhotoConflict=try await photo(5)
            try check(s.error?.contains("Preset application conflict") == true && afterPhotoConflict.revision == five.revision,"photo_change_during_drag_rejects_all_targets")
            try check(!s.developPresetBusy && s.painterStroke == nil,"failed_stroke_releases_busy_state_without_replay")
            s.error=nil;await s.refresh();await s.load(1)
            await s.prepareDevelopPresetEditor(current)
            let stale=s.developPresetEditor!
            _=try await Backend.call("develop_preset_action",["action":"rename","preset_id":current.preset.id,
                "name":"Renamed Elsewhere","expected_revision":current.revision])
            await s.refreshDevelopPresets()
            let saved=await s.saveDevelopPreset(stale,name:"Overwrite",group:"User Presets",fields:["contrast"],policy:"error")
            try check(!saved && s.developPresetEditor?.revision == stale.revision && s.error?.contains("presets or storage changed") == true,"open_editor_preserves_captured_revision_after_external_refresh")
            s.error=nil;s.developPresetEditor=nil
            let renamed=try choice("Renamed Elsewhere")
            s.set("exposure",0.5)
            try check(s.applyDevelopPreset(renamed) == nil,"pending_slider_edit_blocks_preset_application")
            try check(await s.flushEdits(),"pending_adjustment_saves_normally")
            await s.refreshDevelopPresets(["favorites":true])
            try check(s.developPresetPage?.items.count == 1 && s.developPresetPage?.items.first?.id == renamed.preset.id,"favorite_filter_uses_bounded_preset_page")
            let state=s.developPresetPage!
            try check(await s.developPresetAction("storage",revision:state.revision,values:["store_with_catalog":true]),"native_storage_preference_changes_explicitly")
            try check(s.developPresetPage?.local == true && s.developPresetPage?.items.count == 5,"storage_switch_preserves_shared_custom_presets_outside_local_scope")
            try check(try fixtures.map { try Data(contentsOf:URL(fileURLWithPath:$0)) } == originals,"preset_workflows_preserve_original_bytes")
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
