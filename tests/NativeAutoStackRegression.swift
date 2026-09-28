// Purpose: exercise automatic stack confirmation with generated EXIF timestamps.
// Inputs: isolated JPEG sources and a real engine. Outputs: clock, scope, stale
// preview and native state assertions. No desktop interaction or Lightroom claim.
import AppKit
import Foundation

@main struct NativeAutoStackRegression {
    @MainActor static func main() async {
        _ = NSApplication.shared
        let s=Store()
        var checks: [String:Bool] = [:]
        func check(_ value: Bool,_ name: String) throws {
            checks[name]=value
            if !value { throw EngineFailure(message:name) }
        }
        do {
            let fixtures=ProcessInfo.processInfo.environment["LUMARAW_TEST_FIXTURES"]!.components(separatedBy:"|")
            await s.importPaths(fixtures)
            try check(s.total == 5,"five_photos_imported_with_capture_clocks")
            let folder=URL(fileURLWithPath:fixtures[0]).deletingLastPathComponent().path
            s.libraryFilters=["folder":folder,"rating_min":5];await s.refresh()
            try check(s.photos.isEmpty && s.selection.isEmpty,"selection_and_filter_can_be_empty")
            s.prepareAutoStack()
            try check(s.autoStackSource?.folder == folder && s.showAutoStack,"folder_source_captured_explicitly")
            let model=AutoStackModel(source:s.autoStackSource!);model.seconds=0.31
            await model.preview()
            try check(model.plan?.count("photos") == 5 && model.plan?.count("stacks") == 2,"preview_includes_full_source_and_fractional_clocks")
            try check(model.canApply,"fresh_preview_can_be_applied")
            model.seconds=0.3
            try check(!model.canApply,"changed_duration_cannot_apply_old_preview")
            await model.preview()
            try check(model.plan?.count("stacks") == 1,"exact_gap_starts_new_stack")
            model.seconds=0.31;await model.preview()
            _=try await Backend.call("stack_photos",["action":"group","photo_ids":[3,4],"expected_revision":model.plan!.values["stack_revision"]!])
            try check(!(await model.apply(using:s)),"changed_stack_rejects_old_confirmation")
            try check(model.plan == nil && model.error?.contains("Auto-stack conflict") == true,"conflict_requires_new_preview")
            await model.preview()
            try check(await model.apply(using:s),"fresh_confirmation_applies_groups")
            let result=try await Backend.call("list_photos")
            try check(result["total"] as? Int == 3,"two_collapsed_stacks_and_singleton_visible")
            try check(s.photos.isEmpty,"applying_preserves_current_filter")
            s.libraryFilters=[:];await s.refresh()
            try check(s.photoStacks[1]?.count == 2 && s.photoStacks[3]?.count == 2,"native_page_adopts_auto_stack_covers")
            await model.refreshTimes()
            try check(model.progress.contains("Read 5 originals") && model.plan?.count("known") == 5,"metadata_refresh_reports_progress_and_repreviews")
            try check(!model.busy && !model.loading,"metadata_refresh_releases_busy_state")
            let album=try await Backend.call("save_collection",["name":"Automatic collection","kind":"regular","photo_ids":[1,2,5]])
            await s.openCollection(LibraryCollection(album)!)
            s.prepareAutoStack()
            try check(s.autoStackSource?.collectionID == album["id"] as? Int,"regular_collection_source_captured")
            let collectionModel=AutoStackModel(source:s.autoStackSource!);collectionModel.seconds=1
            await collectionModel.preview()
            try check(collectionModel.plan?.count("photos") == 3 && collectionModel.plan?.count("stacks") == 1,"collection_preview_uses_membership")
            try check(await collectionModel.apply(using:s),"collection_confirmation_applies")
            try check(s.total == 2 && s.activeCollection!.revision > 0,"collection_stack_refreshes_revision_and_page")
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
