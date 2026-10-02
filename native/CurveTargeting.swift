// Purpose: geometry-bound photo tone samples and captured parametric gestures.
// Inputs: bounded engine maps and normalized canvas pointer/key events. Outputs:
// transient curve previews and one revision-checked edit on release. No decoding,
// color processing or catalog ownership. Input tones are independent of proofing
// and downstream edits. Stale viewport/photo captures are never rebased.
import Foundation

struct CurveToneMap {
    let path:String
    let width:Int
    let height:Int
    private let data:Data
    init?(_ receipt:[String:Any]) {
        guard receipt["stage"] as? String == "pre-parametric-v1",
              let path=receipt["path"] as? String,
              let width=receipt["width"] as? Int,let height=receipt["height"] as? Int,
              width>0,height>0,width<=2048,height<=2048,width*height<=2048*1536,
              let attributes=try? FileManager.default.attributesOfItem(atPath:path),
              attributes[.type] as? FileAttributeType == .typeRegular,
              (attributes[.size] as? NSNumber)?.intValue == 16+width*height*4,
              let data=try? Data(contentsOf:URL(fileURLWithPath:path),options:.mappedIfSafe),
              data.count == 16+width*height*4,
              Array(data.prefix(8)) == Array("LRTONE1\0".utf8) else {return nil}
        func word(_ offset:Int) -> UInt32 {
            data.withUnsafeBytes {UInt32(littleEndian:$0.loadUnaligned(fromByteOffset:offset,as:UInt32.self))}
        }
        guard word(8) == UInt32(width),word(12) == UInt32(height) else {return nil}
        self.path=path;self.width=width;self.height=height;self.data=data
    }
    func sample(_ point:CGPoint) -> Double? {
        guard point.x.isFinite,point.y.isFinite,(0...1).contains(point.x),(0...1).contains(point.y) else {return nil}
        let x=min(width-1,Int(point.x*Double(width))),y=min(height-1,Int(point.y*Double(height)))
        let bits=data.withUnsafeBytes {UInt32(littleEndian:$0.loadUnaligned(fromByteOffset:16+(y*width+x)*4,as:UInt32.self))}
        let value=Double(Float(bitPattern:bits))
        return value.isFinite && (0...1).contains(value) ? value:nil
    }
}

struct CurveTargetContext:Equatable {
    let photoID:Int
    let revision:Int
    let orientation:Int
    let detail:Bool
    let cx:Double
    let cy:Double
}

struct CurveTargetFrame {
    let map:CurveToneMap
    let context:CurveTargetContext
}

struct CurveTargetSample {
    let point:CGPoint
    let input:Double
    let region:Int
}

struct CurveTargetGesture {
    let capture:ParametricCurveCapture
    let context:CurveTargetContext
    let mapPath:String
    let sample:CurveTargetSample
    let height:Double
    var values:ParametricCurveValues
}

extension Store {
    var curveTargetContext:CurveTargetContext? {
        guard let photo,photo.id == selected else {return nil}
        return CurveTargetContext(photoID:photo.id,revision:photo.revision,orientation:photo.orientation,
                                  detail:detail,cx:detail ? cx:0.5,cy:detail ? cy:0.5)
    }
    var curveTargetActive:Bool {workspace == "library" && develop && canvasTool == "curve" && !compare && !splitCompare}
    var canTargetCurve:Bool {
        curveTargetActive && canEditPointCurves && !hasPendingEdits && !rendering &&
        curveTargetFrame != nil && curveTargetFrame?.context == curveTargetContext
    }
    func setCurveTargeting(_ enabled:Bool) {
        if whiteBalanceTargetActive || whiteBalanceSampling || whiteBalanceArming {cancelWhiteBalanceSelector()}
        cancelMixerTarget(restore:false);mixerTargetFrame=nil
        cancelCurveTarget(restore:false)
        curveTargetFrame=nil;curveTargetSample=nil
        if enabled {
            guard canEditPointCurves,!hasPendingEdits else {return}
            compare=false;splitCompare=false;canvasTool="curve"
        } else if canvasTool == "curve" {canvasTool="view"}
        cancelMainPreview();render(debounce:false)
    }
    func acceptCurveTones(_ result:[String:Any],context:CurveTargetContext) {
        guard curveTargetActive,context == curveTargetContext,
              let geometry=PhotoPreviewGeometry(result),geometry.photoID == context.photoID,
              geometry.revision == context.revision,geometry.orientation == context.orientation,
              geometry.detail == context.detail,let receipt=result["curve_tones"] as? [String:Any],
              receipt["width"] as? Int == result["width"] as? Int,
              receipt["height"] as? Int == result["height"] as? Int else {curveTargetFrame=nil;return}
        let map:CurveToneMap?
        if let old=curveTargetFrame?.map,old.path == receipt["path"] as? String,
           old.width == receipt["width"] as? Int,old.height == receipt["height"] as? Int {map=old}
        else {map=CurveToneMap(receipt)}
        guard let map else {curveTargetFrame=nil;error="The curve input map is invalid. Reload the photo to retry.";return}
        curveTargetFrame=CurveTargetFrame(map:map,context:context)
        if curveTargetGesture == nil,let point=curveTargetSample?.point,let input=map.sample(point) {
            curveTargetSample=CurveTargetSample(point:point,input:input,region:parametricCurve.region(input))
        }
    }
    func hoverCurveTarget(_ point:CGPoint?) {
        guard curveTargetGesture == nil else {return}
        guard canTargetCurve,let point,let input=curveTargetFrame?.map.sample(point) else {curveTargetSample=nil;return}
        curveTargetSample=CurveTargetSample(point:point,input:input,region:parametricCurve.region(input))
    }
    @discardableResult func beginCurveTarget(_ point:CGPoint,height:Double) -> Bool {
        guard canTargetCurve,curveTargetGesture == nil,height.isFinite,height>0,
              let frame=curveTargetFrame,let capture=captureParametricCurve(),let input=frame.map.sample(point) else {return false}
        let sample=CurveTargetSample(point:point,input:input,region:capture.values.region(input))
        curveTargetSample=sample
        curveTargetGesture=CurveTargetGesture(capture:capture,context:frame.context,mapPath:frame.map.path,
            sample:sample,height:height,values:capture.values)
        return true
    }
    func currentCurveTarget(_ gesture:CurveTargetGesture) -> Bool {
        curveTargetActive && canEditPointCurves && !hasPendingEdits &&
        curveTargetContext == gesture.context && curveTargetFrame?.context == gesture.context &&
        curveTargetFrame?.map.path == gesture.mapPath && parametricCurve == gesture.capture.values
    }
    func updateCurveTarget(translationY:Double) {
        guard var gesture=curveTargetGesture else {return}
        guard currentCurveTarget(gesture) else {cancelCurveTarget();return}
        guard translationY.isFinite else {return}
        let sample=gesture.sample
        gesture.values=translationY == 0 ? gesture.capture.values : gesture.capture.values.draggedRegion(sample.region,input:sample.input,
            target:gesture.capture.values.output(sample.input)-translationY/gesture.height)
        curveTargetGesture=gesture
        curveTargetPreviews.request(store:self) { [weak self] in
            guard let self,let latest=self.curveTargetGesture,self.currentCurveTarget(latest) else {return nil}
            return latest.capture.preview(latest.values)
        }
    }
    @discardableResult func finishCurveTarget() -> Bool {
        curveTargetPreviews.cancel()
        guard let gesture=curveTargetGesture else {return false}
        curveTargetGesture=nil
        guard currentCurveTarget(gesture) else {
            error="The photo or viewport changed during targeted adjustment. Select a tone again."
            cancelMainPreview();render();return false
        }
        return commitParametricCurve(gesture.capture,gesture.values)
    }
    func cancelCurveTarget(restore:Bool=true) {
        let hadGesture=curveTargetGesture != nil
        curveTargetPreviews.cancel();curveTargetGesture=nil;curveTargetSample=nil
        if hadGesture && restore {cancelMainPreview();render()}
    }
    func nudgeCurveTarget(_ direction:Double) {
        guard canTargetCurve,curveTargetGesture == nil,let sample=curveTargetSample,
              let capture=captureParametricCurve() else {return}
        _=commitParametricCurve(capture,capture.values.adjusted(sample.region,to:capture.values.amounts[sample.region]+direction))
    }
}
