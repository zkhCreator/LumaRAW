// Purpose: captured native mask management with the real isolated shared service.
// Inputs: generated originals, domain receipts and explicit stale/late contexts.
// Outputs: history, independent copies, no replay, recovery and offscreen controls.
// No desktop input, VoiceOver, AI masks or Lightroom pixel-equivalence evidence.
import AppKit
import Foundation
import SwiftUI

@main struct NativeLocalMaskActionsRegression {
    @MainActor static func main() async {
        _=NSApplication.shared
        let s=Store();var checks:[String:Bool]=[:]
        func check(_ value:Bool,_ name:String) throws {
            checks[name]=value;if !value {throw EngineFailure(message:name)}
        }
        func photo(_ id:Int) async throws -> Photo {
            Photo(try await Backend.call("get_photo",["photo_id":id]))!
        }
        func target(_ index:Int) async throws -> LocalMaskTarget {
            guard let value=await s.prepareLocalMaskTarget(index) else {
                throw EngineFailure(message:s.error ?? "Missing mask target")
            }
            return value
        }
        func accepted(_ result:LocalMaskActionResult) -> Bool {
            if case .accepted=result {return true};return false
        }
        do {
            let paths=ProcessInfo.processInfo.environment["LUMARAW_TEST_FIXTURES"]!.components(separatedBy:"|")
            let originals=try paths.map {try Data(contentsOf:URL(fileURLWithPath:$0))}
            await s.importPaths(paths);s.selected=1;s.selection=[1];await s.load(1)
            s.set("exposure",0.5)
            s.set("masks",[["kind":"brush","name":"Subject 肤色","points":[[0.2,0.3],[0.7,0.8]],
                "radius":0.05,"exposure":0.6,"saturation":(-15),"enabled":true]])
            let original=try await target(0)
            try check(original.revision==1 && !s.hasPendingEdits,"target_flushes_pending_mask_and_global_edits")
            try check(accepted(await s.performLocalMaskAction("rename",target:original,name:"Portrait 🐈")),"native_rename_saves")
            try check(s.localMaskRows[0]["name"] as? String=="Portrait 🐈" &&
                (s.recipe["exposure"] as? NSNumber)?.doubleValue==0.5,"rename_preserves_unrelated_adjustments_and_unicode")
            let same=try await target(0),revision=s.photo!.revision
            try check(accepted(await s.performLocalMaskAction("rename",target:same,name:"Portrait 🐈")) && s.photo?.revision==revision,"equal_name_is_noop")
            let clearName=try await target(0)
            try check(accepted(await s.performLocalMaskAction("rename",target:clearName,name:"")) &&
                LocalMaskPresentation.name(s.localMaskRows[0],index:0)=="Mask 1","empty_name_uses_default_picker_label")
            let restoreName=try await target(0)
            _=await s.performLocalMaskAction("rename",target:restoreName,name:"Portrait 🐈")
            let duplicate=try await target(0)
            try check(accepted(await s.performLocalMaskAction("duplicate_invert",target:duplicate)),"native_duplicate_and_invert_saves")
            try check(s.localMaskRows.count==2 && s.localMaskRows[1]["invert"] as? Bool==true &&
                s.localMaskRows[1]["points"] as? [[Double]]==[[0.2,0.3],[0.7,0.8]],"copy_retains_brush_points_and_adjustments")
            let stale=try await target(1)
            s.selected=2;s.selection=[2];await s.load(2)
            let selectionResult=await s.performLocalMaskAction("delete",target:stale)
            let sourceAfterSelection=try await photo(1)
            try check(!accepted(selectionResult) && (sourceAfterSelection.recipe["masks"] as? [[String:Any]])?.count==2,"changed_photo_never_retargets_old_mask")
            s.error=nil;s.selected=1;s.selection=[1];await s.load(1)
            let external=try await target(1)
            _=try await Backend.call("mask_action",["photo_id":1,"expected_revision":external.revision,
                "mask_index":0,"action":"rename","name":"External"])
            try check(!accepted(await s.performLocalMaskAction("delete",target:external)) && s.activeMaskRecovery != nil,"external_edit_rejects_stale_index_and_requires_review")
            let afterConflict=try await photo(1)
            try check((afterConflict.recipe["masks"] as? [[String:Any]])?.count==2,"conflict_preserves_all_masks")
            let recovery=s.activeMaskRecovery!
            try check(!accepted(await s.performLocalMaskAction("delete",target:external)),"failed_action_is_not_replayed")
            await s.reloadAfterMaskFailure(recovery)
            try check(s.activeMaskRecovery==nil && s.localMaskRows[0]["name"] as? String=="External","explicit_reload_adopts_current_masks")
            let remove=try await target(1)
            try check(accepted(await s.performLocalMaskAction("delete",target:remove)) && s.localMaskRows.count==1,"native_delete_updates_selection_receipt")
            let deletedRevision=s.photo!.revision
            _=try await Backend.call("undo_photo",["photo_id":1,"expected_revision":deletedRevision])
            await s.load(1)
            try check(s.localMaskRows.count==2,"one_undo_restores_deleted_mask")

            let uncertain=try await target(0)
            var calls=0
            let incomplete:LocalMaskCommandCall={method,params in
                calls+=1
                var result=try await Backend.call(method,params)
                result.removeValue(forKey:"mask_index")
                return result
            }
            try check(!accepted(await s.performLocalMaskAction("rename",target:uncertain,name:"Accepted but incomplete",call:incomplete)),"incomplete_accepted_receipt_enters_recovery")
            let acceptedPhoto=try await photo(1)
            try check((acceptedPhoto.recipe["masks"] as? [[String:Any]])?[0]["name"] as? String=="Accepted but incomplete" && calls==1,"accepted_uncertain_change_exists_once_in_catalog")
            _=await s.performLocalMaskAction("rename",target:uncertain,name:"Replay",call:incomplete)
            try check(calls==1,"recovery_blocks_a_second_command")
            let unchanged=s.presenceValue("texture")
            s.setPresence("texture",70)
            try check(s.presenceValue("texture")==unchanged && !s.hasPendingEdits,"recovery_preserves_recipe_and_blocks_unreviewed_slider_edits")
            await s.reloadAfterMaskFailure(s.activeMaskRecovery!)
            let late=try await target(0)
            let delayed:LocalMaskCommandCall={method,params in
                let result=try await Backend.call(method,params)
                s.selected=2;s.selection=[2];await s.load(2)
                return result
            }
            let lateResult=await s.performLocalMaskAction("rename",target:late,name:"Previous photo",call:delayed)
            try check(accepted(lateResult) && s.photo?.id==2 && s.localMaskRows.isEmpty,"late_receipt_does_not_overwrite_new_photo")
            let previous=try await photo(1)
            try check((previous.recipe["masks"] as? [[String:Any]])?[0]["name"] as? String=="Previous photo","late_success_preserves_original_target_mutation")
            s.selected=1;s.selection=[1];await s.load(1);s.error=nil
            let rename=LocalMaskRenameSource(target:try await target(0))
            let host=NSHostingView(rootView:LocalMaskRenameSheet(source:rename).environmentObject(s)
                .environment(\.colorScheme,.dark).background(Color(nsColor:.windowBackgroundColor)))
            host.frame=NSRect(x:0,y:0,width:440,height:240);host.layoutSubtreeIfNeeded()
            try await Task.sleep(nanoseconds:350_000_000);host.layoutSubtreeIfNeeded();host.displayIfNeeded()
            guard let bitmap=host.bitmapImageRepForCachingDisplay(in:host.bounds) else {throw EngineFailure(message:"Missing mask bitmap")}
            host.cacheDisplay(in:host.bounds,to:bitmap)
            guard let bytes=bitmap.representation(using:.png,properties:[:]) else {throw EngineFailure(message:"Missing mask image")}
            try bytes.write(to:URL(fileURLWithPath:Backend.catalog).appendingPathComponent("mask-rename.png"))
            try check(try paths.map {try Data(contentsOf:URL(fileURLWithPath:$0))}==originals,"mask_management_preserves_original_bytes")
            print(String(data:try JSONSerialization.data(withJSONObject:["ok":true,"checks":checks,
                "offscreen_snapshots":["mask-rename.png"],"desktop_ui":"NOT_VERIFIED","voiceover":"NOT_VERIFIED"],
                options:[.prettyPrinted,.sortedKeys]),encoding:.utf8)!)
            exit(0)
        } catch {
            print(String(data:try! JSONSerialization.data(withJSONObject:["ok":false,"checks":checks,
                "error":error.localizedDescription,"store_error":s.error ?? ""],options:.prettyPrinted),encoding:.utf8)!)
            exit(1)
        }
    }
}
