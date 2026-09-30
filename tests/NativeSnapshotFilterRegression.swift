// Purpose: verify live snapshot-status filters and smart sources through IPC.
// Inputs: two generated originals. Outputs: shared-family membership, empty-page
// polling, captured form/pending edit guards and preserved source bytes. These
// state checks do not prove rendered filter pickers, desktop events or VoiceOver.
import AppKit
import Foundation

@main struct NativeSnapshotFilterRegression {
    @MainActor static func main() async {
        _=NSApplication.shared
        let s=Store();var checks:[String:Bool]=[:]
        func check(_ value:Bool,_ name:String)throws {checks[name]=value;if !value {throw EngineFailure(message:name)}}
        func save(_ id:Int,_ name:String) async throws -> [String:Any] {
            let result=try await Backend.call("save_version",["photo_id":id,"name":name])
            return result["version"] as! [String:Any]
        }
        func delete(_ row:[String:Any],_ id:Int=1) async throws {
            _=try await Backend.call("delete_version",["photo_id":id,"version_id":row["id"]!,"expected_version_revision":row["revision"]!])
        }
        do {
            let paths=ProcessInfo.processInfo.environment["LUMARAW_TEST_FIXTURES"]!.components(separatedBy:"|")
            let originals=try paths.map {try Data(contentsOf:URL(fileURLWithPath:$0))}
            var draft=LibraryFilterDraft(["has_snapshots":false,"source_id":9])
            try check(draft.snapshotPresence=="absent" && draft.rules["has_snapshots"] as? Bool == false,"false_filter_round_trips")
            draft.snapshotPresence="present"
            try check(draft.rules["has_snapshots"] as? Bool == true && draft.rules["source_id"] as? Int == 9,"true_filter_preserves_unrelated_criteria")
            draft.snapshotPresence="any"
            try check(draft.rules["has_snapshots"]==nil,"any_removes_presence_rule")
            await s.importPaths(paths);s.showStacks=false;s.libraryFilters=["has_snapshots":true];await s.refresh()
            try check(s.total==0 && s.photo==nil,"initial_filtered_page_is_empty")
            let first=try await save(1,"First")
            await s.refreshVisibleSummaries()
            try check(s.total==1 && s.selected==1 && s.photos.first?.id==1,"empty_page_detects_external_first_snapshot")
            let revision=s.snapshotFilterRevision
            let second=try await save(1,"Second")
            await s.refreshVisibleSummaries()
            try check(s.snapshotFilterRevision==revision && s.total==1,"additional_snapshot_does_not_invalidate_page")
            _=try await Backend.call("rename_version",["photo_id":1,"version_id":second["id"]!,"expected_version_revision":second["revision"]!,"name":"Renamed"])
            await s.refreshVisibleSummaries()
            try check(s.snapshotFilterRevision==revision,"rename_does_not_invalidate_presence")
            try await delete(first);await s.refreshVisibleSummaries()
            try check(s.total==1 && s.snapshotFilterRevision==revision,"nonfinal_delete_keeps_presence")
            var renamed=second;renamed["revision"]=1
            s.prepareSnapshot();let captured=s.snapshotDraft!
            try await delete(renamed);await s.refreshVisibleSummaries()
            try check(s.total==1 && s.snapshotDraft?.id==captured.id && s.snapshotFilterRevision==revision,"open_snapshot_form_defers_membership_refresh")
            s.snapshotDraft=nil;await s.refreshVisibleSummaries()
            try check(s.total==0 && s.selected==nil && s.snapshotFilterRevision>revision,"closing_form_allows_last_snapshot_removal")
            s.libraryFilters=["has_snapshots":false];await s.refresh()
            try check(s.total==2,"no_snapshots_filter_includes_both_originals")
            s.selected=1;s.selection=[1];await s.load(1)
            s.set("exposure",0.6)
            let pendingToken=s.snapshotFilterRevision
            let third=try await save(1,"External while editing")
            await s.refreshVisibleSummaries()
            try check(s.total==2 && s.selected==1 && s.snapshotFilterRevision==pendingToken,"pending_adjustment_defers_presence_refresh")
            try check(await s.flushEdits(),"pending_adjustment_saves")
            await s.refreshVisibleSummaries()
            try check(s.total==1 && s.photos.first?.id==2 && s.snapshotFilterRevision>pendingToken,"completed_edit_allows_membership_refresh")
            let edited=Photo(try await Backend.call("get_photo",["photo_id":1]))!
            try check((edited.recipe["exposure"] as? NSNumber)?.doubleValue==0.6,"filter_refresh_preserves_saved_adjustment")
            s.libraryFilters=[:];s.collectionID=nil;await s.refresh()
            let unfiltered=s.snapshotFilterRevision
            let fourth=try await save(2,"Other original")
            let changed=try await Backend.call("library_state")
            try check(!s.snapshotFilterChanged(changed),"unfiltered_library_avoids_unnecessary_page_refresh")
            await s.refreshVisibleSummaries()
            try check(s.total==2 && s.snapshotFilterRevision==unfiltered,"unfiltered_page_remains_stable")
            try check(await s.saveCollection(name:"With snapshots",kind:"smart",rules:["has_snapshots":true],match:"all",original:nil),"save_snapshot_smart_collection")
            try check(s.total==2 && s.activeCollection?.rules["has_snapshots"] as? Bool == true,"smart_collection_retains_presence_rule")
            try await delete(fourth,2);await s.refreshVisibleSummaries()
            try check(s.total==1 && s.photos.first?.id==1,"active_smart_collection_updates_membership")
            let smart=s.activeCollection!
            let root=LibraryCollection(try await Backend.call("save_collection",["name":"Root","kind":"set"]))!
            _=try await Backend.call("save_collection",["collection_id":smart.id,"expected_revision":smart.revision,"name":smart.name,"kind":"smart","rules":smart.rules,"parent_id":root.id])
            await s.openCollection(root)
            try check(s.total==1,"collection_set_includes_nested_smart_members")
            try await delete(third);await s.refreshVisibleSummaries()
            try check(s.total==0 && s.collectionID==root.id,"empty_nested_set_retains_source")
            _=try await save(2,"Set refill");await s.refreshVisibleSummaries()
            try check(s.total==1 && s.photos.first?.id==2 && s.collectionID==root.id,"empty_set_repopulates_after_external_snapshot")
            let stale:[String:Any]=["snapshot_filter_revision":s.snapshotFilterRevision-1]
            try check(!s.snapshotFilterChanged(stale),"older_presence_receipt_never_regresses_state")
            try check(try paths.map {try Data(contentsOf:URL(fileURLWithPath:$0))} == originals,"all_filter_workflows_preserve_original_bytes")
            print(String(data:try JSONSerialization.data(withJSONObject:["ok":true,"checks":checks,"desktop_ui":"NOT_VERIFIED","voiceover":"NOT_VERIFIED"],options:[.prettyPrinted,.sortedKeys]),encoding:.utf8)!)
            exit(0)
        } catch {
            print(String(data:try! JSONSerialization.data(withJSONObject:["ok":false,"checks":checks,"error":error.localizedDescription,"store_error":s.error ?? ""],options:.prettyPrinted),encoding:.utf8)!)
            exit(1)
        }
    }
}
