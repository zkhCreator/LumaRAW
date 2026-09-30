// Purpose: verify paired layout geometry and shared, captured comparison panning.
// Inputs: generated large originals, native value geometry and real broker replies.
// Outputs: physical-pixel/layout bounds, cache-free layout changes and stale-event
// rejection. No desktop event dispatch, screenshots or VoiceOver claim.
import AppKit
import Foundation

@main struct NativeComparisonLayoutRegression {
    @MainActor static func main() async {
        _=NSApplication.shared
        let s=Store()
        var checks:[String:Bool]=[:]
        func check(_ value:Bool,_ name:String)throws {
            checks[name]=value
            if !value {throw EngineFailure(message:name)}
        }
        func close(_ a:Double,_ b:Double)->Bool {abs(a-b)<0.00001}
        func ready() async throws {
            for _ in 0..<600 {
                if !s.rendering && !s.loading && !s.hasPendingEdits && s.preview != nil &&
                    (!s.needsBeforePreview || s.before != nil && s.beforePreviewContext==s.currentBeforeContext) {return}
                try await Task.sleep(nanoseconds:20_000_000)
            }
            throw EngineFailure(message:"Shared comparison viewport timed out")
        }
        func pixels(_ image:NSImage?)->CGSize {
            let rep=image?.representations.first
            return CGSize(width:rep?.pixelsWide ?? 0,height:rep?.pixelsHigh ?? 0)
        }
        do {
            let available=CGSize(width:800,height:600)
            try check(ComparisonLayout.paneSize(available,mode:.leftRight)==CGSize(width:394,height:600),"whole_left_right_has_equal_panes")
            try check(ComparisonLayout.paneSize(available,mode:.topBottom)==CGSize(width:800,height:294),"whole_top_bottom_has_equal_panes")
            for mode in [BeforeAfterMode.leftRightSplit,.topBottomSplit] {
                try check(ComparisonLayout.paneSize(available,mode:mode)==available,"split_uses_complete_image_frame_\(mode.rawValue)")
            }
            let fit=ComparisonLayout.imageRect(pixels:CGSize(width:2400,height:1600),available:available,detail:false,scale:2)
            try check(close(fit.width,800) && close(fit.height,1600.0/3) && close(fit.minY,100.0/3),"fit_preserves_aspect_and_letterbox")
            try check(close(ComparisonLayout.boundary(rect:fit,position:0.25,vertical:false),200),"horizontal_split_uses_image_extent")
            try check(close(ComparisonLayout.boundary(rect:fit,position:0,vertical:true),fit.minY),"vertical_split_starts_at_image_not_letterbox")
            try check(close(ComparisonLayout.boundary(rect:fit,position:.nan,vertical:false),fit.midX),"invalid_divider_falls_back_to_center")
            let detail=ComparisonLayout.imageRect(pixels:CGSize(width:1024,height:768),available:available,detail:true,scale:2)
            try check(detail.size==CGSize(width:512,height:384),"retina_detail_maps_one_physical_pixel")
            try check(ComparisonLayout.imageRect(pixels:.zero,available:available,detail:true,scale:2) == .zero,"empty_image_geometry_is_safe")

            let paths=ProcessInfo.processInfo.environment["LUMARAW_TEST_FIXTURES"]!.components(separatedBy:"|")
            let originals=try paths.map {try Data(contentsOf:URL(fileURLWithPath:$0))}
            await s.importPaths(paths)
            s.selected=1;s.selection=[1];s.develop=true
            await s.load(1);try await ready()
            s.setComparisonMode(.leftRight);try await ready()
            let loaded=s.before,revision=s.photo!.revision
            await s.readHistory();let history=s.historyPage!.steps.count
            for mode in BeforeAfterMode.allCases.filter(\.isPaired) {
                s.setComparisonMode(mode)
                s.setComparisonPane(ComparisonLayout.paneSize(available,mode:mode),scale:2)
                try await Task.sleep(nanoseconds:250_000_000)
                try check(!s.rendering && s.before === loaded && !s.detail,"fit_layout_reuses_both_images_\(mode.rawValue)")
            }
            s.detail=true
            s.setComparisonPane(CGSize(width:320,height:240),scale:2)
            s.render(debounce:false);try await ready()
            try check(pixels(s.preview)==CGSize(width:640,height:480) && pixels(s.before)==pixels(s.preview),"paired_detail_uses_one_bounded_roi")
            for mode in BeforeAfterMode.allCases.filter(\.isPaired) {
                s.setComparisonMode(mode);try await ready()
                try check(s.detail && s.comparisonMode==mode && s.comparisonFrame != nil,"layout_preserves_shared_one_to_one_\(mode.rawValue)")
            }
            let frame=s.comparisonFrame!,mode=s.comparisonMode
            let translation=CGSize(width:80,height:-45)
            let expected=frame.panned(translation,scale:2)!
            s.panComparison(translation,scale:2,frame:frame,mode:mode);try await ready()
            try check(close(s.cx,expected.x) && close(s.cy,expected.y) && s.beforePreviewContext==s.currentBeforeContext,"pan_moves_both_sides_to_same_center")
            try check(close(expected.x,0.5-160.0/2400) && close(expected.y,0.5+90.0/1800),"pan_converts_retina_points_to_source_pixels")
            let currentContext=s.currentBeforeContext
            s.panComparison(translation,scale:2,frame:frame,mode:mode)
            try check(!s.rendering && s.currentBeforeContext==currentContext,"stale_pan_context_is_rejected")
            try check(frame.panned(CGSize(width:Double.nan,height:0),scale:2)==nil && frame.panned(.zero,scale:0)==nil,"invalid_pan_values_are_rejected")
            let edge=frame.panned(CGSize(width:1_000_000,height:-1_000_000),scale:2)!
            try check(close(edge.x,frame.roi.width/2/2400) && close(edge.y,1-frame.roi.height/2/1800),"pan_clamps_to_actual_roi_edges")
            let rendered=s.comparisonFrame!
            s.setComparisonMode(.leftRight);try await ready()
            let changedModeContext=s.currentBeforeContext
            s.panComparison(translation,scale:2,frame:rendered,mode:mode)
            try check(!s.rendering && s.currentBeforeContext==changedModeContext,"old_layout_gesture_cannot_pan_new_layout")

            s.setComparisonPane(CGSize(width:100_000,height:100_000),scale:2);try await ready()
            try check(s.comparisonPixelWidth==2048 && s.comparisonPixelHeight==1536 && pixels(s.before)==CGSize(width:2048,height:1536),"huge_windows_keep_bounded_engine_requests")
            s.setComparisonMode(.before);try await ready()
            try check(pixels(s.before)==CGSize(width:1600,height:1100),"before_only_restores_standard_detail_viewport")
            s.setComparisonMode(.topBottomSplit);try await ready()
            try check(s.detail && pixels(s.before)==CGSize(width:2048,height:1536),"returning_to_pair_preserves_zoom_and_requests_pair_size")
            s.detail=false;s.render(debounce:false);try await ready()
            try check(s.comparisonShortcut([]) && s.comparisonMode == .leftRight,"y_selects_left_right")
            try check(s.comparisonShortcut(.option) && s.comparisonMode == .topBottom,"option_y_selects_top_bottom")
            try check(s.comparisonShortcut(.shift) && s.comparisonMode == .topBottomSplit,"shift_y_selects_matching_split_axis")
            try check(s.comparisonShortcut(.shift) && s.comparisonMode == .after,"repeated_comparison_shortcut_returns_to_after")
            try check(!s.comparisonShortcut(.command),"unrelated_shortcut_modifiers_are_not_consumed")
            s.setComparisonMode(.topBottom);try await ready()
            await s.startDevelop();try await ready()
            try check(s.comparisonMode == .after && s.develop,"develop_loupe_entry_exits_paired_comparison")
            s.canvasTool="crop";await s.startDevelop();try await ready()
            try check(s.canvasTool=="view","develop_loupe_entry_leaves_drawing_tools")
            await s.readHistory()
            try check(s.photo!.revision==revision && s.historyPage!.steps.count==history,"layout_zoom_pan_do_not_mutate_develop_history")
            s.setComparisonMode(.leftRight);try await ready()
            s.detail=true;s.render(debounce:false);try await ready()
            guard let rotate=s.orientSelection("rotate_right") else {throw EngineFailure(message:"Could not rotate comparison fixture")}
            await rotate.value;try await ready()
            let rotated=s.comparisonFrame!
            try check(rotated.fullWidth==1800 && rotated.fullHeight==2400 && rotated.context.orientation==1,"rotated_pair_uses_displayed_output_dimensions")
            let rotatedCenter=rotated.panned(translation,scale:2)!
            s.panComparison(translation,scale:2,frame:rotated,mode:.leftRight);try await ready()
            try check(close(s.cx,rotatedCenter.x) && close(s.cy,rotatedCenter.y),"rotated_pair_pans_in_displayed_coordinates")
            let oldPhoto=s.comparisonFrame!
            s.selected=2;s.selection=[2];await s.load(2);try await ready()
            let switched=s.currentBeforeContext
            s.panComparison(translation,scale:2,frame:oldPhoto,mode:.leftRight)
            try check(!s.rendering && s.currentBeforeContext==switched && s.beforePreviewContext?.photoID==2,"old_photo_drag_cannot_move_new_photo")
            let pending=s.comparisonFrame!
            s.set("exposure",0.5);let pendingContext=s.currentBeforeContext
            s.panComparison(translation,scale:2,frame:pending,mode:.leftRight)
            try check(!s.rendering && s.currentBeforeContext==pendingContext,"pending_edit_blocks_pan_capture")
            try check(await s.flushEdits(),"pending_edit_finishes_normally")
            try await ready()
            try check(try paths.map {try Data(contentsOf:URL(fileURLWithPath:$0))} == originals,"paired_views_preserve_original_bytes")
            print(String(data:try JSONSerialization.data(withJSONObject:["ok":true,"checks":checks,"desktop_ui":"NOT_VERIFIED","voiceover":"NOT_VERIFIED"],options:[.prettyPrinted,.sortedKeys]),encoding:.utf8)!)
            exit(0)
        } catch {
            print(String(data:try! JSONSerialization.data(withJSONObject:["ok":false,"checks":checks,"error":error.localizedDescription,"store_error":s.error ?? ""],options:.prettyPrinted),encoding:.utf8)!)
            exit(1)
        }
    }
}
