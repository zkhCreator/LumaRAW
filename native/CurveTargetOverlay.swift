// Purpose: photo-space pointer presentation for parametric targeted adjustment.
// Inputs: the displayed image rectangle and Store's matching input map. Outputs:
// normalized coordinates, captured vertical drags and keyboard adjustments.
// Fit uses the canvas's 26-point inset; detail attaches to the actual image frame
// inside its scroll view. No image processing or independent persistence.
import SwiftUI

struct CurveTargetOverlay:View {
    @EnvironmentObject var s:Store
    let imageSize:CGSize
    let available:CGSize
    var fitted=true
    @State private var pressed=false
    @FocusState private var focused:Bool
    static func imageRect(image:CGSize,available:CGSize,fitted:Bool) -> CGRect {
        guard fitted else {return CGRect(origin:.zero,size:available)}
        let factor=max(0,min((available.width-52)/max(1,image.width),(available.height-52)/max(1,image.height)))
        let size=CGSize(width:image.width*factor,height:image.height*factor)
        return CGRect(x:(available.width-size.width)/2,y:(available.height-size.height)/2,width:size.width,height:size.height)
    }
    var rect:CGRect {Self.imageRect(image:imageSize,available:available,fitted:fitted)}
    func point(_ value:CGPoint) -> CGPoint? {
        guard rect.width>0,rect.height>0,rect.contains(value) else {return nil}
        return CGPoint(x:(value.x-rect.minX)/rect.width,y:(value.y-rect.minY)/rect.height)
    }
    var body:some View {
        Canvas {context,_ in
            if let sample=s.curveTargetSample {
                let p=CGPoint(x:rect.minX+sample.point.x*rect.width,y:rect.minY+sample.point.y*rect.height)
                let circle=Path(ellipseIn:CGRect(x:p.x-6,y:p.y-6,width:12,height:12))
                context.stroke(circle,with:.color(.black),lineWidth:4)
                context.stroke(circle,with:.color(.white),lineWidth:2)
            }
        }.contentShape(Rectangle()).focusable().focused($focused)
        .onContinuousHover {phase in
            switch phase {
            case .active(let position):s.hoverCurveTarget(point(position))
            case .ended:if !focused {s.hoverCurveTarget(nil)}
            }
        }
        .gesture(DragGesture(minimumDistance:0).onChanged {value in
            if !pressed {
                pressed=true;focused=true
                if let start=point(value.startLocation) {_=s.beginCurveTarget(start,height:rect.height)}
            }
            s.updateCurveTarget(translationY:value.translation.height)
        }.onEnded {_ in _=s.finishCurveTarget();pressed=false})
        .onKeyPress(.escape) {
            if s.curveTargetGesture != nil {s.cancelCurveTarget()} else {s.setCurveTargeting(false)}
            return .handled
        }
        .onKeyPress(.upArrow) {s.nudgeCurveTarget(1);return .handled}
        .onKeyPress(.downArrow) {s.nudgeCurveTarget(-1);return .handled}
        .onChange(of:available) {_,_ in s.cancelCurveTarget()}
        .onDisappear {s.cancelCurveTarget()}
        .accessibilityLabel("Targeted Tone Curve")
        .accessibilityValue(s.curveTargetSample.map {"\(ParametricCurveValues.labels[$0.region]), input \(Int($0.input*100)) percent"} ?? "Select a tone in the photo")
        .accessibilityHint("Drag upward to lighten or downward to darken. Arrow keys adjust the selected region. Escape cancels.")
        .accessibilityAdjustableAction {s.nudgeCurveTarget($0 == .increment ? 1:-1)}
        .overlay(alignment:.bottom) {
            Text(s.curveTargetSample.map {"\(ParametricCurveValues.labels[$0.region]) · Drag to adjust · ↑ / ↓ · Escape to cancel"} ?? (s.canTargetCurve ? "Select a tone in the photo":"Preparing tone samples…"))
                .font(.caption).padding(8).background(.ultraThinMaterial,in:Capsule()).padding(10).allowsHitTesting(false)
        }
    }
}
