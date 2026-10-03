// Purpose: selector preferences, local loupe and continuous-session regressions.
// Inputs: generated raster originals, isolated memory settings and packaged IPC.
// Outputs: fresh-frame/generation guards, one mutation per click, pending Done,
// zero hover commands/Store invalidations and offscreen toolbar/loupe evidence.
// No actual desktop hover, pointer latency, VoiceOver or Adobe pixel acceptance.
import AppKit
import Combine
import Foundation
import SwiftUI

@MainActor final class WhiteBalanceOptionsGate {
    var reply:[String:Any]?
    var continuation:CheckedContinuation<[String:Any],Error>?
    func call(_ method:String,_ params:[String:Any]) async throws ->[String:Any] {
        let result=try await Backend.call(method,params)
        guard method=="edit_photo" else {return result}
        return try await withCheckedThrowingContinuation {continuation in
            self.reply=result;self.continuation=continuation
        }
    }
    func release() {
        let result=reply;reply=nil
        continuation?.resume(returning:result ?? [:]);continuation=nil
    }
}

@main struct NativeWhiteBalanceOptionsRegression {
    @MainActor static func main() async {
        _=NSApplication.shared
        let storage=MemoryWhiteBalancePreferences()
        let preferences=WhiteBalancePreferences(storage:storage)
        let store=Store(whiteBalancePreferences:preferences)
        var checks:[String:Bool]=[:]
        func check(_ value:Bool,_ name:String)throws {
            checks[name]=value
            if !value {throw EngineFailure(message:name)}
        }
        func wait(_ condition:()->Bool) async throws {
            for _ in 0..<1000 {
                if condition() {return}
                try await Task.sleep(nanoseconds:20_000_000)
            }
            throw EngineFailure(message:"Selector options state did not settle: \(store.error ?? "no error")")
        }
        func ready(_ id:Int) async throws {
            try await wait {store.photo?.id==id && !store.loading && !store.rendering && store.whiteBalancePreviewIdentity != nil}
        }
        let display=WhiteBalanceDisplayGeometry(available:CGSize(width:640,height:480),
            imageRect:CGRect(x:20,y:20,width:600,height:400),displayScale:1,role:"active",after:true)
        func arm(_ id:Int) async throws ->WhiteBalancePreviewIdentity {
            await store.armWhiteBalanceSelector()
            try await wait {store.whiteBalanceTargetActive && store.whiteBalanceArmPreview != nil}
            store.whiteBalanceDisplayDidChange(display)
            guard let identity=store.whiteBalanceArmPreview else {throw EngineFailure(message:"Missing selector frame")}
            return identity
        }
        func snapshot<V:View>(_ view:V,_ name:String,_ size:NSSize) async throws {
            let host=NSHostingView(rootView:view.environment(\.colorScheme,.dark).background(Color(nsColor:.windowBackgroundColor)))
            host.frame=NSRect(origin:.zero,size:size);host.layoutSubtreeIfNeeded()
            try await Task.sleep(nanoseconds:250_000_000)
            host.layoutSubtreeIfNeeded();host.displayIfNeeded()
            guard let bitmap=host.bitmapImageRepForCachingDisplay(in:host.bounds) else {throw EngineFailure(message:"Missing offscreen bitmap")}
            host.cacheDisplay(in:host.bounds,to:bitmap)
            guard let bytes=bitmap.representation(using:.png,properties:[:]) else {throw EngineFailure(message:"Missing offscreen image")}
            try bytes.write(to:URL(fileURLWithPath:Backend.catalog).appendingPathComponent(name))
        }
        do {
            try check(preferences.autoDismiss && preferences.showLoupe && preferences.scale==8,"selector_defaults_are_explicit")
            preferences.setAutoDismiss(false);preferences.setShowLoupe(false);preferences.setScale(16)
            let reloaded=WhiteBalancePreferences(storage:storage)
            try check(!reloaded.autoDismiss && !reloaded.showLoupe && reloaded.scale==16,"selector_preferences_persist_independently_of_recipe")
            preferences.setScale(.nan);try check(preferences.scale==16,"nonfinite_scale_is_rejected")
            preferences.setScale(100);try check(preferences.scale==24,"visual_scale_is_bounded")
            preferences.setScale(8);preferences.setShowLoupe(true)
            let badStorage=MemoryWhiteBalancePreferences()
            badStorage.values=["WhiteBalanceSelector.scale":Double.infinity,"WhiteBalanceSelector.autoDismiss":"bad"]
            let safe=WhiteBalancePreferences(storage:badStorage)
            try check(safe.autoDismiss && safe.scale==8,"malformed_preferences_restore_safe_defaults")
            for scale in [4.0,8.0,24.0] {
                let rectangle=WhiteBalanceLoupeGeometry.destination(point:CGPoint(x:1,y:0),pixels:CGSize(width:180,height:120),scale:scale,canvas:CGSize(width:188,height:120))!
                try check(abs(rectangle.minX+179.5*scale-94)<1e-9 && abs(rectangle.minY+0.5*scale-60)<1e-9,
                          "loupe_centers_edge_pixel_at_scale_\(Int(scale))")
            }
            let hover=WhiteBalanceHoverState()
            var storeInvalidations=0
            let observer=store.objectWillChange.sink {storeInvalidations+=1}
            for index in 0..<1000 {hover.update(CGPoint(x:Double(index)/1000,y:0.5),rgb:[40,50,60])}
            try check(storeInvalidations==0 && hover.presentation.point != nil,"hover_publications_do_not_invalidate_workspace_store")
            preferences.setScale(12)
            try check(storeInvalidations==0,"preference_publications_do_not_invalidate_workspace_store")
            withExtendedLifetime(observer) {}
            hover.update(nil);try check(hover.presentation.point==nil && hover.presentation.rgb==nil,"hover_exit_clears_local_readout")

            let root=URL(fileURLWithPath:ProcessInfo.processInfo.environment["LUMARAW_TEST_FIXTURES"]!.components(separatedBy:"|")[0]).deletingLastPathComponent()
            let original=root.appendingPathComponent("wb-options.png")
            let bitmap=NSBitmapImageRep(bitmapDataPlanes:nil,pixelsWide:180,pixelsHigh:120,bitsPerSample:8,
                samplesPerPixel:4,hasAlpha:true,isPlanar:false,colorSpaceName:.deviceRGB,bytesPerRow:0,bitsPerPixel:0)!
            for y in 0..<120 {for x in 0..<180 {
                bitmap.setColor(NSColor(calibratedRed:x<90 ? 0.58:0.50,green:0.54,blue:x<90 ? 0.50:0.58,alpha:1),atX:x,y:y)
            }}
            let bytes=bitmap.representation(using:.png,properties:[:])!
            try bytes.write(to:original)
            _=try await Backend.call("queue_control",["action":"pause"])
            await store.importPaths([original.path]);await store.startDevelop()
            let id=store.selected!
            try await ready(id)
            let first=try await arm(id)
            var calls:[String]=[]
            let command:WhiteBalanceCommandCall={method,params in calls.append(method);return try await Backend.call(method,params)}
            // Local hover and scale changes perform no backend operation.
            for index in 0..<1000 {
                hover.move(CGPoint(x:20+Double(index)/1000*600,y:220),imageRect:display.imageRect,
                    preview:first,armed:first,frame:store.activeColorFrame,enabled:true)
            }
            try check(calls.isEmpty,"repeated_local_hover_issues_zero_backend_commands")
            try check(hover.presentation.rgb?.count==3,"hover_reuses_matching_engine_rgb_map")
            hover.move(CGPoint(x:320,y:220),imageRect:display.imageRect,preview:first,armed:nil,
                frame:store.activeColorFrame,enabled:true)
            try check(hover.presentation.point==nil && hover.presentation.rgb==nil,"unarmed_hover_cannot_reuse_frame_values")
            preferences.setScale(24)
            let applied=await store.sampleWhiteBalance(localPoint:CGPoint(x:0.25,y:0.5),previewIdentity:first,display:display,call:command)
            try check(applied && calls==["sample_white_balance","edit_photo"],"continuous_click_sends_one_sample_and_one_edit")
            try check(store.whiteBalanceTargetActive && !store.whiteBalanceAwaitingFrame && store.photo?.revision==first.context.revision+1,
                      "continuous_selection_waits_for_saved_revision_frame")
            guard let second=store.whiteBalanceArmPreview else {throw EngineFailure(message:"Continuous selection has no new frame")}
            try check(second.context.revision==store.photo?.revision && second != first &&
                second.sourceFingerprint==first.sourceFingerprint,"continuous_selection_captures_fresh_revision_and_source")
            try check(store.whiteBalanceInteractionGeneration>0,"continuous_selection_retires_old_worker_generation")
            let stale=await store.sampleWhiteBalance(localPoint:CGPoint(x:0.75,y:0.5),previewIdentity:first,display:display,call:command)
            try check(!stale && calls.count==2,"old_frame_cannot_issue_a_second_sample")

            let gate=WhiteBalanceOptionsGate()
            let pending=Task {await store.sampleWhiteBalance(localPoint:CGPoint(x:0.75,y:0.5),previewIdentity:second,display:display,
                call:{method,params in try await gate.call(method,params)})}
            try await wait {gate.continuation != nil}
            try check(store.whiteBalanceAwaitingFrame && store.whiteBalanceToolVisible && !store.whiteBalanceTargetActive,
                      "continuous_pending_edit_keeps_done_visible_and_blocks_clicks")
            let blocked=await store.sampleWhiteBalance(localPoint:CGPoint(x:0.5,y:0.5),previewIdentity:second,display:display,call:command)
            try check(!blocked && calls.count==2,"pending_edit_cannot_start_another_sample")
            store.cancelWhiteBalanceSelector();gate.release()
            let saved=await pending.value
            try await ready(id)
            try check(saved && !store.whiteBalanceToolVisible && !store.whiteBalanceAwaitingFrame,
                      "done_during_accepted_edit_prevents_late_rearm")
            preferences.setAutoDismiss(true)
            let once=try await arm(id)
            let onceSaved=await store.sampleWhiteBalance(localPoint:CGPoint(x:0.25,y:0.5),previewIdentity:once,display:display,call:command)
            try check(onceSaved && !store.whiteBalanceToolVisible,"auto_dismiss_on_ends_after_one_selection")
            try await ready(id)
            preferences.setAutoDismiss(false)
            let failure=try await arm(id)
            let failed=await store.sampleWhiteBalance(localPoint:CGPoint(x:0.5,y:0.5),previewIdentity:failure,display:display,
                call:{_,_ in throw EngineFailure(message:"Synthetic sample failure")})
            try check(!failed && !store.whiteBalanceToolVisible && !store.whiteBalanceAwaitingFrame,
                      "failed_sample_cancels_continuous_selection_without_retry")
            try check(try Data(contentsOf:original)==bytes,"selector_options_preserve_original_bytes")
            guard let image=store.preview else {throw EngineFailure(message:"Missing loaded preview for loupe snapshots")}
            let rgb=store.activeColorFrame?.sample(CGPoint(x:0.5,y:0.5),before:false).map {Array($0.prefix(3))}
            try await snapshot(WhiteBalanceSelectorOptions(preferences:preferences,busy:false,done:{}),"wb-options-toolbar.png",NSSize(width:640,height:72))
            for scale in [8.0,24.0] {
                try await snapshot(WhiteBalanceLoupePanel(image:image,point:CGPoint(x:0.5,y:0.5),detail:false,scale:scale,rgb:rgb),
                    "wb-loupe-\(Int(scale)).png",NSSize(width:204,height:184))
            }
            store.detail=true;store.render(debounce:false)
            try await ready(id)
            guard let detailImage=store.preview,store.whiteBalancePreviewIdentity?.context.detail==true else {
                throw EngineFailure(message:"Missing actual detail frame for loupe snapshot")
            }
            let detailRGB=store.activeColorFrame?.sample(CGPoint(x:0.5,y:0.5),before:false).map {Array($0.prefix(3))}
            try await snapshot(WhiteBalanceLoupePanel(image:detailImage,point:CGPoint(x:0.5,y:0.5),detail:true,scale:8,rgb:detailRGB),
                "wb-loupe-detail-8.png",NSSize(width:204,height:184))
            print(String(data:try JSONSerialization.data(withJSONObject:["ok":true,"checks":checks,
                "offscreen_snapshots":["wb-options-toolbar.png","wb-loupe-8.png","wb-loupe-24.png","wb-loupe-detail-8.png"],
                "desktop_ui":"NOT_VERIFIED","actual_hover_latency":"NOT_VERIFIED"],options:[.prettyPrinted,.sortedKeys]),encoding:.utf8)!)
            exit(0)
        } catch {
            print(String(data:try! JSONSerialization.data(withJSONObject:["ok":false,"checks":checks,
                "error":error.localizedDescription,"store_error":store.error ?? "","desktop_ui":"NOT_VERIFIED"],options:.prettyPrinted),encoding:.utf8)!)
            exit(1)
        }
    }
}
