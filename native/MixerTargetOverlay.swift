// Purpose: photo-space gestures for engine-weighted color mixer targeting.
// Inputs: fitted or actual detail image bounds and Store's matching sparse map.
// Outputs: normalized pointer events and captured control changes. Reuses the
// curve overlay's coordinate rectangle; no pixel processing or recipe persistence.
import SwiftUI

struct MixerTargetOverlay:View {
    @EnvironmentObject var s:Store
    let imageSize:CGSize
    let available:CGSize
    var fitted=true
    @State private var pressed=false
    @FocusState private var focused:Bool
    var rect:CGRect {CurveTargetOverlay.imageRect(image:imageSize,available:available,fitted:fitted)}
    func point(_ value:CGPoint) -> CGPoint? {
        guard rect.width>0,rect.height>0,rect.contains(value) else {return nil}
        return CGPoint(x:(value.x-rect.minX)/rect.width,y:(value.y-rect.minY)/rect.height)
    }
    var body:some View {
        Canvas {context,_ in
            if let sample=s.mixerTargetSample {
                let p=CGPoint(x:rect.minX+sample.point.x*rect.width,y:rect.minY+sample.point.y*rect.height)
                let circle=Path(ellipseIn:CGRect(x:p.x-6,y:p.y-6,width:12,height:12))
                context.stroke(circle,with:.color(.black),lineWidth:4)
                context.stroke(circle,with:.color(.white),lineWidth:2)
            }
        }.contentShape(Rectangle()).focusable().focused($focused)
        .onContinuousHover {phase in
            switch phase {
            case .active(let position):s.hoverMixerTarget(point(position))
            case .ended:if !focused {s.hoverMixerTarget(nil)}
            }
        }
        .gesture(DragGesture(minimumDistance:0).onChanged {value in
            if !pressed {
                pressed=true;focused=true
                if let start=point(value.startLocation) {_=s.beginMixerTarget(start,height:rect.height)}
            }
            s.updateMixerTarget(translationY:value.translation.height)
        }.onEnded {_ in _=s.finishMixerTarget();pressed=false})
        .onKeyPress(.escape) {
            if s.mixerTargetGesture != nil {s.cancelMixerTarget()} else {s.setMixerTargeting(nil)}
            return .handled
        }
        .onKeyPress(.upArrow) {s.nudgeMixerTarget(1);return .handled}
        .onKeyPress(.downArrow) {s.nudgeMixerTarget(-1);return .handled}
        .onChange(of:available) {_,_ in s.cancelMixerTarget()}
        .onDisappear {s.cancelMixerTarget()}
        .accessibilityLabel("Targeted "+MixerFields.label("red_"+s.activeMixerComponent).replacingOccurrences(of:"Red ",with:""))
        .accessibilityValue(s.mixerTargetSample?.label ?? "Select a color in the photo")
        .accessibilityHint("Drag up or down to adjust matching colors. Arrow keys adjust the selection. Escape cancels.")
        .accessibilityAdjustableAction {s.nudgeMixerTarget($0 == .increment ? 1:-1)}
        .overlay(alignment:.bottom) {
            Text(s.mixerTargetSample.map {$0.weights.isEmpty ? "Neutral area · Select a color":"\($0.label) · Drag to adjust · ↑ / ↓ · Escape to cancel"} ?? (s.canTargetMixer ? "Select a color in the photo":"Preparing color samples…"))
                .font(.caption).padding(8).background(.ultraThinMaterial,in:Capsule()).padding(10).allowsHitTesting(false)
        }
    }
}
