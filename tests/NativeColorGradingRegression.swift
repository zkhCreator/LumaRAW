// Purpose: four-wheel native captures, temporary modes and durable shared commands.
// Inputs: generated originals, typed control events and the actual isolated broker.
// Outputs: one-step edits, cancellation/no-retarget assertions and offscreen layouts.
// Geometry tests exercise modifier constraints; no desktop events or VoiceOver proof.
import AppKit
import Foundation
import SwiftUI

@main struct NativeColorGradingRegression {
    @MainActor static func main() async {
        _=NSApplication.shared
        let s=Store();var checks:[String:Bool]=[:]
        func check(_ value:Bool,_ name:String) throws {checks[name]=value;if !value {throw EngineFailure(message:name)}}
        func photo(_ id:Int) async throws->Photo {Photo(try await Backend.call("get_photo",["photo_id":id]))!}
        func number(_ row:Photo,_ key:String)->Double {(row.recipe[key] as? NSNumber)?.doubleValue ?? GradingFields.initial(key)}
        func history() async throws->Int {
            let row=try await photo(1)
            return ((try await Backend.call("list_history",["photo_id":1,"expected_revision":row.revision]))["steps"] as! [[String:Any]]).filter {($0["id"] as? Int ?? 0)>0}.count
        }
        func wait(_ predicate:()->Bool) async throws {
            for _ in 0..<500 {if predicate() {return};try await Task.sleep(nanoseconds:20_000_000)}
            throw EngineFailure(message:"Native grading wait timed out")
        }
        func snapshot<V:View>(_ view:V,name:String,width:Double,height:Double) async throws {
            let host=NSHostingView(rootView:view.environmentObject(s).padding(16).environment(\.colorScheme,.dark).background(Color(nsColor:.windowBackgroundColor)))
            host.frame=NSRect(x:0,y:0,width:width,height:height);host.layoutSubtreeIfNeeded()
            try await Task.sleep(nanoseconds:250_000_000);host.layoutSubtreeIfNeeded();host.displayIfNeeded()
            guard let bitmap=host.bitmapImageRepForCachingDisplay(in:host.bounds) else {throw EngineFailure(message:"Missing bitmap")}
            host.cacheDisplay(in:host.bounds,to:bitmap)
            guard let png=bitmap.representation(using:.png,properties:[:]) else {throw EngineFailure(message:"Missing PNG")}
            try png.write(to:URL(fileURLWithPath:Backend.catalog).appendingPathComponent(name))
        }
        do {
            let paths=ProcessInfo.processInfo.environment["LUMARAW_TEST_FIXTURES"]!.components(separatedBy:"|")
            let originals=try paths.map {try Data(contentsOf:URL(fileURLWithPath:$0))}
            await s.importPaths(paths);s.selected=1;s.selection=[1];s.develop=true;await s.load(1)
            try check(GradingFields.keys.count==14 && GradingFields.keys.allSatisfy {s.gradingValue($0)==GradingFields.initial($0)},"old_photo_has_four_neutral_wheels_and_blending_50")
            let h="grading_midtones_hue",sat="grading_midtones_saturation",lum="grading_midtones_luminance"
            try check(s.beginGrading([h,sat]),"wheel_captures_active_photo")
            let id=s.gradingInteraction.edit!.id
            try check(!s.beginGrading([lum]),"second_control_cannot_replace_active_capture")
            s.updateGrading([h:225,sat:65])
            try await wait {!s.rendering && s.message.hasPrefix("Color Grading preview")}
            let draftRow=try await photo(1),draftHistory=try await history()
            try check(s.gradingInteraction.edit?.id==id && !s.hasPendingEdits && draftRow.revision==0 && draftHistory==0,"live_wheel_preview_is_read_only")
            try check(s.activeViewportFrame==nil && !s.canStartWhiteBalanceSelector && !s.canEditPointCurves,"draft_pixels_are_not_sampling_or_curve_contexts")
            let released=s.finishGrading(),saved=await s.flushEdits()
            try check(released && saved,"release_saves_paired_hue_saturation")
            let releasedRow=try await photo(1),releasedHistory=try await history()
            try check(number(releasedRow,h)==225 && number(releasedRow,sat)==65 && releasedHistory==1,"paired_wheel_has_one_history_step")
            let revision=s.photo!.revision
            s.muteGrading("midtones",pressed:true)
            try check(s.gradingInteraction.edit?.temporaryOnly==true && s.gradingValue(sat)==0,"held_eye_mutes_wheel_only_in_draft")
            s.muteGrading("midtones",pressed:false)
            let mutedRow=try await photo(1),mutedHistory=try await history()
            try check(s.gradingInteraction.edit==nil && s.gradingValue(sat)==65 && mutedRow.revision==revision && mutedHistory==1,"eye_release_restores_without_edit")
            try check(s.beginGrading(["grading_blending"]),"blending_captures")
            s.updateGrading(["grading_blending":80],boost:true)
            try check(s.gradingInteraction.edit!.temporary.count==3 && s.gradingInteraction.edit!.temporary.values.allSatisfy {$0==100},"option_boost_affects_only_three_tonal_wheels")
            s.updateGrading(["grading_blending":80],boost:false)
            try check(s.gradingInteraction.edit!.temporary.isEmpty,"option_release_restores_actual_saturations")
            s.updateGrading(["grading_blending":80],boost:true)
            _=s.finishGrading();try check(await s.flushEdits(),"blending_release_saves")
            let blend=try await photo(1)
            try check(number(blend,"grading_blending")==80 && number(blend,sat)==65 && number(blend,"grading_shadows_saturation")==0,"boost_never_enters_saved_recipe")
            try check(s.beginGrading([h,sat]),"cancel_capture_starts")
            s.updateGrading([h:30,sat:90]);s.cancelGrading()
            let cancelledRow=try await photo(1),cancelledHistory=try await history()
            try check(s.gradingInteraction.edit==nil && number(cancelledRow,h)==225 && cancelledHistory==2,"escape_cancel_preserves_catalog")
            s.copyGrading("midtones");s.pasteGrading("global");try check(await s.flushEdits(),"wheel_paste_saves")
            try check(s.gradingValue("grading_global_hue")==225 && s.gradingValue("grading_global_saturation")==65,"clipboard_maps_values_to_destination_wheel")
            s.setGrading("exposure",1);s.setGrading(h,361)
            try check(!s.hasPendingEdits && s.error != nil,"invalid_fields_and_values_do_not_admit_edits")
            s.error=nil;s.set("exposure",0.5);_=await s.flushEdits()
            s.resetGrading(["global"],overlap:false);try check(await s.flushEdits(),"scoped_wheel_reset_saves")
            try check(s.gradingValue("grading_global_saturation")==0 && s.gradingValue(sat)==65 && s.gradingValue("grading_blending")==80 && (s.recipe["exposure"] as? Double)==0.5,"scoped_reset_preserves_other_wheels_overlap_and_light")
            s.selection=[1,2]
            let review=await s.prepareSyncAdjustments()
            try check(review?.schema.groups["Color Grading"]==GradingFields.keys && review!.schema.initiallySelected.contains("Color Grading") && review!.schema.initiallySelected.contains("Detail"),"sync_exposes_all_grading_fields_and_retains_detail_default")
            try check(await s.sync(["Color Grading"],draft:review),"grading_sync_saves")
            let syncedRow=try await photo(2)
            try check(number(syncedRow,sat)==65 && number(syncedRow,"exposure")==0,"grading_sync_preserves_target_light")
            await s.prepareDevelopPresetEditor()
            let preset=s.developPresetEditor!
            try check(preset.fieldGroups["Color Grading"]==GradingFields.keys && Set(GradingFields.keys).isSubset(of:preset.fields),"develop_preset_editor_includes_all_grading")
            try check(await s.saveDevelopPreset(preset,name:"Four wheels",group:"Tests",fields:Set(GradingFields.keys),policy:"error"),"grading_preset_saves")
            s.developPresetEditor=nil
            let count=try await history()
            try check(s.beginGrading([h]),"switch_capture_starts")
            s.updateGrading([h:70]);s.selected=2;await s.load(2);s.selected=1;await s.load(1)
            let switchHistory=try await history()
            try check(!s.finishGrading() && s.gradingInteraction.edit==nil && switchHistory==count,"switch_return_aba_cannot_save_old_gesture")
            try check(s.beginGrading([h]),"stale_capture_starts")
            s.updateGrading([h:90])
            _=try await Backend.call("edit_photo",["photo_id":1,"expected_revision":s.photo!.revision,"patch":[h:140]])
            _=s.finishGrading()
            try check(!(await s.flushEdits()) && s.error != nil,"external_revision_conflict_fails_visibly")
            try check(number(try await photo(1),h)==140 && s.gradingValue(h)==140,"conflict_is_not_replayed_or_overwritten")
            var drag=GradingWheelDrag(hue:0,saturation:50,point:CGPoint(x:50,y:0),radius:100,hueOnly:false,onHandle:true)
            drag.update(CGPoint(x:80,y:2),radius:100,modifiers:[])
            try check(drag.hue==0 && drag.saturation>79,"handle_soft_lock_preserves_hue_for_small_angle")
            drag.update(CGPoint(x:0,y:80),radius:100,modifiers:[])
            try check(drag.hue>80,"soft_lock_releases_for_intentional_angle_change")
            var shift=GradingWheelDrag(hue:30,saturation:40,point:CGPoint(x:0,y:80),radius:100,hueOnly:false,onHandle:false,modifiers:.shift)
            shift.update(CGPoint(x:-90,y:0),radius:100,modifiers:.shift)
            try check(shift.hue==30 && shift.saturation==90,"shift_click_and_drag_constrain_saturation")
            var command=GradingWheelDrag(hue:30,saturation:40,point:CGPoint(x:0,y:80),radius:100,hueOnly:false,onHandle:false,modifiers:.command)
            command.update(CGPoint(x:-10,y:0),radius:100,modifiers:.command)
            try check(command.saturation==40 && abs(command.hue-180)<0.001,"command_constrains_hue")
            var fine=GradingWheelDrag(hue:0,saturation:50,point:CGPoint(x:50,y:0),radius:100,hueOnly:true,onHandle:true)
            fine.update(CGPoint(x:0,y:80),radius:100,modifiers:.option)
            try check(abs(fine.hue-9)<0.001 && fine.saturation==50,"option_fine_hue_only_preserves_saturation")
            var fineInner=GradingWheelDrag(hue:0,saturation:50,point:CGPoint(x:50,y:0),radius:100,hueOnly:false,onHandle:true)
            let angle=2.0 * Double.pi/180
            fineInner.update(CGPoint(x:50*cos(angle),y:50*sin(angle)),radius:100,modifiers:.option)
            try check(abs(fineInner.hue-0.2)<0.00001 && abs(fineInner.saturation-50)<0.00001,
                "option_fine_inner_handle_releases_soft_constraint_for_small_angle")
            try await snapshot(ColorGradingControls(),name:"grading-three-way.png",width:320,height:570)
            try await snapshot(ColorGradingControls(initialMode:"midtones"),name:"grading-detail.png",width:320,height:490)
            try await snapshot(ColorGradingControls(initialMode:"global"),name:"grading-global.png",width:320,height:410)
            try await snapshot(VStack {GradingWheel(store:s,region:"midtones").frame(width:190,height:190);Text("Midtones Hue 140 · Saturation 65")},name:"grading-wheel.png",width:250,height:260)
            try check(try paths.map {try Data(contentsOf:URL(fileURLWithPath:$0))}==originals,"grading_workflows_preserve_original_bytes")
            print(String(data:try JSONSerialization.data(withJSONObject:["ok":true,"checks":checks,
                "offscreen_snapshots":["grading-three-way.png","grading-detail.png","grading-global.png","grading-wheel.png"],"desktop_ui":"NOT_VERIFIED","voiceover":"NOT_VERIFIED"],options:[.prettyPrinted,.sortedKeys]),encoding:.utf8)!)
            exit(0)
        } catch {
            print(String(data:try! JSONSerialization.data(withJSONObject:["ok":false,"checks":checks,"error":error.localizedDescription,"store_error":s.error ?? ""],options:.prettyPrinted),encoding:.utf8)!)
            exit(1)
        }
    }
}
