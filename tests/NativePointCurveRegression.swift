// Purpose: native point-curve geometry and captured edits over the real broker.
// Inputs: generated photographs and engine-generated curve geometry fixtures.
// Outputs: units, endpoint, gesture, conflict, undo and persistence assertions.
// No rendered desktop, actual key/pointer dispatch or VoiceOver verification.
import AppKit
import Foundation

@main struct NativePointCurveRegression {
    @MainActor static func main() async {
        _=NSApplication.shared
        let s=Store()
        var checks:[String:Bool]=[:]
        func check(_ value:Bool,_ name:String) throws {
            checks[name]=value
            if !value { throw EngineFailure(message:name) }
        }
        func photo(_ id:Int) async throws -> Photo {
            Photo(try await Backend.call("get_photo",["photo_id":id]))!
        }
        func waitForEdit() async throws {
            for _ in 0..<200 {
                if !s.editing { return }
                try await Task.sleep(nanoseconds:20_000_000)
            }
            throw EngineFailure(message:"Edit timed out")
        }
        func waitForPreview() async throws {
            for _ in 0..<400 {
                if !s.rendering,s.preview != nil {return}
                try await Task.sleep(nanoseconds:20_000_000)
            }
            throw EngineFailure(message:"Preview timed out")
        }
        do {
            let paths=ProcessInfo.processInfo.environment["LUMARAW_TEST_FIXTURES"]!.components(separatedBy:"|")
            let originals=try paths.map { try Data(contentsOf:URL(fileURLWithPath:$0)) }
            let geometryPath=ProcessInfo.processInfo.environment["LUMARAW_TEST_CURVES"]!
            let fixtures=try JSONSerialization.jsonObject(with:Data(contentsOf:URL(fileURLWithPath:geometryPath))) as! [[String:Any]]
            var largestError=0.0
            for item in fixtures {
                let points=item["points"] as! [[Double]],samples=item["samples"] as! [[Double]]
                for sample in samples {
                    largestError=max(largestError,abs(PointCurvePlot.value(sample[0],points:points)-sample[1]))
                }
            }
            try check(largestError<0.0002,"native_plot_geometry_matches_engine_spline_including_narrow_segments")
            let added=PointCurveFields.inserted(PointCurveFields.identity,x:0.5,y:0.7)!
            try check(added.index == 1 && added.points.count == 3,"click_insertion_keeps_input_order")
            let limited=PointCurveFields.moved(added.points,index:1,x:2,y:-1)
            try check(limited[1][0]<1 && limited[1][1] == 0 && PointCurveFields.valid(limited),"moving_points_clamps_output_and_cannot_cross_neighbors")
            let endpoint=PointCurveFields.moved(added.points,index:0,x:0.15,y:0.2)
            try check(endpoint[0] == [0.15,0.2],"new_curve_black_endpoint_moves_in_both_axes")
            let oldEndpoint=PointCurveFields.moved(added.points,index:0,x:0.15,y:0.9,legacy:true)
            try check(oldEndpoint[0][0] == 0 && oldEndpoint[0][1] == 0.7,"legacy_endpoint_rules_remain_fixed_and_monotone")
            try check(PointCurveFields.removed(added.points,index:0) == added.points && PointCurveFields.removed(added.points,index:1) == PointCurveFields.identity,"delete_preserves_two_endpoints")
            let maximum=(0..<16).map { [Double($0)/15,Double($0%2)] }
            try check(PointCurveFields.valid(maximum) && PointCurveFields.inserted(maximum,x:0.1,y:0.4) == nil,"sixteen_point_capacity_is_explicit")
            await s.importPaths(paths)
            s.selected=1;s.selection=[1];await s.load(1);await s.loadPointCurvePresets()
            try check(s.pointCurvePresets.count == 3 && s.pointCurvePresets["Linear"] == PointCurveFields.identity,"curve_presets_come_from_engine_schema")
            let capture=s.capturePointCurve("curve_rgb_points")!
            let before=try await photo(1)
            var draft=PointCurveFields.inserted(capture.points,x:0.35,y:0.22)!.points
            draft=PointCurveFields.moved(draft,index:1,x:0.4,y:0.3)
            try check(try await photo(1).revision == before.revision && s.pointCurve("curve_rgb_points") == capture.points,"drag_draft_does_not_write_before_release")
            s.render(curveDraft:(capture,draft),debounce:false);try await waitForPreview()
            let previewed=try await photo(1)
            try check(s.message.hasPrefix("Curve preview") && previewed.revision == before.revision && s.pointCurve("curve_rgb_points") == capture.points,"temporary_native_preview_does_not_save_the_draft")
            let accepted=s.commitPointCurve(capture,draft),flushed=await s.flushEdits()
            try check(accepted && flushed,"drag_release_persists_captured_curve")
            let after=try await photo(1)
            try check(after.revision == before.revision+1 && s.pointCurve("curve_rgb_points") == draft,"one_curve_drag_is_one_history_step")
            let cancel=s.capturePointCurve("curve_rgb_points")!
            _=PointCurveFields.moved(cancel.points,index:1,x:0.5,y:0.8)
            try check(try await photo(1).revision == after.revision,"discarding_drag_keeps_catalog_unchanged")
            s.setPointCurve("curve_red_points",s.pointCurvePresets["Medium Contrast"]!)
            s.setPointCurve("curve_blue_points",[[0,0.1],[0.8,0.85],[1,0.9]])
            s.set("curve_points",[[0,0],[0.3,0.4],[1,1]])
            try check(await s.flushEdits(),"channel_presets_and_legacy_curve_save_together")
            try check(s.pointCurve("curve_green_points") == PointCurveFields.identity && s.pointCurve("curve_rgb_points") == draft,"channel_edit_preserves_other_curves")
            s.resetRGBPointCurves();try check(await s.flushEdits(),"all_rgb_curves_reset")
            try check(PointCurveFields.keys.allSatisfy { s.pointCurve($0) == PointCurveFields.identity } && s.pointCurve("curve_points") == [[0,0],[0.3,0.4],[1,1]],"rgb_reset_preserves_legacy_luminance")
            s.undo();try await waitForEdit()
            try check(s.pointCurve("curve_rgb_points") == draft && s.pointCurve("curve_blue_points") == [[0,0.1],[0.8,0.85],[1,0.9]],"undo_restores_all_reset_channels")
            let stale=s.capturePointCurve("curve_red_points")!
            _=try await Backend.call("edit_photo",["photo_id":1,"expected_revision":s.photo!.revision,"patch":["exposure":1]])
            await s.load(1)
            try check(!s.commitPointCurve(stale,PointCurveFields.identity),"external_refresh_rejects_captured_gesture_without_rebasing")
            s.error=nil
            let unknown=s.capturePointCurve("curve_red_points")!
            _=try await Backend.call("edit_photo",["photo_id":1,"expected_revision":s.photo!.revision,"patch":["curve_red_points":[[0,1],[1,0]]]])
            try check(s.commitPointCurve(unknown,PointCurveFields.identity),"unobserved_external_write_still_uses_captured_revision")
            try check(!(await s.flushEdits()) && s.error != nil && s.pointCurve("curve_red_points") == [[0,1],[1,0]],"service_revision_guard_preserves_external_curve")
            s.error=nil
            let previous=s.capturePointCurve("curve_rgb_points")!
            s.selected=2;s.selection=[2];await s.load(2)
            let switched=s.commitPointCurve(previous,draft),second=try await photo(2)
            try check(!switched && second.revision == 0,"photo_switch_never_retargets_a_drag")
            s.error=nil
            let pending=s.capturePointCurve("curve_rgb_points")!
            s.set("exposure",0.5)
            try check(!s.commitPointCurve(pending,draft) && s.capturePointCurve("curve_red_points") == nil,"pending_adjustments_block_curve_gesture_interleaving")
            try check(await s.flushEdits(),"failed_curve_gesture_retains_other_pending_edits")
            s.error=nil
            let clean=try await photo(2)
            s.setPointCurve("curve_rgb_points",[[0,Double.nan],[1,1]])
            _=await s.flushEdits()
            try check(try await photo(2).revision == clean.revision && s.error != nil,"invalid_numeric_input_never_mutates_recipe")
            s.error=nil;s.selected=1;s.selection=[1,2];await s.load(1)
            await s.sync(["Tone Curve"])
            let synced=try await photo(2)
            try check(PointCurveFields.keys.allSatisfy { synced.recipe[$0] as? [[Double]] == s.pointCurve($0) },"tone_curve_sync_includes_all_four_new_channels")
            try check((synced.recipe["exposure"] as? NSNumber)?.doubleValue == 0.5,"curve_sync_preserves_unchecked_adjustments")
            try check(try paths.map { try Data(contentsOf:URL(fileURLWithPath:$0)) } == originals,"curve_workflows_preserve_original_bytes")
            print(String(data:try JSONSerialization.data(withJSONObject:["ok":true,"checks":checks,"plot_max_error":largestError,
                "desktop_ui":"NOT_VERIFIED","keyboard_pointer_voiceover":"NOT_VERIFIED"],options:[.prettyPrinted,.sortedKeys]),encoding:.utf8)!)
            exit(0)
        } catch {
            print(String(data:try! JSONSerialization.data(withJSONObject:["ok":false,"checks":checks,"error":error.localizedDescription,
                "store_error":s.error ?? ""],options:.prettyPrinted),encoding:.utf8)!)
            exit(1)
        }
    }
}
