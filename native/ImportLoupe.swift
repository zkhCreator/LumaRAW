// Purpose: Import-only fitted and 1:1 Loupe viewport state, frame validation and rendering.
// Inputs: one captured Import item, bounded physical-pixel viewport requests and drag events.
// Outputs: a clipped preview canvas and normalized center updates for ImportReviewModel.
// No catalog/library selection state, image decoding, filesystem reads or pixel processing.
import AppKit
import SwiftUI

struct ImportLoupeViewport: Equatable {
    // Zero means Fit. One means one image pixel per physical display pixel.
    var zoom=0.0
    var cx=0.5
    var cy=0.5

    mutating func move(x: Double,y: Double) {
        cx=min(1,max(0,x));cy=min(1,max(0,y))
    }

    static func clampedCenter(_ center: Double,viewportPixels: Int,fullPixels: Int) -> Double {
        guard fullPixels>0 else { return 0.5 }
        let half=min(0.5,Double(max(1,viewportPixels))/(2*Double(fullPixels)))
        return min(1-half,max(half,center))
    }
}

struct ImportLoupeRequest: Equatable {
    let planID: Int
    let revision: Int
    let itemID: Int
    let source: String
    let viewport: ImportLoupeViewport
    // Fit does not send a viewport, so its dimensions are zero in the native identity.
    let width: Int
    let height: Int

    var params: [String:Any] {
        var result: [String:Any]=["plan_id":planID,"item_id":itemID,"expected_revision":revision,"detail":true]
        if viewport.zoom == 1 {
            result["viewport"]=["cx":viewport.cx,"cy":viewport.cy,"width":width,"height":height]
        }
        return result
    }
}

struct ImportLoupeROI: Equatable {
    let x: Double
    let y: Double
    let width: Double
    let height: Double

    init?(_ value: Any?) {
        guard let values=value as? [Any],values.count == 4,
              let x=(values[0] as? NSNumber)?.doubleValue,
              let y=(values[1] as? NSNumber)?.doubleValue,
              let width=(values[2] as? NSNumber)?.doubleValue,
              let height=(values[3] as? NSNumber)?.doubleValue,
              x.isFinite,y.isFinite,width.isFinite,height.isFinite,
              x>=0,y>=0,width>0,height>0 else { return nil }
        self.x=x;self.y=y;self.width=width;self.height=height
    }

    func isInside(width fullWidth: Int,height fullHeight: Int) -> Bool {
        x+width<=Double(fullWidth)+1 && y+height<=Double(fullHeight)+1
    }
}

struct ImportLoupeFrame {
    let request: ImportLoupeRequest
    let image: NSImage
    // width/height describe the returned PNG ROI; fullWidth/fullHeight describe its source canvas.
    let width: Int
    let height: Int
    let fullWidth: Int
    let fullHeight: Int
    let roi: ImportLoupeROI?

    init?(result: [String:Any],image: NSImage,request: ImportLoupeRequest) {
        guard let width=result["width"] as? Int,width>0,
              let height=result["height"] as? Int,height>0,
              let fullWidth=result["full_width"] as? Int,fullWidth>0,
              let fullHeight=result["full_height"] as? Int,fullHeight>0 else { return nil }
        let roi=ImportLoupeROI(result["roi"])
        if request.viewport.zoom == 1 {
            guard let roi,roi.isInside(width:fullWidth,height:fullHeight),
                  abs(roi.width-Double(width))<=1,abs(roi.height-Double(height))<=1,
                  Self.matchesRequestedCenter(roi:roi,request:request,fullWidth:fullWidth,fullHeight:fullHeight) else { return nil }
        }
        self.request=request;self.image=image;self.width=width;self.height=height
        self.fullWidth=fullWidth;self.fullHeight=fullHeight;self.roi=roi
    }

    private static func matchesRequestedCenter(roi: ImportLoupeROI,request: ImportLoupeRequest,
        fullWidth: Int,fullHeight: Int) -> Bool {
        let expectedX=ImportLoupeViewport.clampedCenter(request.viewport.cx,viewportPixels:request.width,fullPixels:fullWidth)
        let expectedY=ImportLoupeViewport.clampedCenter(request.viewport.cy,viewportPixels:request.height,fullPixels:fullHeight)
        let actualX=(roi.x+roi.width/2)/Double(fullWidth)
        let actualY=(roi.y+roi.height/2)/Double(fullHeight)
        return abs(expectedX-actualX)<=1.5/Double(fullWidth)
            && abs(expectedY-actualY)<=1.5/Double(fullHeight)
    }
}

struct ImportLoupePane: View {
    @ObservedObject var model: ImportReviewModel

    var body: some View {
        VStack(spacing:6) {
            HStack {
                Picker("Zoom",selection:Binding(get:{model.loupeViewport.zoom},set:{model.setLoupeZoom($0)})) {
                    Text("Fit").tag(0.0)
                    Text("100%").tag(1.0)
                }.labelsHidden().accessibilityLabel("Import Loupe zoom").frame(width:140)
                if model.loupeViewport.zoom == 1 {
                    Text("Drag to inspect at 100%").font(.caption).foregroundStyle(.secondary)
                }
                Spacer(minLength:0)
            }
            ImportLoupeCanvas(model:model).frame(maxWidth:.infinity,maxHeight:.infinity)
        }
    }
}

private struct ImportLoupeCanvas: View {
    @ObservedObject var model: ImportReviewModel
    @Environment(\.displayScale) private var displayScale
    @State private var drag=CGSize.zero
    @State private var dragRequest: ImportLoupeRequest?
    @State private var dragStarted=false
    @State private var dragInvalid=false
    @State private var viewportResizeTask: Task<Void,Never>?

    var body: some View {
        GeometryReader { geometry in
            ZStack {
                Rectangle().fill(Color.black.opacity(0.3))
                if let frame=model.currentLoupeFrame {
                    if frame.request.viewport.zoom == 1 {
                        Image(nsImage:frame.image).resizable().interpolation(.none)
                            .frame(width:Double(frame.width)/Double(displayScale),height:Double(frame.height)/Double(displayScale))
                            .offset(drag)
                    } else {
                        Image(nsImage:frame.image).resizable().scaledToFit().padding(10)
                    }
                } else if model.loupeViewport.zoom == 0,let image=model.focused.flatMap({model.images[$0]}) {
                    Image(nsImage:image).resizable().scaledToFit().padding(10)
                } else if let error=model.detailError {
                    VStack(spacing:6) {
                        Image(systemName:"exclamationmark.triangle")
                        Text(error).font(.caption).lineLimit(3).multilineTextAlignment(.center)
                        Button("Retry") { model.refreshDetail() }
                    }.foregroundStyle(.white).padding(10)
                } else {
                    Image(systemName:"photo").foregroundStyle(.secondary)
                }
                if model.detailLoading { ProgressView().controlSize(.small) }
            }
            .frame(width:geometry.size.width,height:geometry.size.height)
            .clipped().contentShape(Rectangle())
            .gesture(DragGesture(minimumDistance:3).onChanged { value in
                if !dragStarted {
                    dragStarted=true
                    guard model.loupeViewport.zoom == 1,let frame=model.currentLoupeFrame else {
                        dragInvalid=true;return
                    }
                    dragRequest=frame.request
                }
                guard !dragInvalid,let request=dragRequest,
                      model.currentLoupeFrame?.request == request else {
                    dragInvalid=true;drag = .zero;return
                }
                drag=value.translation
            }.onEnded { value in
                let request=dragRequest
                let valid = !dragInvalid && dragStarted
                defer { drag = .zero;dragRequest=nil;dragStarted=false;dragInvalid=false }
                guard valid,let request else { return }
                model.finishLoupePan(value.translation,displayScale:Double(displayScale),from:request)
            })
            .onAppear { model.setLoupeViewportSize(geometry.size,displayScale:Double(displayScale)) }
            .onChange(of:geometry.size) { _,size in
                invalidateDrag()
                scheduleViewportSize(size,scale:Double(displayScale))
            }
            .onChange(of:displayScale) { _,scale in
                invalidateDrag()
                scheduleViewportSize(geometry.size,scale:Double(scale))
            }
            .onChange(of:model.focused) { _,_ in invalidateDrag() }
            .onChange(of:model.plan?.revision) { _,_ in invalidateDrag() }
            .onChange(of:model.loupeViewport.zoom) { _,_ in invalidateDrag() }
            .onChange(of:model.detailFrame?.request) { _,_ in invalidateDrag() }
            .onDisappear { viewportResizeTask?.cancel();viewportResizeTask=nil }
        }
        .accessibilityLabel(model.loupeViewport.zoom == 1 ? "Import Loupe at 100 percent":"Fitted Import Loupe preview")
    }

    private func invalidateDrag() {
        if dragStarted { dragInvalid=true }
        drag = .zero
    }

    private func scheduleViewportSize(_ size: CGSize,scale: Double) {
        viewportResizeTask?.cancel()
        model.invalidateLoupeViewportForResize()
        viewportResizeTask=Task { @MainActor in
            do { try await Task.sleep(nanoseconds:160_000_000) } catch { return }
            guard !Task.isCancelled else { return }
            model.setLoupeViewportSize(size,displayScale:scale)
        }
    }
}
