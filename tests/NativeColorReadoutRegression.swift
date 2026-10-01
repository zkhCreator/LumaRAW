// Purpose: native RGB/LAB readouts with independent roles and quiet hover updates.
// Inputs: generated originals and a disposable live engine/catalog. Outputs:
// map/Before/dimension/fallback checks, preserved bytes and Store publication counts.
// State and IPC evidence does not establish rendered mouse or desktop acceptance.
import AppKit
import Combine
import Foundation
import SwiftUI

@main struct NativeColorReadoutRegression {
    @MainActor static func main() async {
        _=NSApplication.shared
        let s=Store();var checks:[String:Bool]=[:]
        func check(_ value:Bool,_ name:String)throws {
            checks[name]=value
            if !value {throw EngineFailure(message:name)}
        }
        func wait(_ ready:()->Bool) async throws {
            for _ in 0..<1200 {
                if ready() {return}
                try await Task.sleep(nanoseconds:20_000_000)
            }
            throw EngineFailure(message:"Color readout preparation timed out")
        }
        func activeReady()->Bool {s.activeColorFrame != nil && !s.rendering}
        func referenceReady()->Bool {s.referenceColorFrame != nil && !s.referenceRenderer.loading}
        do {
            let paths=ProcessInfo.processInfo.environment["LUMARAW_TEST_FIXTURES"]!.components(separatedBy:"|")
            let originals=try paths.map {try Data(contentsOf:URL(fileURLWithPath:$0))}
            await s.importPaths(paths);await s.startDevelop()
            try await wait(activeReady)
            let id=s.selected!,other=s.photos.first(where:{$0.id != id})!.id
            s.hoverColors(CGPoint(x:0.25,y:0.4),role:.active)
            try check(s.colorReadouts.reading.active?.count==6 && s.colorReadouts.reading.reference==nil,"active_rgb_and_lab_are_available")
            var publications=0,readoutPublications=0
            let subscription=s.objectWillChange.sink {publications+=1}
            let colorSubscription=s.colorReadouts.objectWillChange.sink {readoutPublications+=1}
            for _ in 0..<300 {s.hoverColors(CGPoint(x:0.25,y:0.4),role:.active)}
            try check(publications==0 && readoutPublications==0,"same_pixel_hover_does_not_republish")
            for index in 0..<300 {s.hoverColors(CGPoint(x:Double(index)/300,y:0.4),role:.active)}
            try check(publications==0 && s.colorReadoutTask==nil && !s.colorReadoutRequestRunning,"local_hover_never_invalidates_workspace_or_requests_engine")
            s.colorReadouts.lab=true
            try check(publications==0,"lab_toggle_is_local_to_readout_view")
            s.clearColorReadout()
            try check(s.colorReadouts.reading.active==nil,"leaving_photo_clears_values")
            await s.startReferenceView();await s.setReferencePhoto(other)
            try await wait {activeReady() && referenceReady()}
            s.hoverColors(CGPoint(x:0.3,y:0.4),role:.reference)
            try check(s.colorReadouts.reading.active != nil && s.colorReadouts.reading.reference != nil,"equal_dimensions_show_both_roles")
            let after=s.colorReadouts.reading.active
            s.set("exposure",1);try check(s.colorReadouts.reading.active==nil,"pending_edit_hides_stale_sample")
            try check(await s.flushEdits(),"save_active_exposure")
            try await wait(activeReady)
            s.setComparisonMode(.before)
            try await wait {activeReady() && s.activeColorFrame?.before != nil}
            s.hoverColors(CGPoint(x:0.3,y:0.4),role:.reference)
            try check(s.colorReadouts.reading.before && s.colorReadouts.reading.active==after,"reference_pair_uses_frozen_active_before")
            s.setComparisonMode(.after);try await wait(activeReady)
            let reference=s.referencePhoto!
            _=try await Backend.call("edit_photo",["photo_id":other,"expected_revision":reference.revision,"patch":["crop":"1:1"]])
            await s.refreshReferencePhoto();try await wait(referenceReady)
            s.hoverColors(CGPoint(x:0.3,y:0.4),role:.active)
            try check(s.colorReadouts.reading.active != nil && s.colorReadouts.reading.reference==nil,"dimension_mismatch_hides_other_reference_value")
            s.hoverColors(CGPoint(x:0.3,y:0.4),role:.reference)
            try check(s.colorReadouts.reading.reference != nil && s.colorReadouts.reading.active==nil,"dimension_mismatch_hides_other_active_value")
            _=try await Backend.call("edit_photo",["photo_id":other,"expected_revision":s.referencePhoto!.revision,"patch":["crop":"original"]])
            await s.refreshReferencePhoto();try await wait(referenceReady)
            s.setReferencePane(CGSize(width:160,height:100),scale:1)
            s.referenceCX=0.85;s.referenceCY=0.85;s.setReferenceZoom(true)
            try await wait {activeReady() && referenceReady()}
            s.hoverColors(CGPoint(x:0.1,y:0.1),role:.active)
            try check(s.colorReadouts.reading.active != nil && s.colorReadouts.reading.reference==nil && s.colorReadoutTask != nil,"off_viewport_counterpart_is_debounced")
            try await wait {s.colorReadouts.reading.reference != nil || s.colorReadouts.reading.error != nil}
            try check(s.colorReadouts.reading.reference?.count==6 && s.colorReadouts.reading.error==nil,"off_viewport_counterpart_returns_one_pixel")
            let matched=s.colorReadouts.reading
            for _ in 0..<300 {s.hoverColors(CGPoint(x:0.1,y:0.1),role:.active)}
            try check(s.colorReadouts.reading==matched && s.colorReadoutTask==nil && !s.colorReadoutRequestRunning,"matching_pixel_is_reused_without_worker")
            s.hoverColors(CGPoint(x:0.2,y:0.1),role:.active);s.clearColorReadout()
            try await Task.sleep(nanoseconds:400_000_000)
            try check(s.colorReadouts.reading.active==nil && s.colorReadouts.reading.reference==nil,"cancelled_hover_cannot_publish_late_values")
            guard let frame=s.activeColorFrame else {throw EngineFailure(message:"Missing active map")}
            try check(frame.after.sample(CGPoint(x:Double.nan,y:0.5))==nil && frame.after.sample(CGPoint(x:-0.01,y:0.5))==nil,"invalid_coordinates_are_rejected")
            let first=frame.fullPoint(.zero)!,last=frame.fullPoint(CGPoint(x:1,y:1))!
            try check(first.x>0 && first.y>0 && last.x<1 && last.y<1,"edge_samples_use_pixel_centers")
            try check(try paths.enumerated().allSatisfy {try Data(contentsOf:URL(fileURLWithPath:$0.element))==originals[$0.offset]},"readout_workflows_preserve_originals")
            subscription.cancel();colorSubscription.cancel()
            // Render only this component with synthetic values. These images
            // check text layout, not an actual desktop window or mouse event.
            let panel=ColorReadoutState()
            panel.update(ColorReading(active:[100,68.4,12.3,54.2,-128.5,106.9],
                reference:[83.9,64.1,0,50.8,-132.1,98.4],before:true,referenceView:true))
            for lab in [false,true] {
                panel.lab=lab
                let renderer=ImageRenderer(content:ColorReadoutView(state:panel).padding(8)
                    .frame(width:280,height:84).background(Color(white:0.1)).environment(\.colorScheme,.dark))
                renderer.scale=2
                guard let bitmap=renderer.cgImage,
                      let data=NSBitmapImageRep(cgImage:bitmap).representation(using:.png,properties:[:]) else {
                    throw EngineFailure(message:"Readout component could not render")
                }
                let name=lab ? "lab":"rgb"
                try data.write(to:URL(fileURLWithPath:Backend.catalog).appendingPathComponent("readout-\(name).png"))
                try check(bitmap.width==560 && bitmap.height==168,"readout_\(name)_layout_rendered")
            }
            print(String(data:try JSONSerialization.data(withJSONObject:["ok":true,"checks":checks,
                "desktop_ui":"NOT_VERIFIED","voiceover":"NOT_VERIFIED"],options:[.prettyPrinted,.sortedKeys]),encoding:.utf8)!)
            exit(0)
        } catch {
            print(String(data:try! JSONSerialization.data(withJSONObject:["ok":false,"checks":checks,
                "error":error.localizedDescription,"store_error":s.error ?? "","readout_error":s.colorReadouts.reading.error ?? ""],options:.prettyPrinted),encoding:.utf8)!)
            exit(1)
        }
    }
}
