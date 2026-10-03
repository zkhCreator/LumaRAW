// Purpose: global Presence edits, persistence, reset and captured native workflows.
// Inputs: generated photos and the real isolated broker. Outputs: state/IPC
// assertions and an offscreen panel image. No desktop pointer or VoiceOver proof.
import AppKit
import Foundation
import SwiftUI

@main struct NativePresenceRegression {
    @MainActor static func main() async {
        _=NSApplication.shared
        let s=Store();var checks:[String:Bool]=[:]
        func check(_ value:Bool,_ name:String) throws {
            checks[name]=value;if !value {throw EngineFailure(message:name)}
        }
        func photo(_ id:Int) async throws -> Photo {
            Photo(try await Backend.call("get_photo",["photo_id":id]))!
        }
        func waitForEdit() async throws {
            for _ in 0..<400 {
                if !s.hasPendingEdits && !s.historyBusy {return}
                try await Task.sleep(nanoseconds:20_000_000)
            }
            throw EngineFailure(message:"Edit timed out")
        }
        func values(_ row:Photo) -> [Double] {
            PresenceFields.keys.map {(row.recipe[$0] as? NSNumber)?.doubleValue ?? 0}
        }
        do {
            let paths=ProcessInfo.processInfo.environment["LUMARAW_TEST_FIXTURES"]!.components(separatedBy:"|")
            let originals=try paths.map {try Data(contentsOf:URL(fileURLWithPath:$0))}
            await s.importPaths(paths);s.selected=1;s.selection=[1];await s.load(1)
            try check(PresenceFields.keys.allSatisfy {s.presenceValue($0)==0},"old_photo_uses_zero_defaults")
            let before=s.photo!.revision
            s.set("exposure",0.5);s.setPresence("texture",45);s.setPresence("clarity",-35);s.setPresence("dehaze",55)
            try check(await s.flushEdits(),"presence_burst_saves")
            let saved=try await photo(1)
            try check(s.photo!.revision==before+1 && values(saved) == [45,-35,55],"one_recipe_and_history_step_for_burst")
            let revision=s.photo!.revision
            for invalid in [Double.nan,Double.infinity,-101,101] {s.setPresence("texture",invalid)}
            s.setPresence("missing",10)
            _=await s.flushEdits()
            try check(try await photo(1).revision==revision && s.error != nil,"invalid_presence_never_reaches_catalog")
            s.error=nil;s.resetPresence();try check(await s.flushEdits(),"scoped_reset_saves")
            try check(PresenceFields.keys.allSatisfy {s.presenceValue($0)==0} &&
                (s.recipe["exposure"] as? NSNumber)?.doubleValue==0.5,"reset_preserves_other_groups")
            s.undo();try await waitForEdit()
            try check(PresenceFields.keys.map {s.presenceValue($0)} == [45,-35,55],"undo_restores_presence_together")
            s.selection=[1,2];await s.sync(["Presence"])
            let target=try await photo(2)
            try check(values(target)==[45,-35,55] && (target.recipe["exposure"] as? NSNumber)?.doubleValue==0,"presence_sync_preserves_light")
            await s.prepareDevelopPresetEditor()
            let draft=s.developPresetEditor!
            try check(draft.fieldGroups["Presence"]==PresenceFields.keys && Set(PresenceFields.keys).isSubset(of:draft.fields),"preset_editor_exposes_and_selects_presence")
            try check(await s.saveDevelopPreset(draft,name:"Presence only",group:"Tests",fields:Set(PresenceFields.keys),policy:"error"),"partial_presence_preset_saves")
            s.developPresetEditor=nil
            await s.load(1)
            try check(PresenceFields.keys.map {s.presenceValue($0)} == [45,-35,55],"presence_survives_reload")
            let host=NSHostingView(rootView:PresenceControls().environmentObject(s).padding(18)
                .environment(\.colorScheme,.dark).background(Color(nsColor:.windowBackgroundColor)))
            host.frame=NSRect(x:0,y:0,width:320,height:260);host.layoutSubtreeIfNeeded()
            try await Task.sleep(nanoseconds:250_000_000);host.layoutSubtreeIfNeeded();host.displayIfNeeded()
            guard let bitmap=host.bitmapImageRepForCachingDisplay(in:host.bounds) else {throw EngineFailure(message:"Missing offscreen bitmap")}
            host.cacheDisplay(in:host.bounds,to:bitmap)
            guard let bytes=bitmap.representation(using:.png,properties:[:]) else {throw EngineFailure(message:"Missing offscreen image")}
            try bytes.write(to:URL(fileURLWithPath:Backend.catalog).appendingPathComponent("presence-panel.png"))
            _=try await Backend.call("edit_photo",["photo_id":1,"expected_revision":s.photo!.revision,"patch":["texture":-20]])
            s.setPresence("texture",80)
            try check(!(await s.flushEdits()) && s.error != nil,"stale_presence_edit_fails_visibly")
            try check(values(try await photo(1))[0] == -20 && s.presenceValue("texture")==(-20),"conflict_retains_external_value_without_replay")
            try check(try paths.map {try Data(contentsOf:URL(fileURLWithPath:$0))}==originals,"presence_workflows_preserve_original_bytes")
            print(String(data:try JSONSerialization.data(withJSONObject:["ok":true,"checks":checks,
                "offscreen_snapshots":["presence-panel.png"],"desktop_ui":"NOT_VERIFIED","voiceover":"NOT_VERIFIED"],
                options:[.prettyPrinted,.sortedKeys]),encoding:.utf8)!)
            exit(0)
        } catch {
            print(String(data:try! JSONSerialization.data(withJSONObject:["ok":false,"checks":checks,
                "error":error.localizedDescription,"store_error":s.error ?? ""],options:.prettyPrinted),encoding:.utf8)!)
            exit(1)
        }
    }
}
