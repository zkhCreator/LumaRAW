// Purpose: exercise native library state and metadata races through the real broker.
// Inputs: disposable catalog and generated fixtures from run_native.py.
// Outputs: assertions on persisted service state and captured native selections.
// Boundaries: state integration, not desktop gestures or accessibility acceptance.
import AppKit
import Foundation

@main struct NativeLibraryRegression {
    @MainActor static func main() async {
        _ = NSApplication.shared
        let s=Store()
        var checks:[String:Bool]=[:]
        func check(_ value:Bool,_ name:String)throws {
            checks[name]=value
            if !value { throw EngineFailure(message:name) }
        }
        func loaded() async throws {
            for _ in 0..<200 {
                if s.photo?.id == s.selected && s.photo != nil && !s.loading { return }
                try await Task.sleep(nanoseconds:20_000_000)
            }
            throw EngineFailure(message:"Photo did not load")
        }
        do {
            let fixtures=ProcessInfo.processInfo.environment["LUMARAW_TEST_FIXTURES"]!.components(separatedBy:"|")
            await s.importPaths(fixtures)
            try await loaded()
            let id=s.photo!.id
            let captured=s.photo!
            let revision=captured.revision
            _=try await Backend.call("edit_photo",["photo_id":id,"expected_revision":revision,"patch":["exposure":1.2]])
            try check(await s.saveMetadata(targets:[captured],patch:["title":"Evening","keywords":["Travel","travel"],"color_label":"red"]),"metadata_save")
            try check(s.photo?.revision == revision,"metadata_does_not_adopt_external_recipe_revision")
            try check(s.photo?.title == "Evening" && s.photo?.keywords == ["Travel"],"normalized_metadata_applied")
            s.set("exposure",0.8)
            try check(!(await s.flushEdits()) && s.error != nil,"stale_recipe_still_conflicts")
            s.error=nil
            try check(!(await s.saveMetadata(targets:[captured],patch:["title":"Stale"])),"stale_metadata_conflicts")
            s.error=nil
            let persisted=try await Backend.call("get_photo",["photo_id":id])
            try check(persisted["title"] as? String == "Evening","metadata_conflict_preserves_title")
            try check(await s.saveCollection(name:"Red photos",kind:"smart",rules:["color_label":"red"],match:"all",original:nil),"create_smart_collection")
            await s.refresh()
            try check(s.total == 1 && s.photos.first?.id == id,"smart_membership_in_native_page")
            s.collectionID=nil;s.librarySort="name";s.sortDescending=false;s.offset=0
            await s.refresh()
            try check(s.photos.map(\.name) == s.photos.map(\.name).sorted(),"filename_sort")
            s.libraryFilters=["color_label":"purple"];await s.refresh()
            try check(s.total == 0 && s.photo == nil && s.selection.isEmpty,"empty_filter_clears_selection")
            s.libraryFilters=[:];s.search="Evening";s.offset=60;await s.refresh()
            try check(s.offset == 0 && s.total == 1 && s.photos.first?.id == id,"searches_metadata_and_clamps_page")
            let fresh=Photo(try await Backend.call("get_photo",["photo_id":id]))!
            try check(await s.saveMetadata(targets:[fresh],patch:["caption":"A quiet evening"]),"partial_metadata_patch")
            try check(s.photo?.title == "Evening" && s.photo?.caption == "A quiet evening","partial_patch_preserves_unrelated_fields")
            let report:[String:Any]=["ok":true,"checks":checks,"desktop_ui":"NOT_VERIFIED"]
            print(String(data:try JSONSerialization.data(withJSONObject:report,options:[.prettyPrinted,.sortedKeys]),encoding:.utf8)!)
            exit(0)
        } catch {
            print(String(data:try! JSONSerialization.data(withJSONObject:["ok":false,"checks":checks,"error":error.localizedDescription],options:.prettyPrinted),encoding:.utf8)!)
            exit(1)
        }
    }
}
