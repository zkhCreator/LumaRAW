// Purpose: native dictionary import/export and manual person-keyword editing.
// Inputs: generated UTF-8 files, isolated photos and the actual engine broker.
// Outputs: additive imports, refreshed pages, complete CSV files, preserved
// assignments and visible failure states. File panels/rendered UI are unverified.
import AppKit
import Foundation

@main struct NativeKeywordExchangeRegression {
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
            let folder=URL(fileURLWithPath:paths[0]).deletingLastPathComponent()
            let originalBytes=try Data(contentsOf:URL(fileURLWithPath:paths[0]))
            await s.importPaths(paths)
            s.thumbnailRenderer.request([]);s.cancelMainPreview()
            try check(await s.saveKeyword(name:"People",synonyms:["Original"],parentID:nil,original:nil,revision:s.keywordRevision,
                includeExport:false,exportContaining:false,exportSynonyms:false,isPerson:true),"native_editor_saves_manual_person_keyword")
            s.selection=[1];s.selected=1;await s.load(1);await s.refreshKeywords()
            await s.changeKeyword(s.keywordPages[0]!.items[0],action:"add")
            let root=s.keywordPages[0]!.items[0],before=s.photo!
            try check(root.isPerson && !root.includeExport,"person_type_readback")
            let firstRevision=s.keywordRevision
            let input=folder.appendingPathComponent("keywords.csv")
            let header="Include On Export,Export Containing Keywords,Export Synonyms,Person Type Keyword,\n"
            let additions=(0..<65).map { "Y,Y,Y,N,Word \(String(format:"%03d",$0))\n" }.joined()
            let data=header+"Y,Y,Y,N,People\n,,,,\t{Replacement}\nY,N,Y,Y,\tNew Person\n,,,,\t\t{Alias}\nY,Y,Y,N,Other\n"+additions
            try data.write(to:input,atomically:true,encoding:.utf8)
            try check(await s.exchangeKeywords(path:input.path,importing:true,revision:firstRevision),"native_dictionary_import_succeeds")
            try check(!s.keywordBusy && s.message.contains("67 new") && s.message.contains("1 existing"),"import_receipt_reports_created_and_preserved")
            try check(s.keywordPages[0]?.items.count==60 && s.keywordPages[0]?.total==67,"large_import_refreshes_bounded_keyword_page")
            let people=s.keywordPages[0]!.items.first { $0.id==root.id }!
            try check(people.synonyms==["Original"] && people.isPerson && !people.exportContaining && !people.includeExport && !people.exportSynonyms,"import_preserves_existing_attributes_and_synonyms")
            let after=Photo(try await Backend.call("get_photo",["photo_id":1]))!
            try check(after.keywordIDs==before.keywordIDs && after.metadataRevision==before.metadataRevision && after.revision==before.revision,"import_preserves_photo_assignments_and_revisions")
            await s.turnKeywordPage(parent:nil,offset:60)
            try check(s.keywordPages[0]?.items.count==7 && s.keywordPages[0]?.offset==60,"imported_dictionary_is_fully_paged")
            s.expandedKeywords.insert(root.id);await s.loadKeywordPage(parent:root.id)
            let person=s.keywordPages[root.id]!.items[0]
            await s.editKeyword(person)
            let full=s.editingKeyword!
            try check(full.isPerson && full.synonyms==["Alias"] && !full.exportContaining,"imported_child_options_reach_native_editor")
            try check(await s.saveKeyword(name:"Portrait",synonyms:full.synonyms,parentID:root.id,original:full,revision:full.revision,isPerson:false),"manual_person_flag_can_be_changed_without_recognition")
            let current=s.keywordPages[root.id]!.items[0]
            try check(!current.isPerson && !current.exportContaining && current.synonyms==["Alias"],"person_edit_preserves_other_options")
            let csv=folder.appendingPathComponent("export.csv")
            try check(await s.exchangeKeywords(path:csv.path,importing:false,format:"csv",revision:s.keywordRevision),"native_csv_export_succeeds")
            let csvText=try String(contentsOf:csv,encoding:.utf8)
            try check(csvText.hasPrefix(header) && csvText.contains("N,N,N,Y,People") && csvText.contains("Y,N,Y,N,\tPortrait"),"csv_contains_hierarchy_and_complete_options")
            try check(csvText.contains("\t{Original}") && csvText.contains("\t\t{Alias}"),"csv_contains_all_synonyms")
            let txt=folder.appendingPathComponent("export.txt")
            try check(await s.exchangeKeywords(path:txt.path,importing:false,format:"text",revision:s.keywordRevision),"native_text_export_succeeds")
            try check(s.message.contains("Use CSV") && (try String(contentsOf:txt,encoding:.utf8)).contains("[People]"),"text_reports_unrepresented_options")
            let saved=try Data(contentsOf:csv)
            try check(!(await s.exchangeKeywords(path:csv.path,importing:false,format:"csv",revision:s.keywordRevision)) && s.error?.contains("already exists")==true,"existing_export_is_not_replaced")
            try check(try Data(contentsOf:csv)==saved,"collision_preserves_file_bytes")
            let invalid=folder.appendingPathComponent("invalid.txt")
            try "Would Be New\n\t\tInvalid\n".write(to:invalid,atomically:true,encoding:.utf8)
            let revision=s.keywordRevision
            try check(!(await s.exchangeKeywords(path:invalid.path,importing:true,revision:revision)) && s.error?.contains("Keyword line 2")==true,"invalid_import_fails_with_line_number")
            try check(s.keywordRevision==revision && !s.keywordBusy,"failed_import_preserves_revision_and_releases_busy")
            let late=folder.appendingPathComponent("late.txt")
            try "Unwanted\n".write(to:late,atomically:true,encoding:.utf8)
            try check(!(await s.exchangeKeywords(path:late.path,importing:true,revision:firstRevision)) && s.error?.contains("changed")==true,"stale_import_cannot_mutate_catalog")
            let absent=folder.appendingPathComponent("stale.csv")
            try check(!(await s.exchangeKeywords(path:absent.path,importing:false,format:"csv",revision:firstRevision)) && !FileManager.default.fileExists(atPath:absent.path),"stale_export_does_not_publish_file")
            try check(try Data(contentsOf:URL(fileURLWithPath:paths[0]))==originalBytes,"exchange_preserves_original_bytes")
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
