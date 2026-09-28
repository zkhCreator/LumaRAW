// Purpose: selective metadata forms and captured preset/Painter application via IPC.
// Inputs: isolated generated photos, catalog and shared preset storage. Outputs:
// assertions for partial fields, additive keywords, scope, stale drafts/gestures,
// rating conflicts and recipe/original preservation. No rendered UI acceptance.
import AppKit
import Foundation

@main struct NativeMetadataPresetRegression {
    @MainActor static func main() async {
        _=NSApplication.shared
        let s=Store()
        var checks: [String:Bool]=[:]
        func check(_ value: Bool,_ name: String) throws {
            checks[name]=value
            if !value { throw EngineFailure(message:name) }
        }
        func photo(_ id: Int) async throws -> Photo { Photo(try await Backend.call("get_photo",["photo_id":id]))! }
        func choice(_ name: String) throws -> MetadataPresetSelection {
            guard let page=s.metadataPresetPage,let item=page.items.first(where:{$0.name == name}) else {
                throw EngineFailure(message:"Missing preset \(name)")
            }
            return MetadataPresetSelection(preset:item,revision:page.revision)
        }
        func edit(_ id: Int,_ patch: [String:Any]) async throws {
            let p=try await photo(id)
            _=try await Backend.call("edit_metadata",["targets":[["photo_id":id,"expected_metadata_revision":p.metadataRevision]],"patch":patch])
        }
        do {
            let fixtures=ProcessInfo.processInfo.environment["LUMARAW_TEST_FIXTURES"]!.components(separatedBy:"|")
            let originals=try fixtures.map { try Data(contentsOf:URL(fileURLWithPath:$0)) }
            await s.importPaths(fixtures)
            try await edit(1,["title":"Keep","caption":"Clear","keywords":["Existing"],"iptc":["creator":["Alice, Photographer"],"city":"Paris"]])
            try await edit(2,["title":"Other","caption":"Clear","iptc":["city":"London"]])
            s.selected=1;s.selection=[1,2];await s.refresh();await s.load(1);await s.refreshMetadataPresets()
            try check(s.metadataPresetPage?.total == 0 && s.metadataPresetPage?.fields.count == 36,"shared_library_has_complete_field_descriptors")
            await s.prepareMetadataPresetEditor(nil,fromPhoto:true)
            let source=s.metadataPresetEditor!
            try check(source.values["iptc.city"] as? String == "Paris" && source.checked.contains("iptc.creator"),"photo_capture_flattens_iptc_and_checks_filled_fields")
            let values: [String:Any]=["caption":"","keywords":["Places | Coast"],"rating":4,"iptc.creator":[String](),"iptc.rights_usage_terms":"Editorial"]
            let patch=MetadataDraft.patch(values:values,selected:Set(values.keys),fields:source.fields)
            try check(patch["title"] == nil && (patch["iptc"] as? [String:Any])?["creator"] as? [String] == [],"checked_empty_clears_while_unchecked_fields_are_absent")
            try check(await s.saveMetadataPreset(source,name:"Editorial",patch:patch),"save_partial_metadata_preset")
            try check(try await photo(1).caption == "Clear","saving_never_modifies_source_photo")
            s.metadataPresetEditor=nil
            var preset=try choice("Editorial")
            let task=s.applyMetadataPreset(preset)
            try check(task != nil && s.metadataPresetBusy && s.keywordBusy && s.painterBusy,"batch_application_acquires_metadata_busy_state")
            s.set("exposure",1.25)
            await task?.value
            try check((s.photo?.recipe["exposure"] as? NSNumber)?.doubleValue == 1.25,"metadata_refresh_preserves_pending_recipe_draft")
            try check(await s.flushEdits(),"pending_recipe_saves_after_metadata_application")
            let one=try await photo(1),two=try await photo(2)
            try check(one.caption.isEmpty && two.caption.isEmpty && one.rating == 4 && two.rating == 4,"grid_applies_checked_fields_to_selection")
            try check(one.title == "Keep" && two.title == "Other" && two.iptc["city"] as? String == "London","unchecked_scalar_and_iptc_values_survive")
            try check(Set(one.keywords) == Set(["Existing","Places | Coast"]),"preset_keywords_append_without_replacing_existing")
            try check(s.photo?.iptc["rights_usage_terms"] as? String == "Editorial" && !s.metadataPresetBusy,"inspector_adopts_iptc_and_releases_busy_state")
            preset=try choice("Editorial")
            await s.applyMetadataPreset(preset)?.value
            try check(try await photo(2).metadataRevision == two.metadataRevision,"equal_application_is_metadata_noop")
            await s.switchLibraryView(.loupe)
            try await edit(2,["caption":"Loupe untouched"])
            await s.refresh();await s.load(1)
            await s.applyMetadataPreset(preset)?.value
            try check(try await photo(2).caption == "Loupe untouched","loupe_application_targets_only_active_photo")
            await s.switchLibraryView(.grid);s.selected=1;s.selection=[1,2];await s.refresh();await s.load(1)
            s.loadPainterMetadataPreset(preset)
            try check(s.beginPainterStroke(erase:true) && !s.painterSupportsErasing,"metadata_painter_has_no_keyword_erase_semantics")
            s.touchPainterPhotos([3,3,4,999])
            let beforeStroke=try await photo(3)
            try check(s.painterTouched == [3,4] && beforeStroke.rating == 0,"stroke_defers_deduplicated_targets_until_mouse_up")
            await s.endPainterStroke()?.value
            let three=try await photo(3),four=try await photo(4)
            try check(three.rating == 4 && four.rating == 4 && s.selection == [1,2] && s.selected == 1,"painter_applies_without_changing_selection")
            try check(s.painterMetadataPreset?.revision != preset.revision,"successful_own_keyword_additions_advance_loaded_token")
            _=s.beginPainterStroke(erase:false);s.touchPainterPhotos([5]);await s.endPainterStroke()?.value
            try check(try await photo(5).rating == 4,"next_stroke_uses_acknowledged_token")
            _=s.beginPainterStroke(erase:false);s.touchPainterPhotos([3]);s.cancelPainterStroke()
            let afterCancel=try await photo(3)
            try check(s.endPainterStroke() == nil && afterCancel.metadataRevision == three.metadataRevision,"cancel_discards_pending_stroke")
            _=s.beginPainterStroke(erase:false);s.touchPainterPhotos([3,4])
            _=try await Backend.call("rate_photo",["photo_id":3,"rating":2])
            await s.endPainterStroke()?.value
            let afterRatingConflict=try await photo(4)
            try check(s.error?.contains("Rating conflict") == true && afterRatingConflict.metadataRevision == four.metadataRevision,"legacy_rating_change_rejects_entire_captured_stroke")
            try check(!s.metadataPresetBusy && !s.painterBusy && !s.keywordBusy,"failed_application_releases_all_busy_states")
            s.error=nil;await s.refresh();await s.refreshMetadataPresets()
            preset=try choice("Editorial");s.loadPainterMetadataPreset(preset)
            _=s.beginPainterStroke(erase:false);s.touchPainterPhotos([3,4])
            try await edit(3,["title":"Changed elsewhere"])
            await s.endPainterStroke()?.value
            let afterMetadataConflict=try await photo(4)
            try check(s.error?.contains("Metadata conflict") == true && afterMetadataConflict.metadataRevision == four.metadataRevision,"metadata_change_rejects_entire_captured_stroke")
            s.error=nil;await s.refresh();await s.refreshMetadataPresets()
            preset=try choice("Editorial");s.loadPainterMetadataPreset(preset)
            await s.prepareMetadataPresetEditor(preset)
            let stale=s.metadataPresetEditor!
            _=s.beginPainterStroke(erase:false);s.touchPainterPhotos([4])
            _=try await Backend.call("metadata_preset_action",["action":"rename","preset_id":preset.preset.id,"name":"External rename","expected_revision":preset.revision])
            await s.refreshMetadataPresets();await s.endPainterStroke()?.value
            try check(s.error?.contains("presets, storage or keywords changed") == true && s.painterMetadataPreset?.revision == preset.revision,"external_refresh_never_rebases_loaded_painter_capture")
            s.error=nil
            try check(!(await s.saveMetadataPreset(stale,name:"Overwrite",patch:["caption":"Wrong"])),"stale_editor_cannot_overwrite_renamed_preset")
            try check(s.metadataPresetEditor?.revision == stale.revision,"stale_editor_keeps_original_capture")
            s.error=nil;s.metadataPresetEditor=nil;s.setPainting(false)
            s.selected=1;s.selection=[1];await s.load(1);await s.prepareMetadataEditor()
            try check(s.iptcFields.count == 30 && s.metadataTargets.first?.iptc["city"] as? String == "Paris","ordinary_metadata_editor_loads_iptc_values_and_schema")
            try check(await s.saveMetadata(targets:s.metadataTargets,patch:["iptc":["city":"Rome"]]),"ordinary_editor_saves_partial_iptc")
            try check(s.photo?.iptc["city"] as? String == "Rome" && s.photo?.iptc["rights_usage_terms"] as? String == "Editorial","partial_write_receipt_merges_without_clearing_other_iptc")
            await s.refreshMetadataPresets()
            try check(await s.metadataPresetAction("storage",revision:s.metadataPresetPage!.revision,values:["store_with_catalog":true]),"explicit_catalog_storage_switch")
            try check(s.metadataPresetPage?.local == true && s.metadataPresetPage?.total == 0,"shared_presets_remain_separate_from_catalog_scope")
            try check(try fixtures.map { try Data(contentsOf:URL(fileURLWithPath:$0)) } == originals,"original_bytes_unchanged")
            print(String(data:try JSONSerialization.data(withJSONObject:["ok":true,"checks":checks,"desktop_ui":"NOT_VERIFIED"],options:[.prettyPrinted,.sortedKeys]),encoding:.utf8)!)
            exit(0)
        } catch {
            print(String(data:try! JSONSerialization.data(withJSONObject:["ok":false,"checks":checks,"error":error.localizedDescription,"store_error":s.error ?? ""],options:.prettyPrinted),encoding:.utf8)!)
            exit(1)
        }
    }
}
