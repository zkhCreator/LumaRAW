// Purpose: native large-keyword read/edit workflows through a real engine.
// Inputs: generated photographs and XMP with maximal hierarchy paths.
// Outputs: paged complete paths, local draft behavior, compact identity mutations
// and revision/scope preservation. No rendered desktop or VoiceOver acceptance.
import AppKit
import Foundation

@main struct NativeKeywordDetailsRegression {
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
            await s.importPaths(paths)
            s.thumbnailRenderer.request([]);s.cancelMainPreview()
            let branch=(0..<31).map { String($0)+String(repeating:"🌊",count:118) }
            let words=(0..<100).map { (branch+[String($0)+String(repeating:"🌊",count:118)]).joined(separator:"|") }
            let xmp="<rdf:RDF xmlns:rdf=\"http://www.w3.org/1999/02/22-rdf-syntax-ns#\"><rdf:Description xmlns:lr=\"http://ns.adobe.com/lightroom/1.0/\"><lr:hierarchicalSubject><rdf:Bag>"+words.map{"<rdf:li>\($0)</rdf:li>"}.joined()+"</rdf:Bag></lr:hierarchicalSubject></rdf:Description></rdf:RDF>"
            try xmp.write(to:URL(fileURLWithPath:paths[0]).deletingPathExtension().appendingPathExtension("xmp"),atomically:true,encoding:.utf8)
            let folder=try await Backend.call("get_folder",["photo_id":1])
            var plan=(try await Backend.call("prepare_folder_sync",["folder_id":folder["id"]!,
                "expected_revision":folder["folder_revision"]!,"scan_metadata":true]))["plan"] as! [String:Any]
            while plan["state"] as? String == "planning" {
                plan=(try await Backend.call("scan_folder_sync",["plan_id":plan["id"]!,"expected_revision":plan["revision"]!]))["plan"] as! [String:Any]
            }
            plan=(try await Backend.call("apply_folder_sync",["plan_id":plan["id"]!,"expected_revision":plan["revision"]!]))["plan"] as! [String:Any]
            try check(plan["state"] as? String == "applied","long_keyword_sync_applies")
            await s.refresh();s.selected=1;s.selection=[1];await s.load(1)
            s.thumbnailRenderer.request([]);s.cancelMainPreview()
            let first=s.photo!
            try check(first.keywordsDeferred && first.keywordCount==100 && first.keywordIDs.count==100 && first.keywords.isEmpty,"native_photo_keeps_complete_ids_and_explicit_defer_marker")
            let reader=PhotoKeywordsModel(photo:first);await reader.load()
            try check(reader.page.items.count==20 && reader.page.total==100 && reader.error==nil,"native_keyword_read_is_paged")
            var restored=reader.page.items.map(\.path)
            for offset in stride(from:20,to:100,by:20) { await reader.load(offset:offset);restored+=reader.page.items.map(\.path) }
            try check(Set(restored)==Set(words.map{$0.replacingOccurrences(of:"|",with:" | ")}),"all_complete_paths_are_read_without_truncation")
            reader.receive(["photo_id":2,"metadata_revision":first.metadataRevision,"keywords":[],"total":0])
            reader.receive(["photo_id":1,"metadata_revision":first.metadataRevision+1,"keywords":[],"total":0])
            try check(reader.page.total==100 && reader.page.offset==80,"wrong_photo_and_revision_cannot_replace_path_page")
            let chooser=KeywordSelectionModel(ids:first.keywordIDs);await chooser.loadChosen()
            try check(chooser.chosen.total==100 && chooser.chosen.items.count==20,"selection_picker_pages_complete_paths")
            await chooser.toggle(chooser.chosen.items[0].id)
            try check(chooser.ids.count==99 && chooser.chosen.total==99,"remove_changes_local_replacement_set")
            let unchanged=Photo(try await Backend.call("get_photo",["photo_id":1]))!
            try check(unchanged.keywordIDs==first.keywordIDs && unchanged.metadataRevision==first.metadataRevision,"picker_draft_does_not_write_catalog")
            chooser.search="No matching keyword";await chooser.loadSearch()
            try check(chooser.available.total==0 && chooser.available.items.isEmpty,"picker_search_has_explicit_empty_page")
            await chooser.clear()
            try check(chooser.ids.isEmpty && chooser.chosen.total==0,"clear_selection_is_local_and_empty_ids_select_nothing")
            let draft=KeywordSelectionModel(ids:Array(first.keywordIDs.dropFirst(2)))
            await draft.loadSearch();await draft.toggle(draft.available.items[0].id)
            try check(draft.ids.count==99,"picker_adds_existing_keyword_by_identity")
            try check(metadataKeywordIdentityReplacement(first.keywordIDs,additions:"",original:first.keywordIDs,targetCount:1).isEmpty,"unchanged_single_photo_does_not_reassign_keywords")
            let patch=metadataKeywordIdentityReplacement(draft.ids.sorted(),additions:"New | Local",original:first.keywordIDs,targetCount:1)
            try check((patch["keyword_ids"] as? [Int])?.count==99 && patch["keyword_additions"] as? [String]==["New | Local"],"metadata_form_combines_ids_and_new_path")
            _=try await Backend.call("edit_photo",["photo_id":1,"expected_revision":first.revision,"patch":["exposure":1]])
            try check(await s.saveMetadata(targets:[first],patch:patch),"native_identity_metadata_save_succeeds")
            try check(s.photo?.revision==first.revision,"metadata_reply_does_not_adopt_new_recipe_revision")
            try check(s.photo?.keywordsDeferred==true && s.photo?.keywordCount==100 && s.photo?.keywordIDs.count==100,"native_adopts_complete_identity_receipt")
            await reader.load()
            try check(reader.error?.contains("conflict")==true,"stale_photo_reader_requires_reload")
            try check(!(await s.saveMetadata(targets:[first],patch:["caption":"Stale"])) && s.error?.contains("conflict")==true,"stale_identity_editor_cannot_overwrite")
            s.error=nil;s.selection=[1,2];await s.prepareMetadataEditor()
            try check(s.metadataTargets.count==2 && s.metadataTargets[0].keywordIDs.count==100,"batch_editor_captures_complete_ids")
            let template=s.metadataTargets[0]
            let batch=metadataKeywordIdentityReplacement(template.keywordIDs,additions:"",original:template.keywordIDs,targetCount:2)
            try check(await s.saveMetadata(targets:s.metadataTargets,patch:batch),"batch_replacement_submits_ids_without_long_paths")
            let second=Photo(try await Backend.call("get_photo",["photo_id":2]))!
            try check(second.keywordIDs==template.keywordIDs && second.keywordsDeferred,"batch_target_receives_complete_assignment_set")
            print(String(data:try JSONSerialization.data(withJSONObject:["ok":true,"checks":checks,
                "desktop_ui":"NOT_VERIFIED"],options:[.prettyPrinted,.sortedKeys]),encoding:.utf8)!)
            exit(0)
        } catch {
            print(String(data:try! JSONSerialization.data(withJSONObject:["ok":false,"checks":checks,
                "error":error.localizedDescription,"store_error":s.error ?? ""],options:.prettyPrinted),encoding:.utf8)!)
            exit(1)
        }
    }
}
