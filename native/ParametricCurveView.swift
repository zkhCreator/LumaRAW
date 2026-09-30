// Purpose: four-region tone curves with direct graph and split-divider editing.
// Inputs: native gestures, sliders and exact numeric controls. Outputs: temporary
// previews and one captured recipe edit per gesture. Escape restores saved state.
// Graph geometry is presentation only; it does not process photographs or claim
// Adobe pixel equivalence. Legacy curve settings remain separately accessible.
import SwiftUI

private struct ParametricGesture {
    let capture:ParametricCurveCapture
    let region:Int
    let divider:Int?
    let origin:CGPoint
    let slider:Bool
    var values:ParametricCurveValues
}

struct ToneCurveControls:View {
    @EnvironmentObject var s:Store
    @State private var mode="Parametric"
    var body:some View {
        VStack(spacing:12) {
            Picker("Curve Editor",selection:$mode) {
                Text("Parametric").tag("Parametric");Text("Point").tag("Point")
            }.pickerStyle(.segmented)
            if mode == "Parametric" {ParametricCurveControls()} else {PointCurveControls()}
            DisclosureGroup("Legacy Region Adjustments") {
                VStack(spacing:10) {
                    Text("These earlier controls remain separate from the four parametric regions.")
                        .font(.caption).foregroundStyle(.secondary)
                    legacy("Shadow Curve","curve_shadows")
                    legacy("Midtone Curve","curve_midtones")
                    legacy("Highlight Curve","curve_lights")
                }.padding(.top,8)
            }
            if ["curve_shadows","curve_midtones","curve_lights"].contains(where:{((s.recipe[$0] as? NSNumber)?.doubleValue ?? 0) != 0}) {
                Text("Legacy region adjustments are also applied.").font(.caption).foregroundStyle(.secondary)
            }
        }
        .onChange(of:mode) {_,value in if value == "Point",s.canvasTool == "curve" {s.setCurveTargeting(false)}}
        .onChange(of:s.canvasTool) {_,value in if value == "curve" {mode="Parametric"}}
    }
    func legacy(_ label:String,_ key:String) -> some View {
        ParameterRow(label:label,value:Binding(get:{(s.recipe[key] as? NSNumber)?.doubleValue ?? 0},set:{s.set(key,$0)}),range:-30...30)
    }
}

struct ParametricCurveControls:View {
    @EnvironmentObject var s:Store
    @StateObject private var previews=CurvePreviewScheduler()
    @State private var drag:ParametricGesture?
    @State private var cancelled=false
    @State private var activeRegion=1
    @State private var activeDivider:Int?
    @State private var hoverInput:Double?
    @FocusState private var focused:Bool
    var values:ParametricCurveValues {drag?.values ?? s.curveTargetGesture?.values ?? s.parametricCurve}
    var activeLabel:String {
        if let activeDivider {return ["Shadow Split","Midtone Split","Highlight Split"][activeDivider]}
        return ParametricCurveValues.labels[activeRegion]
    }
    var body:some View {
        VStack(spacing:10) {
            HStack {
                Button {s.setCurveTargeting(s.canvasTool != "curve")} label: {
                    Label(s.canvasTool == "curve" ? "Done Targeting":"Adjust in Photo",systemImage:"scope")
                }.disabled(drag != nil || s.hasPendingEdits)
                Spacer()
            }
            HStack {
                Text(activeLabel).font(.caption)
                Spacer()
                if let x=s.curveTargetSample?.input ?? hoverInput {
                    Text("Input \(x*100,specifier:"%.1f") / Output \(values.output(x)*100,specifier:"%.1f")")
                        .font(.caption.monospacedDigit())
                }
            }
            GeometryReader { geometry in graph(geometry.size) }.aspectRatio(1,contentMode:.fit).frame(maxHeight:300)
            ForEach(Array((0..<4).reversed()),id:\.self) {region in amountRow(region)}
            HStack {
                splitField(0,"Shadow Split");splitField(1,"Midtone Split");splitField(2,"Highlight Split")
            }.disabled(drag != nil)
            HStack {
                Button("Reset Splits") {var value=values;value.splits=ParametricCurveValues.defaults.splits;s.setParametricCurve(value)}
                Spacer()
                Button("Reset Parametric Curve") {s.setParametricCurve(.defaults)}
            }.controlSize(.small).disabled(drag != nil)
            Text("Drag the curve to adjust a region, or drag a divider below it. Arrow keys adjust the selection; Escape cancels. Double-click a region name to reset it.")
                .font(.caption).foregroundStyle(.secondary)
        }.disabled(!s.canEditPointCurves)
        .onAppear {cancelled=false}
        .onChange(of:s.selected) {_,_ in
            if drag != nil {cancelled=true}
            previews.cancel();drag=nil;hoverInput=nil
        }
        .onChange(of:s.photo?.revision) {_,revision in
            if let current=drag,let revision,revision != current.capture.revision {
                cancel();s.error="The photo changed during this curve gesture. Review the current curve and try again."
            }
        }
        .onDisappear {cancel()}
        .onChange(of:s.curveTargetSample?.region) {_,region in if let region {activeRegion=region;activeDivider=nil}}
    }
    func amountRow(_ region:Int) -> some View {
        VStack(spacing:4) {
            HStack {
                Text(ParametricCurveValues.labels[region]).font(.callout)
                    .onTapGesture(count:2) {s.setParametricCurve(values.adjusted(region,to:0))}
                Spacer()
                TextField(ParametricCurveValues.labels[region],value:Binding(get:{values.amounts[region]},set:{value in
                    guard value.isFinite,(-100...100).contains(value) else {s.error="Curve amounts must be between −100 and 100";return}
                    s.setParametricCurve(values.adjusted(region,to:value))
                }),format:.number.precision(.fractionLength(0)))
                    .multilineTextAlignment(.trailing).textFieldStyle(.plain).frame(width:50).disabled(drag != nil)
            }
            Slider(value:Binding(get:{values.amounts[region]},set:{value in
                guard !cancelled else {return}
                activeRegion=region;activeDivider=nil
                if var current=drag,current.slider,current.region == region {
                    current.values=current.values.adjusted(region,to:value);drag=current;requestPreview()
                } else if drag == nil {s.setParametricCurve(values.adjusted(region,to:value))}
            }),in:-100...100,step:1,onEditingChanged:{editing in
                if editing {
                    guard let capture=s.captureParametricCurve() else {cancelled=true;return}
                    activeRegion=region;activeDivider=nil
                    drag=ParametricGesture(capture:capture,region:region,divider:nil,origin:.zero,slider:true,values:capture.values)
                } else {finish()}
            }).labelsHidden().accessibilityLabel("Parametric "+ParametricCurveValues.labels[region])
                .disabled(drag != nil && (drag?.slider != true || drag?.region != region))
        }
    }
    func splitField(_ index:Int,_ label:String) -> some View {
        VStack(alignment:.leading,spacing:4) {
            Text(label).font(.caption2).foregroundStyle(.secondary)
            TextField(label,value:Binding(get:{values.splits[index]*100},set:{value in
                guard value.isFinite,(1...99).contains(value) else {s.error="Region splits must be between 1 and 99 percent";return}
                activeDivider=index;s.setParametricCurve(values.movedSplit(index,to:value/100))
            }),format:.number.precision(.fractionLength(1))).textFieldStyle(.roundedBorder)
                .accessibilityLabel(label+" percent")
        }
    }
    func plotRect(_ size:CGSize) -> CGRect {CGRect(x:8,y:8,width:max(1,size.width-16),height:max(1,size.height-34))}
    func normalized(_ point:CGPoint,_ rect:CGRect) -> CGPoint {
        CGPoint(x:min(1,max(0,(point.x-rect.minX)/rect.width)),y:min(1,max(0,1-(point.y-rect.minY)/rect.height)))
    }
    func graph(_ size:CGSize) -> some View {
        let rect=plotRect(size)
        return Canvas {context,_ in
            func location(_ x:Double,_ y:Double) -> CGPoint {CGPoint(x:rect.minX+x*rect.width,y:rect.maxY-y*rect.height)}
            let edges=[0]+values.splits+[1]
            let shade=CGRect(x:rect.minX+edges[activeRegion]*rect.width,y:rect.minY,width:(edges[activeRegion+1]-edges[activeRegion])*rect.width,height:rect.height)
            context.fill(Path(shade),with:.color(.accentColor.opacity(0.08)))
            var grid=Path()
            for step in 0...4 {
                let x=Double(step)/4
                grid.move(to:location(x,0));grid.addLine(to:location(x,1))
                grid.move(to:location(0,x));grid.addLine(to:location(1,x))
            }
            context.stroke(grid,with:.color(.secondary.opacity(0.25)),lineWidth:1)
            var diagonal=Path();diagonal.move(to:location(0,0));diagonal.addLine(to:location(1,1))
            context.stroke(diagonal,with:.color(.secondary.opacity(0.5)),style:StrokeStyle(lineWidth:1,dash:[3,4]))
            var curve=Path();curve.move(to:location(0,0))
            for step in 1...256 {let x=Double(step)/256;curve.addLine(to:location(x,values.output(x)))}
            context.stroke(curve,with:.color(.primary),lineWidth:2)
            if let sample=s.curveTargetSample {
                let p=location(sample.input,values.output(sample.input))
                context.fill(Path(ellipseIn:CGRect(x:p.x-4,y:p.y-4,width:8,height:8)),with:.color(.accentColor))
            }
            for i in 0..<3 {
                let x=rect.minX+values.splits[i]*rect.width
                var line=Path();line.move(to:CGPoint(x:x,y:rect.minY));line.addLine(to:CGPoint(x:x,y:rect.maxY))
                context.stroke(line,with:.color(.secondary.opacity(0.6)),style:StrokeStyle(lineWidth:1,dash:[2,3]))
                var handle=Path();handle.move(to:CGPoint(x:x,y:rect.maxY+4));handle.addLine(to:CGPoint(x:x-6,y:rect.maxY+15));handle.addLine(to:CGPoint(x:x+6,y:rect.maxY+15));handle.closeSubpath()
                context.fill(handle,with:.color(activeDivider == i ? .accentColor:.secondary))
            }
        }.background(Color.secondary.opacity(0.06),in:RoundedRectangle(cornerRadius:6))
        .contentShape(Rectangle()).focusable().focused($focused)
        .overlay(RoundedRectangle(cornerRadius:6).stroke(focused ? Color.accentColor:.clear,lineWidth:1))
        .onContinuousHover {phase in
            switch phase {
            case .active(let position):
                if drag == nil,rect.contains(position) {let x=normalized(position,rect).x;hoverInput=x;activeRegion=values.region(x)}
            case .ended:if drag == nil {hoverInput=nil}
            }
        }
        .gesture(DragGesture(minimumDistance:0).onChanged {value in
            guard !cancelled else {return}
            if drag == nil {
                guard let capture=s.captureParametricCurve() else {return}
                let start=normalized(value.startLocation,rect)
                var divider:Int?
                if value.startLocation.y>rect.maxY {
                    let closest=(0..<3).min {abs(capture.values.splits[$0]-start.x)<abs(capture.values.splits[$1]-start.x)}!
                    guard abs(capture.values.splits[closest]-start.x)*rect.width<=14 else {return}
                    divider=closest
                } else if !rect.contains(value.startLocation) {return}
                activeDivider=divider;activeRegion=capture.values.region(start.x);focused=true
                drag=ParametricGesture(capture:capture,region:activeRegion,divider:divider,origin:start,slider:false,values:capture.values)
            }
            guard var current=drag,!current.slider else {return}
            let end=normalized(value.location,rect)
            if let divider=current.divider {
                current.values=current.capture.values.movedSplit(divider,to:current.capture.values.splits[divider]+end.x-current.origin.x)
            } else {
                let input=current.origin.x
                let target=current.capture.values.output(input)+end.y-current.origin.y
                current.values=current.capture.values.draggedRegion(current.region,input:input,target:target)
                hoverInput=current.origin.x
            }
            drag=current;requestPreview()
        }.onEnded {_ in finish()})
        .onKeyPress(.escape) {if drag != nil {cancel();return .handled};return .ignored}
        .onKeyPress(.upArrow) {nudge(1);return .handled}
        .onKeyPress(.downArrow) {nudge(-1);return .handled}
        .onKeyPress(.leftArrow) {if activeDivider != nil {nudge(-1)} else {activeRegion=max(0,activeRegion-1)};return .handled}
        .onKeyPress(.rightArrow) {if activeDivider != nil {nudge(1)} else {activeRegion=min(3,activeRegion+1)};return .handled}
        .accessibilityElement(children:.ignore).accessibilityLabel("Parametric curve, "+activeLabel)
        .accessibilityValue(activeDivider.map {"\(values.splits[$0]*100) percent"} ?? "\(values.amounts[activeRegion])")
        .accessibilityAdjustableAction {nudge($0 == .increment ? 1:-1)}
    }
    func nudge(_ direction:Double) {
        guard drag == nil else {return}
        if let i=activeDivider {s.setParametricCurve(values.movedSplit(i,to:values.splits[i]+direction/100))}
        else {s.setParametricCurve(values.adjusted(activeRegion,to:values.amounts[activeRegion]+direction))}
    }
    func requestPreview() {
        previews.request(store:s) {guard let current=drag else {return nil};return current.capture.preview(current.values)}
    }
    func finish() {
        previews.cancel()
        if let current=drag,!cancelled,!s.commitParametricCurve(current.capture,current.values) {s.render()}
        drag=nil;cancelled=false
    }
    func cancel() {
        let wasDragging=drag != nil
        previews.cancel();drag=nil;cancelled=true
        if wasDragging {s.cancelMainPreview();s.render()}
    }
}
