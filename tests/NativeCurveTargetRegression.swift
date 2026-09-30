// Purpose: bounded tone-map decoding and photo-targeted gesture state regression.
// Inputs: generated photographs and the real engine/broker. Outputs: alignment,
// temporary-preview, cancellation, revision and one-release-one-edit assertions.
// No desktop automation or claims about rendered layout, event dispatch or VO.
import AppKit
import Foundation

@main struct NativeCurveTargetRegression {
    @MainActor static func main() async {
        _=NSApplication.shared
        let s=Store();var checks:[String:Bool]=[:]
        func check(_ value:Bool,_ name:String) throws {checks[name]=value;if !value {throw EngineFailure(message:name)}}
        func photo(_ id:Int) async throws -> Photo {Photo(try await Backend.call("get_photo",["photo_id":id]))!}
        func ready() async throws {
            for _ in 0..<500 {
                if s.canTargetCurve {return}
                try await Task.sleep(nanoseconds:20_000_000)
            }
            throw EngineFailure(message:"Curve map timed out: \(s.error ?? "")")
        }
        func settle() async throws {
            for _ in 0..<500 {
                if !s.rendering,s.curveTargetFrame != nil {return}
                try await Task.sleep(nanoseconds:20_000_000)
            }
            throw EngineFailure(message:"Draft timed out")
        }
        do {
            let paths=ProcessInfo.processInfo.environment["LUMARAW_TEST_FIXTURES"]!.components(separatedBy:"|")
            let originals=try paths.map {try Data(contentsOf:URL(fileURLWithPath:$0))}
            let file=URL(fileURLWithPath:paths[0]).deletingLastPathComponent().appendingPathComponent("test.tones")
            func bytes(_ values:[Float],width:UInt32=3,height:UInt32=2) -> Data {
                var data=Data("LRTONE1\0".utf8)
                for value in [width,height]+values.map(\.bitPattern) {var word=value.littleEndian;withUnsafeBytes(of:&word){data.append(contentsOf:$0)}}
                return data
            }
            let receipt:[String:Any]=["path":file.path,"width":3,"height":2,"stage":"pre-parametric-v1"]
            try bytes([0,0.2,0.4,0.6,0.8,1]).write(to:file)
            let map=CurveToneMap(receipt)!
            try check(map.sample(.zero) == 0 && map.sample(CGPoint(x:1,y:1)) == 1 && abs(map.sample(CGPoint(x:0.5,y:0.25))!-0.2)<1e-7,"map_samples_top_left_row_order_and_inclusive_edges")
            try check(map.sample(CGPoint(x:-0.01,y:0.5)) == nil && map.sample(CGPoint(x:Double.nan,y:0.5)) == nil,"out_of_frame_and_nonfinite_pointers_rejected")
            try bytes([0,1]).write(to:file)
            try check(CurveToneMap(receipt) == nil,"truncated_map_rejected_before_sampling")
            try bytes([0,0.2,0.4,0.6,0.8,1],width:2,height:3).write(to:file)
            try check(CurveToneMap(receipt) == nil,"header_dimensions_must_match_receipt")
            try bytes([Float.nan,0.2,0.4,0.6,0.8,1]).write(to:file)
            try check(CurveToneMap(receipt)?.sample(.zero) == nil,"nonfinite_engine_sample_never_reaches_curve_editor")
            var oversized=receipt;oversized["width"]=Int.max
            try check(CurveToneMap(oversized) == nil,"oversized_map_rejected_without_overflow_or_allocation")
            let fit=CurveTargetOverlay.imageRect(image:CGSize(width:600,height:400),available:CGSize(width:1000,height:800),fitted:true)
            try check(fit.minX == 26 && abs(fit.width/fit.height-1.5)<1e-12 && fit.midY == 400,"fit_pointer_rect_matches_centered_inset_image")
            let detail=CurveTargetOverlay.imageRect(image:CGSize(width:1600,height:1100),available:CGSize(width:800,height:550),fitted:false)
            try check(detail == CGRect(x:0,y:0,width:800,height:550),"detail_coordinates_attach_to_retina_image_frame_before_scroll_centering")
            await s.importPaths(paths);s.selected=1;s.selection=[1];s.develop=true;await s.load(1)
            s.setCurveTargeting(true);try await ready()
            let clickRevision=s.photo!.revision
            _=s.beginCurveTarget(CGPoint(x:0.5,y:0.5),height:500);s.updateCurveTarget(translationY:0)
            _=s.finishCurveTarget();_=await s.flushEdits();try await ready()
            try check(s.photo?.revision == clickRevision && s.parametricCurve == .defaults,"click_without_vertical_drag_does_not_create_rounding_edit")
            let initial=try await photo(1),frame=s.curveTargetFrame!,point=CGPoint(x:0.37,y:0.62)
            s.hoverCurveTarget(point)
            let sample=s.curveTargetSample!
            try check(sample.input>0 && sample.input<1 && sample.region == s.parametricCurve.region(sample.input),"real_worker_input_selects_correct_parametric_region")
            try check(s.beginCurveTarget(point,height:500),"gesture_captures_current_photo_revision_and_viewport")
            for dy in [-1.0,-3,-5] {s.updateCurveTarget(translationY:dy)}
            let draft=s.curveTargetGesture!.values
            try check(draft.amounts[sample.region]>0 && s.parametricCurve == .defaults,"upward_drag_lightens_transient_region_without_local_recipe_write")
            try await Task.sleep(nanoseconds:220_000_000);try await settle()
            let unchanged=try await photo(1)
            try check(unchanged.revision == initial.revision && s.curveTargetFrame?.map.path == frame.map.path,"draft_preview_reuses_input_map_and_writes_no_history")
            let finished=s.finishCurveTarget(),flushed=await s.flushEdits()
            try check(finished && flushed,"release_commits_captured_target_adjustment")
            try await ready()
            let saved=try await photo(1)
            try check(saved.revision == initial.revision+1 && s.parametricCurve == draft,"many_drag_updates_create_exactly_one_revision")
            try check(s.curveTargetSample?.point == point,"saved_preview_retains_keyboard_target_at_same_photo_position")
            s.nudgeCurveTarget(1);try check(await s.flushEdits(),"selected_photo_tone_accepts_keyboard_increment")
            try await ready()
            try check(abs(s.parametricCurve.amounts[sample.region]-draft.amounts[sample.region]-1)<1e-9,"keyboard_increment_changes_only_selected_region")
            let prior=try await photo(1)
            try check(s.beginCurveTarget(point,height:500),"second_gesture_uses_new_revision")
            s.updateCurveTarget(translationY:20);s.cancelCurveTarget();try await ready()
            let cancelled=try await photo(1)
            try check(s.curveTargetGesture == nil && cancelled.revision == prior.revision && s.parametricCurve == ParametricCurveValues(recipe:prior.recipe),"escape_cancels_draft_and_restores_saved_curve")
            _=s.beginCurveTarget(point,height:500);s.updateCurveTarget(translationY:10);s.detail=true
            try check(!s.finishCurveTarget() && !s.hasPendingEdits,"zoom_change_rejects_captured_gesture_without_rebasing")
            s.error=nil;s.render(debounce:false);try await ready()
            try check(s.curveTargetFrame?.context.detail == true && s.curveTargetFrame?.map.path != frame.map.path,"detail_receipt_replaces_fitted_map")
            s.cx=0.8
            try check(!s.canTargetCurve && !s.beginCurveTarget(point,height:500),"viewport_pan_rejects_old_map_before_next_reply")
            s.render(debounce:false);try await ready()
            s.compare=true;try check(!s.beginCurveTarget(point,height:500),"before_image_cannot_be_used_as_adjustment_target");s.compare=false
            s.splitCompare=true;try check(!s.canTargetCurve,"split_comparison_blocks_targeting");s.splitCompare=false
            _=s.beginCurveTarget(point,height:500);s.updateCurveTarget(translationY:-3)
            let revision=s.photo!.revision
            _=try await Backend.call("edit_photo",["photo_id":1,"expected_revision":revision,"patch":["exposure":0.5]])
            try check(s.finishCurveTarget(),"unseen_external_edit_still_submits_captured_revision")
            try check(!(await s.flushEdits()) && s.error != nil,"service_rejects_conflicting_target_release")
            s.error=nil;try await ready()
            try check((s.recipe["exposure"] as? NSNumber)?.doubleValue == 0.5,"conflict_reload_preserves_external_adjustment")
            _=s.beginCurveTarget(point,height:500);s.updateCurveTarget(translationY:-3)
            s.selected=2;s.selection=[2];await s.load(2);try await ready()
            try check(s.curveTargetGesture == nil && !s.finishCurveTarget(),"selection_change_discards_capture_instead_of_retargeting")
            let second=try await photo(2);try check(second.revision == 0,"other_photo_receives_no_targeted_edit")
            s.set("exposure",0.3);try check(!s.beginCurveTarget(point,height:500),"pending_adjustments_block_sampling_stale_input_tones")
            _=await s.flushEdits();s.setCurveTargeting(false)
            try check(!s.curveTargetActive && s.curveTargetFrame == nil,"tool_exit_drops_sampling_state")
            try check(try paths.map {try Data(contentsOf:URL(fileURLWithPath:$0))} == originals,"targeted_workflows_preserve_original_bytes")
            print(String(data:try JSONSerialization.data(withJSONObject:["ok":true,"checks":checks,
                "desktop_ui":"NOT_VERIFIED","keyboard_pointer_voiceover":"NOT_VERIFIED"],options:[.prettyPrinted,.sortedKeys]),encoding:.utf8)!)
            exit(0)
        } catch {
            print(String(data:try! JSONSerialization.data(withJSONObject:["ok":false,"checks":checks,"error":error.localizedDescription,"store_error":s.error ?? ""],options:.prettyPrinted),encoding:.utf8)!)
            exit(1)
        }
    }
}
