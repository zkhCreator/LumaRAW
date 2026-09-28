// Purpose: complete vocabulary editing and parent selection over bounded IPC.
// Inputs: generated photos, maximal valid Unicode hierarchy and synonyms.
// Outputs: native summary/detail separation, identity/revision guards, local
// parent selection and unchanged values after editing. No rendered UI evidence.
import AppKit
import Foundation

@main struct NativeKeywordVocabularyRegression {
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
            var parent: Int?
            var names: [String]=[]
            var revision=s.keywordRevision
            for i in 0..<31 {
                let name=String(format:"%02d",i)+String(repeating:"🌊",count:118)
                names.append(name)
                let result=try await Backend.call("save_keyword",["name":name,"parent_id":parent as Any? ?? NSNull(),"expected_revision":revision])
                parent=result["keyword_id"] as? Int;revision=result["keyword_revision"] as! Int
            }
            let aliases=(0..<30).map { String(format:"%02d",$0)+String(repeating:"🐳",count:118) }
            for i in 0..<61 {
                let result=try await Backend.call("save_keyword",["name":String(format:"%02d",i)+String(repeating:"🌴",count:118),
                    "parent_id":parent!,"synonyms":aliases,"expected_revision":revision,"include_export":false,"export_containing":false,"export_synonyms":false])
                revision=result["keyword_revision"] as! Int
            }
            s.expandedKeywords.insert(parent!);await s.loadKeywordPage(parent:parent)
            let page=s.keywordPages[parent!]!,summary=page.items[0]
            try check(page.items.count==60 && page.total==61 && summary.detailsDeferred,"maximal_vocabulary_has_bounded_summary_page")
            try check(summary.synonyms.isEmpty && summary.path.contains("…"),"summary_explicitly_defers_full_edit_values")
            s.selection=[1,2];s.selected=1
            await s.editKeyword(summary)
            let original=s.editingKeyword!
            try check(s.showKeywordEditor && !s.keywordEditorLoading && !original.detailsDeferred,"editor_waits_for_complete_keyword")
            try check(original.synonyms==aliases && original.path==(names+[summary.name]).joined(separator:" | "),"editor_reads_all_synonyms_and_full_path")
            try check(original.parentPath==names.joined(separator:" | ") && original.parentID==parent,"parent_display_has_authoritative_path")
            try check(!original.includeExport && !original.exportContaining && !original.exportSynonyms,"complete_editor_preserves_export_policies")
            try check(s.keywordEditorTargets.map(\.id).sorted()==[1,2],"editor_captures_photo_targets_before_read")
            let fullResult=try await Backend.call("get_keyword",["keyword_id":summary.id,"expected_revision":revision])
            var wrong=fullResult;wrong["keyword_revision"]=revision+1
            do { _=try summary.resolved(wrong);try check(false,"wrong_detail_revision_rejected") }
            catch { try check(error.localizedDescription.contains("changed"),"wrong_detail_revision_rejected") }
            wrong=fullResult;var row=wrong["keyword"] as! [String:Any];row["id"]=summary.id+1;wrong["keyword"]=row
            do { _=try summary.resolved(wrong);try check(false,"wrong_detail_identity_rejected") }
            catch { try check(error.localizedDescription.contains("changed"),"wrong_detail_identity_rejected") }
            s.showKeywordEditor=false
            let oldRequest=Task { await s.editKeyword(summary) }
            while !s.keywordEditorLoading { await Task.yield() }
            s.selection=[2];s.selected=2
            await s.editKeyword()
            await oldRequest.value
            try check(s.editingKeyword==nil && s.keywordEditorTargets.map(\.id)==[2] && s.showKeywordEditor,"superseded_detail_cannot_replace_new_editor")
            let picker=KeywordParentModel(revision:revision)
            await picker.load()
            try check(picker.error==nil && picker.items.count==1,"parent_picker_starts_at_captured_revision")
            for _ in 0..<31 { await picker.browse(picker.items[0]) }
            try check(picker.parents.last?.id==parent && picker.items.count==60 && picker.total==61,"parent_browser_reaches_deep_bounded_page")
            let chosen=await picker.choose(picker.items[0])
            try check(chosen?.id==summary.id && chosen?.path==original.path,"parent_selection_resolves_complete_path")
            await picker.load(offset:60)
            try check(picker.offset==60 && picker.items.count==1,"parent_browser_pages_without_retaining_previous_rows")
            await picker.up()
            try check(picker.parents.count==30 && picker.items.count==1,"parent_up_restores_complete_previous_branch")
            let cancelled=KeywordParentModel(revision:revision)
            let read=Task { await cancelled.load() }
            while !cancelled.loading { await Task.yield() }
            cancelled.cancel();await read.value
            try check(cancelled.items.isEmpty && !cancelled.loading,"dismissed_parent_reader_ignores_late_reply")
            try check(!(await s.saveKeyword(name:summary.name,synonyms:[],parentID:parent,original:summary,revision:revision)),"deferred_summary_cannot_clear_synonyms")
            let saved=await s.saveKeyword(name:"Renamed",synonyms:original.synonyms,parentID:original.parentID,original:original,revision:revision)
            try check(saved,"complete_keyword_editor_can_save")
            revision=s.keywordRevision
            let fresh=try await Backend.call("get_keyword",["keyword_id":original.id,"expected_revision":revision])
            let edited=fresh["keyword"] as! [String:Any]
            try check(edited["synonyms"] as? [String]==aliases && edited["include_export"] as? Int==0 && edited["export_containing"] as? Int==0,"rename_preserves_full_values_and_export_policy")
            await s.editKeyword(summary)
            try check(!s.showKeywordEditor && s.error?.contains("changed")==true,"stale_summary_cannot_open_overwriting_editor")
            let staleChoice=await picker.choose(summary)
            try check(staleChoice==nil && picker.error?.contains("changed")==true,"stale_parent_selection_fails_visibly")
            let newPicker=KeywordParentModel(revision:revision-1);await newPicker.load()
            try check(newPicker.items.isEmpty && newPicker.error?.contains("changed")==true,"stale_parent_page_is_not_adopted")
            let currentPage=try await Backend.call("list_keywords",["parent_id":parent!])
            let current=LibraryKeyword((currentPage["keywords"] as! [[String:Any]])[0],revision:revision,selection:[])!
            await s.editKeyword(parent:current)
            try check(s.editingKeyword==nil && s.newKeywordParent?.detailsDeferred==false && s.newKeywordParent?.path.contains("…")==false,"create_inside_resolves_full_parent")
            let state=try await Backend.call("library_state")
            try check(state["keyword_revision"] as? Int==revision,"browsing_and_drafts_do_not_mutate_catalog")
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
