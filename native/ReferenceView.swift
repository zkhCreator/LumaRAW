// Purpose: session-scoped Reference/Active roles in Develop, separate from recipes.
// Inputs: explicit reference selection, module transitions, viewport and drop events.
// Outputs: one bounded reference request plus active-only native editing actions.
// Lock retains identity across module changes, not across app restarts. Reference
// pixels follow saved catalog edits; active selection never retargets the reference.
// SQL, image processing and persistent photographic state remain in the engine.
import SwiftUI
import UniformTypeIdentifiers

struct CatalogPhotoDrag:Codable,Transferable {
    let session:String
    let photoID:Int
    static var transferRepresentation:some TransferRepresentation {
        CodableRepresentation(contentType:UTType(exportedAs:"local.lumaraw.catalog-photo",conformingTo:.data))
    }
}

enum ReferenceLayout {
    static func unitPoint(_ point:CGPoint,pixels:CGSize,available:CGSize,detail:Bool,scale:Double)->CGPoint? {
        guard point.x.isFinite,point.y.isFinite else {return nil}
        let area=detail ? available:CGSize(width:max(1,available.width-52),height:max(1,available.height-52))
        var rect=ComparisonLayout.imageRect(pixels:pixels,available:area,detail:detail,scale:scale)
        rect.origin=CGPoint(x:(available.width-rect.width)/2,y:(available.height-rect.height)/2)
        guard rect.width>0,rect.height>0,rect.contains(point) else {return nil}
        return CGPoint(x:(point.x-rect.minX)/rect.width,y:(point.y-rect.minY)/rect.height)
    }
}

extension Store {
    var isReferenceView:Bool {workspace=="library" && develop && referenceEnabled}
    var referenceRequest:ReferenceRequest? {
        guard isReferenceView,let p=referencePhoto else {return nil}
        return ReferenceRequest(context:BeforePreviewContext(photoID:p.id,revision:p.revision,orientation:p.orientation,
            detail:referenceDetail,cx:referenceDetail ? referenceCX:0.5,cy:referenceDetail ? referenceCY:0.5,
            gamut:gamut,proofSHA:proof["sha256"] as? String ?? "",
            width:referenceDetail ? referencePixelWidth:0,height:referenceDetail ? referencePixelHeight:0),
            proofPath:proof["path"] as? String ?? "")
    }

    func startReferenceView() async {
        reviewSwitchGeneration+=1;let token=reviewSwitchGeneration
        guard await flushEdits(),token==reviewSwitchGeneration,selected != nil,!browsing else {return}
        reviewRenderer.stop();workspace="library";develop=true
        referenceEnabled=true;comparisonMode = .after;canvasTool="view"
        render(debounce:false);updateReferenceRequest()
    }

    func endReferenceView() {
        referenceEnabled=false;referenceCropPhotoID=nil
        referenceRenderer.stop()
    }

    func leaveReferenceModule() {
        endReferenceView()
        referenceReadGeneration+=1
        if !referenceLocked {clearReferencePhoto()}
    }

    func clearReferencePhoto() {
        referenceReadGeneration+=1;referencePhoto=nil;referenceError=nil
        referenceDetail=false;referenceCX=0.5;referenceCY=0.5
        referenceRenderer.stop()
    }

    func setReferencePhoto(_ id:Int) async {
        guard photos.contains(where:{$0.id==id}) else {return}
        referenceReadGeneration+=1;let token=referenceReadGeneration
        guard await flushEdits(),token==referenceReadGeneration else {return}
        do {
            let reply=try await Backend.call("photo_summaries",["photo_ids":[id]])
            guard token==referenceReadGeneration else {return}
            guard let row=(reply["photos"] as? [[String:Any]])?.first,let p=Photo(row),p.id==id else {
                throw EngineFailure(message:"The reference photo is no longer in this catalog.")
            }
            referencePhoto=p;referenceError=nil
            referenceDetail=false;referenceCX=0.5;referenceCY=0.5
            updateReferenceRequest()
        } catch {if token==referenceReadGeneration {referenceError=error.localizedDescription}}
    }

    func refreshReferencePhoto(force:Bool=false) async {
        guard isReferenceView,let current=referencePhoto else {return}
        let token=referenceReadGeneration
        do {
            let reply=try await Backend.call("photo_summaries",["photo_ids":[current.id]])
            guard token==referenceReadGeneration,isReferenceView,referencePhoto?.id==current.id,
                  referencePhoto?.revision==current.revision else {return}
            guard let row=(reply["photos"] as? [[String:Any]])?.first,let p=Photo(row) else {
                referenceRenderer.stop();referenceError="The reference photo was removed from the catalog. Choose another reference."
                return
            }
            referencePhoto=p;referenceError=nil;updateReferenceRequest(force:force)
        } catch {if token==referenceReadGeneration {referenceError=error.localizedDescription}}
    }

    func updateReferenceRequest(force:Bool=false) {
        if let request=referenceRequest {referenceRenderer.request(request,force:force)}
    }

    func setReferencePane(_ size:CGSize,scale:Double) {
        guard size.width.isFinite,size.height.isFinite,scale.isFinite,scale>0 else {return}
        let width=Int(min(2048,max(1,(size.width*scale).rounded())))
        let height=Int(min(1536,max(1,(size.height*scale).rounded())))
        guard width != referencePixelWidth || height != referencePixelHeight else {return}
        referencePixelWidth=width;referencePixelHeight=height
        if referenceDetail {updateReferenceRequest()}
        if isReferenceView && detail {render()}
    }

    func setReferenceZoom(_ zoom:Bool) {
        referenceDetail=zoom;updateReferenceRequest()
    }

    func toggleReferenceZoom(at point:CGPoint) {
        guard isReferenceView,referencePhoto != nil,!referenceRenderer.loading,
              point.x.isFinite,point.y.isFinite,(0...1).contains(point.x),(0...1).contains(point.y) else {return}
        if !referenceDetail {referenceCX=point.x;referenceCY=point.y}
        setReferenceZoom(!referenceDetail)
    }

    func toggleReferenceActiveZoom(at point:CGPoint) {
        guard isReferenceView,photo != nil,canvasTool=="view",!loading,!rendering,!hasPendingEdits,
              point.x.isFinite,point.y.isFinite,(0...1).contains(point.x),(0...1).contains(point.y) else {return}
        if !detail {cx=point.x;cy=point.y}
        detail.toggle();render(debounce:false)
    }

    func panReference(_ translation:CGSize,scale:Double,frame:ReferenceFrame) {
        guard isReferenceView,referenceDetail,!referenceRenderer.loading,
              frame.request==referenceRequest,
              let point=frame.region.panned(translation,scale:scale) else {return}
        referenceCX=point.x;referenceCY=point.y;updateReferenceRequest()
    }

    func panReferenceActive(_ translation:CGSize,scale:Double,frame:BeforeAfterFrame) {
        guard isReferenceView,detail,canvasTool=="view",!rendering,!loading,!browsing,!hasPendingEdits,
              frame.context==currentBeforeContext,
              let point=frame.panned(translation,scale:scale) else {return}
        cx=point.x;cy=point.y;render(debounce:false)
    }

    func referenceDrag(_ id:Int)->CatalogPhotoDrag {CatalogPhotoDrag(session:referenceDragSession,photoID:id)}
    func canDropReference(_ items:[CatalogPhotoDrag])->Bool {
        items.count==1 && items[0].session==referenceDragSession && photos.contains(where:{$0.id==items[0].photoID})
    }
    func dropReference(_ items:[CatalogPhotoDrag],active:Bool)->Bool {
        guard isReferenceView,canDropReference(items) else {return false}
        let id=items[0].photoID
        Task {
            if active {
                guard await flushEdits(),isReferenceView else {return}
                choose(id)
            } else {await setReferencePhoto(id)}
        }
        return true
    }

    func requestCropTool() {
        guard let selected,!loading,!browsing else {return}
        if isReferenceView {referenceCropPhotoID=selected;return}
        activateCropTool()
    }
    func confirmReferenceCrop() {
        let captured=referenceCropPhotoID;referenceCropPhotoID=nil
        guard isReferenceView,captured==selected,!loading,!browsing else {return}
        endReferenceView();activateCropTool()
    }
    private func activateCropTool() {
        cancelCurveTarget(restore:false);cancelMixerTarget(restore:false)
        canvasTool="crop";detail=false;comparisonMode = .after;render(debounce:false)
    }
}

struct ReferencePhotoAction:View {
    @EnvironmentObject var s:Store
    let photoID:Int
    var body:some View {
        Button("Set as Reference Photo") {Task {await s.setReferencePhoto(photoID)}}
            .disabled(s.browsing || s.loading)
    }
}
