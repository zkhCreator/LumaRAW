// Purpose: native sparse color sampling and captured multi-band target edits.
// Inputs: synthetic maps/photos and real broker replies. Outputs: parser, gesture,
// treatment, history, undo and conflict assertions. No desktop automation or
// rendered pointer, keyboard, VoiceOver or Lightroom equivalence evidence.
import AppKit
import Foundation

@main struct NativeMixerTargetRegression {
    @MainActor static func main() async {
        _=NSApplication.shared
        let s=Store();var checks:[String:Bool]=[:]
        func check(_ value:Bool,_ name:String) throws {checks[name]=value;if !value {throw EngineFailure(message:name)}}
        func photo(_ id:Int) async throws -> Photo {Photo(try await Backend.call("get_photo",["photo_id":id]))!}
        func ready() async throws {
            for _ in 0..<500 {if s.canTargetMixer {return};try await Task.sleep(nanoseconds:20_000_000)}
            throw EngineFailure(message:"Mixer map timed out: \(s.error ?? "")")
        }
        func settled() async throws {
            for _ in 0..<500 {if !s.rendering,s.mixerTargetFrame != nil {return};try await Task.sleep(nanoseconds:20_000_000)}
            throw EngineFailure(message:"Mixer draft timed out")
        }
        do {
            let paths=ProcessInfo.processInfo.environment["LUMARAW_TEST_FIXTURES"]!.components(separatedBy:"|")
            let originals=try paths.map {try Data(contentsOf:URL(fileURLWithPath:$0))}
            let file=URL(fileURLWithPath:paths[0]).deletingLastPathComponent().appendingPathComponent("test.mixer")
            func bytes(_ words:[UInt32],width:UInt32=2,height:UInt32=1) -> Data {
                var data=Data("LRMIX1\0\0".utf8)
                for value in [width,height]+words {var word=value.littleEndian;withUnsafeBytes(of:&word){data.append(contentsOf:$0)}}
                return data
            }
            let words:[UInt32]=[2<<24|1<<8,Float(0.25).bitPattern,Float(1).bitPattern,0,0,0,0,0]
            let receipt:[String:Any]=["path":file.path,"width":2,"height":1,"stage":"mixer-target-v1","mode":"hsl","bands":MixerFields.bands]
            try bytes(words).write(to:file)
            let map=MixerTargetMap(receipt)!,sample=map.sample(.zero)!
            try check(sample.count == 2 && sample[0].index == 0 && sample[0].weight == 0.25 && sample[1].index == 1 && sample[1].weight == 1,"sparse_map_decodes_band_ids_and_exact_float32_weights")
            try check(map.sample(CGPoint(x:1,y:1))?.isEmpty == true,"inclusive_last_pixel_can_be_neutral")
            try check(map.sample(CGPoint(x:1.01,y:0)) == nil && map.sample(CGPoint(x:Double.nan,y:0)) == nil,"invalid_photo_coordinates_rejected")
            var invalid=words;invalid[0]=4<<24;try bytes(invalid).write(to:file)
            try check(MixerTargetMap(receipt)?.sample(.zero) == nil,"more_than_three_weights_rejected")
            invalid=words;invalid[0]=2<<24;try bytes(invalid).write(to:file)
            try check(MixerTargetMap(receipt)?.sample(.zero) == nil,"duplicate_band_ids_rejected")
            invalid=words;invalid[1]=Float.nan.bitPattern;try bytes(invalid).write(to:file)
            try check(MixerTargetMap(receipt)?.sample(.zero) == nil,"nonfinite_weights_rejected")
            invalid=words;invalid[1]=Float(1.01).bitPattern;try bytes(invalid).write(to:file)
            try check(MixerTargetMap(receipt)?.sample(.zero) == nil,"out_of_range_weights_rejected")
            try bytes(Array(words.prefix(4))).write(to:file)
            try check(MixerTargetMap(receipt) == nil,"truncated_buffer_rejected_before_sampling")
            var oversized=receipt;oversized["height"]=Int.max
            try check(MixerTargetMap(oversized) == nil,"oversized_map_rejected_without_overflow")
            await s.importPaths(paths);s.selected=1;s.selection=[1];s.develop=true;await s.load(1)
            let point=CGPoint(x:0.4,y:0.6)
            var firstPath:String?
            for component in MixerFields.components {
                s.setMixerTargeting(component);try await ready()
                if firstPath == nil {firstPath=s.mixerTargetFrame!.map.path}
                try check(s.mixerTargetFrame?.map.path == firstPath,"\(component)_reuses_pre_hsl_samples_after_downstream_edits")
                s.hoverMixerTarget(point)
                try check(s.mixerTargetSample!.weights.count>=2,"\(component)_targets_neighboring_bands")
                let before=try await photo(1)
                try check(s.beginMixerTarget(point,height:500),"\(component)_captures_current_photo")
                let capture=s.mixerTargetGesture!.capture
                for dy in [-5.0,-15,-25] {s.updateMixerTarget(translationY:dy)}
                let expected=capture.adjusted(10)
                try check(s.mixerTargetGesture!.values == expected && MixerFields.bands.map({s.mixerValue($0+"_"+component)}) == capture.values,"\(component)_shows_weighted_draft_without_recipe_mutation")
                try await Task.sleep(nanoseconds:230_000_000);try await settled()
                try check(try await photo(1).revision == before.revision && s.message.hasPrefix("Mixer preview"),"\(component)_temporary_worker_preview_preserves_history")
                let released=s.finishMixerTarget(),flushed=await s.flushEdits()
                try check(released && flushed,"\(component)_release_saves")
                try await ready()
                let saved=try await photo(1)
                try check(saved.revision == before.revision+1 && zip(MixerFields.bands,expected).allSatisfy({abs(s.mixerValue($0.0+"_"+component)-$0.1)<1e-9}),"\(component)_multi_band_gesture_is_one_revision_with_correct_units")
            }
            let clicked=s.photo!.revision
            _=s.beginMixerTarget(point,height:500);s.updateMixerTarget(translationY:0);_=s.finishMixerTarget();_=await s.flushEdits();try await ready()
            try check(s.photo!.revision == clicked,"click_without_drag_creates_no_history")
            let beforeKeyboard=MixerFields.bands.map {s.mixerValue($0+"_lum")}
            let weights=s.mixerTargetSample!.weights
            s.nudgeMixerTarget(1);_=await s.flushEdits();try await ready()
            try check(weights.allSatisfy {abs(s.mixerValue(MixerFields.bands[$0.index]+"_lum")-beforeKeyboard[$0.index]-$0.weight)<1e-9},"keyboard_increment_preserves_neighbor_weights")
            let cancelRevision=s.photo!.revision
            _=s.beginMixerTarget(point,height:500);s.updateMixerTarget(translationY:80);s.cancelMixerTarget();try await ready()
            try check(s.photo!.revision == cancelRevision && s.mixerTargetGesture == nil,"escape_discards_all_linked_draft_values")
            _=s.beginMixerTarget(point,height:500);s.updateMixerTarget(translationY:-10);s.detail=true
            try check(!s.finishMixerTarget() && !s.hasPendingEdits,"zoom_change_rejects_captured_target")
            s.error=nil;s.render(debounce:false);try await ready();s.cx=0.8
            try check(!s.canTargetMixer && !s.beginMixerTarget(point,height:500),"viewport_pan_invalidates_old_map_before_reply")
            s.render(debounce:false);try await ready()
            s.set("monochrome",true);try check(await s.flushEdits(),"black_and_white_treatment_saves");try await ready()
            let bwPath=s.mixerTargetFrame!.map.path
            try check(s.activeMixerComponent == "bw" && s.mixerTargetFrame?.map.mode == "bw" && bwPath != firstPath,"treatment_switch_targets_pre_monochrome_color_stage")
            _=s.beginMixerTarget(point,height:500);let bwCapture=s.mixerTargetGesture!.capture
            s.updateMixerTarget(translationY:-30);_=s.finishMixerTarget();_=await s.flushEdits();try await ready()
            let bwValues=MixerFields.bands.map {s.mixerValue($0+"_bw")}
            try check(bwValues == bwCapture.adjusted(12) && s.mixerTargetFrame?.map.path == bwPath,"bw_drag_updates_only_bw_values_and_reuses_input_colors")
            s.undo()
            for _ in 0..<200 {if !s.editing {break};try await Task.sleep(nanoseconds:20_000_000)}
            try await ready()
            try check(MixerFields.bands.allSatisfy {s.mixerValue($0+"_bw") == 0},"undo_restores_all_linked_bw_bands_together")
            _=s.beginMixerTarget(point,height:500);s.updateMixerTarget(translationY:-15)
            _=try await Backend.call("edit_photo",["photo_id":1,"expected_revision":s.photo!.revision,"patch":["exposure":0.5]])
            try check(s.finishMixerTarget(),"unseen_external_edit_keeps_captured_service_revision")
            try check(!(await s.flushEdits()) && s.error != nil,"external_revision_conflict_never_overwrites_newer_recipe")
            s.error=nil;try await ready()
            _=s.beginMixerTarget(point,height:500);s.updateMixerTarget(translationY:-15)
            s.selected=2;s.selection=[2];await s.load(2);try await ready()
            let second=try await photo(2)
            try check(s.mixerTargetGesture == nil && !s.finishMixerTarget() && second.revision == 0,"selection_change_never_retargets_color_edit")
            _=s.beginMixerTarget(point,height:500);s.updateMixerTarget(translationY:-10);s.setCurveTargeting(true)
            try check(!s.mixerTargetActive && s.mixerTargetGesture == nil && s.mixerTargetFrame == nil,"switching_to_curve_tool_discards_mixer_capture")
            s.setMixerTargeting("sat");try await ready();s.compare=true
            try check(!s.canTargetMixer,"before_comparison_cannot_be_sampled");s.compare=false;s.splitCompare=true
            try check(!s.canTargetMixer,"split_comparison_cannot_be_sampled");s.splitCompare=false
            s.set("contrast",5);try check(!s.beginMixerTarget(point,height:500),"pending_other_edits_block_stale_color_sampling")
            _=await s.flushEdits();s.setMixerTargeting(nil)
            try check(s.mixerTargetFrame == nil && !s.mixerTargetActive,"tool_exit_releases_color_map")
            try check(try paths.map {try Data(contentsOf:URL(fileURLWithPath:$0))} == originals,"all_targeted_workflows_preserve_original_bytes")
            print(String(data:try JSONSerialization.data(withJSONObject:["ok":true,"checks":checks,
                "desktop_ui":"NOT_VERIFIED","keyboard_pointer_voiceover":"NOT_VERIFIED"],options:[.prettyPrinted,.sortedKeys]),encoding:.utf8)!)
            exit(0)
        } catch {
            print(String(data:try! JSONSerialization.data(withJSONObject:["ok":false,"checks":checks,"error":error.localizedDescription,"store_error":s.error ?? ""],options:.prettyPrinted),encoding:.utf8)!)
            exit(1)
        }
    }
}
