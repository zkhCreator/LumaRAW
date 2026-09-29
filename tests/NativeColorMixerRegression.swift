// Purpose: verify native eight-band mixer edits against the real broker.
// Inputs: generated photos and an isolated catalog/preset library. Outputs:
// assertions for displayed units, reset scopes, treatment retention, persistence,
// sync and stale revisions. No rendered desktop or pointer/VoiceOver evidence.
import AppKit
import Foundation

@main struct NativeColorMixerRegression {
    @MainActor static func main() async {
        _=NSApplication.shared
        let s=Store()
        var checks: [String:Bool]=[:]
        func check(_ value: Bool,_ name: String) throws {
            checks[name]=value
            if !value { throw EngineFailure(message:name) }
        }
        func photo(_ id: Int) async throws -> Photo {
            Photo(try await Backend.call("get_photo",["photo_id":id]))!
        }
        func number(_ row: Photo,_ key: String) -> Double {
            (row.recipe[key] as? NSNumber)?.doubleValue ?? 0
        }
        func waitForEdit() async throws {
            for _ in 0..<200 {
                if !s.editing { return }
                try await Task.sleep(nanoseconds:20_000_000)
            }
            throw EngineFailure(message:"Edit timed out")
        }
        do {
            let paths=ProcessInfo.processInfo.environment["LUMARAW_TEST_FIXTURES"]!.components(separatedBy:"|")
            let originals=try paths.map { try Data(contentsOf:URL(fileURLWithPath:$0)) }
            await s.importPaths(paths)
            s.selected=1;s.selection=[1];await s.load(1)
            let first=s.photo!.revision
            for band in MixerFields.bands {
                s.setMixer(band+"_hue",50)
                s.setMixer(band+"_sat",-25)
                s.setMixer(band+"_lum",35)
                s.setMixer(band+"_bw",60)
            }
            try check(await s.flushEdits(),"all_thirty_two_channels_save_together")
            let saved=try await photo(1)
            try check(saved.revision == first+1,"slider_burst_is_one_history_step")
            try check(MixerFields.bands.allSatisfy { number(saved,$0+"_hue") == 15 && s.mixerValue($0+"_hue") == 50 },"hue_display_scale_preserves_stored_degrees")
            try check(MixerFields.bands.allSatisfy { number(saved,$0+"_sat") == -25 && number(saved,$0+"_lum") == 35 && number(saved,$0+"_bw") == 60 },"saturation_luminance_bw_keep_native_units")
            s.set("monochrome",true);try check(await s.flushEdits(),"black_and_white_treatment_saves")
            s.set("monochrome",false);try check(await s.flushEdits(),"color_treatment_saves")
            try check(s.mixerValue("yellow_lum") == 35 && s.mixerValue("blue_bw") == 60,"treatment_switch_retains_both_mixes")
            s.resetMixer(monochrome:false,component:"sat")
            try check(await s.flushEdits(),"component_reset_saves")
            try check(MixerFields.bands.allSatisfy { s.mixerValue($0+"_sat") == 0 && s.mixerValue($0+"_lum") == 35 && s.mixerValue($0+"_hue") == 50 },"component_reset_preserves_other_components")
            s.resetMixer(monochrome:false,band:"aqua")
            try check(await s.flushEdits(),"selected_color_reset_saves")
            try check(s.mixerValue("aqua_hue") == 0 && s.mixerValue("aqua_lum") == 0 && s.mixerValue("blue_hue") == 50 && s.mixerValue("aqua_bw") == 60,"selected_color_reset_preserves_other_colors_and_bw")
            s.resetMixer(monochrome:true)
            try check(await s.flushEdits(),"bw_panel_reset_saves")
            try check(MixerFields.bands.allSatisfy { s.mixerValue($0+"_bw") == 0 } && s.mixerValue("blue_lum") == 35,"bw_reset_preserves_color_mix")
            s.undo();try await waitForEdit()
            try check(MixerFields.bands.allSatisfy { s.mixerValue($0+"_bw") == 60 },"undo_restores_complete_bw_mix")
            let revision=s.photo!.revision
            for value in [Double.nan,Double.infinity,101,-101] { s.setMixer("yellow_lum",value) }
            _=await s.flushEdits()
            try check(try await photo(1).revision == revision && s.error != nil,"invalid_values_never_enter_pending_edits")
            s.error=nil
            s.selection=[1,2];await s.sync(["Black & White Mix"])
            let bw=try await photo(2)
            try check(number(bw,"red_bw") == 60 && number(bw,"blue_lum") == 0,"bw_sync_does_not_copy_color_controls")
            await s.sync(["Color"])
            let color=try await photo(2)
            try check(number(color,"blue_hue") == 15 && number(color,"purple_lum") == 35 && number(color,"red_bw") == 60,"color_sync_includes_new_bands_and_preserves_bw")
            await s.prepareDevelopPresetEditor()
            let draft=s.developPresetEditor!
            let fields=Set(draft.fieldGroups.values.flatMap { $0 })
            try check(fields.count > 64 && fields.isSuperset(of:Set(MixerFields.keys(monochrome:false)+MixerFields.keys(monochrome:true))) && draft.fields.contains("red_bw"),"full_preset_editor_exposes_all_mixer_fields")
            try check(await s.saveDevelopPreset(draft,name:"All mixer settings",group:"Tests",fields:fields,policy:"error"),"native_full_recipe_preset_exceeds_old_field_limit")
            s.developPresetEditor=nil
            _=try await Backend.call("edit_photo",["photo_id":1,"expected_revision":s.photo!.revision,"patch":["purple_lum":-22]])
            s.setMixer("purple_lum",77)
            try check(!(await s.flushEdits()) && s.error != nil,"stale_mixer_edit_surfaces_revision_conflict")
            try check(number(try await photo(1),"purple_lum") == -22 && s.mixerValue("purple_lum") == -22,"conflict_keeps_external_value_without_replay")
            s.error=nil
            s.resetMixer(monochrome:false);try check(await s.flushEdits(),"whole_color_panel_reset_saves")
            try check(MixerFields.keys(monochrome:false).allSatisfy { s.mixerValue($0) == 0 } && s.mixerValue("red_bw") == 60,"color_reset_preserves_bw_mix")
            try check(try paths.map { try Data(contentsOf:URL(fileURLWithPath:$0)) } == originals,"all_mixer_workflows_preserve_original_bytes")
            print(String(data:try JSONSerialization.data(withJSONObject:["ok":true,"checks":checks,
                "desktop_ui":"NOT_VERIFIED","voiceover":"NOT_VERIFIED"],options:[.prettyPrinted,.sortedKeys]),encoding:.utf8)!)
            exit(0)
        } catch {
            print(String(data:try! JSONSerialization.data(withJSONObject:["ok":false,"checks":checks,
                "error":error.localizedDescription,"store_error":s.error ?? ""],options:.prettyPrinted),encoding:.utf8)!)
            exit(1)
        }
    }
}
