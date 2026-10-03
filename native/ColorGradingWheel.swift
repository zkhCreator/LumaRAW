// Purpose: native pointer/keyboard input and cached visuals for Color Grading.
// Inputs: wheel positions, captured recipe controls and Mac modifier keys.
// Outputs: H/S drafts, hue-only edge edits, bounded slider drafts and release saves.
// Shift constrains saturation, Command hue, Option gives fine steps. A six-degree
// soft hue lock and 0.1 fine multiplier are LumaRAW interaction conventions.
// Keyboard Option arrows work only while this wheel is hovered in its key window.
// No photo pixels, image decoding, catalog I/O or framework-global appearance changes.
import AppKit
import SwiftUI

struct GradingWheelDrag {
    var hue:Double,saturation:Double
    let hueOnly:Bool
    private var lastHue:Double,lastSaturation:Double
    private let lockedHue:Double
    private var softLock:Bool
    init(hue:Double,saturation:Double,point:CGPoint,radius:Double,hueOnly:Bool,onHandle:Bool,modifiers:NSEvent.ModifierFlags=[]) {
        self.hue=hue;self.saturation=saturation;self.hueOnly=hueOnly
        let polar=Self.polar(point,radius:radius)
        lastHue=polar.0;lastSaturation=polar.1;lockedHue=hue
        softLock=onHandle && saturation>0 && !hueOnly
        if !onHandle && !modifiers.contains(.option) {
            if !modifiers.contains(.shift) || hueOnly {self.hue=polar.0}
            if !hueOnly && !modifiers.contains(.command) {self.saturation=polar.1}
        }
    }
    static func polar(_ point:CGPoint,radius:Double)->(Double,Double) {
        let angle=atan2(point.y,point.x)*180 / .pi
        return ((angle+360).truncatingRemainder(dividingBy:360),min(100,max(0,hypot(point.x,point.y)/radius*100)))
    }
    static func delta(_ a:Double,_ b:Double)->Double {
        (a-b+540).truncatingRemainder(dividingBy:360)-180
    }
    mutating func update(_ point:CGPoint,radius:Double,modifiers:NSEvent.ModifierFlags) {
        guard radius>0,point.x.isFinite,point.y.isFinite else {return}
        let (nextHue,nextSaturation)=Self.polar(point,radius:radius)
        let factor=modifiers.contains(.option) ? 0.1:1.0
        let onlySaturation=modifiers.contains(.shift) && !hueOnly
        let onlyHue=hueOnly || modifiers.contains(.command)
        if softLock,abs(Self.delta(nextHue,lockedHue))>6 {softLock=false}
        if !onlySaturation && !softLock {
            hue=(hue+Self.delta(nextHue,lastHue)*factor+360).truncatingRemainder(dividingBy:360)
        }
        if !onlyHue {saturation=min(100,max(0,saturation+(nextSaturation-lastSaturation)*factor))}
        lastHue=nextHue;lastSaturation=nextSaturation
    }
}

struct GradingWheel:NSViewRepresentable {
    let store:Store
    let region:String
    func makeNSView(context:Context)->GradingWheelView {GradingWheelView(store:store,region:region)}
    func updateNSView(_ view:GradingWheelView,context:Context) {view.refresh()}
}

@MainActor final class GradingWheelView:NSView {
    private weak var store:Store?
    private let region:String
    private var drag:GradingWheelDrag?
    private var captureID:UUID?
    private var hovered=false
    private var tracking:NSTrackingArea?
    private var keyMonitor:Any?
    override var isFlipped:Bool {true}
    override var acceptsFirstResponder:Bool {true}
    private var radius:Double {max(1,min(bounds.width,bounds.height)/2-12)}
    private var center:CGPoint {CGPoint(x:bounds.midX,y:bounds.midY)}
    private var hueKey:String {"grading_"+region+"_hue"}
    private var satKey:String {"grading_"+region+"_saturation"}
    init(store:Store,region:String) {
        self.store=store;self.region=region;super.init(frame:.zero)
        setAccessibilityElement(true);setAccessibilityRole(.slider);setAccessibilityLabel(region.capitalized+" Color Grading")
        toolTip="Drag hue and saturation · Shift: saturation · Command: hue · Option: fine · Option arrows: hue/saturation · Escape: cancel"
    }
    required init?(coder:NSCoder) {nil}
    deinit {if let keyMonitor {NSEvent.removeMonitor(keyMonitor)}}
    func refresh() {
        if let captureID,store?.gradingInteraction.edit?.id != captureID {drag=nil;self.captureID=nil}
        needsDisplay=true
    }
    override func updateTrackingAreas() {
        super.updateTrackingAreas()
        if let tracking {removeTrackingArea(tracking)}
        let area=NSTrackingArea(rect:.zero,options:[.mouseEnteredAndExited,.activeInKeyWindow,.inVisibleRect],owner:self,userInfo:nil)
        tracking=area;addTrackingArea(area)
    }
    override func mouseEntered(with event:NSEvent) {
        hovered=true
        if keyMonitor==nil {keyMonitor=NSEvent.addLocalMonitorForEvents(matching:.keyDown) { [weak self] event in
            guard let self,self.hovered,self.window?.isKeyWindow==true else {return event}
            return self.handleKey(event) ? nil:event
        }}
    }
    override func mouseExited(with event:NSEvent) {hovered=false}
    private func point(_ event:NSEvent)->CGPoint {
        let p=convert(event.locationInWindow,from:nil);return CGPoint(x:p.x-center.x,y:p.y-center.y)
    }
    private func handlePoint(hue:Double,saturation:Double)->CGPoint {
        let angle=hue * .pi/180
        return CGPoint(x:cos(angle)*radius*saturation/100,y:sin(angle)*radius*saturation/100)
    }
    override func mouseDown(with event:NSEvent) {
        guard let store,store.canEditGrading,drag==nil,store.gradingInteraction.edit==nil else {return}
        let hue=store.gradingValue(hueKey),saturation=store.gradingValue(satKey),p=point(event)
        guard hypot(p.x,p.y)<=radius+11 else {return}
        let handle=handlePoint(hue:hue,saturation:saturation)
        let outer=handlePoint(hue:hue,saturation:(radius+7)/radius*100)
        let hueOnly=hypot(p.x-outer.x,p.y-outer.y)<=6 || hypot(p.x,p.y)>radius+2
        if event.clickCount==2 {
            if hueOnly {store.setGrading(hueKey,0)} else {store.apply([hueKey:0.0,satKey:0.0])}
            return
        }
        guard store.beginGrading(hueOnly ? [hueKey]:[hueKey,satKey]) else {return}
        window?.makeFirstResponder(self);captureID=store.gradingInteraction.edit?.id
        var next=GradingWheelDrag(hue:hue,saturation:saturation,point:p,radius:radius,hueOnly:hueOnly,
            onHandle:hypot(p.x-handle.x,p.y-handle.y)<=8 || hypot(p.x-outer.x,p.y-outer.y)<=6,modifiers:event.modifierFlags)
        next.update(p,radius:radius,modifiers:event.modifierFlags);drag=next;publish()
    }
    override func mouseDragged(with event:NSEvent) {
        guard var drag,let store,store.gradingInteraction.edit?.id==captureID,
              let edit=store.gradingInteraction.edit,store.gradingMatches(edit) else {
            store?.cancelGrading();self.drag=nil;captureID=nil;return
        }
        drag.update(point(event),radius:radius,modifiers:event.modifierFlags);self.drag=drag;publish()
    }
    private func publish() {
        guard let drag else {return}
        store?.updateGrading(drag.hueOnly ? [hueKey:drag.hue]:[hueKey:drag.hue,satKey:drag.saturation]);needsDisplay=true
    }
    override func mouseUp(with event:NSEvent) {
        guard drag != nil,store?.gradingInteraction.edit?.id==captureID else {drag=nil;captureID=nil;return}
        drag=nil;captureID=nil;_=store?.finishGrading();needsDisplay=true
    }
    override func keyDown(with event:NSEvent) {if !handleKey(event) {super.keyDown(with:event)}}
    private func handleKey(_ event:NSEvent)->Bool {
        guard let store else {return false}
        if event.keyCode==53,store.gradingInteraction.edit != nil {store.cancelGrading();drag=nil;captureID=nil;return true}
        guard event.modifierFlags.contains(.option),[123,124,125,126].contains(event.keyCode),
              store.canEditGrading,store.gradingInteraction.edit==nil else {return false}
        let step=event.modifierFlags.contains(.shift) ? 10.0:1.0
        if event.keyCode==123 || event.keyCode==124 {
            store.setGrading(hueKey,(store.gradingValue(hueKey)+(event.keyCode==123 ? step:-step)+360).truncatingRemainder(dividingBy:360))
        } else {store.setGrading(satKey,min(100,max(0,store.gradingValue(satKey)+(event.keyCode==126 ? step:-step))))}
        needsDisplay=true;return true
    }
    private static let image:NSImage = {
        let side=256.0
        let image=NSImage(size:NSSize(width:side,height:side))
        image.lockFocusFlipped(true)
        let rect=NSRect(x:0,y:0,width:side,height:side)
            for index in 0..<360 {
                let start=Double(index) * .pi/180,end=(Double(index)+1.5) * .pi/180
                let path=NSBezierPath();path.move(to:CGPoint(x:128,y:128))
                path.line(to:CGPoint(x:128+128*cos(start),y:128+128*sin(start)))
                path.line(to:CGPoint(x:128+128*cos(end),y:128+128*sin(end)));path.close()
                NSColor(calibratedHue:Double(index)/360,saturation:1,brightness:0.95,alpha:1).setFill();path.fill()
            }
            NSGradient(starting:NSColor(white:0.55,alpha:1),ending:NSColor(white:0.55,alpha:0))!
                .draw(in:NSBezierPath(ovalIn:rect),relativeCenterPosition:.zero)
        image.unlockFocus()
        return image
    }()
    override func draw(_ dirtyRect:NSRect) {
        guard let store else {return}
        Self.image.draw(in:CGRect(x:center.x-radius,y:center.y-radius,width:radius*2,height:radius*2),from:.zero,
            operation:.sourceOver,fraction:1,respectFlipped:true,hints:nil)
        let hue=store.gradingValue(hueKey),sat=store.gradingValue(satKey)
        for (saturation,size) in [(sat,8.0),((radius+7)/radius*100,6.0)] {
            let p=handlePoint(hue:hue,saturation:saturation)
            let circle=NSBezierPath(ovalIn:CGRect(x:center.x+p.x-size/2,y:center.y+p.y-size/2,width:size,height:size))
            NSColor.black.setFill();circle.fill();NSColor.white.setStroke();circle.lineWidth=1.5;circle.stroke()
        }
        setAccessibilityValue("Hue \(Int(hue)) degrees, saturation \(Int(sat)) percent")
    }
}

struct GradingSlider:NSViewRepresentable {
    let store:Store,key:String,boost:Bool
    func makeNSView(context:Context)->GradingSliderView {GradingSliderView(store:store,key:key,boost:boost)}
    func updateNSView(_ view:GradingSliderView,context:Context) {view.refresh()}
}

@MainActor final class GradingSliderView:NSSlider {
    private weak var store:Store?
    private let field:String,boost:Bool
    private var captureID:UUID?
    private var monitor:Any?
    init(store:Store,key:String,boost:Bool) {
        self.store=store;field=key;self.boost=boost;super.init(frame:.zero)
        minValue=GradingFields.limits(key).lowerBound;maxValue=GradingFields.limits(key).upperBound
        isContinuous=true;target=self;action=#selector(changed);refresh()
    }
    required init?(coder:NSCoder) {nil}
    deinit {if let monitor {NSEvent.removeMonitor(monitor)}}
    func refresh() {
        doubleValue=store?.gradingValue(field) ?? GradingFields.initial(field)
        isEnabled=store?.canEditGrading==true && (store?.gradingInteraction.edit==nil || store?.gradingInteraction.edit?.id==captureID)
    }
    override func mouseDown(with event:NSEvent) {
        if event.clickCount==2 {store?.setGrading(field,GradingFields.initial(field));refresh();return}
        guard let store,store.beginGrading([field]) else {return}
        captureID=store.gradingInteraction.edit?.id
        if boost {
            monitor=NSEvent.addLocalMonitorForEvents(matching:.flagsChanged) { [weak self] event in
                self?.publish(event.modifierFlags);return event
            }
            publish(event.modifierFlags)
        }
        super.mouseDown(with:event)
        if let monitor {NSEvent.removeMonitor(monitor);self.monitor=nil}
        if store.gradingInteraction.edit?.id==captureID {_=store.finishGrading()}
        captureID=nil;refresh()
    }
    @objc private func changed() {
        if captureID != nil {publish(NSEvent.modifierFlags)}
        else {store?.setGrading(field,doubleValue)}
    }
    private func publish(_ flags:NSEvent.ModifierFlags) {
        guard store?.gradingInteraction.edit?.id==captureID,captureID != nil else {return}
        store?.updateGrading([field:doubleValue],boost:boost && flags.contains(.option))
    }
}
