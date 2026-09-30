// Purpose: Reference/Active state, viewport and late-reply regression through IPC.
// Inputs: generated originals and an isolated engine catalog. Outputs: role/lock,
// edit isolation, bounded ROI, cancellation, drop and crop-confirmation receipts.
// Controlled transport adds deterministic races; no desktop events, rendering
// inspection, physical display or VoiceOver acceptance is implied.
import AppKit
import Foundation

@MainActor final class DelayedReferenceTransport {
    let path:String
    var pending:[Int:CheckedContinuation<[String:Any],Error>]=[:]
    init(path:String) {self.path=path}
    func call(_ method:String,_ params:[String:Any]) async throws -> [String:Any] {
        guard method=="preview_photo" else {return [:]}
        return try await withCheckedThrowingContinuation {pending[params["photo_id"] as! Int]=$0}
    }
    func finish(_ id:Int,revision:Int=0) {
        pending.removeValue(forKey:id)?.resume(returning:["photo_id":id,"revision":revision,"preview":path,
            "full_width":2400,"full_height":1800,"width":1680,"height":1260,"roi":[0,0,2400,1800],
            "geometry":["orientation":0,"crop_box":[0.0,0.0,1.0,1.0]],"detail":false])
    }
}

@main struct NativeReferenceRegression {
    @MainActor static func main() async {
        _=NSApplication.shared
        let s=Store();var checks:[String:Bool]=[:]
        func check(_ value:Bool,_ name:String)throws {checks[name]=value;if !value {throw EngineFailure(message:name)}}
        func until(_ condition:()->Bool) async throws {
            for _ in 0..<800 {
                if condition() {return}
                try await Task.sleep(nanoseconds:25_000_000)
            }
            throw EngineFailure(message:"Reference did not settle: \(s.referenceError ?? s.referenceRenderer.error ?? s.error ?? "no error")")
        }
        func referenceReady() async throws {
            try await until {s.referenceRenderer.frame?.request==s.referenceRequest && s.referenceRenderer.frame != nil && !s.referenceRenderer.loading}
        }
        func activeReady(_ id:Int) async throws {
            try await until {s.photo?.id==id && !s.loading && !s.rendering && s.activeViewportFrame?.context==s.currentBeforeContext && s.preview != nil}
        }
        func read(_ id:Int) async throws -> [String:Any] {try await Backend.call("get_photo",["photo_id":id])}
        func request(_ id:Int)->ReferenceRequest {
            ReferenceRequest(context:BeforePreviewContext(photoID:id,revision:0,orientation:0,detail:false,
                cx:0.5,cy:0.5,gamut:false,proofSHA:"",width:0,height:0),proofPath:"")
        }
        do {
            let paths=ProcessInfo.processInfo.environment["LUMARAW_TEST_FIXTURES"]!.components(separatedBy:"|")
            let originals=try paths.map {try Data(contentsOf:URL(fileURLWithPath:$0))}
            await s.importPaths(paths);s.choose(2);try await activeReady(2)
            await s.setReferencePhoto(1)
            try check(s.selected==2 && s.referencePhoto?.id==1 && !s.develop,"assigning_reference_preserves_active_and_module")
            await s.startReferenceView();try await referenceReady();try await activeReady(2)
            try check(s.isReferenceView && s.comparisonMode == .after && s.canvasTool=="view","reference_entry_uses_editable_active")
            let originalFrame=s.referenceRenderer.frame!,generation=s.referenceRenderer.generation
            try check(originalFrame.request.params["include_before"] as? Bool == false && originalFrame.request.params["expected_revision"] as? Int == 0,"reference_is_bound_and_skips_before_processing")
            s.selection=[1,2,3]
            try check(s.actionPhotoIDs==[2],"multi_selection_edits_only_active")
            s.set("exposure",0.7);try check(await s.flushEdits(),"active_adjustment_commits")
            try await activeReady(2)
            let refPhoto=try await read(1),activePhoto=try await read(2)
            try check((refPhoto["recipe"] as! [String:Any])["exposure"] as? Double == 0 && refPhoto["revision"] as? Int == 0,"active_edit_preserves_reference_recipe_and_revision")
            try check((activePhoto["recipe"] as! [String:Any])["exposure"] as? Double == 0.7,"active_edit_changes_active_recipe")
            try check(s.referenceRenderer.generation==generation && s.referenceRenderer.frame?.image === originalFrame.image,"active_edit_reuses_reference_pixels")
            s.choose(3);try await activeReady(3)
            try check(s.isReferenceView && s.referencePhoto?.id==1 && s.referenceRenderer.frame?.image === originalFrame.image,"active_navigation_keeps_reference_identity_and_pixels")
            s.referenceVertical=true;s.setReferencePane(CGSize(width:200,height:150),scale:2)
            try check(s.referenceRenderer.generation==generation,"fit_layout_and_resize_start_no_reference_work")
            try check(s.referencePixelWidth==400 && s.referencePixelHeight==300,"pane_uses_physical_pixels")
            let centerPoint=ReferenceLayout.unitPoint(CGPoint(x:200,y:150),pixels:CGSize(width:2400,height:1800),available:CGSize(width:400,height:300),detail:false,scale:2)
            try check(centerPoint==CGPoint(x:0.5,y:0.5) && ReferenceLayout.unitPoint(CGPoint(x:2,y:2),pixels:CGSize(width:2400,height:1800),available:CGSize(width:400,height:300),detail:false,scale:2)==nil,"fit_click_maps_image_center_and_ignores_letterbox")
            s.toggleReferenceZoom(at:CGPoint(x:0.5,y:0.5));try await referenceReady()
            try check(s.referenceDetail && !s.detail,"reference_image_click_zooms_only_reference")
            s.toggleReferenceZoom(at:CGPoint(x:0.5,y:0.5));try await referenceReady()
            try check(!s.referenceDetail,"reference_image_click_returns_to_fit")
            s.toggleReferenceActiveZoom(at:CGPoint(x:0.5,y:0.5));try await activeReady(3)
            try check(s.detail && !s.referenceDetail,"active_image_click_zooms_only_active")
            s.toggleReferenceActiveZoom(at:CGPoint(x:0.5,y:0.5));try await activeReady(3)
            try check(!s.detail,"active_image_click_returns_to_fit")
            s.setReferenceZoom(true);try await referenceReady()
            let detailFrame=s.referenceRenderer.frame!
            try check(detailFrame.region.roi.size==CGSize(width:400,height:300) && !s.detail,"reference_zoom_is_independent")
            let activeCenter=(s.cx,s.cy)
            s.panReference(CGSize(width:40,height:-30),scale:2,frame:detailFrame);try await referenceReady()
            try check(s.referenceCX<0.5 && s.referenceCY>0.5 && s.cx==activeCenter.0 && s.cy==activeCenter.1,"reference_pan_preserves_active_viewport")
            let currentRequest=s.referenceRequest
            s.panReference(CGSize(width:100,height:0),scale:2,frame:detailFrame)
            try check(s.referenceRequest==currentRequest,"stale_reference_drag_is_rejected")
            s.panReference(CGSize(width:10000,height:0),scale:2,frame:s.referenceRenderer.frame!);try await referenceReady()
            try check(s.referenceRenderer.frame!.region.roi.minX==0,"reference_pan_clamps_to_image_edge")
            s.panReference(CGSize(width:-40,height:0),scale:2,frame:s.referenceRenderer.frame!);try await referenceReady()
            try check(s.referenceRenderer.frame!.region.roi.minX>0,"pan_reverses_from_returned_roi_without_sticky_edge")
            let refCenter=(s.referenceCX,s.referenceCY)
            s.detail=true;s.render(debounce:false);try await activeReady(3)
            try check(s.activeViewportFrame?.roi.size==CGSize(width:400,height:300),"active_detail_uses_its_pane_dimensions")
            let activeFrame=s.activeViewportFrame!
            s.panReferenceActive(CGSize(width:-45,height:0),scale:2,frame:activeFrame);try await activeReady(3)
            try check(s.cx>0.5 && s.referenceCX==refCenter.0 && s.referenceCY==refCenter.1,"active_pan_preserves_reference_viewport")
            let center=s.cx;s.panReferenceActive(CGSize(width:20,height:0),scale:2,frame:activeFrame)
            try check(s.cx==center,"stale_active_drag_is_rejected")
            s.setReferencePane(CGSize(width:CGFloat.nan,height:100),scale:2)
            try check(s.referencePixelWidth==400 && s.referencePixelHeight==300,"invalid_pane_geometry_is_rejected")
            s.setReferencePane(CGSize(width:100000,height:100000),scale:3);try await referenceReady();try await activeReady(3)
            try check(s.referencePixelWidth==2048 && s.referencePixelHeight==1536,"viewports_remain_bounded")
            let beforeGeneration=s.referenceRenderer.generation
            s.setComparisonMode(.before);try await activeReady(3)
            try check(s.isReferenceView && s.before != nil && s.compare,"before_toggle_preserves_reference_layout")
            try check(s.referenceRenderer.generation==beforeGeneration,"active_before_toggle_does_not_render_reference")
            s.setComparisonMode(.after)
            let drag=s.referenceDrag(2)
            try check(s.canDropReference([drag]) && !s.canDropReference([drag,drag]) && !s.canDropReference([CatalogPhotoDrag(session:"foreign",photoID:2)]) && !s.canDropReference([s.referenceDrag(999)]),"drops_are_single_visible_photos_from_same_session")
            try check(s.dropReference([drag],active:true),"active_drop_is_accepted")
            try await activeReady(2)
            try check(s.referencePhoto?.id==1,"active_drop_keeps_reference")
            try check(s.dropReference([s.referenceDrag(3)],active:false),"reference_drop_is_accepted")
            try await until {s.referencePhoto?.id==3};try await referenceReady()
            try check(s.selected==2 && !s.referenceDetail,"reference_drop_preserves_active_and_resets_reference_zoom")
            s.requestCropTool()
            try check(s.referenceCropPhotoID==2 && s.isReferenceView && s.canvasTool != "crop","crop_requires_explicit_exit_confirmation")
            s.referenceCropPhotoID=nil
            try check(s.isReferenceView,"cancelled_crop_keeps_reference_view")
            s.requestCropTool();s.choose(4);try await activeReady(4);s.confirmReferenceCrop()
            try check(s.isReferenceView && s.canvasTool != "crop","stale_crop_confirmation_does_not_target_another_photo")
            s.requestCropTool();s.confirmReferenceCrop()
            try check(!s.isReferenceView && s.canvasTool=="crop" && s.referencePhoto?.id==3,"confirmed_crop_exits_but_retains_reference")
            await s.startReferenceView();try await referenceReady();try await activeReady(4)
            s.referenceLocked=true;await s.switchLibraryView(.grid)
            try check(!s.isReferenceView && s.referencePhoto?.id==3 && s.referenceRenderer.frame==nil,"locked_reference_survives_module_exit_without_retaining_pixels")
            await s.startReferenceView();try await referenceReady();try await activeReady(4)
            await s.startDevelop()
            try check(!s.referenceEnabled && s.referencePhoto?.id==3 && s.develop,"develop_loupe_keeps_reference_assignment")
            await s.startReferenceView();try await referenceReady();try await activeReady(4)
            s.referenceLocked=false;s.workspace="exports"
            try check(s.referencePhoto==nil && !s.referenceEnabled && s.referenceRenderer.frame==nil,"unlocked_reference_clears_on_workspace_exit")
            s.workspace="library";await s.setReferencePhoto(1);await s.startReferenceView();try await referenceReady();try await activeReady(4)
            _=try await Backend.call("edit_photo",["photo_id":1,"expected_revision":0,"patch":["exposure":0.2]])
            await s.refreshReferencePhoto();try await referenceReady()
            try check(s.referencePhoto?.revision==1 && s.referenceRenderer.frame?.request.context.revision==1 && s.selected==4,"reference_follows_saved_edits_without_retargeting_active")
            let valid=s.referenceRenderer.frame!
            s.setComparisonMode(.leftRight)
            try check(!s.referenceEnabled && s.referencePhoto?.id==1,"paired_before_after_exits_reference_view")
            s.panReference(CGSize(width:1,height:1),scale:1,frame:valid)
            try check(s.referenceRenderer.frame==nil,"hidden_reference_ignores_old_drag")
            await s.startReferenceView();try await referenceReady();try await activeReady(4)
            let source=try await read(1)
            let copies=try await Backend.call("create_virtual_copies",["targets":[["photo_id":1,"expected_revision":source["revision"]!,"expected_metadata_revision":source["metadata_revision"]!]]])
            let copyID=(copies["photos"] as! [[String:Any]])[0]["id"] as! Int
            await s.refresh();await s.setReferencePhoto(copyID);try await referenceReady()
            try check(s.referencePhoto?.isVirtual==true && s.selected != copyID,"virtual_copy_has_independent_reference_identity")
            s.libraryFilters=["is_virtual":false];await s.refresh();try await referenceReady()
            try check(!s.photos.contains(where:{$0.id==copyID}) && s.referencePhoto?.id==copyID,"reference_survives_filtering_out_of_visible_page")
            let copy=try await read(copyID)
            _=try await Backend.call("remove_virtual_copies",["targets":[["photo_id":copyID,"expected_revision":copy["revision"]!,"expected_metadata_revision":copy["metadata_revision"]!,"expected_source_revision":copy["source_revision"]!]]])
            await s.refreshReferencePhoto()
            try check(s.referenceError != nil && s.referenceRenderer.frame==nil && s.referencePhoto?.id==copyID,"removed_reference_stops_pixels_and_reports_explicit_error")
            await s.setReferencePhoto(4);try await referenceReady();try await activeReady(4)
            try check(s.referencePhoto?.id==s.selected && s.referenceRenderer.frame != nil,"same_photo_can_occupy_both_roles_without_frame_collision")
            let transport=DelayedReferenceTransport(path:paths[0]),renderer=ReferenceRenderer(call:{try await transport.call($0,$1)})
            renderer.request(request(101));try await until {transport.pending[101] != nil}
            renderer.request(request(102));try await until {transport.pending[102] != nil}
            transport.finish(102);try await until {renderer.frame != nil}
            let retained=renderer.frame!.image;transport.finish(101)
            try await Task.sleep(nanoseconds:100_000_000)
            try check(renderer.frame?.request.context.photoID==102 && renderer.frame?.image === retained,"late_superseded_reference_reply_cannot_repaint")
            renderer.request(request(103));try await until {transport.pending[103] != nil};transport.finish(103,revision:9)
            try await until {!renderer.loading}
            try check(renderer.frame==nil && renderer.error != nil,"mismatched_revision_receipt_is_visible_error")
            renderer.request(request(104));try await until {transport.pending[104] != nil};renderer.stop();transport.finish(104)
            try await Task.sleep(nanoseconds:100_000_000)
            try check(renderer.frame==nil && !renderer.loading,"hidden_view_cancels_late_reference_reply")
            try check(try paths.map {try Data(contentsOf:URL(fileURLWithPath:$0))}==originals,"reference_workflows_preserve_original_bytes")
            print(String(data:try JSONSerialization.data(withJSONObject:["ok":true,"checks":checks,"desktop_ui":"NOT_VERIFIED","voiceover":"NOT_VERIFIED"],options:[.prettyPrinted,.sortedKeys]),encoding:.utf8)!)
            exit(0)
        } catch {
            print(String(data:try! JSONSerialization.data(withJSONObject:["ok":false,"checks":checks,"error":error.localizedDescription,"store_error":s.error ?? ""],options:.prettyPrinted),encoding:.utf8)!)
            exit(1)
        }
    }
}
