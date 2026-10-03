// Purpose: a bounded visual loupe and selector toolbar using retained After pixels.
// Inputs: the loaded preview, a local hover point, matching engine RGB readouts and
// local tool preferences. Outputs: magnification and explicit option/Done actions.
// Hover owns a separate observable object; it never publishes the whole Store,
// reads image files, starts workers, computes WB or changes click coordinates.
// Fit magnification remains a preview; displayed RGB is not the solver footprint.
import AppKit
import SwiftUI

struct WhiteBalanceHoverPresentation:Equatable {
    let point:CGPoint?
    let rgb:[Double]?
}

@MainActor final class WhiteBalanceHoverState:ObservableObject {
    @Published private(set) var presentation=WhiteBalanceHoverPresentation(point:nil,rgb:nil)
    func update(_ point:CGPoint?,rgb:[Double]? = nil) {
        let next=WhiteBalanceHoverPresentation(point:point,rgb:rgb)
        if next != presentation {presentation=next}
    }
    func move(_ location:CGPoint?,imageRect:CGRect,preview:WhiteBalancePreviewIdentity?,
              armed:WhiteBalancePreviewIdentity?,frame:ColorReadoutFrame?,enabled:Bool) {
        guard enabled,let preview,armed==preview,let location,
              let local=WhiteBalancePointMapping.localPoint(location,imageRect:imageRect),
              let full=WhiteBalancePointMapping.fullPoint(local,preview:preview) else {update(nil);return}
        let values=frame?.region.context==preview.context ? frame?.sample(full,before:false):nil
        update(local,rgb:values.map {Array($0.prefix(3))})
    }
}

@MainActor enum WhiteBalanceLoupeGeometry {
    static func destination(point:CGPoint,pixels:CGSize,scale:Double,canvas:CGSize)->CGRect? {
        guard point.x.isFinite,point.y.isFinite,(0...1).contains(point.x),(0...1).contains(point.y),
              pixels.width>0,pixels.height>0,pixels.width.isFinite,pixels.height.isFinite,
              WhiteBalancePreferences.scaleRange.contains(scale) else {return nil}
        let x=min(pixels.width-1,floor(point.x*pixels.width))+0.5
        let y=min(pixels.height-1,floor(point.y*pixels.height))+0.5
        return CGRect(x:canvas.width/2-x*scale,y:canvas.height/2-y*scale,
                      width:pixels.width*scale,height:pixels.height*scale)
    }
    static func origin(point:CGPoint,imageRect:CGRect,available:CGSize,panel:CGSize)->CGPoint {
        let x=imageRect.minX+point.x*imageRect.width,y=imageRect.minY+point.y*imageRect.height
        let proposed=x+panel.width+24<=available.width ? x+24:x-panel.width-24
        return CGPoint(x:min(max(0,available.width-panel.width),max(0,proposed)),
                       y:min(max(0,available.height-panel.height),max(0,y+24)))
    }
}

struct WhiteBalanceLoupePanel:View {
    @Environment(\.displayScale) private var displayScale
    let image:NSImage
    let point:CGPoint
    let detail:Bool
    let scale:Double
    let rgb:[Double]?
    static let size=CGSize(width:204,height:184)
    private var pixels:CGSize {
        let rep=image.representations.first
        return CGSize(width:rep?.pixelsWide ?? Int(image.size.width),height:rep?.pixelsHigh ?? Int(image.size.height))
    }
    var body:some View {
        VStack(spacing:6) {
            Text(detail ? "1:1 output · \(Int(scale))×":"Fit preview · \(Int(scale))×")
                .font(.caption.weight(.medium))
            Canvas {context,size in
                let dpi=displayScale.isFinite && displayScale>0 ? displayScale:1
                let physical=CGSize(width:size.width*dpi,height:size.height*dpi)
                guard let rectangle=WhiteBalanceLoupeGeometry.destination(point:point,pixels:pixels,scale:scale,canvas:physical) else {return}
                context.clip(to:Path(CGRect(origin:.zero,size:size)))
                // Scale means screen pixels per retained image pixel, including
                // Retina. The view/click coordinates remain in native points.
                context.scaleBy(x:1/dpi,y:1/dpi)
                context.draw(Image(nsImage:image).interpolation(.none),in:rectangle)
                let center=CGRect(x:physical.width/2-scale/2,y:physical.height/2-scale/2,width:scale,height:scale)
                context.stroke(Path(center),with:.color(.black),lineWidth:3)
                context.stroke(Path(center),with:.color(.white),lineWidth:1)
            }.frame(width:188,height:120).background(Color.black)
            if let rgb,rgb.count>=3 {
                Text(String(format:"RGB (%%)  %.1f  %.1f  %.1f",rgb[0],rgb[1],rgb[2]))
                    .font(.caption2.monospacedDigit())
            } else {Text("RGB (%) —").font(.caption2).foregroundStyle(.secondary)}
        }
        .padding(8).frame(width:Self.size.width,height:Self.size.height)
        .background(.regularMaterial,in:RoundedRectangle(cornerRadius:8))
        .overlay(RoundedRectangle(cornerRadius:8).stroke(Color.white.opacity(0.3)))
        .accessibilityElement(children:.combine)
        .accessibilityLabel("White Balance Loupe")
        .accessibilityHint("Magnifies the current After image. Scale does not change the white-balance sample.")
    }
}

struct WhiteBalanceSelectorOptions:View {
    @ObservedObject var preferences:WhiteBalancePreferences
    let busy:Bool
    let done:()->Void
    private var choices:some View {
        HStack(spacing:12) {
            Toggle("Auto Dismiss",isOn:Binding(get:{preferences.autoDismiss},set:{preferences.setAutoDismiss($0)}))
            Toggle("Show Loupe",isOn:Binding(get:{preferences.showLoupe},set:{preferences.setShowLoupe($0)}))
        }.toggleStyle(.checkbox).disabled(busy)
    }
    private var scale:some View {
        HStack(spacing:6) {
            Text("Scale")
            Slider(value:Binding(get:{preferences.scale},set:{preferences.setScale($0)}),
                   in:WhiteBalancePreferences.scaleRange,step:1).frame(width:90)
                .accessibilityLabel("Loupe Scale")
            Text("\(Int(preferences.scale))×").monospacedDigit().frame(width:30,alignment:.trailing)
            Button("Done",action:done).accessibilityHint("Ends white-balance point selection.")
        }
    }
    var body:some View {
        ViewThatFits(in:.horizontal) {
            HStack(spacing:16) {choices;scale}
            VStack(spacing:8) {choices;scale}
        }
        .font(.caption).padding(10).background(.regularMaterial,in:RoundedRectangle(cornerRadius:8))
        .contentShape(Rectangle()).onTapGesture {}
    }
}
