// Purpose: native WB selector state, command capture and paired-edit regressions.
// Inputs: generated raster originals and real packaged service commands.
// Outputs: bounded point mapping, cancellation/stale guards, one-edit/history
// receipts and offscreen layout images. No desktop pointer or keyboard evidence.
import AppKit
import Foundation
import SwiftUI

@MainActor final class WhiteBalanceResponseGate {
    var holdMethod:String?
    var heldReply:[String:Any]?
    var continuation:CheckedContinuation<[String:Any],Error>?
    var calls:[(String,[String:Any])]=[]

    func call(_ method:String,_ params:[String:Any]) async throws ->[String:Any] {
        calls.append((method,params))
        let reply=try await Backend.call(method,params)
        guard method==holdMethod else {return reply}
        return try await withCheckedThrowingContinuation {continuation in
            self.heldReply=reply;self.continuation=continuation
        }
    }

    func release() {
        let reply=heldReply
        heldReply=nil;continuation?.resume(returning:reply ?? [:]);continuation=nil;holdMethod=nil
    }
}

@main struct NativeWhiteBalanceRegression {
    @MainActor static func main() async {
        _=NSApplication.shared
        let store=Store()
        var checks:[String:Bool]=[:]
        var diagnostics:[String:Any]=[:]
        func check(_ value:Bool,_ name:String)throws {
            checks[name]=value
            if !value {throw EngineFailure(message:name)}
        }
        func wait(_ predicate:()->Bool) async throws {
            for _ in 0..<800 {
                if predicate() {return}
                try await Task.sleep(nanoseconds:20_000_000)
            }
            throw EngineFailure(message:"White-balance state did not settle: selected=\(String(describing:store.selected)), photo=\(String(describing:store.photo?.id)), revision=\(String(describing:store.photo?.revision)), arming=\(store.whiteBalanceArming), sampling=\(store.whiteBalanceSampling), tool=\(store.canvasTool), rendering=\(store.rendering), error=\(store.error ?? "no error")")
        }
        let display=WhiteBalanceDisplayGeometry(available:CGSize(width:640,height:480),
            imageRect:CGRect(x:34,y:26,width:572,height:428),displayScale:2,role:"active",after:true)
        func photo(_ id:Int) async throws ->Photo {
            guard let result=Photo(try await Backend.call("get_photo",["photo_id":id])) else {
                throw EngineFailure(message:"Photo \(id) was not returned")
            }
            return result
        }
        func ready(_ id:Int) async throws {
            try await wait {store.photo?.id==id && !store.loading && !store.rendering && store.whiteBalancePreviewIdentity != nil}
        }
        func armSelector(_ id:Int) async throws ->WhiteBalancePreviewIdentity {
            guard store.selected==id else {throw EngineFailure(message:"Test must select its target before arming")}
            await store.armWhiteBalanceSelector()
            try await wait {store.whiteBalanceTargetActive && store.whiteBalanceArmPreview?.context.photoID==id}
            store.whiteBalanceDisplayDidChange(display)
            guard let identity=store.whiteBalanceArmPreview else {
                throw EngineFailure(message:"White-balance selector did not capture the visible preview")
            }
            return identity
        }
        func holdArmingAfterFlush(_ id:Int) async throws ->Task<Void,Never> {
            store.canvasTool="curve"
            store.editing=true
            let task=Task {await store.armWhiteBalanceSelector()}
            try await wait {store.whiteBalanceArming}
            store.editing=false
            store.rendering=true
            try await wait {store.whiteBalanceArming && store.canvasTool=="view"}
            return task
        }
        func writeSnapshot<V:View>(_ name:String,_ view:V,_ size:NSSize,_ root:URL) async throws {
            let hostedView=view.environment(\.colorScheme,.dark)
                .background(Color(nsColor:.windowBackgroundColor))
            let host=NSHostingView(rootView:hostedView)
            host.frame=NSRect(origin:.zero,size:size)
            host.layoutSubtreeIfNeeded()
            try await Task.sleep(nanoseconds:250_000_000)
            host.layoutSubtreeIfNeeded();host.displayIfNeeded()
            guard host.bounds.width>0,host.bounds.height>0,
                  let bitmap=host.bitmapImageRepForCachingDisplay(in:host.bounds) else {
                throw EngineFailure(message:"Could not render offscreen white-balance snapshot \(name)")
            }
            host.cacheDisplay(in:host.bounds,to:bitmap)
            guard let background=bitmap.colorAt(x:0,y:0)?.usingColorSpace(.deviceRGB) else {
                throw EngineFailure(message:"Could not inspect offscreen snapshot pixels \(name)")
            }
            var contrastSamples=0
            var colorBuckets=Set<Int>()
            for y in stride(from:0,to:bitmap.pixelsHigh,by:6) {
                for x in stride(from:0,to:bitmap.pixelsWide,by:6) {
                    guard let color=bitmap.colorAt(x:x,y:y)?.usingColorSpace(.deviceRGB) else {continue}
                    let red=color.redComponent,green=color.greenComponent,blue=color.blueComponent
                    let difference=max(abs(red-background.redComponent),
                        max(abs(green-background.greenComponent),abs(blue-background.blueComponent)))
                    if difference>0.08 {contrastSamples+=1}
                    let r=Int((red*15).rounded()),g=Int((green*15).rounded()),b=Int((blue*15).rounded())
                    colorBuckets.insert((r<<8)|(g<<4)|b)
                }
            }
            guard contrastSamples>=20,colorBuckets.count>=4 else {
                throw EngineFailure(message:"Offscreen snapshot appears blank: \(name)")
            }
            guard let data=bitmap.representation(using:.png,properties:[:]) else {
                throw EngineFailure(message:"Could not encode offscreen white-balance snapshot \(name)")
            }
            try data.write(to:root.appendingPathComponent(name))
        }
        func makeRaster(_ path:URL,_ red:CGFloat,_ green:CGFloat,_ blue:CGFloat)throws ->Data {
            guard let bitmap=NSBitmapImageRep(bitmapDataPlanes:nil,pixelsWide:64,pixelsHigh:48,
                bitsPerSample:8,samplesPerPixel:4,hasAlpha:true,isPlanar:false,colorSpaceName:.deviceRGB,
                bytesPerRow:0,bitsPerPixel:0) else {throw EngineFailure(message:"Could not allocate test raster")}
            let color=NSColor(calibratedRed:red,green:green,blue:blue,alpha:1)
            for y in 0..<48 {for x in 0..<64 {bitmap.setColor(color,atX:x,y:y)}}
            guard let bytes=bitmap.representation(using:.png,properties:[:]) else {
                throw EngineFailure(message:"Could not encode test raster")
            }
            try bytes.write(to:path)
            return bytes
        }

        do {
            let fixtureRoot=URL(fileURLWithPath:ProcessInfo.processInfo.environment["LUMARAW_TEST_FIXTURES"]!
                .components(separatedBy:"|")[0]).deletingLastPathComponent()
            let firstURL=fixtureRoot.appendingPathComponent("wb-neutral-a.png")
            let secondURL=fixtureRoot.appendingPathComponent("wb-neutral-b.png")
            let firstBytes=try makeRaster(firstURL,0.54,0.50,0.46)
            let secondBytes=try makeRaster(secondURL,0.49,0.48,0.47)
            let originals=[firstURL:firstBytes,secondURL:secondBytes]

            // Fit is the complete frame; a detail click expands through its ROI.
            let fitContext=BeforePreviewContext(photoID:9,revision:3,orientation:0,detail:false,
                cx:0.5,cy:0.5,gamut:false,proofSHA:"",width:0,height:0)
            let fit=WhiteBalancePreviewIdentity(context:fitContext,sourceFingerprint:String(repeating:"a",count:24),
                fullWidth:1600,fullHeight:1200,roiX:0,roiY:0,roiWidth:1600,roiHeight:1200)
            let fitPoint=WhiteBalancePointMapping.fullPoint(CGPoint(x:0.25,y:0.75),preview:fit)
            try check(fitPoint==CGPoint(x:0.25,y:0.75),"fit_click_uses_full_output_coordinates")
            let detailContext=BeforePreviewContext(photoID:9,revision:3,orientation:0,detail:true,
                cx:0.5,cy:0.5,gamut:false,proofSHA:"",width:800,height:600)
            let detail=WhiteBalancePreviewIdentity(context:detailContext,sourceFingerprint:fit.sourceFingerprint,
                fullWidth:4000,fullHeight:3000,roiX:1000,roiY:600,roiWidth:800,roiHeight:600)
            let roiPoint=WhiteBalancePointMapping.fullPoint(CGPoint(x:0.5,y:0.5),preview:detail)
            try check(roiPoint==CGPoint(x:0.35,y:0.30),"detail_click_expands_roi_to_full_output")
            try check(WhiteBalancePointMapping.localPoint(.zero,imageRect:CGRect(x:10,y:10,width:80,height:40))==nil &&
                      WhiteBalancePointMapping.fullPoint(CGPoint(x:1.01,y:0.5),preview:detail)==nil,
                      "image_margins_and_out_of_range_coordinates_are_rejected")

            await store.importPaths([firstURL.path,secondURL.path])
            await store.startDevelop()
            guard let firstID=store.selected else {throw EngineFailure(message:"Import did not select a photo")}
            guard let secondID=store.photos.first(where:{$0.id != firstID})?.id else {
                throw EngineFailure(message:"Import did not produce a second photo")
            }
            try await ready(firstID)
            let firstOriginal=try await photo(firstID)
            let initialHistory=try await Backend.call("list_history",[
                "photo_id":firstID,"expected_revision":firstOriginal.revision
            ])
            let initialSteps=(initialHistory["steps"] as? [[String:Any]])?.count ?? 0
            store.setComparisonMode(.leftRight)
            try await ready(firstID)
            _=try await armSelector(firstID)
            try check(store.comparisonMode == .after,"arming_from_paired_view_targets_after_only")

            guard let identity=store.whiteBalanceArmPreview else {throw EngineFailure(message:"Missing captured preview")}

                var recorded:[(String,[String:Any])]=[]
                let realCall:WhiteBalanceCommandCall={method,params in
                    recorded.append((method,params))
                    return try await Backend.call(method,params)
                }
                let applied=await store.sampleWhiteBalance(localPoint:CGPoint(x:0.5,y:0.5),
                    previewIdentity:identity,display:display,call:realCall)
                diagnostics=["first_click_calls":recorded.map{$0.0},"tool":store.canvasTool,
                             "registered_display_matches":store.whiteBalanceDisplayGeometry==display,
                             "error":store.error ?? ""]
                try check(applied,"one_neutral_click_completes_sample_and_edit")
                try check(recorded.map{$0.0}==["sample_white_balance","edit_photo"],"one_click_sends_one_sample_and_one_mutation")
                let sampleParams=recorded.first?.1 ?? [:]
                try check(sampleParams["expected_source_fingerprint"] as? String==identity.sourceFingerprint &&
                    (sampleParams["client_id"] as? String)==store.whiteBalanceClient &&
                    sampleParams["generation"] as? Int != nil,"sample_binds_frame_fingerprint_and_cancellable_client")
                let editParams=recorded.last?.1 ?? [:]
                let patch=editParams["patch"] as? [String:Any] ?? [:]
                try check(Set(patch.keys)==Set(["temperature","tint"]) &&
                    editParams["expected_revision"] as? Int==firstOriginal.revision &&
                    editParams["expected_source_fingerprint"] as? String==identity.sourceFingerprint,
                    "temperature_and_tint_share_one_captured_source_edit")
                try await ready(firstID)
                let saved=try await photo(firstID)
                let savedHistory=try await Backend.call("list_history",[
                    "photo_id":firstID,"expected_revision":saved.revision
                ])
                let savedSteps=(savedHistory["steps"] as? [[String:Any]])?.count ?? 0
                try check(saved.revision==firstOriginal.revision+1 && savedSteps==initialSteps+1,
                          "paired_white_balance_is_one_revision_and_history_step")
                try await wait {store.historyPage?.photoID==firstID && store.historyPage?.revision==saved.revision}
                try await wait {store.thumbnailRenderer.frames[firstID]?.target.revision==saved.revision}
                try check(store.historyPage?.revision==saved.revision &&
                          store.thumbnailRenderer.frames[firstID]?.target.revision==saved.revision,
                          "successful_edit_refreshes_history_and_revision_keyed_thumbnail")

                // A sampler may return the photo's current WB values. The
                // real edit remains successful even though the catalog treats
                // it as a no-op and does not advance revision or history.
                let noOpBefore=try await photo(firstID)
                let noOpIdentity=try await armSelector(firstID)
                let noOpTemperature=(noOpBefore.recipe["temperature"] as? NSNumber)?.doubleValue ?? 0
                let noOpTint=(noOpBefore.recipe["tint"] as? NSNumber)?.doubleValue ?? 0
                var noOpCalls:[(String,[String:Any])]=[]
                let noOpApplied=await store.sampleWhiteBalance(localPoint:CGPoint(x:0.5,y:0.5),
                    previewIdentity:noOpIdentity,display:display,call:{method,params in
                        noOpCalls.append((method,params))
                        if method=="sample_white_balance" {
                            return ["photo_id":firstID,"revision":noOpIdentity.context.revision,
                                "source_fingerprint":noOpIdentity.sourceFingerprint,
                                "temperature":noOpTemperature,"tint":noOpTint]
                        }
                        return try await Backend.call(method,params)
                    })
                let noOpAfter=try await photo(firstID)
                let noOpHistory=try await Backend.call("list_history",[
                    "photo_id":firstID,"expected_revision":noOpAfter.revision
                ])
                let noOpSteps=(noOpHistory["steps"] as? [[String:Any]])?.count ?? 0
                let noOpPatch=noOpCalls.last?.1["patch"] as? [String:Any] ?? [:]
                try check(noOpApplied && noOpCalls.map{$0.0}==["sample_white_balance","edit_photo"] &&
                          noOpCalls.last?.1["expected_revision"] as? Int==noOpBefore.revision &&
                          (noOpPatch["temperature"] as? NSNumber)?.doubleValue==noOpTemperature &&
                          (noOpPatch["tint"] as? NSNumber)?.doubleValue==noOpTint &&
                          noOpAfter.revision==noOpBefore.revision && noOpSteps==savedSteps && store.error==nil,
                          "no_op_white_balance_is_successful_without_revision_or_history_increment")

                // Recipe changes made while the accepted paired edit is
                // in flight remain pending and commit on its returned revision.
                let beforePending=try await photo(firstID)
                let pendingIdentity=try await armSelector(firstID)
                let pendingGate=WhiteBalanceResponseGate();pendingGate.holdMethod="edit_photo"
                let pendingTask=Task {await store.sampleWhiteBalance(localPoint:CGPoint(x:0.42,y:0.58),
                    previewIdentity:pendingIdentity,display:display,call:{method,params in
                        try await pendingGate.call(method,params)
                    })}
                try await wait {pendingGate.continuation != nil}
                store.set("exposure",0.35)
                try check((store.recipe["exposure"] as? NSNumber)?.doubleValue==0.35 &&
                          store.hasPendingEdits,
                          "concurrent_recipe_change_remains_pending_during_white_balance_edit")
                guard let pendingRow=pendingGate.heldReply,let pendingWB=Photo(pendingRow) else {
                    throw EngineFailure(message:"Paired WB reply was not captured")
                }
                pendingGate.release()
                let pendingApplied=await pendingTask.value
                try await ready(firstID)
                let afterPending=try await photo(firstID)
                try await wait {store.historyPage?.revision==afterPending.revision}
                try await wait {store.thumbnailRenderer.frames[firstID]?.target.revision==afterPending.revision}
                try check(pendingApplied && pendingWB.revision>=beforePending.revision &&
                          afterPending.revision==pendingWB.revision+1 &&
                          (afterPending.recipe["exposure"] as? NSNumber)?.doubleValue==0.35 &&
                          (store.recipe["exposure"] as? NSNumber)?.doubleValue==0.35 &&
                          !store.hasPendingEdits && !store.editing,
                          "accepted_white_balance_preserves_and_commits_pending_recipe_patch")

                // A rejected paired WB mutation preserves the unsaved slider
                // patch for an explicit discard/reload decision. It never
                // retries the uncertain white-balance mutation.
                let failedEditBefore=try await photo(firstID)
                let failedEditIdentity=try await armSelector(firstID)
                var failedEditContinuation:CheckedContinuation<Void,Never>?
                var failedEditCalls:[String]=[]
                let failedEditTask=Task {await store.sampleWhiteBalance(localPoint:CGPoint(x:0.44,y:0.56),
                    previewIdentity:failedEditIdentity,display:display,call:{method,params in
                        failedEditCalls.append(method)
                        if method=="sample_white_balance" {return try await Backend.call(method,params)}
                        if method=="edit_photo" {
                            await withCheckedContinuation { (continuation:CheckedContinuation<Void,Never>) in
                                failedEditContinuation=continuation
                            }
                            throw EngineFailure(message:"Injected white-balance edit failure")
                        }
                        return try await Backend.call(method,params)
                    })}
                try await wait {failedEditContinuation != nil}
                store.set("exposure",0.72)
                try check(store.editing && store.hasPendingEdits &&
                          (store.recipe["exposure"] as? NSNumber)?.doubleValue==0.72,
                          "recipe_slider_edit_queues_while_white_balance_save_is_pending")
                failedEditContinuation?.resume();failedEditContinuation=nil
                let failedEditApplied=await failedEditTask.value
                let failedEditAfter=try await photo(firstID)
                let catalogExposure=(failedEditBefore.recipe["exposure"] as? NSNumber)?.doubleValue
                let flushRecovery=await store.flushEdits()
                let failedEditRecovery=store.whiteBalanceEditRecovery
                try check(!failedEditApplied && failedEditCalls==["sample_white_balance","edit_photo"] &&
                          store.hasPendingEdits && !store.editing && !flushRecovery && store.error != nil &&
                          !store.canChangePhoto && failedEditRecovery?.photoID==firstID &&
                          failedEditRecovery?.revision==failedEditBefore.revision &&
                          store.photo?.id==firstID && store.photo?.revision==failedEditBefore.revision &&
                          failedEditAfter.revision==failedEditBefore.revision &&
                          (store.recipe["exposure"] as? NSNumber)?.doubleValue==0.72 && catalogExposure != 0.72,
                          "failed_white_balance_preserves_pending_patch_and_exposes_explicit_recovery")
                guard let failedEditRecovery=store.whiteBalanceEditRecovery else {
                    throw EngineFailure(message:"Failed white-balance edit did not expose a recovery action")
                }
                await store.discardWhiteBalancePendingEdits(failedEditRecovery)
                try await ready(firstID)
                let afterDiscard=try await photo(firstID)
                try check(!store.hasPendingEdits && !store.editing && store.canChangePhoto &&
                          store.photo?.id==firstID && store.photo?.revision==afterDiscard.revision &&
                          afterDiscard.revision==failedEditBefore.revision &&
                          (store.recipe["exposure"] as? NSNumber)?.doubleValue==catalogExposure,
                          "explicit_discard_reloads_captured_catalog_photo_and_unblocks_navigation")
                store.activateReviewPhoto(secondID)
                try await ready(secondID)
                try check(store.selected==secondID && store.photo?.id==secondID,
                          "photo_navigation_recovers_after_failed_white_balance_save")
                let staleRecovery=failedEditRecovery
                store.set("exposure",0.19)
                await store.discardWhiteBalancePendingEdits(staleRecovery)
                try check(store.selected==secondID && store.photo?.id==secondID &&
                          store.hasPendingEdits &&
                          (store.recipe["exposure"] as? NSNumber)?.doubleValue==0.19,
                          "stale_recovery_cannot_clear_new_photo_draft_or_change_selection")
                await store.commit()
                try await ready(secondID)
                let recoveredNewDraft=try await photo(secondID)
                try check(!store.hasPendingEdits && recoveredNewDraft.revision==store.photo?.revision &&
                          (recoveredNewDraft.recipe["exposure"] as? NSNumber)?.doubleValue==0.19,
                          "new_photo_draft_remains_committable_after_stale_recovery")

                // Cancellation of the preview-wait phase clears arming state;
                // tool and comparison changes also abort it without trapping
                // the next explicit arm attempt.
                store.activateReviewPhoto(firstID)
                try await ready(firstID)
                let cancelledArmer=try await holdArmingAfterFlush(firstID)
                cancelledArmer.cancel()
                try await wait {!store.whiteBalanceArming}
                await cancelledArmer.value
                store.rendering=false
                try check(!store.whiteBalanceTargetActive && !store.whiteBalanceArming,
                          "task_cancellation_clears_preview_wait_arming_state")

                // Cancelling a flush that is waiting on a newer edit must
                // return without clearing that edit's busy state.
                store.editing=true
                let cancelledFlush=Task {await store.flushEdits()}
                await Task.yield()
                cancelledFlush.cancel()
                let flushResult=await cancelledFlush.value
                try check(!flushResult && store.editing,
                          "cancelled_flush_exits_without_clearing_active_edit")
                store.editing=false
                let rearmedAfterFlush=try await armSelector(firstID)
                try check(rearmedAfterFlush.context.photoID==firstID && store.whiteBalanceTargetActive,
                          "white_balance_can_rearm_after_cancelled_flush")
                store.cancelWhiteBalanceSelector()
                try await wait {!store.whiteBalanceTargetActive && !store.whiteBalanceArming}

                let toolArmer=try await holdArmingAfterFlush(firstID)
                store.canvasTool="curve"
                store.whiteBalanceCanvasToolDidChange("curve")
                try await wait {!store.whiteBalanceArming}
                await toolArmer.value
                store.rendering=false
                try check(store.canvasTool=="curve" && !store.whiteBalanceArming && !store.whiteBalanceTargetActive,
                          "tool_change_during_arming_cancels_without_stale_reactivation")
                _=try await armSelector(firstID)
                store.canvasTool="curve"
                store.whiteBalanceCanvasToolDidChange("curve")
                try check(!store.whiteBalanceTargetActive && store.whiteBalanceArmPreview==nil &&
                          !store.whiteBalanceSampling,
                          "active_selector_cancels_when_user_changes_canvas_tool")
                store.cancelWhiteBalanceSelector()

                let comparisonArmer=try await holdArmingAfterFlush(firstID)
                store.setComparisonMode(.before)
                try await wait {!store.whiteBalanceArming}
                await comparisonArmer.value
                try await ready(firstID)
                try check(store.comparisonMode == .before && !store.whiteBalanceArming && !store.whiteBalanceTargetActive,
                          "comparison_change_during_arming_cancels_cleanly")
                store.setComparisonMode(.after)
                try await ready(firstID)
                _=try await armSelector(firstID)
                store.setComparisonMode(.before)
                try check(!store.whiteBalanceTargetActive && store.whiteBalanceArmPreview==nil &&
                          !store.whiteBalanceSampling,
                          "active_selector_cancels_when_user_leaves_after_view")
                try await ready(firstID)
                store.setComparisonMode(.after)
                try await ready(firstID)
                store.cancelWhiteBalanceSelector()

                // Geometry is captured at the target overlay. A changed
                // viewport cancels a pending sample and cannot reuse its click.
                let mismatchedDisplayIdentity=try await armSelector(firstID)
                let resizedDisplay=WhiteBalanceDisplayGeometry(available:CGSize(width:720,height:540),
                    imageRect:CGRect(x:38,y:30,width:644,height:480),displayScale:2,role:"active",after:true)
                store.whiteBalanceDisplayGeometry=resizedDisplay
                var mismatchedDisplayCalls=0
                let mismatchedDisplay=await store.sampleWhiteBalance(localPoint:CGPoint(x:0.3,y:0.7),
                    previewIdentity:mismatchedDisplayIdentity,display:display,call:{_,_ in
                        mismatchedDisplayCalls+=1;return [:]
                    })
                store.whiteBalanceDisplayDidChange(nil)
                try check(!mismatchedDisplay && mismatchedDisplayCalls==0 && !store.whiteBalanceTargetActive,
                          "sample_rejects_display_geometry_that_no_longer_matches_capture")

                let viewportIdentity=try await armSelector(firstID)
                let viewportGate=WhiteBalanceResponseGate();viewportGate.holdMethod="sample_white_balance"
                let viewportTask=Task {await store.sampleWhiteBalance(localPoint:CGPoint(x:0.3,y:0.7),
                    previewIdentity:viewportIdentity,display:display,call:{method,params in
                        try await viewportGate.call(method,params)
                    })}
                try await wait {viewportGate.continuation != nil}
                store.whiteBalanceDisplayDidChange(resizedDisplay)
                try await wait {!store.whiteBalanceTargetActive && !store.whiteBalanceSampling}
                viewportGate.release()
                let viewportApplied=await viewportTask.value
                try check(!viewportApplied && viewportGate.calls.filter{$0.0=="edit_photo"}.isEmpty &&
                          !store.whiteBalanceArming,
                          "viewport_change_cancels_captured_sample_before_mutation")

                let failedIdentity=try await armSelector(firstID)
                store.error=nil
                var failedCalls:[String]=[]
                let failedSample=await store.sampleWhiteBalance(localPoint:CGPoint(x:0.5,y:0.5),
                    previewIdentity:failedIdentity,display:display,call:{method,_ in
                        failedCalls.append(method)
                        throw EngineFailure(message:"Injected sample failure")
                    })
                try check(!failedSample && failedCalls==["sample_white_balance"] && store.error != nil &&
                          !store.whiteBalanceTargetActive && !store.whiteBalanceSampling && !store.whiteBalanceArming,
                          "sample_failure_is_visible_and_leaves_no_armed_state")
                let recoveredIdentity=try await armSelector(firstID)
                try check(store.whiteBalanceTargetActive && recoveredIdentity.context.photoID==firstID,
                          "selector_can_be_armed_again_after_sample_failure")
                store.cancelWhiteBalanceSelector()

                let lateFailureIdentity=try await armSelector(firstID)
                var lateFailureContinuation:CheckedContinuation<Void,Never>?
                var lateFailureCalls:[String]=[]
                let lateFailureTask=Task {await store.sampleWhiteBalance(localPoint:CGPoint(x:0.48,y:0.52),
                    previewIdentity:lateFailureIdentity,display:display,call:{method,params in
                        lateFailureCalls.append(method)
                        let reply=try await Backend.call(method,params)
                        if method=="sample_white_balance" {
                            await withCheckedContinuation {continuation in lateFailureContinuation=continuation}
                            throw EngineFailure(message:"Late injected sampler failure")
                        }
                        return reply
                    })}
                try await wait {lateFailureContinuation != nil}
                store.cancelWhiteBalanceSelector()
                store.editing=true
                store.error="A newer action completed."
                lateFailureContinuation?.resume();lateFailureContinuation=nil
                let lateFailureApplied=await lateFailureTask.value
                try check(!lateFailureApplied && store.editing && store.error=="A newer action completed." &&
                          lateFailureCalls==["sample_white_balance"],
                          "late_sampler_failure_after_cancel_preserves_newer_edit_and_status")
                store.editing=false

                // Reference mode retains its separate photo, but only the
                // active After role is eligible for the selector.
                await store.startReferenceView()
                await store.setReferencePhoto(secondID)
                try await ready(firstID)
                store.setComparisonMode(.before)
                try await ready(firstID)
                let referenceIdentity=try await armSelector(firstID)
                var referenceCalls=0
                let referenceOnly=WhiteBalanceDisplayGeometry(available:display.available,imageRect:display.imageRect,
                    displayScale:display.displayScale,role:"reference",after:true)
                let rejectedReference=await store.sampleWhiteBalance(localPoint:CGPoint(x:0.5,y:0.5),
                    previewIdentity:referenceIdentity,display:referenceOnly,call:{_,_ in
                        referenceCalls+=1;throw EngineFailure(message:"Reference point should never be sampled")
                    })
                try check(!rejectedReference && referenceCalls==0 && store.referencePhoto?.id==secondID &&
                          store.comparisonMode == .after,"reference_view_preserves_reference_and_rejects_reference_role")
                store.cancelWhiteBalanceSelector()

                // A result held after the real read must be discarded when the
                // user leaves the captured photo; the read cannot become an edit.
                store.leaveReferenceModule()
                store.selected=firstID;store.selection=[firstID];await store.load(firstID)
                try await ready(firstID)
                let staleIdentity=try await armSelector(firstID)
                let beforeStale=try await photo(firstID)
                let gate=WhiteBalanceResponseGate();gate.holdMethod="sample_white_balance"
                let staleTask=Task {await store.sampleWhiteBalance(localPoint:CGPoint(x:0.4,y:0.6),
                    previewIdentity:staleIdentity,display:display,call:{method,params in try await gate.call(method,params)})}
                try await wait {gate.continuation != nil}
                store.selected=secondID;store.selection=[secondID];await store.load(secondID)
                try await ready(secondID)
                gate.release()
                let staleApplied=await staleTask.value
                let afterStale=try await photo(firstID)
                try check(!staleApplied && afterStale.revision==beforeStale.revision &&
                    store.selected==secondID && store.photo?.id==secondID &&
                    !gate.calls.contains(where:{$0.0=="edit_photo"}),
                    "late_sample_after_photo_switch_is_discarded_without_edit_or_retarget")

                // Revision conflicts remain visible after the sampler returns;
                // the native layer does not retry its captured edit.
                let revisionIdentity=try await armSelector(secondID)
                let capturedRevision=store.photo!.revision
                let revisionGate=WhiteBalanceResponseGate();revisionGate.holdMethod="sample_white_balance"
                let revisionTask=Task {await store.sampleWhiteBalance(localPoint:CGPoint(x:0.45,y:0.55),
                    previewIdentity:revisionIdentity,display:display,call:{method,params in try await revisionGate.call(method,params)})}
                try await wait {revisionGate.continuation != nil}
                _=try await Backend.call("edit_photo",["photo_id":secondID,"expected_revision":capturedRevision,
                    "patch":["exposure":0.25]])
                revisionGate.release()
                let conflictApplied=await revisionTask.value
                let currentSecond=try await photo(secondID)
                try check(!conflictApplied && currentSecond.revision==capturedRevision+1 &&
                    store.photo?.revision==capturedRevision && store.error != nil &&
                    revisionGate.calls.filter{$0.0=="edit_photo"}.count==1,
                    "stale_recipe_revision_is_visible_and_never_retried")
                store.selected=secondID;store.selection=[secondID];await store.load(secondID)
                try await ready(secondID)

                // The read may succeed, but the final lock-time fingerprint
                // check must reject a source changed between sample and edit.
                let secondOriginal=try await photo(secondID)
                store.selected=secondID;store.selection=[secondID];await store.load(secondID)
                try await ready(secondID)
                let sourceIdentity=try await armSelector(secondID)
                let sourcePhoto=store.photo!
                let oldAttributes=try FileManager.default.attributesOfItem(atPath:sourcePhoto.path)
                let oldDate=oldAttributes[.modificationDate] as? Date ?? Date()
                let sourceCall:WhiteBalanceCommandCall={method,params in
                    let reply=try await Backend.call(method,params)
                    if method=="sample_white_balance" {
                        try FileManager.default.setAttributes([.modificationDate:oldDate.addingTimeInterval(20)],
                                                              ofItemAtPath:sourcePhoto.path)
                    }
                    return reply
                }
                let refused=await store.sampleWhiteBalance(localPoint:CGPoint(x:0.5,y:0.5),
                    previewIdentity:sourceIdentity,display:display,call:sourceCall)
                let afterSourceRace=try await photo(secondID)
                try FileManager.default.setAttributes([.modificationDate:oldDate],ofItemAtPath:sourcePhoto.path)
                try check(!refused && afterSourceRace.revision==secondOriginal.revision && store.error != nil,
                          "source_change_between_sample_and_edit_is_visible_and_not_applied")

                // Hold the accepted edit reply and navigate to another photo.
                // The catalog write remains attached to the captured ID, while
                // late UI adoption must leave the newly selected photo intact.
                store.error=nil;store.selected=secondID;store.selection=[secondID];await store.load(secondID)
                try await ready(secondID)
                let mutationIdentity=try await armSelector(secondID)
                let gateEdit=WhiteBalanceResponseGate();gateEdit.holdMethod="edit_photo"
                let secondDisplay=display
                let heldEdit=Task {await store.sampleWhiteBalance(localPoint:CGPoint(x:0.5,y:0.5),
                    previewIdentity:mutationIdentity,display:secondDisplay,call:{method,params in try await gateEdit.call(method,params)})}
                try await wait {gateEdit.continuation != nil}
                guard let acceptedMutation=gateEdit.heldReply,let acceptedMutationPhoto=Photo(acceptedMutation) else {
                    throw EngineFailure(message:"Captured WB edit reply was not returned")
                }
                store.selected=firstID;store.selection=[firstID];await store.load(firstID)
                try await ready(firstID)
                let selectedBeforeRelease=store.photo!
                gateEdit.release()
                let committed=await heldEdit.value
                try await wait {store.photo?.id==firstID && !store.loading}
                let selectedAfterRelease=store.photo!
                let committedPhoto=try await photo(secondID)
                try check(committed && committedPhoto.revision==acceptedMutationPhoto.revision &&
                    store.selected==firstID && selectedAfterRelease.id==selectedBeforeRelease.id &&
                    selectedAfterRelease.revision==selectedBeforeRelease.revision,
                    "late_accepted_edit_never_steals_new_photo_selection_or_ui_state")

                // An accepted reply for an older revision must not replace a
                // newer revision already loaded for the same photo identity.
                store.selected=firstID;store.selection=[firstID];await store.load(firstID)
                try await ready(firstID)
                let samePhotoIdentity=try await armSelector(firstID)
                let samePhotoGate=WhiteBalanceResponseGate();samePhotoGate.holdMethod="edit_photo"
                let samePhotoTask=Task {await store.sampleWhiteBalance(localPoint:CGPoint(x:0.52,y:0.48),
                    previewIdentity:samePhotoIdentity,display:display,call:{method,params in
                        try await samePhotoGate.call(method,params)
                    })}
                try await wait {samePhotoGate.continuation != nil}
                guard let acceptedRow=samePhotoGate.heldReply,
                      let acceptedPhoto=Photo(acceptedRow) else {
                    throw EngineFailure(message:"White-balance edit reply was not captured")
                }
                let newerRow=try await Backend.call("edit_photo",[
                    "photo_id":firstID,"expected_revision":acceptedPhoto.revision,
                    "patch":["exposure":0.9]
                ])
                guard let newerPhoto=Photo(newerRow) else {throw EngineFailure(message:"Newer photo edit was not returned")}
                await store.load(firstID)
                try await ready(firstID)
                samePhotoGate.release()
                let oldReplyCommitted=await samePhotoTask.value
                let finalSamePhoto=try await photo(firstID)
                try check(oldReplyCommitted && newerPhoto.revision==acceptedPhoto.revision+1 &&
                    store.photo?.revision==newerPhoto.revision && finalSamePhoto.revision==newerPhoto.revision &&
                    (store.photo?.recipe["exposure"] as? NSNumber)?.doubleValue==0.9 &&
                    (finalSamePhoto.recipe["exposure"] as? NSNumber)?.doubleValue==0.9 && store.error != nil,
                    "late_accepted_reply_does_not_replace_newer_same_photo_revision")
            for (url,bytes) in originals {
                try check(try Data(contentsOf:url)==bytes,"white_balance_preserves_original_\(url.lastPathComponent)")
            }
            // Offscreen view lifecycles register their own geometry. Render
            // only after state checks so they cannot invalidate a held click.
            _=try await armSelector(firstID)
            let inspectorRoot=URL(fileURLWithPath:Backend.catalog)
            try FileManager.default.createDirectory(at:inspectorRoot,withIntermediateDirectories:true)
            try await writeSnapshot("white-balance-inspector.png",InspectorView().environmentObject(store),
                              NSSize(width:390,height:1700),inspectorRoot)
            try await writeSnapshot("white-balance-active-canvas.png",
                WhiteBalanceTargetOverlay(imageSize:CGSize(width:64,height:48),available:CGSize(width:640,height:480),
                    fitted:true,role:"active",after:true).environmentObject(store),
                NSSize(width:640,height:480),inspectorRoot)
            print(String(data:try JSONSerialization.data(withJSONObject:["ok":true,"checks":checks,
                "offscreen_snapshots":["white-balance-inspector.png","white-balance-active-canvas.png"],
                "desktop_ui":"NOT_VERIFIED","keyboard_pointer_voiceover":"NOT_VERIFIED"],
                options:[.prettyPrinted,.sortedKeys]),encoding:.utf8)!)
            exit(0)
        } catch {
            print(String(data:try! JSONSerialization.data(withJSONObject:["ok":false,"checks":checks,
                "error":error.localizedDescription,"store_error":store.error ?? "","diagnostics":diagnostics,
                "desktop_ui":"NOT_VERIFIED"],options:.prettyPrinted),encoding:.utf8)!)
            exit(1)
        }
    }
}
