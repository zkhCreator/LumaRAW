// Purpose: captured drawing safety through real native state and engine commands.
// Inputs: generated originals, typed pointer events and real selection/preview edits.
// The harness perturbs one generated fixture's stat then restores it to test the
// final source fence. App workflows never write originals; byte hashes stay equal.
// Outputs: no retargeting/replay, bounded paths, crop/history and offscreen stroke evidence.
// No desktop pointer dispatch, VoiceOver, camera accuracy or performance percentile claim.
import AppKit
import Foundation
import SwiftUI

@main struct NativeDrawingRegression {
    @MainActor static func main() async {
        _=NSApplication.shared
        let s=Store();var checks:[String:Bool]=[:]
        let rect=CGRect(x:10,y:10,width:400,height:300)
        let start=CGPoint(x:90,y:70),end=CGPoint(x:290,y:220)
        func check(_ value:Bool,_ name:String) throws {
            checks[name]=value;if !value {throw EngineFailure(message:name)}
        }
        func ready(_ id:Int) async throws {
            for _ in 0..<800 {
                if s.photo?.id==id,!s.loading,!s.rendering,
                   s.activeViewportFrame?.context==s.currentBeforeContext,
                   s.previewGeometry?.revision==s.photo?.revision,s.preview != nil {return}
                try await Task.sleep(nanoseconds:20_000_000)
            }
            throw EngineFailure(message:"Drawing frame did not settle: \(s.error ?? "no error")")
        }
        func capture(_ tool:String) throws ->DrawingContext {
            s.canvasTool=tool
            guard let value=s.drawingContext(image:s.preview!,rect:rect) else {throw EngineFailure(message:"Missing drawing context")}
            return value
        }
        func stroke(_ context:DrawingContext)->DrawingStroke {
            var gesture=DrawingGesture()
            gesture.update(start:start,location:start,current:context)
            gesture.update(start:start,location:end,current:context)
            return gesture.finish(current:context)!
        }
        func row(_ id:Int) async throws ->Photo {Photo(try await Backend.call("get_photo",["photo_id":id]))!}
        func snapshot(_ stroke:DrawingStroke,current:DrawingContext?,name:String) async throws ->Int {
            let host=NSHostingView(rootView:DrawingStrokePreview(stroke:stroke,current:current).background(Color.black))
            host.frame=NSRect(x:0,y:0,width:420,height:320);host.layoutSubtreeIfNeeded()
            try await Task.sleep(nanoseconds:250_000_000);host.layoutSubtreeIfNeeded();host.displayIfNeeded()
            guard let bitmap=host.bitmapImageRepForCachingDisplay(in:host.bounds) else {throw EngineFailure(message:"Missing drawing bitmap")}
            host.cacheDisplay(in:host.bounds,to:bitmap)
            let bytes=bitmap.representation(using:.png,properties:[:])!
            try bytes.write(to:URL(fileURLWithPath:Backend.catalog).appendingPathComponent(name))
            var whites=0
            for y in stride(from:0,to:bitmap.pixelsHigh,by:5) {
                for x in stride(from:0,to:bitmap.pixelsWide,by:5) {
                    if let color=bitmap.colorAt(x:x,y:y)?.usingColorSpace(.deviceRGB),
                       color.redComponent>0.8,color.greenComponent>0.8,color.blueComponent>0.8 {whites+=1}
                }
            }
            return whites
        }
        do {
            let paths=ProcessInfo.processInfo.environment["LUMARAW_TEST_FIXTURES"]!.components(separatedBy:"|")
            let originals=try paths.map {try Data(contentsOf:URL(fileURLWithPath:$0))}
            await s.importPaths(paths);s.selected=1;s.selection=[1];s.develop=true;await s.load(1);try await ready(1)
            let context=try capture("brush"),image=s.preview!,brush=stroke(context)
            var tap=DrawingGesture();tap.update(start:start,location:start,current:context)
            try check(tap.finish(current:context)==nil,"pointer_tap_does_not_create_mask")
            var invalid=DrawingGesture()
            invalid.update(start:.zero,location:end,current:context)
            invalid.update(start:start,location:end,current:context)
            try check(invalid.cancelled && invalid.finish(current:context)==nil,"outside_start_stays_cancelled_until_release")
            let white=try await snapshot(brush,current:context,name:"drawing-current.png")
            let hidden=try await snapshot(brush,current:nil,name:"drawing-stale.png")
            try check(white>20 && hidden==0,"offscreen_stroke_only_draws_for_matching_context")
            let source=s.previewSourceFingerprint
            s.previewSourceFingerprint=String(repeating:"f",count:24)
            try check(!s.applyDrawing(brush,image:image,rect:rect) && !s.hasPendingEdits,
                "changed_source_token_rejects_previous_stroke")
            s.previewSourceFingerprint=source
            var cancelled=DrawingGesture();cancelled.update(start:start,location:end,current:context)
            cancelled.update(start:start,location:end,current:nil)
            cancelled.update(start:start,location:end,current:context)
            try check(cancelled.cancelled && cancelled.finish(current:context)==nil,"transient_change_cannot_rearm_same_gesture")
            try check(!s.applyDrawing(brush,image:image,rect:rect.insetBy(dx:1,dy:1)) && !s.hasPendingEdits,
                "window_geometry_change_cannot_save_old_stroke")
            s.canvasTool="crop"
            try check(!s.applyDrawing(brush,image:image,rect:rect) && s.canvasTool=="crop" && !s.hasPendingEdits,
                "tool_change_is_not_retargeted_or_overwritten")
            s.canvasTool="brush";s.maskActionBusy=true
            try check(s.drawingContext(image:image,rect:rect)==nil && !s.applyDrawing(brush,image:image,rect:rect),
                "mask_management_blocks_drawing")
            s.maskActionBusy=false
            s.maskActionRecovery=LocalMaskRecovery(photoID:1,message:"Explicit reload required")
            try check(s.drawingContext(image:image,rect:rect)==nil && !s.applyDrawing(brush,image:image,rect:rect),
                "uncertain_mask_state_blocks_drawing")
            s.maskActionRecovery=nil
            s.selected=2;s.selection=[2];await s.load(2);try await ready(2)
            try check(!s.applyDrawing(brush,image:s.preview!,rect:rect) && !s.hasPendingEdits,
                "real_photo_switch_never_applies_previous_points")
            let two=try await row(2)
            try check((two.recipe["masks"] as? [[String:Any]])?.isEmpty==true && two.revision==0,
                "new_photo_catalog_remains_unmodified")
            s.selected=1;s.selection=[1];await s.load(1);try await ready(1);s.canvasTool="brush"
            try check(!s.applyDrawing(brush,image:s.preview!,rect:rect) && !s.hasPendingEdits,
                "return_to_same_photo_and_revision_still_rejects_old_frame")
            let pending=stroke(try capture("brush"));s.set("exposure",0.25)
            try check(!s.applyDrawing(pending,image:s.preview!,rect:rect),"pending_adjustments_block_stroke_adoption")
            try check(await s.flushEdits(),"unrelated_pending_edit_saves");try await ready(1)
            let external=stroke(try capture("brush"))
            _=try await Backend.call("edit_photo",["photo_id":1,"expected_revision":s.photo!.revision,"patch":["exposure":0.5]])
            try check(s.applyDrawing(external,image:s.preview!,rect:rect),"captured_local_draft_uses_reviewed_revision")
            let saved=await s.flushEdits(),conflict=try await row(1)
            try check(!saved && (conflict.recipe["masks"] as? [[String:Any]])?.isEmpty==true &&
                (conflict.recipe["exposure"] as? NSNumber)?.doubleValue==0.5,"external_revision_conflict_never_overwrites_or_replays")
            s.error=nil;await s.load(1);try await ready(1)
            let sourceStroke=stroke(try capture("brush")),sourceRevision=s.photo!.revision
            let attributes=try FileManager.default.attributesOfItem(atPath:paths[0])
            let modified=attributes[.modificationDate] as! Date
            try FileManager.default.setAttributes([.modificationDate:modified.addingTimeInterval(2)],ofItemAtPath:paths[0])
            let sourceApplied=s.applyDrawing(sourceStroke,image:s.preview!,rect:rect)
            let sourceSaved=await s.flushEdits(),sourcePhoto=try await row(1)
            try FileManager.default.setAttributes([.modificationDate:modified],ofItemAtPath:paths[0])
            try check(sourceApplied && !sourceSaved && sourcePhoto.revision==sourceRevision &&
                (sourcePhoto.recipe["masks"] as? [[String:Any]])?.isEmpty==true,
                "changed_original_stat_rejected_before_catalog_write")
            s.error=nil;await s.load(1);try await ready(1)
            let linear=try capture("linear");var long=DrawingGesture()
            for i in 0..<700 {long.update(start:start,location:CGPoint(x:90+Double(i)*0.4,y:220),current:linear)}
            let line=long.finish(current:linear)!
            try check(line.points.count==2 && line.points.last!.x>0.85,"long_nonbrush_drag_updates_endpoint_with_bounded_storage")
            let brushContext=try capture("brush");var longBrush=DrawingGesture()
            for i in 0..<700 {longBrush.update(start:start,location:CGPoint(x:90+Double(i)*0.4,y:220),current:brushContext)}
            let bounded=longBrush.finish(current:brushContext)!
            try check(bounded.points.count==500,"brush_retains_engine_point_bound")
            let brushApplied=s.applyDrawing(bounded,image:s.preview!,rect:rect)
            let brushSaved=await s.flushEdits()
            try check(brushApplied && brushSaved,"bounded_brush_saves_through_shared_service")
            let painted=try await row(1)
            try check((painted.recipe["masks"] as? [[String:Any]])?.first?["points"] as? [[Double]] != nil &&
                (painted.recipe["exposure"] as? NSNumber)?.doubleValue==0.5,"drawing_preserves_unrelated_adjustments")
            _=try await Backend.call("undo_photo",["photo_id":1,"expected_revision":painted.revision])
            await s.load(1);try await ready(1)
            let undone=try await row(1)
            try check((undone.recipe["masks"] as? [[String:Any]])?.isEmpty==true,
                "one_undo_removes_one_completed_drawing")
            s.set("crop_box",[0.1,0.2,0.9,0.8]);_=await s.flushEdits();try await ready(1)
            let crop=stroke(try capture("crop"))
            let cropApplied=s.applyDrawing(crop,image:s.preview!,rect:rect),cropSaved=await s.flushEdits()
            try check(cropApplied && cropSaved,"nested_crop_saves")
            let cropped=try await row(1),box=cropped.recipe["crop_box"] as! [Double]
            try check(zip(box,[0.26,0.32,0.66,0.62]).allSatisfy {abs($0.0-$0.1)<1e-8},
                "nested_crop_uses_captured_engine_crop_geometry")
            try check(try paths.map {try Data(contentsOf:URL(fileURLWithPath:$0))}==originals,
                "drawing_workflows_preserve_original_bytes")
            print(String(data:try JSONSerialization.data(withJSONObject:["ok":true,"checks":checks,
                "offscreen_snapshots":["drawing-current.png","drawing-stale.png"],
                "desktop_ui":"NOT_VERIFIED","voiceover":"NOT_VERIFIED"],options:[.prettyPrinted,.sortedKeys]),encoding:.utf8)!)
            exit(0)
        } catch {
            print(String(data:try! JSONSerialization.data(withJSONObject:["ok":false,"checks":checks,
                "error":error.localizedDescription,"store_error":s.error ?? ""],options:.prettyPrinted),encoding:.utf8)!)
            exit(1)
        }
    }
}
