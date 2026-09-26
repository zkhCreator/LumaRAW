// Purpose: direct-manipulation crop and local masks in normalized image space.
// Inputs: pointer positions within the displayed image rectangle. Outputs: recipe
// patches only. Existing crop/ratio is mapped correctly before a nested crop.
// Keyboard-accessible equivalent controls remain in the inspector.
import SwiftUI

struct DrawingOverlay:View {
    @EnvironmentObject var s:Store
    let image:NSImage
    let available:CGSize
    @State private var points:[CGPoint]=[]
    var rect:CGRect {
        let size=image.size
        let factor=min(max(1,available.width-52)/size.width,max(1,available.height-52)/size.height)
        let w=size.width*factor,h=size.height*factor
        return CGRect(x:(available.width-w)/2,y:(available.height-h)/2,width:w,height:h)
    }
    func normalize(_ p:CGPoint)->CGPoint {CGPoint(x:min(1,max(0,(p.x-rect.minX)/rect.width)),y:min(1,max(0,(p.y-rect.minY)/rect.height)))}
    var body:some View {
        Canvas {context,_ in
            guard let start=points.first,let end=points.last else{return}
            var path=Path()
            let a=CGPoint(x:rect.minX+start.x*rect.width,y:rect.minY+start.y*rect.height)
            let b=CGPoint(x:rect.minX+end.x*rect.width,y:rect.minY+end.y*rect.height)
            if s.canvasTool=="crop" {path.addRect(CGRect(x:min(a.x,b.x),y:min(a.y,b.y),width:abs(a.x-b.x),height:abs(a.y-b.y)))}
            else if s.canvasTool=="radial" {let r=hypot(b.x-a.x,b.y-a.y);path.addEllipse(in:CGRect(x:a.x-r,y:a.y-r,width:r*2,height:r*2))}
            else {path.move(to:a);for p in points{path.addLine(to:CGPoint(x:rect.minX+p.x*rect.width,y:rect.minY+p.y*rect.height))}}
            context.stroke(path,with:.color(.white),style:StrokeStyle(lineWidth:s.canvasTool=="brush" ? min(rect.width,rect.height)*0.08:2,dash:s.canvasTool=="brush" ? []:[7,4]))
        }
        .contentShape(Rectangle())
        .gesture(DragGesture(minimumDistance:2).onChanged{value in
            guard rect.contains(value.startLocation)else{return}
            if points.isEmpty{points=[normalize(value.startLocation)]}
            if points.count<500{points.append(normalize(value.location))}
        }.onEnded{_ in apply();points=[];s.canvasTool="view"})
        .overlay(alignment:.bottom){Text(s.canvasTool=="crop" ? "Drag to select the crop area":"Drag to add a local mask · Default exposure +0.5 EV").font(.caption).padding(8).background(.ultraThinMaterial,in:Capsule()).padding(.bottom,12)}
        .accessibilityLabel("Draw on the photo, or use the keyboard controls in the inspector")
    }
    func apply(){
        guard let a=points.first,let b=points.last else{return}
        if s.canvasTool=="crop" {
            let x0=min(a.x,b.x),x1=max(a.x,b.x),y0=min(a.y,b.y),y1=max(a.y,b.y)
            guard x1-x0>0.02,y1-y0>0.02 else{return}
            var box=s.recipe["crop_box"] as? [Double] ?? [0,0,1,1]
            var w=(s.metadata["width"] as? NSNumber)?.doubleValue ?? image.size.width
            var h=(s.metadata["height"] as? NSNumber)?.doubleValue ?? image.size.height
            if (s.recipe["rotation"] as? Int ?? 0)%180 != 0{swap(&w,&h)}
            let ratioName=s.recipe["crop"] as? String ?? "original"
            if ratioName != "original" {
                let values=ratioName.split(separator:":").compactMap{Double($0)}
                if values.count==2 {
                    let ratio=values[0]/values[1],cw=(box[2]-box[0])*w,ch=(box[3]-box[1])*h
                    if cw/ch>ratio{let delta=(cw-ch*ratio)/2/w;box[0]+=delta;box[2]-=delta}
                    else{let delta=(ch-cw/ratio)/2/h;box[1]+=delta;box[3]-=delta}
                }
            }
            let cw=box[2]-box[0],ch=box[3]-box[1]
            let newBox=[box[0]+x0*cw,box[1]+y0*ch,box[0]+x1*cw,box[1]+y1*ch]
            guard newBox[2]-newBox[0]>=0.01,newBox[3]-newBox[1]>=0.01 else{return}
            s.set("crop","original");s.set("crop_box",newBox)
        }else{
            var masks=s.recipe["masks"] as? [[String:Any]] ?? [];guard masks.count<12 else{s.error="Up to 12 local masks are supported";return}
            var mask:[String:Any]=["name":"Mask \(masks.count+1)","kind":s.canvasTool,"x":a.x,"y":a.y,"x2":b.x,"y2":b.y,"feather":0.5,"exposure":0.5]
            mask["radius"]=s.canvasTool=="brush" ? 0.04:min(1,max(0.01,hypot((b.x-a.x)*rect.width,(b.y-a.y)*rect.height)/min(rect.width,rect.height)))
            if s.canvasTool=="brush"{mask["points"]=points.map{[$0.x,$0.y]}}
            masks.append(mask);s.set("masks",masks)
        }
    }
}
