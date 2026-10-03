// Purpose: capture one crop/mask pointer gesture against its displayed After frame.
// Inputs: pointer positions, immutable frame/source/tool/rectangle identity and Store.
// Outputs: bounded normalized strokes and guarded partial recipe patches.
// A cancelled gesture stays cancelled until release; it never follows a new photo.
// No SQL, pixels, image decoding, mutation replay or new mask processing equations.
import AppKit
import Foundation

struct DrawingContext:Equatable {
    let frame:BeforePreviewContext
    let generation:Int
    let sourceFingerprint:String
    let imageID:ObjectIdentifier
    let tool:String
    let cropBox:[Double]
    let rect:CGRect
    func normalized(_ point:CGPoint)->CGPoint {
        CGPoint(x:min(1,max(0,(point.x-rect.minX)/rect.width)),
                y:min(1,max(0,(point.y-rect.minY)/rect.height)))
    }
}

struct DrawingStroke {
    let context:DrawingContext
    let points:[CGPoint]
}

struct DrawingEditSource {
    let photoID:Int,revision:Int
    let fingerprint:String
}

struct DrawingGesture {
    private(set) var context:DrawingContext?
    private(set) var points:[CGPoint]=[]
    private(set) var cancelled=false
    private var moved=false
    private var start:CGPoint?
    var preview:DrawingStroke? {
        guard !cancelled,let context,!points.isEmpty else {return nil}
        return DrawingStroke(context:context,points:points)
    }
    mutating func update(start:CGPoint,location:CGPoint,current:DrawingContext?) {
        guard !cancelled else {return}
        guard start.x.isFinite,start.y.isFinite,location.x.isFinite,location.y.isFinite,
              let current else {cancel();return}
        if let context {
            guard context==current else {cancel();return}
        } else {
            guard current.rect.contains(start) else {cancel();return}
            context=current;self.start=start;points=[current.normalized(start)]
        }
        if let origin=self.start,hypot(location.x-origin.x,location.y-origin.y)>=2 {moved=true}
        let point=current.normalized(location)
        if current.tool=="brush" {
            if points.count<500,points.last != point {points.append(point)}
        } else if points.count==1 {points.append(point)}
        else {points[1]=point}
    }
    mutating func cancel() {cancelled=true;points=[]}
    mutating func finish(current:DrawingContext?)->DrawingStroke? {
        defer {self=DrawingGesture()}
        guard !cancelled,moved,let context,context==current,points.count>=2 else {return nil}
        return DrawingStroke(context:context,points:points)
    }
}

extension Store {
    func drawingContext(image:NSImage,rect:CGRect)->DrawingContext? {
        guard develop,!compare,!splitCompare,!detail,!rendering,!loading,!editing,!browsing,
              !hasPendingEdits,!orientationBusy,!developPresetBusy,!historyBusy,!snapshotBusy,
              !syncBusy,!maskActionBusy,activeMaskRecovery==nil,whiteBalanceEditRecovery==nil,
              ["crop","radial","linear","brush"].contains(canvasTool),
              rect.origin.x.isFinite,rect.origin.y.isFinite,rect.width.isFinite,rect.height.isFinite,
              rect.width>0,rect.height>0,let photo,photo.id==selected,preview===image,
              let frame=currentBeforeContext,activeViewportFrame?.context==frame,
              let geometry=previewGeometry,!geometry.detail,geometry.photoID==photo.id,
              geometry.revision==photo.revision,geometry.orientation==photo.orientation,
              (0...7).contains(photo.orientation),let source=previewSourceFingerprint,
              source.utf8.count==24,source.utf8.allSatisfy({(48...57).contains($0) || (97...102).contains($0)}) else {return nil}
        return DrawingContext(frame:frame,generation:drawingFrameGeneration,sourceFingerprint:source,imageID:ObjectIdentifier(image),
            tool:canvasTool,cropBox:geometry.cropBox,rect:rect)
    }

    @discardableResult func applyDrawing(_ stroke:DrawingStroke,image:NSImage,rect:CGRect)->Bool {
        guard drawingContext(image:image,rect:rect)==stroke.context else {
            message="Drawing cancelled because the photo, tool or preview changed. Draw again.";return false
        }
        let context=stroke.context
        let canonical=stroke.points.map {PhotoOrientation.inverse($0,orientation:context.frame.orientation)}
        guard let a=canonical.first,let b=canonical.last else {return false}
        if context.tool=="crop" {
            let x0=min(a.x,b.x),x1=max(a.x,b.x),y0=min(a.y,b.y),y1=max(a.y,b.y)
            guard x1-x0>0.02,y1-y0>0.02 else {return false}
            let box=context.cropBox,cw=box[2]-box[0],ch=box[3]-box[1]
            let newBox=[box[0]+x0*cw,box[1]+y0*ch,box[0]+x1*cw,box[1]+y1*ch]
            guard newBox[2]-newBox[0]>=0.01,newBox[3]-newBox[1]>=0.01 else {return false}
            set("crop","original");set("crop_box",newBox)
        } else {
            var masks=localMaskRows
            guard masks.count<12 else {error="Up to 12 local masks are supported";return false}
            var mask:[String:Any]=["name":"Mask \(masks.count+1)","kind":context.tool,
                "x":a.x,"y":a.y,"x2":b.x,"y2":b.y,"feather":0.5,"exposure":0.5]
            let first=stroke.points.first!,last=stroke.points.last!
            mask["radius"]=context.tool=="brush" ? 0.04:min(1,max(0.01,
                hypot((last.x-first.x)*rect.width,(last.y-first.y)*rect.height)/min(rect.width,rect.height)))
            if context.tool=="brush" {mask["points"]=canonical.map {[$0.x,$0.y]}}
            masks.append(mask);set("masks",masks)
        }
        if hasPendingEdits {bindDrawingEditSource(context);canvasTool="view";return true}
        return false
    }
}
