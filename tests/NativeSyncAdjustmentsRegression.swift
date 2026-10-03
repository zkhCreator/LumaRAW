// Purpose: real native Sync reviews, dynamic groups and revision-bound batches.
// Inputs: generated originals, isolated broker and explicit selection changes.
// Outputs: source/target conflict, history, no-replay and offscreen form evidence.
// No desktop pointer, keyboard routing, VoiceOver or Lightroom acceptance proof.
import AppKit
import Foundation
import SwiftUI

@main struct NativeSyncAdjustmentsRegression {
    @MainActor static func main() async {
        _=NSApplication.shared
        let s=Store();var checks:[String:Bool]=[:]
        func check(_ value:Bool,_ name:String) throws {
            checks[name]=value;if !value {throw EngineFailure(message:name)}
        }
        func photo(_ id:Int) async throws -> Photo {
            Photo(try await Backend.call("get_photo",["photo_id":id]))!
        }
        func edit(_ id:Int,_ patch:[String:Any]) async throws {
            let row=try await photo(id)
            _=try await Backend.call("edit_photo",["photo_id":id,"expected_revision":row.revision,"patch":patch])
        }
        func targetRevisions() async throws -> [Int] {
            var result:[Int]=[]
            for id in 2...5 {result.append(try await photo(id).revision)}
            return result
        }
        func review() async throws -> SyncAdjustmentsDraft {
            guard let draft=await s.prepareSyncAdjustments() else {
                throw EngineFailure(message:s.error ?? "Missing Sync review")
            }
            return draft
        }
        do {
            let paths=ProcessInfo.processInfo.environment["LUMARAW_TEST_FIXTURES"]!.components(separatedBy:"|")
            let originals=try paths.map {try Data(contentsOf:URL(fileURLWithPath:$0))}
            await s.importPaths(paths)
            try check(s.error==nil && s.photos.count==5,"five_isolated_sync_fixtures_import")
            s.selected=1;s.selection=[1,2,3,4,5];await s.load(1)
            s.set("exposure",0.5);s.setPresence("texture",45);s.setPresence("clarity",-35);s.setPresence("dehaze",55)
            let initial=try await review()
            try check(initial.source.revision==1 && !s.hasPendingEdits && initial.targets.map(\.id)==[2,3,4,5],"review_flushes_and_captures_source_and_sorted_targets")
            try check(initial.schema.groups["Presence"]==PresenceFields.keys &&
                initial.schema.names.contains("Presence") && initial.schema.initiallySelected.contains("Presence"),"sync_form_includes_engine_presence_group")
            var schema=try await Backend.call("recipe_schema")
            var future=schema["groups"] as! [String:[String]]
            future["Future Group"]=["texture"];future.removeValue(forKey:"Lens");schema["groups"]=future
            let decoded=SyncAdjustmentsSchema(schema)!
            try check(decoded.names.contains("Future Group") && !decoded.names.contains("Lens"),"new_and_removed_engine_groups_are_reflected_without_ui_changes")
            future["Invalid Group"]=["missing_field"];schema["groups"]=future
            try check(SyncAdjustmentsSchema(schema)==nil,"invalid_group_contract_fails_without_fallback_list")

            let before=try await targetRevisions()
            s.selection=[1,2]
            let selectionAccepted=await s.sync(["Presence"],draft:initial)
            let afterSelection=try await targetRevisions()
            try check(!selectionAccepted && s.error != nil && afterSelection==before,"changed_selection_rejects_review_without_target_writes")
            s.selection=initial.photoIDs;s.error=nil
            s.setPresence("texture",40)
            let pendingAccepted=await s.sync(["Presence"],draft:initial)
            let afterPending=try await targetRevisions()
            try check(!pendingAccepted && afterPending==before,"pending_source_edit_invalidates_review")
            try check(await s.flushEdits(),"pending_source_edit_saves_independently")
            let sourceReview=try await review()
            try await edit(1,["texture":-20])
            let sourceAccepted=await s.sync(["Presence"],draft:sourceReview)
            let afterSource=try await targetRevisions()
            try check(!sourceAccepted && s.error?.contains("Edit conflict") == true && afterSource==before,"external_source_change_rejects_whole_batch")
            try check(s.photo?.revision==sourceReview.source.revision,"source_conflict_does_not_rebase_or_replay_review")
            s.error=nil
            let targetReview=try await review()
            try check(targetReview.source.revision==3 && s.photo?.revision==3 && s.presenceValue("texture")==(-20),"explicit_review_again_refreshes_external_source_settings")
            try await edit(5,["exposure":2])
            let targetAccepted=await s.sync(["Presence"],draft:targetReview)
            let afterTarget=try await targetRevisions()
            try check(!targetAccepted && afterTarget==[0,0,0,1],"last_target_conflict_preserves_all_earlier_targets")
            s.error=nil
            let ready=try await review()
            let duplicateAccepted=await s.sync(["Presence","Presence"],draft:ready)
            let unknownAccepted=await s.sync(["Missing"],draft:ready)
            let emptyAccepted=await s.sync([],draft:ready)
            try check(!duplicateAccepted && !unknownAccepted && !emptyAccepted,"invalid_checkbox_groups_never_submit")
            s.error=nil
            try check(await s.sync(["Presence"],draft:ready),"reviewed_presence_batch_succeeds")
            for id in 2...5 {
                let target=try await photo(id)
                try check(PresenceFields.keys.map {(target.recipe[$0] as? NSNumber)?.doubleValue ?? 0}==[-20,-35,55] &&
                    (target.recipe["exposure"] as? NSNumber)?.doubleValue==(id==5 ? 2:0),"presence_only_preserves_target_light_\(id)")
            }
            let synced=try await targetRevisions()
            try check(synced==[1,1,1,2],"each_target_gets_one_history_revision")
            let same=try await review()
            let sameAccepted=await s.sync(["Presence"],draft:same)
            let afterSame=try await targetRevisions()
            try check(sameAccepted && afterSame==synced,"equal_presence_sync_is_noop")
            _=try await Backend.call("undo_photo",["photo_id":2,"expected_revision":1])
            let undone=try await photo(2)
            try check(PresenceFields.keys.allSatisfy {(undone.recipe[$0] as? NSNumber)?.doubleValue==0},"one_undo_restores_all_presence_fields")
            s.syncBusy=true
            let sourceBefore=s.presenceValue("texture")
            s.setPresence("texture",80)
            try check(!(await s.sync(["Presence"])) && s.presenceValue("texture")==sourceBefore && !s.hasPendingEdits,"busy_sync_blocks_reentry_and_source_slider_changes")
            s.syncBusy=false;s.error=nil

            let host=NSHostingView(rootView:SyncSheet().environmentObject(s)
                .environment(\.colorScheme,.dark).background(Color(nsColor:.windowBackgroundColor)))
            host.frame=NSRect(x:0,y:0,width:480,height:580);host.layoutSubtreeIfNeeded()
            try await Task.sleep(nanoseconds:700_000_000);host.layoutSubtreeIfNeeded();host.displayIfNeeded()
            guard let bitmap=host.bitmapImageRepForCachingDisplay(in:host.bounds) else {throw EngineFailure(message:"Missing Sync bitmap")}
            host.cacheDisplay(in:host.bounds,to:bitmap)
            guard let bytes=bitmap.representation(using:.png,properties:[:]) else {throw EngineFailure(message:"Missing Sync image")}
            try bytes.write(to:URL(fileURLWithPath:Backend.catalog).appendingPathComponent("sync-presence.png"))
            s.selection=[2,3]
            try check(await s.prepareSyncAdjustments()==nil,"source_must_belong_to_reviewed_selection")
            s.selection=[1]
            try check(await s.prepareSyncAdjustments()==nil,"single_photo_cannot_sync")
            s.selection=Set(1...62)
            try check(await s.prepareSyncAdjustments()==nil,"over_sixty_targets_rejected_before_reads")
            try check(try paths.map {try Data(contentsOf:URL(fileURLWithPath:$0))}==originals,"sync_preserves_original_bytes")
            print(String(data:try JSONSerialization.data(withJSONObject:["ok":true,"checks":checks,
                "offscreen_snapshots":["sync-presence.png"],"desktop_ui":"NOT_VERIFIED","voiceover":"NOT_VERIFIED"],
                options:[.prettyPrinted,.sortedKeys]),encoding:.utf8)!)
            exit(0)
        } catch {
            print(String(data:try! JSONSerialization.data(withJSONObject:["ok":false,"checks":checks,
                "error":error.localizedDescription,"store_error":s.error ?? ""],options:.prettyPrinted),encoding:.utf8)!)
            exit(1)
        }
    }
}
