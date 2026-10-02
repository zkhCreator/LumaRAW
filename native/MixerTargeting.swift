// Purpose: engine-weighted photo targeting for HSL and Black & White Mix.
// Inputs: bounded sparse band maps, current recipe and canvas gestures. Outputs:
// temporary previews and one captured multi-band edit per release. The engine
// owns color analysis; native code applies its weights to control-space deltas.
// Stale photo/viewport/treatment captures never rebase. No SQL or pixel equations.
import Foundation

struct MixerBandWeight {
    let index:Int
    let weight:Double
}

struct MixerTargetMap {
    let path:String
    let width:Int
    let height:Int
    let mode:String
    private let data:Data
    init?(_ receipt:[String:Any]) {
        guard receipt["stage"] as? String == "mixer-target-v1",
              receipt["bands"] as? [String] == MixerFields.bands,
              let mode=receipt["mode"] as? String,["hsl","bw"].contains(mode),
              let path=receipt["path"] as? String,
              let width=receipt["width"] as? Int,let height=receipt["height"] as? Int,
              width>0,height>0,width<=2048,height<=2048,width*height<=2048*1536,
              let attributes=try? FileManager.default.attributesOfItem(atPath:path),
              attributes[.type] as? FileAttributeType == .typeRegular,
              (attributes[.size] as? NSNumber)?.intValue == 16+width*height*16,
              let data=try? Data(contentsOf:URL(fileURLWithPath:path),options:.mappedIfSafe),
              data.count == 16+width*height*16,Array(data.prefix(8)) == Array("LRMIX1\0\0".utf8) else {return nil}
        let dimensions=data.withUnsafeBytes {buffer in
            (UInt32(littleEndian:buffer.loadUnaligned(fromByteOffset:8,as:UInt32.self)),
             UInt32(littleEndian:buffer.loadUnaligned(fromByteOffset:12,as:UInt32.self)))
        }
        guard dimensions.0 == width,dimensions.1 == height else {return nil}
        self.path=path;self.width=width;self.height=height;self.mode=mode;self.data=data
    }
    func sample(_ point:CGPoint) -> [MixerBandWeight]? {
        guard point.x.isFinite,point.y.isFinite,(0...1).contains(point.x),(0...1).contains(point.y) else {return nil}
        let x=min(width-1,Int(point.x*Double(width))),y=min(height-1,Int(point.y*Double(height)))
        let offset=16+(y*width+x)*16
        return data.withUnsafeBytes {buffer in
            func word(_ index:Int) -> UInt32 {UInt32(littleEndian:buffer.loadUnaligned(fromByteOffset:offset+index*4,as:UInt32.self))}
            let packed=word(0),count=Int(packed>>24)
            guard count<=3 else {return nil}
            var result:[MixerBandWeight]=[]
            for slot in 0..<count {
                let index=Int((packed>>(slot*8))&255),weight=Double(Float(bitPattern:word(slot+1)))
                guard index<8,weight.isFinite,weight>0,weight<=1,!result.contains(where:{$0.index == index}) else {return nil}
                result.append(MixerBandWeight(index:index,weight:weight))
            }
            return result
        }
    }
}

struct MixerTargetFrame {
    let map:MixerTargetMap
    let context:CurveTargetContext
}

struct MixerTargetSample {
    let point:CGPoint
    let weights:[MixerBandWeight]
    var label:String {weights.isEmpty ? "Neutral area":weights.map {MixerFields.bands[$0.index].capitalized}.joined(separator:" / ")}
}

struct MixerPreviewDraft {
    let photoID:Int
    let revision:Int
    let patch:[String:Any]
}

struct MixerTargetCapture {
    let context:CurveTargetContext
    let mapPath:String
    let component:String
    let sample:MixerTargetSample
    let height:Double
    let values:[Double]
    func adjusted(_ delta:Double) -> [Double] {
        guard delta.isFinite else {return values}
        var result=values
        for band in sample.weights {result[band.index]=min(100,max(-100,values[band.index]+delta*band.weight))}
        return result
    }
    func patch(_ draft:[Double]) -> [String:Any] {
        guard draft.count == 8,draft.allSatisfy({$0.isFinite && (-100...100).contains($0)}) else {return [:]}
        var result:[String:Any]=[:]
        for i in 0..<8 where draft[i] != values[i] {
            result[MixerFields.bands[i]+"_"+component]=component == "hue" ? draft[i]*0.3:draft[i]
        }
        return result
    }
}

struct MixerTargetGesture {
    let capture:MixerTargetCapture
    var values:[Double]
}

extension Store {
    var activeMixerComponent:String {(recipe["monochrome"] as? Bool ?? false) ? "bw":mixerTargetComponent}
    var mixerTargetMode:String {activeMixerComponent == "bw" ? "bw":"hsl"}
    var mixerTargetActive:Bool {workspace == "library" && develop && canvasTool == "mixer" && !compare && !splitCompare}
    var canTargetMixer:Bool {
        mixerTargetActive && canEditPointCurves && !hasPendingEdits && !rendering &&
        mixerTargetFrame != nil && mixerTargetFrame?.context == curveTargetContext && mixerTargetFrame?.map.mode == mixerTargetMode
    }
    func setMixerTargeting(_ component:String?) {
        if whiteBalanceTargetActive || whiteBalanceSampling || whiteBalanceArming {cancelWhiteBalanceSelector()}
        guard component == nil || MixerFields.components.contains(component!) || component == "bw" else {return}
        guard component == nil || canEditPointCurves && !hasPendingEdits else {return}
        cancelMixerTarget(restore:false);mixerTargetFrame=nil
        cancelCurveTarget(restore:false);curveTargetFrame=nil
        if let component {mixerTargetComponent=component == "bw" ? "lum":component;compare=false;splitCompare=false;canvasTool="mixer"}
        else if canvasTool == "mixer" {canvasTool="view"}
        cancelMainPreview();render(debounce:false)
    }
    func acceptMixerTarget(_ result:[String:Any],context:CurveTargetContext,mode:String) {
        guard mixerTargetActive,context == curveTargetContext,mode == mixerTargetMode,
              let geometry=PhotoPreviewGeometry(result),geometry.photoID == context.photoID,
              geometry.revision == context.revision,geometry.orientation == context.orientation,geometry.detail == context.detail,
              let receipt=result["mixer_target"] as? [String:Any],receipt["mode"] as? String == mode,
              receipt["width"] as? Int == result["width"] as? Int,receipt["height"] as? Int == result["height"] as? Int else {mixerTargetFrame=nil;return}
        let map:MixerTargetMap?
        if let old=mixerTargetFrame?.map,old.path == receipt["path"] as? String,
           old.width == receipt["width"] as? Int,old.height == receipt["height"] as? Int {map=old}
        else {map=MixerTargetMap(receipt)}
        guard let map else {mixerTargetFrame=nil;error="The mixer input map is invalid. Reload the photo to retry.";return}
        mixerTargetFrame=MixerTargetFrame(map:map,context:context)
        if mixerTargetGesture == nil,let point=mixerTargetSample?.point,let weights=map.sample(point) {
            mixerTargetSample=MixerTargetSample(point:point,weights:weights)
        }
    }
    func hoverMixerTarget(_ point:CGPoint?) {
        guard mixerTargetGesture == nil else {return}
        guard canTargetMixer,let point,let weights=mixerTargetFrame?.map.sample(point) else {mixerTargetSample=nil;return}
        mixerTargetSample=MixerTargetSample(point:point,weights:weights)
    }
    @discardableResult func beginMixerTarget(_ point:CGPoint,height:Double) -> Bool {
        guard canTargetMixer,mixerTargetGesture == nil,height.isFinite,height>0,
              let frame=mixerTargetFrame,let weights=frame.map.sample(point),!weights.isEmpty else {return false}
        let values=MixerFields.bands.map {mixerValue($0+"_"+activeMixerComponent)}
        let sample=MixerTargetSample(point:point,weights:weights)
        mixerTargetSample=sample
        let capture=MixerTargetCapture(context:frame.context,mapPath:frame.map.path,component:activeMixerComponent,sample:sample,height:height,values:values)
        mixerTargetGesture=MixerTargetGesture(capture:capture,values:values)
        return true
    }
    func currentMixerTarget(_ capture:MixerTargetCapture) -> Bool {
        mixerTargetActive && canEditPointCurves && !hasPendingEdits && activeMixerComponent == capture.component &&
        curveTargetContext == capture.context && mixerTargetFrame?.context == capture.context &&
        mixerTargetFrame?.map.path == capture.mapPath &&
        MixerFields.bands.map({mixerValue($0+"_"+capture.component)}) == capture.values
    }
    func updateMixerTarget(translationY:Double) {
        guard var gesture=mixerTargetGesture else {return}
        guard currentMixerTarget(gesture.capture) else {cancelMixerTarget();return}
        guard translationY.isFinite else {return}
        gesture.values=gesture.capture.adjusted(-translationY/gesture.capture.height*200)
        mixerTargetGesture=gesture
        mixerTargetPreviews.requestMixer(store:self) { [weak self] in
            guard let self,let latest=self.mixerTargetGesture,self.currentMixerTarget(latest.capture) else {return nil}
            let patch=latest.capture.patch(latest.values)
            guard !patch.isEmpty else {return nil}
            return MixerPreviewDraft(photoID:latest.capture.context.photoID,revision:latest.capture.context.revision,patch:patch)
        }
    }
    @discardableResult func finishMixerTarget() -> Bool {
        mixerTargetPreviews.cancel()
        guard let gesture=mixerTargetGesture else {return false}
        mixerTargetGesture=nil
        guard currentMixerTarget(gesture.capture) else {
            error="The photo or mixer target changed during adjustment. Select a color again."
            cancelMainPreview();render();return false
        }
        cancelMainPreview()
        let patch=gesture.capture.patch(gesture.values)
        for (key,value) in patch {set(key,value)}
        if patch.isEmpty {render()}
        return true
    }
    func cancelMixerTarget(restore:Bool=true) {
        let hadGesture=mixerTargetGesture != nil
        mixerTargetPreviews.cancel();mixerTargetGesture=nil;mixerTargetSample=nil
        if hadGesture && restore {cancelMainPreview();render()}
    }
    func nudgeMixerTarget(_ direction:Double) {
        guard let point=mixerTargetSample?.point,beginMixerTarget(point,height:200) else {return}
        updateMixerTarget(translationY:-direction);_=finishMixerTarget()
    }
    func displayedMixerValue(_ key:String) -> Double {
        if let gesture=mixerTargetGesture,let index=MixerFields.bands.firstIndex(where:{$0+"_"+gesture.capture.component == key}) {
            return gesture.values[index]
        }
        return mixerValue(key)
    }
}
