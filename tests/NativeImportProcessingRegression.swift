// Purpose: native Apply During Import choices and captured draft conflicts.
// Inputs: five generated originals and an isolated real broker/preset repository.
// Outputs: preset/None/new form state, keyword draft preservation and final photos.
// No rendered desktop, actual keyboard dispatch or VoiceOver acceptance is claimed.
import AppKit
import Foundation

@main struct NativeImportProcessingRegression {
    @MainActor static func main() async {
        _=NSApplication.shared
        var checks: [String:Bool]=[:]
        func check(_ value: Bool,_ name: String) throws {
            checks[name]=value
            if !value { throw EngineFailure(message:name) }
        }
        do {
            let paths=ProcessInfo.processInfo.environment["LUMARAW_TEST_FIXTURES"]!.components(separatedBy:"|")
            let originals=try paths.map { try Data(contentsOf:URL(fileURLWithPath:$0)) }
            _=try await Backend.call("import_photos",["paths":[paths[0]]])
            _=try await Backend.call("edit_photo",["photo_id":1,"expected_revision":0,"patch":["exposure":1.5]])
            let library=try await Backend.call("list_develop_presets")
            let saved=try await Backend.call("save_develop_preset",["photo_id":1,"expected_photo_revision":1,
                "name":"Import Light","group_name":"User Presets","fields":["exposure"],"expected_revision":library["revision"]!])
            let developID=saved["preset_id"] as! String
            let originalPhoto=try await Backend.call("get_photo",["photo_id":1])
            let review=ImportReviewModel(sources:Array(paths.dropFirst()))
            await review.load(initial:true);await review.scan()
            review.openProcessing()
            let editor=review.processingEditor!
            await editor.load()
            try check(editor.ready && editor.developPage != nil && editor.metadataPage != nil,"ready_review_loads_paged_preset_choices")
            try check(editor.developID.isEmpty && editor.metadataID.isEmpty && !editor.keywordsDirty,"new_import_has_no_applied_settings")
            editor.keywordsText="Trip, Places | Coast"
            let keywordState=try await Backend.call("list_keywords")
            try check(editor.keywordsDirty && keywordState["total"] as? Int == 0,"keyword_draft_does_not_create_vocabulary")
            let develop=editor.developPage!.items.first{$0.id == developID}!
            let oldKey=(review.plan!.values["processing"] as? [String:Any])?["develop_key"] as? String
            await editor.chooseDevelop(DevelopPresetSelection(preset:develop,revision:editor.developPage!.revision))
            try check(editor.developID == developID && editor.revision == review.plan?.revision,"develop_choice_updates_only_acknowledged_plan_revision")
            try check(editor.keywordsDirty && editor.keywordsText == "Trip, Places | Coast","choosing_develop_preserves_unsaved_keyword_draft")
            let newKey=(review.plan!.values["processing"] as? [String:Any])?["develop_key"] as? String
            try check(oldKey != newKey,"develop_choice_changes_preview_identity")
            let created=await editor.createMetadata(name:"Import Rights",patch:["copyright":"Photo credit","rating":5,"keywords":["Preset Tag"]],revision:editor.metadataPage!.revision)
            try check(created && editor.metadataName == "Import Rights","new_metadata_form_saves_and_captures_preset")
            let metadataID=editor.metadataID
            try check(editor.keywordsDirty,"new_metadata_preserves_keyword_draft")
            await editor.saveKeywords()
            try check(!editor.keywordsDirty && editor.savedKeywordsText.contains("Trip"),"explicit_keyword_save_acknowledges_draft")
            let before=try await Backend.call("status")
            let noTags=try await Backend.call("list_keywords")
            try check(before["photos"] as? Int == 1 && noTags["total"] as? Int == 0,"settings_do_not_import_or_assign_keywords")
            editor.keywordsText="Unsaved"
            await editor.chooseMetadata(nil)
            try check(editor.metadataID.isEmpty && editor.developID == developID && editor.keywordsText == "Unsaved","none_clears_one_preset_without_discarding_draft")
            let choice=editor.metadataPage!.items.first{$0.id == metadataID}!
            await editor.chooseMetadata(MetadataPresetSelection(preset:choice,revision:editor.metadataPage!.revision))
            let revision=editor.revision
            _=try await Backend.call("set_import_options",["plan_id":editor.planID,"expected_revision":revision,"skip_duplicates":false])
            await editor.saveKeywords()
            try check(editor.error?.contains("changed") == true && editor.revision == revision,"external_plan_change_rejects_draft_without_rebase")
            try check(editor.keywordsText == "Unsaved" && editor.keywordsDirty,"conflict_preserves_local_draft")
            editor.invalidate();review.processingEditor=nil
            await review.load();review.openProcessing()
            let reopened=review.processingEditor!;await reopened.load()
            try check(reopened.ready && !reopened.keywordsText.contains("Unsaved") && reopened.keywordsText.contains("Trip"),"reopen_reads_only_persisted_keyword_choices")
            try check(reopened.developID == developID && reopened.metadataID == metadataID,"closing_settings_preserves_chosen_presets")
            let page=try await Backend.call("list_metadata_presets")
            _=try await Backend.call("metadata_preset_action",["action":"delete","preset_id":metadataID,"expected_revision":page["revision"]!])
            await reopened.browseMetadata()
            try check(reopened.metadataID == metadataID && reopened.metadataName == "Import Rights" && reopened.metadataPage?.total == 0,"library_refresh_does_not_retarget_captured_preset")
            reopened.invalidate();review.processingEditor=nil
            await review.apply()
            try check(review.plan?.state == "applied" && review.plan?.number("imported") == 4,"checked_photos_import_with_captured_settings")
            let photo=try await Backend.call("get_photo",["photo_id":2])
            try check(((photo["recipe"] as? [String:Any])?["exposure"] as? NSNumber)?.doubleValue == 1.5,"imported_recipe_contains_selected_develop_fields")
            try check(photo["copyright"] as? String == "Photo credit" && photo["rating"] as? Int == 5,"deleted_preset_snapshot_still_initializes_metadata")
            try check(Set(photo["keywords"] as? [String] ?? []) == Set(["Trip","Places | Coast","Preset Tag"]),"preset_and_additional_keywords_are_unioned")
            let afterOriginal=try await Backend.call("get_photo",["photo_id":1])
            try check(NSDictionary(dictionary:originalPhoto).isEqual(to:afterOriginal),"preexisting_catalog_photo_is_unchanged")
            try check(try paths.map { try Data(contentsOf:URL(fileURLWithPath:$0)) } == originals,"original_file_bytes_are_unchanged")
            review.invalidate()
            print(String(data:try JSONSerialization.data(withJSONObject:["ok":true,"checks":checks,"desktop_ui":"NOT_VERIFIED"],options:[.prettyPrinted,.sortedKeys]),encoding:.utf8)!)
            exit(0)
        } catch {
            print(String(data:try! JSONSerialization.data(withJSONObject:["ok":false,"checks":checks,"error":error.localizedDescription],options:.prettyPrinted),encoding:.utf8)!)
            exit(1)
        }
    }
}
