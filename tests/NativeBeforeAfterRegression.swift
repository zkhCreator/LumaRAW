// Purpose: verify native comparison actions against real worker/broker replies.
// Inputs: isolated photographs and catalog. Outputs: preview context, copied
// recipes, history/conflict and source-safety assertions. No desktop input or
// VoiceOver acceptance; comparison state has no global application undo yet.
import AppKit
import Foundation

@main struct NativeBeforeAfterRegression {
    @MainActor static func main() async {
        _=NSApplication.shared
        let s=Store();var checks:[String:Bool]=[:]
        func check(_ value:Bool,_ name:String)throws {checks[name]=value;if !value {throw EngineFailure(message:name)}}
        func ready() async throws {
            for _ in 0..<500 {
                if !s.hasPendingEdits && !s.historyBusy && !s.rendering && s.preview != nil &&
                    (!s.needsBeforePreview || s.before != nil && s.beforePreviewContext==s.currentBeforeContext) {return}
                try await Task.sleep(nanoseconds:20_000_000)
            }
            throw EngineFailure(message:"Comparison preview timed out")
        }
        func waitForEdit() async throws {
            for _ in 0..<400 {
                if !s.hasPendingEdits && !s.historyBusy {return}
                try await Task.sleep(nanoseconds:20_000_000)
            }
            throw EngineFailure(message:"Comparison edit timed out")
        }
        func exposure()->Double {(s.recipe["exposure"] as? NSNumber)?.doubleValue ?? -99}
        func set(_ value:Double) async throws {
            s.set("exposure",value);try check(await s.flushEdits(),"save_\(value)")
            try await ready();await s.readHistory()
        }
        do {
            let paths=ProcessInfo.processInfo.environment["LUMARAW_TEST_FIXTURES"]!.components(separatedBy:"|")
            let originals=try paths.map {try Data(contentsOf:URL(fileURLWithPath:$0))}
            await s.importPaths(paths);s.selected=1;s.selection=[1];s.develop=true;await s.load(1)
            try await ready();await s.readHistory()
            try check(s.before==nil && !s.needsBeforePreview,"after_only_skips_before_processing")
            try await set(1)
            let first=s.historyPage!.cursor
            s.beforeAfter("after_to_before");try await waitForEdit();await s.readHistory()
            try check(exposure()==1 && s.historyPage?.steps.count==2,"copy_after_preserves_recipe_and_history")
            try await set(2)
            s.setComparisonMode("before");try await ready()
            try check(s.compare && s.before != nil && s.beforeLabel=="Copied from After","before_mode_loads_saved_snapshot")
            try check(s.before?.tiffRepresentation != s.preview?.tiffRepresentation,"before_pixels_differ_from_current_after")
            let cached=s.before
            s.setComparisonMode("after");s.setComparisonMode("before")
            try check(!s.rendering && s.before === cached,"unchanged_toggle_reuses_loaded_before_image")
            s.setComparisonMode("split");try await ready()
            try check(s.splitCompare && !s.compare && !s.detail,"split_mode_keeps_aligned_fit_preview")
            await s.readHistory();let history=s.historyPage!,count=history.steps.count
            s.beforeAfter("history_to_before",step:first,captured:history);try await waitForEdit();try await ready();await s.readHistory()
            try check(exposure()==2 && s.historyPage?.steps.count==count && s.beforeLabel.hasPrefix("Exposure"),"history_step_copies_to_before_without_selecting_it")
            s.beforeAfter("swap");try await waitForEdit();try await ready();await s.readHistory()
            try check(exposure()==1 && s.historyPage?.steps.count==count+1,"swap_updates_after_in_one_history_step")
            s.beforeAfter("before_to_after");try await waitForEdit();try await ready();await s.readHistory()
            try check(exposure()==2,"copy_before_to_after_uses_complete_saved_recipe")
            let snapshot=s.before?.tiffRepresentation
            s.moveDevelopHistory("clear_history",captured:s.historyPage);try await waitForEdit();try await ready();await s.readHistory()
            try check(s.before?.tiffRepresentation==snapshot && s.historyPage?.steps.count==1,"clear_history_does_not_retarget_before")
            let stale=s.historyPage!
            _=try await Backend.call("edit_photo",["photo_id":1,"expected_revision":s.photo!.revision,"patch":["exposure":0.25]])
            s.beforeAfter("swap",captured:stale);try await waitForEdit();try await ready();await s.readHistory()
            try check(s.error != nil && exposure()==0.25,"external_change_rejects_swap_without_replay")
            s.error=nil
            let wrongPhoto=s.historyPage!
            s.selected=2;s.selection=[2];await s.load(2);try await ready();await s.readHistory()
            s.beforeAfter("history_to_before",step:0,captured:wrongPhoto)
            try check(s.error != nil && s.photo?.revision==0,"captured_history_cannot_target_another_photo")
            s.error=nil
            s.setComparisonMode("before");try await ready()
            try check(s.beforeLabel=="Import" && s.beforePreviewContext?.photoID==2,"switch_loads_that_photos_initial_before")
            s.detail=true;s.render(debounce:false);try await ready()
            try check(s.beforePreviewContext?.detail==true && s.before != nil,"detail_view_loads_matching_before_context")
            s.setComparisonMode("after");s.set("exposure",0.5);let revision=s.photo!.revision
            s.beforeAfter("after_to_before")
            try check(s.photo!.revision==revision,"pending_edit_blocks_comparison_mutation")
            try check(await s.flushEdits(),"pending_edit_saves_normally")
            try check(try paths.map {try Data(contentsOf:URL(fileURLWithPath:$0))} == originals,"comparison_workflows_preserve_original_bytes")
            print(String(data:try JSONSerialization.data(withJSONObject:["ok":true,"checks":checks,"desktop_ui":"NOT_VERIFIED","voiceover":"NOT_VERIFIED"],options:[.prettyPrinted,.sortedKeys]),encoding:.utf8)!)
            exit(0)
        } catch {
            print(String(data:try! JSONSerialization.data(withJSONObject:["ok":false,"checks":checks,"error":error.localizedDescription,"store_error":s.error ?? ""],options:.prettyPrinted),encoding:.utf8)!)
            exit(1)
        }
    }
}
