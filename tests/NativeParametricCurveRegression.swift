// Purpose: parametric graph geometry, draft scheduling and captured native edits.
// Inputs: generated photographs, engine geometry samples and the real broker.
// Outputs: validation, preview, undo/sync and conflict assertions. No rendered
// desktop layout, actual slider/key/pointer dispatch or VoiceOver evidence.
import AppKit
import Foundation

@main struct NativeParametricCurveRegression {
    @MainActor static func main() async {
        _=NSApplication.shared
        let s=Store();var checks:[String:Bool]=[:]
        func check(_ value:Bool,_ name:String) throws {checks[name]=value;if !value {throw EngineFailure(message:name)}}
        func photo(_ id:Int) async throws -> Photo {Photo(try await Backend.call("get_photo",["photo_id":id]))!}
        func waitForPreview() async throws {
            for _ in 0..<400 {if !s.rendering,s.preview != nil {return};try await Task.sleep(nanoseconds:20_000_000)}
            throw EngineFailure(message:"Preview timed out")
        }
        do {
            let paths=ProcessInfo.processInfo.environment["LUMARAW_TEST_FIXTURES"]!.components(separatedBy:"|")
            let originals=try paths.map {try Data(contentsOf:URL(fileURLWithPath:$0))}
            let fixtures=try JSONSerialization.jsonObject(with:Data(contentsOf:URL(fileURLWithPath:ProcessInfo.processInfo.environment["LUMARAW_TEST_CURVES"]!))) as! [[String:Any]]
            var error=0.0
            for item in fixtures {
                let values=ParametricCurveValues(recipe:item["recipe"] as! [String:Any])
                for sample in item["samples"] as! [[Double]] {error=max(error,abs(values.output(sample[0])-sample[1]))}
            }
            try check(error<1e-6,"native_graph_geometry_matches_engine_including_one_percent_regions")
            let defaults=ParametricCurveValues.defaults
            try check(defaults.valid && defaults.splits == [0.25,0.5,0.75],"normalized_defaults_and_four_regions")
            try check([0.0,0.249,0.25,0.5,0.75,1].map {defaults.region($0)} == [0,0,1,2,3,3],"graph_inputs_select_the_correct_region")
            let moved=defaults.movedSplit(1,to:0.8)
            try check(moved.splits[1] == 0.74 && moved.valid && moved.amounts == defaults.amounts,"divider_cannot_cross_neighbor_or_change_amounts")
            try check(defaults.movedSplit(0,to:-1).splits[0] == 0.01 && defaults.movedSplit(2,to:2).splits[2] == 0.99,"end_dividers_leave_one_percent_regions")
            try check(defaults.adjusted(0,to:200).amounts[0] == 100 && defaults.adjusted(3,to:-200).amounts[3] == -100,"graph_drag_limits_amounts")
            let pointer=defaults.draggedRegion(1,input:0.375,target:0.42)
            try check(abs(pointer.output(0.375)-0.42)<1e-7 && pointer.amounts[0] == 0 && pointer.splits == defaults.splits,"graph_drag_follows_target_output_in_the_captured_region")
            try check(defaults.draggedRegion(0,input:0,target:0.2) == defaults && defaults.draggedRegion(3,input:0.875,target:1).amounts[3] == 100,"graph_drag_preserves_fixed_black_and_clamps_unreachable_output")
            await s.importPaths(paths);s.selected=1;s.selection=[1];await s.load(1)
            let capture=s.captureParametricCurve()!,before=try await photo(1)
            let draft=capture.values.adjusted(1,to:60).adjusted(3,to:-65).movedSplit(0,to:0.2).movedSplit(2,to:0.8)
            s.render(curveDraft:capture.preview(draft),debounce:false);try await waitForPreview()
            let previewed=try await photo(1)
            try check(s.message.hasPrefix("Curve preview") && previewed.revision == before.revision && s.parametricCurve == capture.values,"parametric_preview_never_saves_recipe_or_revision")
            let scheduler=CurvePreviewScheduler()
            var latest=draft.adjusted(1,to:10),reads=0
            var sampledAmount:Double?
            s.cancelMainPreview();s.rendering=true
            scheduler.request(store:s) {reads+=1;sampledAmount=latest.amounts[1];return capture.preview(latest)}
            latest=draft.adjusted(1,to:70)
            scheduler.request(store:s) {reads+=100;return capture.preview(draft)}
            try await Task.sleep(nanoseconds:240_000_000)
            try check(reads == 0,"pending_curve_preview_waits_for_in_flight_image")
            s.rendering=false
            for _ in 0..<100 {if reads>0 {break};try await Task.sleep(nanoseconds:20_000_000)}
            try await waitForPreview()
            try check(reads == 1 && sampledAmount == 70 && s.message.hasPrefix("Curve preview"),"repeated_drafts_coalesce_to_one_latest_request")
            scheduler.request(store:s) {reads+=1;return capture.preview(draft)};scheduler.cancel()
            try await Task.sleep(nanoseconds:220_000_000)
            try check(reads == 1,"cancelled_pending_draft_never_launches_a_preview")
            let accepted=s.commitParametricCurve(capture,draft),saved=await s.flushEdits()
            try check(accepted && saved,"captured_region_and_split_gesture_saves")
            let after=try await photo(1)
            try check(after.revision == before.revision+1 && s.parametricCurve == draft,"many_draft_changes_save_one_history_step")
            let discarded=s.captureParametricCurve()!;_ = discarded.values.adjusted(0,to:80)
            let same=try await photo(1)
            try check(same.revision == after.revision,"discarded_gesture_preserves_saved_curve")
            s.setParametricCurve(draft.movedSplit(2,to:0.501));try check(await s.flushEdits(),"split_only_edit_saves")
            s.setPointCurve("curve_blue_points",[[0,0.1],[1,0.9]]);s.set("curve_midtones",9)
            try check(await s.flushEdits(),"point_and_legacy_curves_remain_independent")
            let prior=s.parametricCurve
            s.setParametricCurve(.defaults);try check(await s.flushEdits(),"parametric_reset_saves")
            try check(s.pointCurve("curve_blue_points") == [[0,0.1],[1,0.9]] && (s.recipe["curve_midtones"] as? NSNumber)?.intValue == 9,"parametric_reset_preserves_point_and_legacy_curves")
            s.undo()
            for _ in 0..<200 {if !s.editing {break};try await Task.sleep(nanoseconds:20_000_000)}
            try check(s.parametricCurve == prior,"undo_restores_region_values_and_splits_together")
            let stale=s.captureParametricCurve()!
            _=try await Backend.call("edit_photo",["photo_id":1,"expected_revision":s.photo!.revision,"patch":["parametric_highlights":10]])
            await s.load(1)
            try check(!s.commitParametricCurve(stale,.defaults),"observed_external_edit_rejects_captured_gesture")
            s.error=nil
            let unseen=s.captureParametricCurve()!
            _=try await Backend.call("edit_photo",["photo_id":1,"expected_revision":s.photo!.revision,"patch":["parametric_darks":22]])
            try check(s.commitParametricCurve(unseen,unseen.values.adjusted(2,to:60)),"unseen_write_keeps_captured_service_revision")
            let failed=await s.flushEdits()
            try check(!failed && s.error != nil && s.parametricCurve.amounts[1] == 22,"service_conflict_preserves_external_parametric_values")
            s.error=nil
            let switched=s.captureParametricCurve()!
            s.selected=2;s.selection=[2];await s.load(2)
            let rejected=s.commitParametricCurve(switched,draft),second=try await photo(2)
            try check(!rejected && second.revision == 0,"photo_switch_never_retargets_curve_gesture")
            s.error=nil
            let pending=s.captureParametricCurve()!
            s.set("exposure",0.75)
            try check(s.captureParametricCurve() == nil && !s.commitParametricCurve(pending,draft),"pending_other_edits_block_gesture_interleaving")
            try check(await s.flushEdits(),"rejected_gesture_retains_pending_exposure")
            s.error=nil
            var invalid=s.parametricCurve;invalid.splits=[0.2,0.2,0.8]
            let clean=try await photo(2)
            s.setParametricCurve(invalid);_ = await s.flushEdits()
            let unchanged=try await photo(2)
            try check(unchanged.revision == clean.revision && s.error != nil,"invalid_splits_never_write_a_recipe")
            s.error=nil;s.selected=1;s.selection=[1,2];await s.load(1);await s.sync(["Tone Curve"])
            let synced=try await photo(2)
            try check(ParametricCurveValues(recipe:synced.recipe) == s.parametricCurve,"tone_curve_sync_copies_regions_and_splits")
            try check((synced.recipe["exposure"] as? NSNumber)?.doubleValue == 0.75,"curve_sync_preserves_unselected_adjustments")
            try check(try paths.map {try Data(contentsOf:URL(fileURLWithPath:$0))} == originals,"parametric_workflows_preserve_original_bytes")
            print(String(data:try JSONSerialization.data(withJSONObject:["ok":true,"checks":checks,"plot_max_error":error,
                "desktop_ui":"NOT_VERIFIED","keyboard_pointer_voiceover":"NOT_VERIFIED"],options:[.prettyPrinted,.sortedKeys]),encoding:.utf8)!)
            exit(0)
        } catch {
            print(String(data:try! JSONSerialization.data(withJSONObject:["ok":false,"checks":checks,"error":error.localizedDescription,"store_error":s.error ?? ""],options:.prettyPrinted),encoding:.utf8)!)
            exit(1)
        }
    }
}
