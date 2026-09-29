// Purpose: direct and keyboard-accessible point-curve editing in the inspector.
// Inputs: selected channel, pointer/numeric actions and current Store recipes.
// Outputs: captured gestures committed once on release, or immediate partial edits.
// Drag drafts never mutate a different photo or rebase after an external edit.
// This control graph is not a pixel renderer or proof of Adobe curve equivalence.
import SwiftUI

private struct CurveDrag {
    let capture: PointCurveCapture
    let index: Int
    let origin: CGPoint
    let anchor: [Double]
    var points: [[Double]]
}

struct PointCurveControls: View {
    @EnvironmentObject var s:Store
    @State private var channel="curve_rgb_points"
    @State private var selectedPoint=0
    @State private var drag:CurveDrag?
    @State private var cancelled=false
    @State private var draftPreviewTask:Task<Void,Never>?
    @State private var draftPreviewGeneration=0
    @FocusState private var plotFocused:Bool
    var legacy:Bool { channel == PointCurveFields.legacy }
    var points:[[Double]] { drag?.points ?? s.pointCurve(channel) }
    var index:Int { min(max(0,selectedPoint),points.count-1) }
    var color:Color {
        switch channel {
        case "curve_red_points":return .red
        case "curve_green_points":return .green
        case "curve_blue_points":return .blue
        default:return .primary
        }
    }
    var channels:[String] {
        PointCurveFields.keys+(s.pointCurve(PointCurveFields.legacy) != PointCurveFields.identity || legacy ? [PointCurveFields.legacy]:[])
    }
    var body:some View {
        VStack(spacing:10) {
            Picker("Curve Channel",selection:$channel) {
                ForEach(channels,id:\.self) { Text(PointCurveFields.label($0)).tag($0) }
            }.disabled(drag != nil)
            GeometryReader { geometry in graph(geometry.size) }.aspectRatio(1,contentMode:.fit)
                .frame(maxHeight:300)
            Picker("Point Curve",selection:Binding(get:{
                s.pointCurvePresets.first(where: { $0.value == points })?.key ?? "Custom"
            },set:{ name in
                if let value=s.pointCurvePresets[name] { s.setPointCurve(channel,value);selectedPoint=0 }
            })) {
                Text("Custom").tag("Custom")
                ForEach(["Linear","Medium Contrast","Strong Contrast"].filter { s.pointCurvePresets[$0] != nil },id:\.self) { Text($0).tag($0) }
            }.disabled(drag != nil)
            Picker("Selected Point",selection:$selectedPoint) {
                ForEach(points.indices,id:\.self) { i in
                    Text("\(i+1) · Input \(points[i][0]*255,specifier:"%.1f") / Output \(points[i][1]*255,specifier:"%.1f")").tag(i)
                }
            }.disabled(drag != nil)
            HStack {
                coordinate("Input",axis:0)
                coordinate("Output",axis:1)
            }.disabled(drag != nil)
            HStack {
                Button("Add Point") { addPoint() }.disabled(points.count>=16 || drag != nil)
                Button("Delete Point") { deletePoint() }.disabled(index == 0 || index == points.count-1 || drag != nil)
                Spacer()
                Text("\(points.count)/16").font(.caption).foregroundStyle(.secondary)
            }.controlSize(.small)
            HStack {
                Button("Reset Channel") { s.setPointCurve(channel,PointCurveFields.identity);selectedPoint=0 }
                Spacer()
                Button("Reset RGB Curves") { s.resetRGBPointCurves();selectedPoint=0 }
            }.controlSize(.small).disabled(drag != nil)
            Text("Click to add a point. Drag or use arrow keys to adjust. Delete removes an interior point; Escape cancels a drag.")
                .font(.caption).foregroundStyle(.secondary)
            if s.pointCurve(PointCurveFields.legacy) != PointCurveFields.identity {
                Text("An earlier luminance curve is also applied. Choose Legacy Luminance to review or reset it.")
                    .font(.caption).foregroundStyle(.secondary)
            }
        }.disabled(!s.canEditPointCurves)
        .onAppear { cancelled=false }
        .task { if s.pointCurvePresets.isEmpty { await s.loadPointCurvePresets() } }
        .onChange(of:channel) { _,_ in selectedPoint=0;drag=nil }
        .onChange(of:s.selected) { _,_ in
            if drag != nil {cancelled=true}
            draftPreviewGeneration+=1;draftPreviewTask?.cancel();draftPreviewTask=nil;drag=nil;selectedPoint=0
        }
        .onChange(of:s.photo?.revision) { _,revision in
            if let current=drag,let revision,revision != current.capture.revision {
                cancelDrag();s.error="The photo changed during this curve gesture. Review the current curve and try again."
            }
        }
        .onDisappear { cancelDrag() }
    }
    func coordinate(_ label:String,axis:Int) -> some View {
        VStack(alignment:.leading) {
            Text(label).font(.caption).foregroundStyle(.secondary)
            TextField(label,value:Binding(get:{points[index][axis]*255},set:{value in
                guard value.isFinite,(0...255).contains(value) else {s.error="Curve coordinates must be between 0 and 255";return}
                let x=axis == 0 ? value/255:points[index][0]
                let y=axis == 1 ? value/255:points[index][1]
                s.setPointCurve(channel,PointCurveFields.moved(points,index:index,x:x,y:y,legacy:legacy))
            }),format:.number.precision(.fractionLength(1))).textFieldStyle(.roundedBorder)
                .accessibilityLabel(PointCurveFields.label(channel)+" curve point "+label.lowercased())
        }
    }
    func plotRect(_ size:CGSize) -> CGRect { CGRect(x:10,y:10,width:max(1,size.width-20),height:max(1,size.height-20)) }
    func normalized(_ position:CGPoint,_ rect:CGRect) -> CGPoint {
        CGPoint(x:min(1,max(0,(position.x-rect.minX)/rect.width)),y:min(1,max(0,1-(position.y-rect.minY)/rect.height)))
    }
    func graph(_ size:CGSize) -> some View {
        let rect=plotRect(size)
        return Canvas { context,_ in
            func location(_ x:Double,_ y:Double) -> CGPoint { CGPoint(x:rect.minX+x*rect.width,y:rect.maxY-y*rect.height) }
            var grid=Path()
            for step in 0...4 {
                let t=Double(step)/4
                grid.move(to:location(t,0));grid.addLine(to:location(t,1))
                grid.move(to:location(0,t));grid.addLine(to:location(1,t))
            }
            context.stroke(grid,with:.color(.secondary.opacity(0.3)),lineWidth:1)
            var diagonal=Path();diagonal.move(to:location(0,0));diagonal.addLine(to:location(1,1))
            context.stroke(diagonal,with:.color(.secondary.opacity(0.5)),style:StrokeStyle(lineWidth:1,dash:[3,4]))
            var curve=Path();curve.move(to:location(0,points[0][1]));curve.addLine(to:location(points[0][0],points[0][1]))
            let slopes=PointCurvePlot.slopes(points)
            for i in 0..<points.count-1 {
                let a=points[i],b=points[i+1],width=b[0]-a[0]
                if legacy { curve.addLine(to:location(b[0],b[1])) }
                else {
                    curve.addCurve(to:location(b[0],b[1]),control1:location(a[0]+width/3,a[1]+slopes[i]*width/3),control2:location(b[0]-width/3,b[1]-slopes[i+1]*width/3))
                }
            }
            curve.addLine(to:location(1,points.last![1]));context.stroke(curve,with:.color(color),lineWidth:2)
            for i in points.indices {
                let center=location(points[i][0],points[i][1]),radius:CGFloat=i == index ? 5:3.5
                let dot=Path(ellipseIn:CGRect(x:center.x-radius,y:center.y-radius,width:2*radius,height:2*radius))
                context.fill(dot,with:.color(color));context.stroke(dot,with:.color(.primary.opacity(0.7)),lineWidth:1)
            }
        }.background(Color.secondary.opacity(0.08),in:RoundedRectangle(cornerRadius:6))
        .contentShape(Rectangle()).focusable().focused($plotFocused)
        .overlay(RoundedRectangle(cornerRadius:6).stroke(plotFocused ? Color.accentColor:.clear,lineWidth:1))
        .gesture(DragGesture(minimumDistance:0).onChanged { value in
            guard !cancelled else { return }
            if drag == nil {
                guard rect.contains(value.startLocation),let capture=s.capturePointCurve(channel) else { return }
                plotFocused=true
                let start=normalized(value.startLocation,rect)
                let closest=capture.points.indices.min { a,b in
                    hypot((capture.points[a][0]-start.x)*rect.width,(capture.points[a][1]-start.y)*rect.height)<hypot((capture.points[b][0]-start.x)*rect.width,(capture.points[b][1]-start.y)*rect.height)
                }!
                let distance=hypot((capture.points[closest][0]-start.x)*rect.width,(capture.points[closest][1]-start.y)*rect.height)
                if distance<=10 { drag=CurveDrag(capture:capture,index:closest,origin:start,anchor:capture.points[closest],points:capture.points) }
                else if let inserted=PointCurveFields.inserted(capture.points,x:start.x,y:start.y,legacy:legacy) {
                    drag=CurveDrag(capture:capture,index:inserted.index,origin:start,anchor:inserted.points[inserted.index],points:inserted.points)
                } else { return }
                selectedPoint=drag!.index
            }
            let end=normalized(value.location,rect)
            if var current=drag {
                current.points=PointCurveFields.moved(current.points,index:current.index,x:current.anchor[0]+(end.x-current.origin.x),y:current.anchor[1]+(end.y-current.origin.y),legacy:legacy)
                drag=current
                requestDraftPreview()
            }
        }.onEnded { _ in
            draftPreviewGeneration+=1;draftPreviewTask?.cancel();draftPreviewTask=nil
            if let current=drag,!cancelled,!s.commitPointCurve(current.capture,current.points) {s.render()}
            drag=nil;cancelled=false
        })
        .contextMenu {
            let captured=s.capturePointCurve(channel)
            let selected=index
            Button("Delete Selected Control Point") {
                if let captured {s.commitPointCurve(captured,PointCurveFields.removed(captured.points,index:selected))}
            }.disabled(captured == nil || selected == 0 || selected == points.count-1)
            Button("Flatten Curve") {if let captured {s.commitPointCurve(captured,PointCurveFields.identity)}}
                .disabled(captured == nil)
        }
        .onKeyPress(.escape) { if drag != nil {cancelDrag();return .handled};return .ignored }
        .onKeyPress(.delete) { deletePoint();return .handled }
        .onKeyPress(.upArrow) { nudge(0,1);return .handled }
        .onKeyPress(.downArrow) { nudge(0,-1);return .handled }
        .onKeyPress(.leftArrow) { nudge(-1,0);return .handled }
        .onKeyPress(.rightArrow) { nudge(1,0);return .handled }
        .accessibilityElement(children:.ignore)
        .accessibilityLabel(PointCurveFields.label(channel)+" point curve")
        .accessibilityValue("Point \(index+1) of \(points.count), input \(points[index][0]*255), output \(points[index][1]*255)")
        .accessibilityAdjustableAction { direction in nudge(0,direction == .increment ? 1:-1) }
    }
    func nudge(_ dx:Double,_ dy:Double) {
        guard drag == nil else { return }
        s.setPointCurve(channel,PointCurveFields.moved(points,index:index,x:points[index][0]+dx/255,y:points[index][1]+dy/255,legacy:legacy))
    }
    func addPoint() {
        guard drag == nil else { return }
        var largest=0
        var widest=0.0
        for i in 0..<points.count-1 {
            let width=points[i+1][0]-points[i][0]
            if width>widest {widest=width;largest=i}
        }
        let x=(points[largest][0]+points[largest+1][0])/2
        if let result=PointCurveFields.inserted(points,x:x,y:PointCurvePlot.value(x,points:points,legacy:legacy),legacy:legacy) {
            s.setPointCurve(channel,result.points);selectedPoint=result.index
        }
    }
    func deletePoint() {
        guard drag == nil else { return }
        let result=PointCurveFields.removed(points,index:index)
        s.setPointCurve(channel,result);selectedPoint=min(index,result.count-1)
    }
    func requestDraftPreview() {
        guard draftPreviewTask == nil else {return}
        draftPreviewGeneration+=1;let token=draftPreviewGeneration
        draftPreviewTask=Task { @MainActor in
            defer {if token == draftPreviewGeneration {draftPreviewTask=nil}}
            try? await Task.sleep(nanoseconds:180_000_000)
            // Keep one in-flight image and one coalesced latest draft. Continuous
            // pointer movement must not repeatedly kill an unfinished worker.
            while s.rendering && !Task.isCancelled {
                try? await Task.sleep(nanoseconds:40_000_000)
            }
            guard !Task.isCancelled,token == draftPreviewGeneration,let current=drag else {return}
            s.render(curveDraft:(current.capture,current.points),debounce:false)
        }
    }
    func cancelDrag() {
        let wasDragging=drag != nil
        draftPreviewGeneration+=1;draftPreviewTask?.cancel();draftPreviewTask=nil;drag=nil;cancelled=true
        if wasDragging {s.cancelMainPreview();s.render()}
    }
}
