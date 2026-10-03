// Purpose: direct-manipulation crop and local masks in normalized image space.
// Inputs: pointer positions within the displayed image rectangle. Outputs: recipe
// patches only. Renderer crop bounds and inverse catalog orientation preserve
// nested crops and mask positions. Drawing requires a matching fitted After frame.
// Capture begins on pointer-down; photo/source/preview/tool/geometry changes cancel
// the entire gesture. Release never retargets points. Pixel equations stay in engine.
// Keyboard-accessible equivalent controls remain in the inspector.
import SwiftUI

struct DrawingOverlay:View {
    @EnvironmentObject var s:Store
    let image:NSImage
    let available:CGSize
    @State private var gesture=DrawingGesture()
    var current:DrawingContext? {s.drawingContext(image:image,rect:rect)}
    var rect:CGRect {
        let size=image.size
        guard [size.width,size.height,available.width,available.height].allSatisfy({$0.isFinite && $0>0}) else {return .zero}
        let factor=min(max(1,available.width-52)/size.width,max(1,available.height-52)/size.height)
        let w=size.width*factor,h=size.height*factor
        return CGRect(x:(available.width-w)/2,y:(available.height-h)/2,width:w,height:h)
    }
    var body:some View {
        DrawingStrokePreview(stroke:gesture.preview,current:current)
        .contentShape(Rectangle())
        .onChange(of:current) {_,value in
            if let captured=gesture.context,captured != value {gesture.cancel()}
        }
        .gesture(DragGesture(minimumDistance:0).onChanged {value in
            gesture.update(start:value.startLocation,location:value.location,current:current)
        }.onEnded {value in
            let captured=gesture.context
            if captured != nil {gesture.update(start:value.startLocation,location:value.location,current:current)}
            if let stroke=gesture.finish(current:current) {_=s.applyDrawing(stroke,image:image,rect:rect)}
            else if captured != nil,captured != current {
                s.message="Drawing cancelled because the photo, tool or preview changed. Draw again."
            }
        })
        .overlay(alignment:.bottom){Text(s.canvasTool=="crop" ? "Drag to select the crop area":"Drag to add a local mask · Default exposure +0.5 EV").font(.caption).padding(8).background(.ultraThinMaterial,in:Capsule()).padding(.bottom,12)}
        .accessibilityLabel("Draw on the photo, or use the keyboard controls in the inspector")
    }
}

struct DrawingStrokePreview:View {
    let stroke:DrawingStroke?
    let current:DrawingContext?
    var body:some View {
        Canvas {context,_ in
            guard let stroke,stroke.context==current,let start=stroke.points.first,let end=stroke.points.last else{return}
            let rect=stroke.context.rect,tool=stroke.context.tool
            var path=Path()
            let a=CGPoint(x:rect.minX+start.x*rect.width,y:rect.minY+start.y*rect.height)
            let b=CGPoint(x:rect.minX+end.x*rect.width,y:rect.minY+end.y*rect.height)
            if tool=="crop" {path.addRect(CGRect(x:min(a.x,b.x),y:min(a.y,b.y),width:abs(a.x-b.x),height:abs(a.y-b.y)))}
            else if tool=="radial" {let r=hypot(b.x-a.x,b.y-a.y);path.addEllipse(in:CGRect(x:a.x-r,y:a.y-r,width:r*2,height:r*2))}
            else {path.move(to:a);for p in stroke.points {path.addLine(to:CGPoint(x:rect.minX+p.x*rect.width,y:rect.minY+p.y*rect.height))}}
            context.stroke(path,with:.color(.white),style:StrokeStyle(lineWidth:tool=="brush" ? min(rect.width,rect.height)*0.08:2,dash:tool=="brush" ? []:[7,4]))
        }
    }
}
