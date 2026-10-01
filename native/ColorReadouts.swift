// Purpose: present engine-computed RGB/LAB values for displayed photo positions.
// Inputs: bounded immutable float maps, captured preview context and hover events.
// Outputs: local constant-time lookups and a debounced one-pixel read only when
// the matching Reference/Active position is outside the other retained viewport.
// File reads use two bounded background operations. Hover publications belong to
// the readout view's separate observable state, never the whole workspace Store.
// No decoding/color equations, mutations or assumed display-profile equivalence.
import SwiftUI

struct ColorReadoutMap {
    let path:String,width:Int,height:Int
    private let data:Data
    init?(_ receipt:[String:Any]) {
        guard receipt["stage"] as? String == "develop-sdr-d50-v1",
              receipt["channels"] as? [String] == ["R","G","B","L","a","b"],
              receipt["rgb_space"] as? String == "ProPhoto-D50-sRGB-transfer",
              receipt["lab_white"] as? String == "D50",receipt["proofed"] as? Bool == false,
              receipt["sdr_clipped"] as? Bool == true,
              let path=receipt["path"] as? String,let width=receipt["width"] as? Int,let height=receipt["height"] as? Int,
              width>0,height>0,width<=2048,height<=2048,width*height<=2048*1536,
              let attributes=try? FileManager.default.attributesOfItem(atPath:path),
              attributes[.type] as? FileAttributeType == .typeRegular,
              (attributes[.size] as? NSNumber)?.intValue == 16+width*height*24,
              let data=try? Data(contentsOf:URL(fileURLWithPath:path),options:.uncached),
              data.count==16+width*height*24,Array(data.prefix(8))==Array("LRCOL1\0\0".utf8) else {return nil}
        func word(_ at:Int)->UInt32 {
            data.withUnsafeBytes {UInt32(littleEndian:$0.loadUnaligned(fromByteOffset:at,as:UInt32.self))}
        }
        guard word(8)==UInt32(width),word(12)==UInt32(height) else {return nil}
        self.path=path;self.width=width;self.height=height;self.data=data
    }
    func sample(_ point:CGPoint)->[Double]? {
        guard point.x.isFinite,point.y.isFinite,(0...1).contains(point.x),(0...1).contains(point.y) else {return nil}
        let x=min(width-1,Int(point.x*Double(width))),y=min(height-1,Int(point.y*Double(height)))
        let offset=16+(y*width+x)*24
        let values=data.withUnsafeBytes {bytes in (0..<6).map {index in
            Double(Float(bitPattern:UInt32(littleEndian:bytes.loadUnaligned(fromByteOffset:offset+index*4,as:UInt32.self))))
        }}
        guard values.allSatisfy(\.isFinite),values.prefix(3).allSatisfy({(-0.001...100.001).contains($0)}),
              (-0.001...100.001).contains(values[3]),values.suffix(2).allSatisfy({abs($0)<=256}) else {return nil}
        return values
    }
}

struct ColorReadoutFrame {
    let after:ColorReadoutMap,before:ColorReadoutMap?
    let region:BeforeAfterFrame
    let imageWidth:Int,imageHeight:Int
    init?(_ result:[String:Any],context:BeforePreviewContext) {
        guard let geometry=PhotoPreviewGeometry(result),geometry.photoID==context.photoID,
              geometry.revision==context.revision,geometry.orientation==context.orientation,geometry.detail==context.detail,
              let receipt=result["color_readouts"] as? [String:Any],let map=ColorReadoutMap(receipt),
              map.width==result["width"] as? Int,map.height==result["height"] as? Int,
              let region=BeforeAfterFrame(result,context:context),
              let width=result["image_width"] as? Int,let height=result["image_height"] as? Int,
              width>0,height>0,width<=250_000_000,height<=250_000_000,width<=250_000_000/height else {return nil}
        self.after=map;self.region=region;imageWidth=width;imageHeight=height
        let before=(result["before_color_readouts"] as? [String:Any]).flatMap(ColorReadoutMap.init)
        self.before=before?.width==map.width && before?.height==map.height ? before:nil
    }
    func fullPoint(_ local:CGPoint)->CGPoint? {
        guard local.x.isFinite,local.y.isFinite,(0...1).contains(local.x),(0...1).contains(local.y) else {return nil}
        let x=min(after.width-1,Int(local.x*Double(after.width)))
        let y=min(after.height-1,Int(local.y*Double(after.height)))
        return CGPoint(x:(region.roi.minX+(Double(x)+0.5)*region.roi.width/Double(after.width))/Double(region.fullWidth),
                       y:(region.roi.minY+(Double(y)+0.5)*region.roi.height/Double(after.height))/Double(region.fullHeight))
    }
    func sample(_ full:CGPoint,before:Bool)->[Double]? {
        let local=CGPoint(x:(full.x*Double(region.fullWidth)-region.roi.minX)/region.roi.width,
                          y:(full.y*Double(region.fullHeight)-region.roi.minY)/region.roi.height)
        guard local.x>=0,local.y>=0,local.x<1,local.y<1 else {return nil}
        return (before ? self.before:after)?.sample(local)
    }
    func pointRequest(_ point:CGPoint,before:Bool)->[String:Any] {
        let x=min(imageWidth-1,max(0,Int(point.x*Double(imageWidth))))
        let y=min(imageHeight-1,max(0,Int(point.y*Double(imageHeight))))
        return ["photo_id":region.context.photoID,"expected_revision":region.context.revision,
                "include_before":before,"include_color_readouts":true,
                "detail":["cx":(Double(x)+0.5)/Double(imageWidth),"cy":(Double(y)+0.5)/Double(imageHeight),"width":1,"height":1]]
    }
}

enum ColorReadoutLoader {
    private static let queue:OperationQueue = {
        let queue=OperationQueue()
        queue.name="local.lumaraw.color-readout-load"
        queue.maxConcurrentOperationCount=2
        queue.qualityOfService = .userInitiated
        return queue
    }()
    static func frame(_ result:[String:Any],context:BeforePreviewContext?) async -> ColorReadoutFrame? {
        guard let context,result["color_readouts"] != nil,!Task.isCancelled else {return nil}
        return await withCheckedContinuation {continuation in
            queue.addOperation {continuation.resume(returning:ColorReadoutFrame(result,context:context))}
        }
    }
    static func map(_ receipt:[String:Any]) async -> ColorReadoutMap? {
        guard !Task.isCancelled else {return nil}
        return await withCheckedContinuation {continuation in
            queue.addOperation {continuation.resume(returning:ColorReadoutMap(receipt))}
        }
    }
}

struct ColorReading:Equatable {
    var active:[Double]?
    var reference:[Double]?
    var before=false
    var referenceView=false
    var error:String?
}

@MainActor final class ColorReadoutState:ObservableObject {
    @Published var lab=false
    @Published private(set) var reading=ColorReading()
    func update(_ next:ColorReading) {
        if reading != next {reading=next}
    }
}

enum ColorReadoutRole {case active,before,reference}

struct ColorReadoutTarget:Equatable {
    let context:BeforePreviewContext
    let x:Int,y:Int
    let before:Bool
    init(frame:ColorReadoutFrame,point:CGPoint,before:Bool) {
        context=frame.region.context
        x=min(frame.imageWidth-1,max(0,Int(point.x*Double(frame.imageWidth))))
        y=min(frame.imageHeight-1,max(0,Int(point.y*Double(frame.imageHeight))))
        self.before=before
    }
}

extension Store {
    var activeColorFrame:ColorReadoutFrame? {
        guard develop,workspace=="library",!loading,!browsing,!rendering,!hasPendingEdits,
              let frame=colorReadoutFrame,frame.region.context==currentBeforeContext else {return nil}
        return frame
    }
    var referenceColorFrame:ColorReadoutFrame? {
        guard isReferenceView,referenceError==nil,!referenceRenderer.loading,
              let frame=referenceRenderer.frame,frame.request==referenceRequest else {return nil}
        return frame.colors
    }
    func clearColorReadout() {
        cancelColorReadoutRequest()
        colorReadoutCached=nil
        colorReadouts.update(ColorReading(before:compare,referenceView:isReferenceView))
    }
    private func cancelColorReadoutRequest() {
        colorReadoutGeneration+=1;colorReadoutTask?.cancel();colorReadoutTask=nil
        if colorReadoutRequestRunning {
            colorReadoutRequestRunning=false
            let token=colorReadoutGeneration,client=colorReadoutClient
            Task {_=try? await Backend.call("cancel_preview",["client_id":client,"generation":token])}
        }
    }
    func hoverColors(_ local:CGPoint?,role:ColorReadoutRole) {
        cancelColorReadoutRequest()
        var reading=ColorReading(before:compare,referenceView:isReferenceView)
        guard develop,workspace=="library",canvasTool=="view",let local else {
            colorReadouts.update(reading);return
        }
        let isReference=role == .reference,isBefore=role == .before || (role == .active && compare)
        let own=isReference ? referenceColorFrame:activeColorFrame
        guard let own,let point=own.fullPoint(local),let value=own.sample(point,before:isBefore) else {
            colorReadouts.update(reading);return
        }
        reading.before=isBefore || (isReference && compare)
        if isReference {reading.reference=value} else {reading.active=value}
        guard isReferenceView,let other=isReference ? activeColorFrame:referenceColorFrame,
              own.imageWidth==other.imageWidth,own.imageHeight==other.imageHeight else {
            colorReadouts.update(reading);return
        }
        let otherBefore=isReference && compare
        if let values=other.sample(point,before:otherBefore) {
            if isReference {reading.active=values} else {reading.reference=values}
            colorReadouts.update(reading)
            return
        }
        let target=ColorReadoutTarget(frame:other,point:point,before:otherBefore)
        if let cached=colorReadoutCached,cached.target==target {
            if isReference {reading.active=cached.values} else {reading.reference=cached.values}
            colorReadouts.update(reading);return
        }
        colorReadouts.update(reading)
        // A counterpart outside its independently panned viewport cannot be
        // sampled from visible pixels. Wait for the pointer to settle, then
        // request one exact full-resolution pixel through the bounded worker.
        let token=colorReadoutGeneration,client=colorReadoutClient
        colorReadoutTask=Task {
            try? await Task.sleep(nanoseconds:160_000_000)
            guard !Task.isCancelled,token==colorReadoutGeneration else {return}
            colorReadoutRequestRunning=true
            var params=other.pointRequest(point,before:otherBefore)
            params["client_id"]=client;params["generation"]=token
            do {
                let reply=try await Backend.call("preview_photo",params)
                guard !Task.isCancelled,token==colorReadoutGeneration else {return}
                let key=otherBefore ? "before_color_readouts":"color_readouts"
                guard reply["photo_id"] as? Int==other.region.context.photoID,
                      reply["revision"] as? Int==other.region.context.revision,
                      let receipt=reply[key] as? [String:Any] else {
                    throw EngineFailure(message:"The matching color sample changed. Move over the photo to retry.")
                }
                let loaded=await ColorReadoutLoader.map(receipt)
                guard !Task.isCancelled,token==colorReadoutGeneration else {return}
                guard let map=loaded,map.width==1,map.height==1,
                      let values=map.sample(CGPoint(x:0.5,y:0.5)) else {
                    throw EngineFailure(message:"The matching color sample could not be loaded.")
                }
                if isReference {reading.active=values} else {reading.reference=values}
                colorReadoutCached=(target,values)
                colorReadouts.update(reading)
            } catch {
                if token==colorReadoutGeneration {
                    reading.error=error.localizedDescription;colorReadouts.update(reading)
                }
            }
            if token==colorReadoutGeneration {colorReadoutRequestRunning=false}
        }
    }
}

struct ColorReadoutView:View {
    @ObservedObject var state:ColorReadoutState
    var body:some View {
        let reading=state.reading
        VStack(alignment:.leading,spacing:4) {
            HStack {
                Text(reading.referenceView ? (reading.before ? "Reference / Active (Before)":"Reference / Active") : (reading.before ? "Before":"After"))
                Spacer()
                Text(state.lab ? "Lab":"RGB (%)")
            }.foregroundStyle(.secondary)
            HStack {
                ForEach(0..<3) {channel in
                    let index=channel+(state.lab ? 3:0)
                    let label=(state.lab ? ["L","a","b"]:["R","G","B"])[channel]
                    Text("\(label) \(value(index))").frame(maxWidth:.infinity,alignment:.leading)
                }
            }.monospacedDigit()
            if let error=reading.error {Text("Matching sample unavailable").foregroundStyle(.secondary).help(error)}
        }.font(.system(size:10)).accessibilityElement(children:.combine)
            .help("SDR Develop values before soft proofing: RGB uses ProPhoto D50 primaries with the sRGB transfer curve; Lab uses D50. Fit samples the fitted preview, 1:1 samples full-resolution pixels.")
    }
    private func value(_ index:Int)->String {
        func number(_ values:[Double]?)->String {values.map {String(format:"%.1f",$0[index])} ?? "--"}
        return state.reading.referenceView ? "\(number(state.reading.reference))/\(number(state.reading.active))":number(state.reading.active)
    }
}

struct ColorReadoutModeMenu:View {
    @ObservedObject var state:ColorReadoutState
    var body:some View {Toggle("Show Lab Color Values",isOn:$state.lab)}
}

struct ColorReadoutHover:ViewModifier {
    @EnvironmentObject private var s:Store
    let imageSize:CGSize,available:CGSize
    var fitted=true
    var role:ColorReadoutRole = .active
    func body(content:Content)->some View {
        content.onContinuousHover {phase in
            switch phase {
            case .active(let location):
                let rect=CurveTargetOverlay.imageRect(image:imageSize,available:available,fitted:fitted)
                let point=rect.width>0 && rect.height>0 && rect.contains(location)
                    ? CGPoint(x:(location.x-rect.minX)/rect.width,y:(location.y-rect.minY)/rect.height):nil
                s.hoverColors(point,role:role)
            case .ended:s.clearColorReadout()
            }
        }.onDisappear {s.clearColorReadout()}
    }
}
