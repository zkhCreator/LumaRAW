// Purpose: exercise snapshot capture and sharing through native Store and IPC.
// Inputs: two disposable originals. Outputs: recipe/history/Before isolation,
// paging, stale forms and preserved source bytes. No desktop or VoiceOver test.
import AppKit
import Foundation

@main struct NativeSnapshotsRegression {
    @MainActor static func main() async {
        _=NSApplication.shared
        let s=Store();var checks:[String:Bool]=[:]
        func check(_ value:Bool,_ name:String)throws {checks[name]=value;if !value {throw EngineFailure(message:name)}}
        func exposure()->Double {(s.recipe["exposure"] as? NSNumber)?.doubleValue ?? -99}
        func set(_ value:Double) async throws {s.set("exposure",value);try check(await s.flushEdits(),"save_\(value)")}
        func waitForCopy() async throws {
            for _ in 0..<400 {
                if s.photo?.isVirtual==true && !s.loading {return}
                try await Task.sleep(nanoseconds:20_000_000)
            }
            throw EngineFailure(message:"Virtual copy selection timed out")
        }
        func capture()throws ->SnapshotDraft {
            guard let page=s.snapshotPage,let row=page.entries.first else {throw EngineFailure(message:"Missing snapshot")}
            return SnapshotDraft(page:page,version:row)
        }
        do {
            let paths=ProcessInfo.processInfo.environment["LUMARAW_TEST_FIXTURES"]!.components(separatedBy:"|")
            let originals=try paths.map {try Data(contentsOf:URL(fileURLWithPath:$0))}
            await s.importPaths(paths);s.selected=1;s.selection=[1];s.develop=true;await s.load(1);await s.readVersions()
            try check(s.snapshotPage?.entries.isEmpty==true && s.snapshotReady,"initial_snapshot_state")
            try await set(1);await s.readHistory()
            let firstStep=s.historyPage!.cursor
            s.prepareSnapshot();let draft=s.snapshotDraft!
            try check(await s.applySnapshotDraft(draft,name:"Light"),"create_captured_current_snapshot")
            s.snapshotDraft=nil
            let initial=try capture(),created=initial.version!.created
            try check(s.snapshotPage?.entries.count==1 && initial.version!.revision==0,"created_summary_has_version_token")
            s.prepareSnapshotRename(initial.version!,page:s.snapshotPage!)
            try check(await s.applySnapshotDraft(s.snapshotDraft!,name:"Bright"),"rename_captured_snapshot")
            s.snapshotDraft=nil
            try check(s.snapshotPage?.entries.first?.created==created && s.snapshotPage?.entries.first?.revision==1,"rename_preserves_identity_and_creation_time")
            try await set(2);await s.readVersions(onlyChanged:true)
            try check(s.snapshotPage?.photoRevision==s.photo?.revision,"unchanged_list_refreshes_photo_capture")
            try check(await s.performSnapshot("update_version",captured:try capture()),"update_current_settings")
            try check(await s.performSnapshot("before_after",captured:try capture()),"copy_snapshot_to_before")
            try await set(3);await s.readVersions(onlyChanged:true)
            try check(await s.performSnapshot("update_version",captured:try capture()),"replace_snapshot_after_before_copy")
            do {
                _=try await Backend.call("before_after",["photo_id":1,"expected_revision":s.photo!.revision,"action":"before_to_after"])
                await s.load(1);await s.readVersions()
                try check(exposure()==2,"before_value_stays_frozen_after_snapshot_update")
            }
            try check(await s.performSnapshot("restore_version",captured:try capture()),"restore_snapshot")
            try check(exposure()==3,"restore_uses_new_snapshot_settings")
            await s.readHistory();let cursor=s.historyPage!.cursor,revision=s.photo!.revision
            s.prepareSnapshot(step:firstStep,history:s.historyPage)
            try check(await s.applySnapshotDraft(s.snapshotDraft!,name:"Earlier"),"snapshot_from_retained_history")
            s.snapshotDraft=nil;await s.readHistory()
            try check(s.historyPage?.cursor==cursor && s.photo?.revision==revision && exposure()==3,"history_snapshot_does_not_move_cursor_or_edit_photo")
            let stale=try capture()
            _=try await Backend.call("rename_version",["photo_id":1,"version_id":stale.version!.id,"expected_version_revision":stale.version!.revision,"name":"Changed externally"])
            try check(!(await s.performSnapshot("delete_version",captured:stale)) && s.snapshotError?.contains("Snapshot conflict")==true,"stale_snapshot_delete_is_rejected_without_replay")
            await s.readVersions(onlyChanged:true)
            try check(s.snapshotError?.contains("Snapshot conflict")==true,"background_poll_preserves_visible_conflict")
            await s.readVersions();let count=s.snapshotPage!.entries.count
            s.prepareSnapshot();let stalePhoto=s.snapshotDraft!
            _=try await Backend.call("edit_photo",["photo_id":1,"expected_revision":s.photo!.revision,"patch":["exposure":0.75]])
            try check(!(await s.applySnapshotDraft(stalePhoto,name:"Must not exist")) && s.snapshotError?.contains("Edit conflict")==true,"external_photo_change_rejects_captured_create")
            await s.refreshSnapshotPhoto()
            try check(exposure()==0.75 && s.snapshotPage?.entries.count==count && !s.snapshotCaptureValid(stalePhoto),"explicit_refresh_keeps_open_form_stale")
            s.snapshotDraft=nil
            let crossPhoto=try capture()
            s.selected=2;s.selection=[2];await s.load(2);await s.readVersions()
            try check(!(await s.performSnapshot("restore_version",captured:crossPhoto)) && exposure()==0,"capture_cannot_target_another_original")
            s.selected=1;s.selection=[1];await s.load(1);await s.readVersions()
            await s.createVirtualCopies(ids:[1]);try await waitForCopy();await s.readVersions()
            try check(s.photo?.isVirtual==true && s.snapshotPage?.entries.count==count && s.snapshotPage?.sourceID==crossPhoto.sourceID,"virtual_copy_sees_shared_snapshot_page")
            let shared=try capture()
            try check(await s.performSnapshot("delete_version",captured:shared),"shared_delete_from_copy")
            let master=SnapshotPage(try await Backend.call("list_versions",["photo_id":1]))!
            try check(master.entries.count==count-1,"shared_delete_visible_from_original")
            s.selected=1;s.selection=[1];await s.load(1)
            for i in 0..<65 {
                _=try await Backend.call("save_version",["photo_id":1,"expected_revision":s.photo!.revision,"name":String(format:"Page %03d",i)])
            }
            await s.readVersions()
            try check(s.snapshotPage?.entries.count==60 && s.snapshotPage?.nextAfter != nil,"bounded_alphabetical_first_page")
            await s.readVersions(after:s.snapshotPage!.nextAfter)
            let after=s.snapshotAfter,pageNames=s.snapshotPage!.entries.map(\.name)
            try check(pageNames.count==6 && pageNames==pageNames.sorted(),"bounded_alphabetical_next_page")
            await s.readVersions(onlyChanged:true)
            try check(s.snapshotAfter==after && s.snapshotPage!.entries.map(\.name)==pageNames,"conditional_poll_preserves_deep_page")
            _=try await Backend.call("save_version",["photo_id":1,"name":"A external snapshot"])
            await s.readVersions(onlyChanged:true)
            try check(s.snapshotAfter==nil && s.snapshotPage?.entries.first?.name=="A external snapshot","changed_list_returns_first_page")
            s.snapshotBusy=true;s.set("exposure",4)
            try check(!s.hasPendingEdits && !s.historyReady && exposure()==0.75,"snapshot_command_blocks_parameter_and_history_edits")
            s.snapshotBusy=false
            s.set("exposure",0.5);s.prepareSnapshot()
            try check(s.snapshotDraft==nil && !s.snapshotReady,"pending_edit_blocks_new_capture")
            try check(await s.flushEdits(),"pending_edit_commits_normally")
            try check(try paths.map {try Data(contentsOf:URL(fileURLWithPath:$0))} == originals,"snapshot_workflows_preserve_original_bytes")
            print(String(data:try JSONSerialization.data(withJSONObject:["ok":true,"checks":checks,"desktop_ui":"NOT_VERIFIED","voiceover":"NOT_VERIFIED"],options:[.prettyPrinted,.sortedKeys]),encoding:.utf8)!)
            exit(0)
        } catch {
            print(String(data:try! JSONSerialization.data(withJSONObject:["ok":false,"checks":checks,"error":error.localizedDescription,"store_error":s.error ?? "","snapshot_error":s.snapshotError ?? ""],options:.prettyPrinted),encoding:.utf8)!)
            exit(1)
        }
    }
}
