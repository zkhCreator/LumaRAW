// Purpose: real Import Loupe Fit/1:1 viewport and stale-frame regression evidence.
// Inputs: five patterned 2400x1800 PNGs, an isolated catalog and packaged Backend.
// Outputs: request/ROI, physical-pixel sizing, edge/reverse pan, stale cancellation and originals checks.
// Offscreen snapshots are layout evidence only; desktop interaction is NOT_VERIFIED.
import AppKit
import Foundation
import SwiftUI

@MainActor private final class RecordingImportLoupeTransport {
    var calls: [(String,[String:Any])]=[]
    func call(_ method: String,_ params: [String:Any]) async throws -> [String:Any] {
        calls.append((method,params))
        return try await Backend.call(method,params)
    }
}

@MainActor private final class DelayedImportLoupeTransport {
    private struct Pending {
        let params: [String:Any]
        let continuation: CheckedContinuation<[String:Any],Error>
    }
    private var pending: [Pending]=[]
    var count: Int { pending.count }

    func call(_ method: String,_ params: [String:Any]) async throws -> [String:Any] {
        if method == "cancel_preview" { return [:] }
        return try await withCheckedThrowingContinuation { continuation in
            pending.append(Pending(params:params,continuation:continuation))
        }
    }

    func complete(_ index: Int,pathsByID: [Int:String],previewPath: String) {
        let request=pending[index]
        request.continuation.resume(returning:loupeResponse(request.params,pathsByID:pathsByID,previewPath:previewPath))
    }
}

private func loupeResponse(_ params: [String:Any],pathsByID: [Int:String],previewPath: String) -> [String:Any] {
    let itemID=params["item_id"] as? Int ?? 0
    let source=pathsByID[itemID] ?? ""
    let fullWidth=2400,fullHeight=1800
    var width=1600,height=1200
    var roi=[0,0,width,height]
    let oneToOne=params["viewport"] is [String:Any]
    if let viewport=params["viewport"] as? [String:Any] {
        width=min(fullWidth,viewport["width"] as? Int ?? 1)
        height=min(fullHeight,viewport["height"] as? Int ?? 1)
        let cx=viewport["cx"] as? Double ?? 0.5
        let cy=viewport["cy"] as? Double ?? 0.5
        let x=max(0,min(fullWidth-width,Int((cx*Double(fullWidth)-Double(width)/2).rounded())))
        let y=max(0,min(fullHeight-height,Int((cy*Double(fullHeight)-Double(height)/2).rounded())))
        roi=[x,y,width,height]
    }
    let roiValue: Any=oneToOne ? roi:NSNull()
    return ["plan_id":params["plan_id"] as? Int ?? 0,"item_id":itemID,
        "revision":params["expected_revision"] as? Int ?? 0,"source":source,"preview":previewPath,
        "detail":oneToOne,"width":width,"height":height,"full_width":fullWidth,"full_height":fullHeight,"roi":roiValue]
}

@MainActor @main struct NativeImportLoupeRegression {
    static func main() async {
        _ = NSApplication.shared
        var checks: [String:Bool]=[:]
        var screenshots: [String]=[]
        func check(_ value: Bool,_ name: String) throws {
            checks[name]=value
            if !value { throw EngineFailure(message:name) }
        }
        func waitUntil(_ predicate: @MainActor () -> Bool) async {
            for _ in 0..<1200 {
                if predicate() { return }
                try? await Task.sleep(nanoseconds:10_000_000)
            }
        }
        func snapshot<V: View>(_ name: String,_ view: V,_ size: NSSize,_ root: URL,
            ready: @MainActor () -> Bool) async throws {
            let host=NSHostingView(rootView:view.background(Color(nsColor:.windowBackgroundColor)))
            host.frame=NSRect(origin:.zero,size:size)
            host.layoutSubtreeIfNeeded()
            try await Task.sleep(nanoseconds:200_000_000)
            await waitUntil(ready)
            host.layoutSubtreeIfNeeded()
            guard ready() else { throw EngineFailure(message:"Loupe frame did not settle before offscreen snapshot") }
            guard let bitmap=host.bitmapImageRepForCachingDisplay(in:host.bounds) else {
                throw EngineFailure(message:"No offscreen bitmap for \(name)")
            }
            host.cacheDisplay(in:host.bounds,to:bitmap)
            guard let png=bitmap.representation(using:.png,properties:[:]) else {
                throw EngineFailure(message:"No offscreen PNG for \(name)")
            }
            try png.write(to:root.appendingPathComponent(name));screenshots.append(name)
        }

        do {
            let paths=ProcessInfo.processInfo.environment["LUMARAW_TEST_FIXTURES"]!
                .components(separatedBy:"|")
            try check(paths.count == 5,"runner_supplies_five_patterned_sources")
            let originalBytes=try paths.map{try Data(contentsOf:URL(fileURLWithPath:$0))}
            let root=URL(fileURLWithPath:ProcessInfo.processInfo.environment["LUMARAW_CATALOG"]!)
                .deletingLastPathComponent()
            let recorder=RecordingImportLoupeTransport()
            let review=ImportReviewModel(sources:paths,detailCall:{method,params in try await recorder.call(method,params)})
            await review.scan()
            try check(review.plan?.ready == true && review.items.count == 5,"real_import_review_scans_patterned_sources")
            guard let plan=review.plan,let first=review.items.first else {
                throw EngineFailure(message:"Import Loupe fixture review did not become ready")
            }
            let pathsByID=Dictionary(uniqueKeysWithValues:review.items.map{($0.id,$0.path)})

            review.focus(first,detail:true)
            await waitUntil { review.currentLoupeFrame != nil && !review.detailLoading }
            let fitFrame=review.currentLoupeFrame
            let fitCall=recorder.calls.last(where:{$0.0 == "preview_import_item"})?.1
            try check(fitCall?["detail"] as? Bool == true && fitCall?["viewport"] == nil,
                "fit_request_keeps_fitted_detail_without_viewport")
            try check(fitFrame?.width == 1600 && fitFrame?.height == 1200
                && (fitFrame?.width ?? 0) <= 1600 && (fitFrame?.height ?? 0) <= 1600,
                "fit_frame_uses_bounded_preview_dimensions")

            review.setLoupeViewportSize(CGSize(width:400,height:300),displayScale:2)
            try check(review.loupePixelSize.width == 800 && review.loupePixelSize.height == 600,
                "retina_two_viewport_uses_physical_pixels")
            review.setLoupeZoom(1)
            await waitUntil { review.currentLoupeFrame?.request.width == 800 && !review.detailLoading }
            let oneToOne=review.currentLoupeFrame
            let fullCall=recorder.calls.last(where:{$0.0 == "preview_import_item"})?.1
            let viewport=fullCall?["viewport"] as? [String:Any]
            try check(fullCall?["detail"] as? Bool == true && viewport?["width"] as? Int == 800
                && viewport?["height"] as? Int == 600 && viewport?["cx"] as? Double == 0.5
                && viewport?["cy"] as? Double == 0.5,
                "one_to_one_request_sends_normalized_center_and_backing_pixels")
            try check(oneToOne?.width == 800 && oneToOne?.height == 600
                && oneToOne?.fullWidth == 2400 && oneToOne?.fullHeight == 1800
                && oneToOne?.roi?.x == 800 && oneToOne?.roi?.y == 600,
                "one_to_one_frame_validates_png_size_and_roi")

            if let frame=review.currentLoupeFrame {
                review.finishLoupePan(CGSize(width:5000,height:5000),displayScale:2,from:frame.request)
            }
            await waitUntil { review.currentLoupeFrame?.roi?.x == 0 && review.currentLoupeFrame?.roi?.y == 0
                && !review.detailLoading }
            let edge=review.currentLoupeFrame
            try check(edge?.roi?.x == 0 && edge?.roi?.y == 0
                && abs(review.loupeViewport.cx-Double(review.loupePixelSize.width)/(2*2400)) < 0.000001
                && abs(review.loupeViewport.cy-Double(review.loupePixelSize.height)/(2*1800)) < 0.000001,
                "large_pan_clamps_to_first_real_roi_without_dead_zone")
            if let frame=review.currentLoupeFrame {
                review.finishLoupePan(CGSize(width:-10,height:-10),displayScale:2,from:frame.request)
            }
            await waitUntil { review.currentLoupeFrame?.roi?.x == 20 && review.currentLoupeFrame?.roi?.y == 20
                && !review.detailLoading }
            try check(review.currentLoupeFrame?.roi?.x == 20 && review.currentLoupeFrame?.roi?.y == 20,
                "small_reverse_pan_moves_roi_by_physical_pixel_delta")

            try await snapshot("import-loupe-100-offscreen.png",
                ImportLoupePane(model:review).environment(\.displayScale,2),NSSize(width:400,height:330),root,
                ready:{review.currentLoupeFrame != nil && !review.detailLoading})

            let delayed=DelayedImportLoupeTransport()
            let late=ImportReviewModel(sources:paths,detailCall:{method,params in try await delayed.call(method,params)})
            late.plan=plan;late.items=review.items;late.total=review.total;late.loupe=true
            late.focus(late.items[0],detail:true)
            await waitUntil { delayed.count == 1 }
            late.focus(late.items[1])
            await waitUntil { delayed.count == 2 }
            delayed.complete(1,pathsByID:pathsByID,previewPath:paths[1])
            await waitUntil { late.currentLoupeFrame?.request.itemID == late.items[1].id }
            delayed.complete(0,pathsByID:pathsByID,previewPath:paths[0])
            try? await Task.sleep(nanoseconds:100_000_000)
            try check(late.currentLoupeFrame?.request.itemID == late.items[1].id,
                "late_previous_focus_reply_cannot_replace_current_frame")
            late.invalidate()

            let resizingTransport=DelayedImportLoupeTransport()
            let resizing=ImportReviewModel(sources:paths,detailCall:{method,params in try await resizingTransport.call(method,params)})
            resizing.plan=plan;resizing.items=review.items;resizing.total=review.total
            resizing.focused=resizing.items[0].id;resizing.loupe=true
            resizing.setLoupeViewportSize(CGSize(width:400,height:300),displayScale:2)
            resizing.setLoupeZoom(1)
            guard let oldViewportRequest=resizing.currentLoupeRequest else {
                throw EngineFailure(message:"100 percent resize request was not captured")
            }
            await waitUntil { resizingTransport.count == 1 }
            resizing.setLoupeViewportSize(CGSize(width:420,height:300),displayScale:2)
            await waitUntil { resizingTransport.count == 2 }
            resizingTransport.complete(1,pathsByID:pathsByID,previewPath:paths[0])
            await waitUntil { resizing.currentLoupeFrame?.request.width == 840 }
            resizingTransport.complete(0,pathsByID:pathsByID,previewPath:paths[0])
            try? await Task.sleep(nanoseconds:100_000_000)
            try check(resizing.currentLoupeFrame?.request.width == 840
                && resizing.loupePixelSize.width == 840,
                "late_old_pane_reply_cannot_replace_resized_viewport")
            let viewportBeforeStalePan=resizing.loupeViewport
            let requestsBeforeStalePan=resizingTransport.count
            resizing.finishLoupePan(CGSize(width:40,height:25),displayScale:2,from:oldViewportRequest)
            try check(resizing.loupeViewport == viewportBeforeStalePan
                && resizingTransport.count == requestsBeforeStalePan,
                "saved_pre_resize_request_cannot_pan_or_queue_another_render")
            resizing.invalidate()

            let wrongPaths=pathsByID
            let wrongIdentity=ImportReviewModel(sources:paths,detailCall:{method,params in
                if method == "cancel_preview" { return [:] }
                var result=loupeResponse(params,pathsByID:wrongPaths,previewPath:paths[0])
                result["source"]="/stale/cached-source.png"
                return result
            })
            wrongIdentity.plan=plan;wrongIdentity.items=review.items;wrongIdentity.total=review.total
            wrongIdentity.loupe=true;wrongIdentity.focus(wrongIdentity.items[0],detail:true)
            await waitUntil { wrongIdentity.detailError != nil }
            try check(wrongIdentity.currentLoupeFrame == nil,"mismatched_cached_source_identity_is_discarded")
            wrongIdentity.invalidate()

            try check(try paths.map{try Data(contentsOf:URL(fileURLWithPath:$0))} == originalBytes,
                "all_loupe_modes_and_pans_preserve_original_bytes")
            await review.cancel();review.invalidate()
            let receipt:[String:Any]=["ok":true,"passed":checks.count,"checks":checks,
                "offscreen_screenshots":screenshots,"desktop_ui":"NOT_VERIFIED"]
            let data=try JSONSerialization.data(withJSONObject:receipt,options:[.prettyPrinted,.sortedKeys])
            print(String(decoding:data,as:UTF8.self));exit(0)
        } catch {
            let receipt:[String:Any]=["ok":false,"checks":checks,"error":error.localizedDescription,
                "offscreen_screenshots":screenshots,"desktop_ui":"NOT_VERIFIED"]
            let data=(try? JSONSerialization.data(withJSONObject:receipt,options:[.prettyPrinted,.sortedKeys])) ?? Data()
            print(String(decoding:data,as:UTF8.self));exit(1)
        }
    }
}
