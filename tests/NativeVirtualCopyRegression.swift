// Purpose: verify virtual-copy native state against a real portable engine.
// Inputs: generated photos and an isolated catalog. Outputs: JSON assertions for
// copy selection, independent edits, shared snapshots, conflicts and safe removal.
// This does not inspect rendered menus, keyboard routing, badges or VoiceOver.
import AppKit
import Foundation

@main struct NativeVirtualCopyRegression {
    @MainActor static func main() async {
        _ = NSApplication.shared
        let s=Store()
        var checks: [String:Bool] = [:]
        func check(_ value: Bool,_ name: String) throws {
            checks[name]=value
            if !value { throw EngineFailure(message:name) }
        }
        func until(_ condition: () -> Bool) async throws {
            for _ in 0..<400 {
                if condition() { return }
                try await Task.sleep(nanoseconds:20_000_000)
            }
            throw EngineFailure(message:"Virtual-copy state timed out")
        }
        func get(_ id: Int) async throws -> Photo {
            Photo(try await Backend.call("get_photo",["photo_id":id]))!
        }
        do {
            let fixtures=ProcessInfo.processInfo.environment["LUMARAW_TEST_FIXTURES"]!.components(separatedBy:"|")
            await s.importPaths(fixtures)
            try await until { s.photo != nil && !s.loading }
            let master=s.photo!
            await s.createVirtualCopies(ids:[master.id])
            try await until { s.photo?.isVirtual == true && !s.loading }
            let copy=s.photo!
            try check(copy.id != master.id && copy.path == master.path && copy.copyName == "Copy 1","copy_shares_source_and_has_distinct_identity")
            try check(s.selection == [copy.id],"visible_new_copy_is_selected")
            s.set("exposure",1.25)
            try check(await s.flushEdits(),"copy_adjustment_saved")
            let original=try await get(master.id)
            try check((original.recipe["exposure"] as? NSNumber)?.doubleValue == 0,"master_adjustments_unchanged")
            await s.saveVersion("Shared snapshot")
            let versions=try await Backend.call("list_versions",["photo_id":master.id])
            try check((versions["versions"] as? [[String:Any]])?.first?["name"] as? String == "Shared snapshot","snapshot_visible_on_master")
            let current=try await get(copy.id)
            try check(await s.saveMetadata(targets:[current],patch:["copy_name":"Print crop"]),"copy_name_saved")
            try check(s.photo?.displayName.contains("Print crop") == true,"copy_name_displayed")
            await s.setCopyAsMaster()
            let promoted=try await get(copy.id)
            let demoted=try await get(master.id)
            try check(!promoted.isVirtual && demoted.isVirtual && promoted.id == copy.id,"master_roles_swap_without_new_ids")
            try check((promoted.recipe["exposure"] as? NSNumber)?.doubleValue == 1.25 && promoted.masterID == copy.id,"promoted_copy_keeps_recipe")
            await s.showPhotoFamily(promoted)
            try check(s.total == 2 && s.libraryFilters["source_id"] as? Int == promoted.sourceID,"family_view_is_bounded_source_filter")
            await s.showPhotoFamily(demoted,masterOnly:true)
            try await until { s.photo?.id == promoted.id && !s.loading }
            try check(s.total == 1 && s.photos.first?.id == promoted.id,"go_to_master_finds_promoted_master")
            await s.prepareCopyRemoval(ids:[master.id])
            let stale=s.copyRemovalTargets
            _=try await Backend.call("edit_metadata",["targets":[["photo_id":master.id,"expected_metadata_revision":demoted.metadataRevision]],"patch":["copy_name":"Keep newer name"]])
            try check(!(await s.removeVirtualCopies(stale)) && s.error?.contains("Metadata conflict") == true,"stale_removal_confirmation_preserves_new_metadata")
            s.error=nil
            let fresh=try await get(master.id)
            try check(fresh.copyName == "Keep newer name","conflicted_copy_remains")
            try check(await s.removeVirtualCopies([fresh]),"confirmed_copy_removed")
            try check(FileManager.default.fileExists(atPath:master.path),"source_file_survives_copy_removal")
            let remaining=try await Backend.call("list_versions",["photo_id":promoted.id])
            try check((remaining["versions"] as? [[String:Any]])?.count == 1,"shared_snapshot_survives_removal")
            s.libraryFilters=[:];s.librarySort="imported";s.sortDescending=true;await s.refresh()
            try check(await s.saveCollection(name:"Variants",kind:"regular",rules:[:],match:"all",original:nil,includePhotos:true),"collection_created_for_variants")
            await s.createVirtualCopies(ids:[promoted.id])
            try check(s.total == 2 && s.activeCollection?.name == "Variants","copy_created_inside_current_regular_collection")
            let rule=LibraryFilterDraft(["is_virtual":true,"copy_name":"Print"])
            try check(rule.rules["is_virtual"] as? Bool == true && rule.rules["copy_name"] as? String == "Print","virtual_filter_form_round_trips")
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
