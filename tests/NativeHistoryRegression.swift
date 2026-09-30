// Purpose: exercise native Develop history against the real service and broker.
// Inputs: two disposable originals. Outputs: bounded state, undo/redo, captured
// revision, navigation and source-safety assertions. No desktop or VoiceOver test.
import AppKit
import Foundation

@main struct NativeHistoryRegression {
    @MainActor static func main() async {
        _=NSApplication.shared
        let s=Store();var checks:[String:Bool]=[:]
        func check(_ value:Bool,_ name:String)throws {checks[name]=value;if !value {throw EngineFailure(message:name)}}
        func waitForEdit() async throws {
            for _ in 0..<400 {
                if !s.hasPendingEdits && !s.historyBusy {return}
                try await Task.sleep(nanoseconds:20_000_000)
            }
            throw EngineFailure(message:"Edit timed out")
        }
        func exposure()->Double {(s.recipe["exposure"] as? NSNumber)?.doubleValue ?? -99}
        func set(_ value:Double) async throws {s.set("exposure",value);try check(await s.flushEdits(),"save_\(value)")}
        do {
            let paths=ProcessInfo.processInfo.environment["LUMARAW_TEST_FIXTURES"]!.components(separatedBy:"|")
            let originals=try paths.map {try Data(contentsOf:URL(fileURLWithPath:$0))}
            await s.importPaths(paths);s.selected=1;s.selection=[1];await s.load(1);await s.readHistory()
            try check(s.historyPage?.steps.count==1 && s.historyPage?.steps.first?.id==0,"initial_import_state")
            try check(!s.canUndoDevelop && !s.canRedoDevelop,"initial_undo_redo_disabled")
            try await set(1);try await set(2);try await set(3);await s.readHistory()
            try check(s.historyPage?.steps.count==4 && s.canUndoDevelop && !s.canRedoDevelop,"three_edits_are_ordered_steps")
            let latest=s.historyPage!,oldStep=latest.steps[2].id
            s.undo();try await waitForEdit();await s.readHistory()
            try check(exposure()==2 && s.canRedoDevelop && s.historyPage?.steps.count==4,"undo_retains_future_states")
            s.redo();try await waitForEdit();await s.readHistory()
            try check(exposure()==3 && !s.canRedoDevelop,"redo_restores_full_recipe")
            let current=s.historyPage!
            s.moveDevelopHistory("select_history",step:oldStep,captured:current);try await waitForEdit();await s.readHistory()
            try check(exposure()==1 && s.canRedoDevelop,"select_earlier_step")
            try await set(-1);await s.readHistory()
            try check(s.historyPage?.steps.count==3 && !s.canRedoDevelop && s.historyPage!.cursor>latest.cursor,"new_edit_replaces_future_without_reusing_step_id")
            let branch=s.historyPage!
            s.moveDevelopHistory("rename_history",step:branch.cursor,name:"Final light",captured:branch)
            s.set("exposure",4)
            try await waitForEdit();await s.readHistory()
            try check(exposure()==(-1) && s.historyPage?.currentLabel=="Final light","history_mutation_blocks_concurrent_parameter_edit")
            s.moveDevelopHistory("select_history",step:0,captured:branch)
            try check(s.error?.contains("History changed")==true && exposure()==(-1),"old_native_history_capture_is_rejected")
            s.error=nil
            let stale=s.historyPage!
            _=try await Backend.call("edit_photo",["photo_id":1,"expected_revision":s.photo!.revision,"patch":["exposure":0.75]])
            s.moveDevelopHistory("clear_history",captured:stale);try await waitForEdit();await s.readHistory()
            try check(s.error != nil && exposure()==0.75,"external_edit_rejects_clear_and_reloads_without_replay")
            try check(s.historyPage!.steps.count==4,"conflicted_clear_preserves_history")
            s.error=nil
            let beforeSwitch=s.historyPage!
            s.selected=2;s.selection=[2];await s.load(2);await s.readHistory()
            try check(s.historyPage?.photoID==2 && !s.canUndoDevelop,"switch_replaces_history_context")
            s.moveDevelopHistory("select_history",step:0,captured:beforeSwitch)
            try check(s.error != nil && s.photo?.revision==0,"cross_photo_history_capture_rejected")
            s.error=nil;s.selected=1;s.selection=[1];await s.load(1)
            for i in 0..<65 {
                _=try await Backend.call("edit_photo",["photo_id":1,"expected_revision":s.photo!.revision+i,"patch":["exposure":Double(i%10)/10]])
            }
            await s.load(1);await s.readHistory()
            try check(s.historyPage?.steps.count==60 && s.historyPage?.nextBefore != nil,"native_page_bounds")
            await s.readHistory(before:s.historyPage!.nextBefore)
            try check(s.historyPage!.steps.last?.id==0 && s.historyBefore != nil,"older_page_reaches_import_state")
            let page=s.historyPage!
            s.moveDevelopHistory("select_history",step:0,captured:page);try await waitForEdit();await s.readHistory()
            try check(exposure()==0 && !s.canUndoDevelop && s.canRedoDevelop,"return_to_import_keeps_redo")
            let initial=s.historyPage!
            s.moveDevelopHistory("clear_history",captured:initial);try await waitForEdit();await s.readHistory()
            try check(s.historyPage?.steps.count==1 && s.historyPage?.currentLabel=="History cleared" && !s.canRedoDevelop,"clear_keeps_current_recipe_as_new_baseline")
            await s.load(1);await s.readHistory()
            try check(exposure()==0 && s.historyPage?.steps.count==1,"reload_preserves_cleared_baseline")
            try check(try paths.map {try Data(contentsOf:URL(fileURLWithPath:$0))} == originals,"all_workflows_preserve_original_bytes")
            print(String(data:try JSONSerialization.data(withJSONObject:["ok":true,"checks":checks,"desktop_ui":"NOT_VERIFIED","voiceover":"NOT_VERIFIED"],options:[.prettyPrinted,.sortedKeys]),encoding:.utf8)!)
            exit(0)
        } catch {
            print(String(data:try! JSONSerialization.data(withJSONObject:["ok":false,"checks":checks,"error":error.localizedDescription,"store_error":s.error ?? ""],options:.prettyPrinted),encoding:.utf8)!)
            exit(1)
        }
    }
}
