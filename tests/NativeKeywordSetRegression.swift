// Purpose: native keyword-set state and complete custom-preset workflows over IPC.
// Inputs: isolated shared storage, generated photos and captured editor state.
// Outputs: nine slots, explicit drafts, scope isolation, stale-write failures and
// Grid versus active-photo application. No rendered UI or shortcut dispatch proof.
import AppKit
import Foundation

@main struct NativeKeywordSetRegression {
    @MainActor static func main() async {
        _ = NSApplication.shared
        let s=Store()
        var checks: [String:Bool]=[:]
        func check(_ value: Bool,_ name: String) throws {
            checks[name]=value
            if !value { throw EngineFailure(message:name) }
        }
        do {
            let paths=ProcessInfo.processInfo.environment["LUMARAW_TEST_FIXTURES"]!.components(separatedBy:"|")
            let original=try Data(contentsOf:URL(fileURLWithPath:paths[0]))
            await s.importPaths(paths);s.thumbnailRenderer.request([]);s.cancelMainPreview()
            try check(s.keywordSets?.selected.id == "recent" && s.keywordSetSlots == Array(repeating:"",count:9),"empty_recent_set_has_nine_slots")
            try check(!s.canApplyKeywordSlot(1) && !s.canApplyKeywordSlot(0) && !s.canApplyKeywordSlot(10),"empty_and_invalid_slots_are_disabled")
            let slots=["Places | Coast","Portrait"]+Array(repeating:"",count:7)
            try check(await s.saveKeywordSet(name:"Travel",slots:slots,id:nil,revision:s.keywordSets!.revision),"native_create_preset")
            let sharedID=s.keywordSets!.selected.id
            try check(s.keywordSets?.slots == slots && s.keywordSets?.items.count == 1,"saved_preset_has_complete_slots")
            s.selection=[1,2];s.selected=1;await s.load(1);await s.refreshKeywords()
            await s.applyKeywordSlot(1)
            let first=Photo(try await Backend.call("get_photo",["photo_id":1]))!
            let second=Photo(try await Backend.call("get_photo",["photo_id":2]))!
            try check(first.keywords == ["Places | Coast"] && second.keywordIDs == first.keywordIDs,"grid_applies_to_all_selected_photos")
            try check(first.revision == 0 && second.revision == 0 && !s.keywordSetBusy && !s.keywordBusy,"application_preserves_recipe_and_releases_busy")
            s.develop=true
            await s.applyKeywordSlot(2)
            let active=Photo(try await Backend.call("get_photo",["photo_id":1]))!
            let inactive=Photo(try await Backend.call("get_photo",["photo_id":2]))!
            try check(active.keywords.contains("Portrait") && !inactive.keywords.contains("Portrait"),"develop_applies_only_to_active_photo")
            let draft=["Draft"]+Array(repeating:"",count:8)
            try check(s.changeKeywordSetDraft(draft,revision:s.keywordSets!.revision),"change_keeps_transient_draft")
            await s.applyKeywordSlot(1)
            try check(s.photo?.keywords.contains("Draft") == true && s.keywordSets?.slots == slots,"draft_applies_without_saving_preset")
            try check(s.keywordSetDraftRevision == s.keywordSets?.revision,"own_application_advances_draft_token")
            let stale=s.keywordSets!.revision
            _=try await Backend.call("save_keyword_set",["set_id":sharedID,"name":"External","slots":slots,"expected_revision":stale])
            await s.refreshKeywordSets()
            try check(s.keywordSetDraft == draft && s.keywordSetDraftRevision == stale,"external_refresh_preserves_draft_and_original_token")
            s.error=nil;await s.applyKeywordSlot(1)
            try check(s.error?.contains("changed") == true && !s.keywordSetBusy,"stale_draft_cannot_silently_apply_after_external_change")
            try check(!(await s.saveKeywordSet(name:"Late",slots:draft,id:sharedID,revision:stale)),"stale_editor_cannot_overwrite_newer_preset")
            s.error=nil
            try check(await s.keywordSetAction("select",id:"recent"),"select_recent_keywords")
            try check(s.keywordSetDraft == nil && s.keywordSetDraftRevision == nil && s.keywordSetSlots[0] == "Draft","selection_discards_draft_and_reads_recent")
            s.develop=false;await s.applyKeywordSlot(1)
            let tagged=Photo(try await Backend.call("get_photo",["photo_id":2]))!
            try check(tagged.keywords.contains("Draft"),"recent_slot_applies_saved_keyword_identity")
            let recent=s.keywordSets!
            try check(await s.saveKeywordSet(name:"From Recent",slots:recent.slots,id:nil,revision:recent.revision),"recent_keywords_can_seed_new_preset")
            let recentID=s.keywordSets!.selected.id
            try check(await s.keywordSetAction("storage",storeWithCatalog:true),"switch_to_catalog_storage")
            try check(s.keywordSets?.storeWithCatalog == true && s.keywordSets?.total == 0 && s.keywordSets?.selected.id == "recent","storage_switch_does_not_copy_shared_presets")
            try check(await s.saveKeywordSet(name:"Local",slots:slots,id:nil,revision:s.keywordSets!.revision),"save_catalog_preset")
            let localID=s.keywordSets!.selected.id
            try check(await s.keywordSetAction("storage",storeWithCatalog:false),"switch_back_to_shared_storage")
            try check(s.keywordSets?.selected.id == recentID && s.keywordSets?.total == 2,"shared_presets_are_preserved_across_scope_switch")
            try check(await s.keywordSetAction("storage",storeWithCatalog:true) && s.keywordSets?.selected.id == localID,"catalog_preset_is_preserved_across_scope_switch")
            try check(await s.saveKeywordSet(name:"Renamed Local",slots:slots,id:localID,revision:s.keywordSets!.revision),"rename_preset_by_stable_identity")
            let before=Photo(try await Backend.call("get_photo",["photo_id":1]))!
            try check(await s.keywordSetAction("delete",id:localID),"delete_preset")
            let after=Photo(try await Backend.call("get_photo",["photo_id":1]))!
            try check(s.keywordSets?.selected.id == "recent" && before.keywordIDs == after.keywordIDs && before.metadataRevision == after.metadataRevision,"deleting_preset_keeps_assigned_photo_metadata")
            for index in 0..<32 {
                _=try await Backend.call("save_keyword_set",["name":String(format:"Set %02d",index),"slots":slots,
                    "expected_revision":s.keywordSets!.revision])
                await s.refreshKeywordSets()
            }
            try check(s.keywordSets?.items.count == 30 && s.keywordSets?.total == 32,"preset_browser_is_bounded")
            await s.refreshKeywordSets(offset:30)
            try check(s.keywordSets?.offset == 30 && s.keywordSets?.items.count == 2 && s.keywordSets?.slots == slots,"last_preset_page_retains_complete_selected_slots")
            try check(try Data(contentsOf:URL(fileURLWithPath:paths[0])) == original,"preset_workflows_preserve_original_bytes")
            print(String(data:try JSONSerialization.data(withJSONObject:["ok":true,"checks":checks,
                "desktop_ui":"NOT_VERIFIED","shortcut_dispatch":"NOT_VERIFIED"],options:[.prettyPrinted,.sortedKeys]),encoding:.utf8)!)
            exit(0)
        } catch {
            print(String(data:try! JSONSerialization.data(withJSONObject:["ok":false,"checks":checks,
                "error":error.localizedDescription,"store_error":s.error ?? ""],options:.prettyPrinted),encoding:.utf8)!)
            exit(1)
        }
    }
}
