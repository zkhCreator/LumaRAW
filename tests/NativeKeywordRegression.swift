// Purpose: native keyword hierarchy and assignment integration over real IPC.
// Inputs: isolated generated photos and catalog. Outputs: state assertions for
// selection scope, revision conflicts and external updates. No desktop evidence.
import AppKit
import Foundation

@main struct NativeKeywordRegression {
    @MainActor static func main() async {
        _ = NSApplication.shared
        let s=Store()
        var checks: [String:Bool]=[:]
        func check(_ value: Bool,_ name: String) throws {
            checks[name]=value
            if !value { throw EngineFailure(message:name) }
        }
        do {
            let legacy=["Literal, comma","Parent | Child"]
            try check(metadataKeywordReplacement(legacy.joined(separator:", "),original:legacy,targetCount:1) == nil,"editing_title_does_not_reparse_unchanged_legacy_keywords")
            try check(metadataKeywordReplacement(legacy.joined(separator:", "),original:legacy,targetCount:2) == legacy,"batch_replacement_preserves_unchanged_literal_keyword_names")
            try check(metadataKeywordReplacement("New, Places > Coast",original:legacy,targetCount:1) == ["New","Places > Coast"],"explicit_keyword_text_changes_are_parsed")
            let paths=ProcessInfo.processInfo.environment["LUMARAW_TEST_FIXTURES"]!.components(separatedBy:"|")
            await s.importPaths(paths)
            try check(s.keywordPages[0]?.total == 0 && s.keywordRevision == 0,"empty_keywords_initialized")
            let rootSaved=await s.saveKeyword(name:"Animals",synonyms:["Fauna"],parentID:nil,original:nil,revision:s.keywordRevision)
            try check(rootSaved,"create_root_keyword")
            let root=s.keywordPages[0]!.items.first!
            let childSaved=await s.saveKeyword(name:"Dog",synonyms:["Canine"],parentID:root.id,original:nil,revision:s.keywordRevision)
            try check(childSaved,"create_nested_keyword")
            s.expandedKeywords.insert(root.id);await s.loadKeywordPage(parent:root.id)
            try check(s.keywordPages[root.id]?.items.first?.path == "Animals | Dog","lazy_child_has_qualified_path")
            s.selection=[1,2];s.selected=1;await s.load(1);await s.refreshKeywords()
            var dog=s.keywordPages[root.id]!.items.first!
            await s.changeKeyword(dog,action:"add")
            dog=s.keywordPages[root.id]!.items.first!
            try check(dog.selectedCount == 2 && dog.photoCount == 2,"grid_assignment_applies_to_selected_photos")
            try check(s.photo?.keywords == ["Animals | Dog"] && s.photo?.revision == 0,"keyword_assignment_preserves_recipe_revision")
            s.selection=[1,2,3];await s.refreshKeywords()
            dog=s.keywordPages[root.id]!.items.first!
            try check(dog.selectedCount == 2 && dog.selection.count == 3,"mixed_assignment_state")
            s.develop=true;await s.refreshKeywords()
            dog=s.keywordPages[root.id]!.items.first!
            await s.changeKeyword(dog,action:"remove")
            let second=Photo(try await Backend.call("get_photo",["photo_id":2]))!
            try check(s.photo?.keywords.isEmpty == true && second.keywords == ["Animals | Dog"],"develop_assignment_changes_only_active_photo")
            s.develop=false;await s.refreshKeywords()
            dog=s.keywordPages[root.id]!.items.first!
            let stale=dog
            await s.changeKeyword(dog,action:"add")
            await s.changeKeyword(stale,action:"remove")
            try check(s.error?.contains("Keyword list changed") == true,"stale_keyword_action_rejected")
            s.error=nil
            await s.showKeywordPhotos(s.keywordPages[0]!.items.first!)
            try check(s.total == 3 && s.libraryFilters["keyword_id"] as? Int == root.id && !s.showStacks,"parent_filter_includes_nested_photos")
            try check(s.folderID == nil && s.collectionID == nil && !s.develop,"show_photos_opens_all_library_source")
            await s.refreshKeywords()
            let currentRoot=s.keywordPages[0]!.items.first!
            let renamed=await s.saveKeyword(name:"Wildlife",synonyms:["Fauna"],parentID:nil,original:currentRoot,revision:currentRoot.revision)
            try check(renamed && s.photo?.keywords == ["Wildlife | Dog"],"rename_parent_refreshes_active_keyword_path")
            s.keywordSearch="canine";await s.refreshKeywords(reset:true)
            try check(s.keywordPages[0]?.items.count == 1 && s.keywordPages[0]?.items.first?.name == "Dog","synonym_search_is_bounded_flat_result")
            try check(s.keywordPages.count == 1 && s.expandedKeywords.isEmpty,"search_releases_expanded_pages")
            s.keywordSearch="";await s.refreshKeywords(reset:true)
            s.expandedKeywords.insert(root.id);await s.loadKeywordPage(parent:root.id)
            let external=s.keywordPages[root.id]!.items.first!
            _=try await Backend.call("save_keyword",["name":"Hound","keyword_id":external.id,"parent_id":root.id,"expected_revision":external.revision])
            await s.refreshVisibleSummaries()
            try check(s.keywordPages[root.id]?.items.first?.name == "Hound","external_rename_detected_by_summary_poll")
            try check(s.photo?.keywords == ["Wildlife | Hound"],"external_path_change_updates_inspector_metadata")
            await s.deleteKeyword(s.keywordPages[0]!.items.first!)
            try check(s.total == 0 && s.keywordPages[0]?.total == 0,"delete_subtree_updates_empty_keyword_filter")
            try check(s.keywordPages[root.id] == nil,"delete_releases_child_pages")
            let revision=(try await Backend.call("library_state"))["keyword_revision"] as! Int
            _=try await Backend.call("save_keyword",["name":"External","expected_revision":revision])
            await s.refreshVisibleSummaries()
            try check(s.keywordPages[0]?.items.first?.name == "External","empty_photo_page_detects_external_keyword_creation")
            s.libraryFilters=[:];await s.openLibraryMode("all")
            s.selection=[1,2];s.selected=1;await s.editKeyword()
            let captured=s.keywordEditorTargets
            s.selection=[3];s.selected=3
            let created=await s.saveKeyword(name:"Captured",synonyms:[],parentID:nil,original:nil,
                revision:s.keywordEditorRevision,targets:captured)
            let first=Photo(try await Backend.call("get_photo",["photo_id":1]))!
            let third=Photo(try await Backend.call("get_photo",["photo_id":3]))!
            try check(created && first.keywords == ["Captured"] && third.keywords.isEmpty,"create_and_assign_uses_captured_selection")
            let fourth=Photo(try await Backend.call("get_photo",["photo_id":4]))!
            _=try await Backend.call("edit_metadata",["targets":[["photo_id":4,"expected_metadata_revision":fourth.metadataRevision]],
                "patch":["keywords":(0..<100).map { String(format:"Tag%03d",$0) }]])
            await s.refreshVisibleSummaries()
            await s.turnKeywordPage(parent:nil,offset:60)
            try check(s.keywordPages[0]?.offset == 60 && s.keywordPages[0]?.items.count == 42 && s.keywordPages.count == 1,"keyword_browser_pages_without_retaining_old_rows")
            s.keywordSearch="Tag09";await s.refreshKeywords(reset:true)
            try check(s.keywordPages[0]?.offset == 0 && s.keywordPages[0]?.total == 10,"new_keyword_search_resets_page_offset")
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
