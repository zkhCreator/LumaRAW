// Purpose: Mac pointer adapter for a bounded Library Painter stroke.
// Inputs: thumbnail rectangles and local mouse events. Outputs: touched IDs and
// one Store commit at mouse-up. Segment intersection handles coalesced drag events.
// No photo selection, pixels or metadata rules. Disabled views pass events through;
// layout changes, dismissal and Escape discard a stroke that has not been submitted.
import SwiftUI
import AppKit

struct PainterThumbnailAnchors: PreferenceKey {
    static var defaultValue: [Int:Anchor<CGRect>]=[:]
    static func reduce(value: inout [Int:Anchor<CGRect>],nextValue: ()->[Int:Anchor<CGRect>]) {
        value.merge(nextValue(),uniquingKeysWith:{ _,new in new })
    }
}

func painterIntersects(_ rect: CGRect,from start: CGPoint,to end: CGPoint) -> Bool {
    guard rect.width>0,rect.height>0 else { return false }
    let dx=end.x-start.x,dy=end.y-start.y
    var lower: CGFloat=0,upper: CGFloat=1
    for (p,q) in [(-dx,start.x-rect.minX),(dx,rect.maxX-start.x),(-dy,start.y-rect.minY),(dy,rect.maxY-start.y)] {
        if p == 0 { if q<0 { return false };continue }
        let t=q/p
        if p<0 { lower=max(lower,t) } else { upper=min(upper,t) }
        if lower>upper { return false }
    }
    return true
}

struct PainterPointerLayer: NSViewRepresentable {
    @EnvironmentObject var s: Store
    let rectangles: [Int:CGRect]
    func makeNSView(context: Context) -> PainterPointerView { PainterPointerView() }
    func updateNSView(_ view: PainterPointerView,context: Context) {
        if view.dragging && (view.rectangles != rectangles || !s.painterCanReceive) { view.cancelStroke(deferred:true) }
        let newlyActivated=s.painterEnabled && !view.painterActivated
        let returningFromPicker=view.pickerPresented && s.painterKeywordPicker == nil
        view.painterActivated=s.painterEnabled
        view.pickerPresented=s.painterKeywordPicker != nil
        view.store=s;view.rectangles=rectangles;view.enabled=s.painterCanReceive
        if newlyActivated || returningFromPicker {
            DispatchQueue.main.async { [weak view] in
                guard let view,view.enabled,view.store?.painterCanReceive == true else { return }
                view.window?.makeFirstResponder(view)
            }
        }
        view.window?.invalidateCursorRects(for:view)
    }
    static func dismantleNSView(_ view: PainterPointerView,coordinator: ()) { view.cancelStroke(deferred:true) }
}

final class PainterPointerView: NSView {
    weak var store: Store?
    var rectangles: [Int:CGRect]=[:]
    var enabled=false
    var painterActivated=false
    var pickerPresented=false
    var dragging=false
    private var previous=CGPoint.zero
    override var isFlipped: Bool { true }
    override var acceptsFirstResponder: Bool { enabled }
    override func hitTest(_ point: NSPoint) -> NSView? { enabled ? super.hitTest(point):nil }
    override func resetCursorRects() {
        if enabled { addCursorRect(bounds,cursor:cursor) }
    }
    private var cursor: NSCursor {
        let erasing=store?.painterSupportsErasing == true && NSEvent.modifierFlags.contains(.option)
        if let image=NSImage(systemSymbolName:erasing ? "eraser":"paintbrush.pointed",accessibilityDescription:erasing ? "Remove Painter attribute":"Painter") {
            image.size=NSSize(width:22,height:22)
            return NSCursor(image:image,hotSpot:NSPoint(x:2,y:20))
        }
        return .crosshair
    }
    override func flagsChanged(with event: NSEvent) {
        cursor.set()
        if enabled,store?.painterKind == "keywords",
           event.modifierFlags.intersection([.shift,.command,.option,.control]) == .shift {
            cancelStroke();store?.choosePainterKeywordSets()
        }
    }
    override func mouseDown(with event: NSEvent) {
        guard enabled,store?.beginPainterStroke(erase:event.modifierFlags.contains(.option)) == true else { return }
        window?.makeFirstResponder(self);dragging=true
        previous=convert(event.locationInWindow,from:nil)
        touch(previous)
    }
    override func mouseDragged(with event: NSEvent) {
        if dragging { touch(convert(event.locationInWindow,from:nil)) }
    }
    override func mouseUp(with event: NSEvent) {
        guard dragging else { return }
        touch(convert(event.locationInWindow,from:nil));dragging=false
        store?.endPainterStroke()
    }
    override func keyDown(with event: NSEvent) {
        if event.keyCode == 53 { cancelStroke();store?.setPainting(false);window?.makeFirstResponder(nil) }
        else { super.keyDown(with:event) }
    }
    func cancelStroke(deferred: Bool=false) {
        dragging=false
        if deferred {
            // Do not publish SwiftUI state during representable update/teardown.
            // The captured identity prevents a delayed cancellation from clearing
            // a newer stroke; pointer submission is disabled immediately above.
            if let id=store?.painterStroke?.id {
                DispatchQueue.main.async { [weak store] in store?.cancelPainterStroke(id:id) }
            }
        } else { store?.cancelPainterStroke() }
    }
    private func touch(_ point: CGPoint) {
        let ids=rectangles.filter { painterIntersects($0.value,from:previous,to:point) }.keys.sorted()
        store?.touchPainterPhotos(ids);previous=point
    }
}
