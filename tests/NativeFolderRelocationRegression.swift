// Purpose: exercise missing-folder plans through real native state and broker IPC.
// Inputs: isolated generated rasters and catalog. Outputs: bounded scan, explicit
// apply/cancel/resume and source-adoption assertions. Moves affect fixtures only;
// this does not automate or verify the rendered desktop or Finder dialogs.
import AppKit
import Foundation

@main struct NativeFolderRelocationRegression {
    @MainActor static func main() async {
        _ = NSApplication.shared
        let s=Store()
        var checks: [String:Bool]=[:]
        func check(_ value: Bool,_ name: String) throws {
            checks[name]=value
            if !value { throw EngineFailure(message:name) }
        }
        func revision() async throws -> Int { (try await Backend.call("library_state"))["folder_revision"] as! Int }
        do {
            let paths=ProcessInfo.processInfo.environment["LUMARAW_TEST_FIXTURES"]!.components(separatedBy:"|")
            await s.importPaths(paths)
            s.thumbnailRenderer.request([]);s.cancelMainPreview()
            let root=LibraryFolder(try await Backend.call("get_folder",["photo_id":1]))!
            let child=LibraryFolder(try await Backend.call("get_folder",["photo_id":2]))!
            await s.changeFolder(child,patch:["favorite":true,"color_label":"red"])
            _=try await Backend.call("create_virtual_copies",["targets":[["photo_id":2,"expected_revision":0,"expected_metadata_revision":0]]])
            _=try await Backend.call("edit_metadata",["targets":[["photo_id":2,"expected_metadata_revision":0]],"patch":["title":"Keep this title","keywords":["Places | Coast"]]])
            let old=URL(fileURLWithPath:root.path)
            let new=old.deletingLastPathComponent().appendingPathComponent("Located")
            try FileManager.default.moveItem(at:old,to:new)
            try FileManager.default.removeItem(at:new.appendingPathComponent("child/b.png"))
            let model=FolderRelocationModel(folder:root)
            await model.reload()
            try check(model.plan == nil && !model.loading,"empty_saved_plan_loads")
            await model.prepare(destination:new.path,revision:try await revision())
            try check(model.canScan && !model.canApply,"prepare_requires_scan_before_apply")
            try check(model.plan?.count("physical_count") == 3 && model.plan?.count("photo_count") == 4,"plan_counts_physical_families_and_copies")
            await model.scan()
            try check(model.canApply && model.plan?.count("missing") == 1 && model.plan?.count("unverified") == 2,"scan_reports_missing_and_unindexed_files")
            let before=try await Backend.call("get_photo",["photo_id":2])
            try check((before["path"] as? String) == paths[1],"scan_keeps_original_catalog_paths")
            try check(model.items.count == 1 && model.total == 1,"bounded_issue_page_contains_missing_file")
            // Set a source without triggering a preview against its missing path.
            s.folderID=child.id;s.activeFolder=child;s.selected=nil;s.photo=nil
            await model.apply(using:s)
            try check(model.plan?.state == "applied" && model.error == nil,"explicit_apply_completes")
            try check(s.folderID == child.id && s.activeFolder?.path == new.appendingPathComponent("child").path,"active_child_identity_and_path_adopted")
            try check(s.activeFolder?.favorite == true && s.activeFolder?.color == "red","folder_presentation_preserved")
            try check(s.total == 3 && s.photos.count <= 60,"active_source_counts_copies_and_missing_originals")
            let after=try await Backend.call("get_photo",["photo_id":2])
            try check(after["title"] as? String == "Keep this title" && (after["keyword_tags"] as? [[String:Any]])?.count == 1,"metadata_and_hierarchy_preserved")
            try check(after["source_revision"] as? Int == (before["source_revision"] as? Int ?? -1)+1,"family_source_revision_advanced")
            try check(s.photo?.path.hasPrefix(new.path) == true,"active_photo_path_reloaded")
            s.thumbnailRenderer.request([]);s.cancelMainPreview()
            let next=new.deletingLastPathComponent().appendingPathComponent("Again")
            try FileManager.default.moveItem(at:new,to:next)
            let relocated=LibraryFolder(try await Backend.call("get_folder",["photo_id":1]))!
            let second=FolderRelocationModel(folder:relocated)
            await second.reload();await second.prepare(destination:next.path,revision:try await revision())
            let resumed=FolderRelocationModel(folder:nil)
            await resumed.reload()
            try check(resumed.plan?.id == second.plan?.id && resumed.canScan,"new_model_restores_durable_plan_without_auto_apply")
            await resumed.cancel(using:s)
            try check(resumed.plan?.state == "cancelled" && !resumed.canApply,"explicit_cancel_discards_plan")
            let cancelled=try await Backend.call("get_photo",["photo_id":1])
            try check(cancelled["path"] as? String == new.appendingPathComponent("direct.png").path,"cancel_leaves_catalog_paths_unchanged")
            // A late polling response must never regress a completed receipt.
            resumed.receive(["plan":["id":resumed.plan!.id,"revision":0,"state":"planning"]])
            try check(resumed.plan?.state == "cancelled","stale_response_cannot_restore_cancelled_plan")
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
