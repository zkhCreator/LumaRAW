// Purpose: four paired comparison layouts with a shared physical-pixel viewport.
// Inputs: aligned engine images, captured ROI/context and native view/drag events.
// Outputs: fitted or 1:1 presentation and one synchronized pan request on release.
// No image processing, SQL or recipe changes. Resizing only requests bounded
// engine viewports; fitted layout/divider changes reuse already loaded images.
import AppKit
import SwiftUI

enum ComparisonLayout {
    static let gap:CGFloat = 12

    static func paneSize(_ available:CGSize,mode:BeforeAfterMode)->CGSize {
        let width=max(1,available.width),height=max(1,available.height)
        guard mode.isPaired && !mode.isSplit else {return CGSize(width:width,height:height)}
        return mode.vertical
            ? CGSize(width:width,height:max(1,(height-gap)/2))
            : CGSize(width:max(1,(width-gap)/2),height:height)
    }

    static func imageRect(pixels:CGSize,available:CGSize,detail:Bool,scale:Double)->CGRect {
        guard pixels.width>0,pixels.height>0,available.width>0,available.height>0,
              scale.isFinite,scale>0 else {return .zero}
        let ratio=detail ? 1/scale:min(available.width/pixels.width,available.height/pixels.height)
        let size=CGSize(width:pixels.width*ratio,height:pixels.height*ratio)
        return CGRect(x:(available.width-size.width)/2,y:(available.height-size.height)/2,
                      width:size.width,height:size.height)
    }

    static func boundary(rect:CGRect,position:Double,vertical:Bool)->CGFloat {
        let fraction=position.isFinite ? min(1,max(0,position)):0.5
        return vertical ? rect.minY+rect.height*fraction:rect.minX+rect.width*fraction
    }
}

struct BeforeAfterCanvas:View {
    @EnvironmentObject private var s:Store
    @Environment(\.displayScale) private var displayScale
    @State private var drag:CGSize = .zero
    @State private var captured:BeforeAfterFrame?
    @State private var capturedMode:BeforeAfterMode?

    private var mode:BeforeAfterMode {s.comparisonMode}

    var body:some View {
        VStack(spacing:8) {
            GeometryReader {geometry in
                comparison(size:geometry.size)
                    .onAppear {updatePane(geometry.size)}
                    .onChange(of:geometry.size) {_,size in updatePane(size)}
                    .onChange(of:mode) {_,_ in updatePane(geometry.size)}
                    .onChange(of:displayScale) {_,_ in updatePane(geometry.size)}
            }.padding(16)
            if mode.isSplit {
                HStack {
                    Text(mode.vertical ? "Before · Top":"Before · Left")
                    Slider(value:$s.splitPosition,in:0...1)
                        .accessibilityLabel(mode.vertical ? "Top and bottom comparison divider":"Left and right comparison divider")
                    Text(mode.vertical ? "After · Bottom":"After · Right")
                }.font(.caption).frame(maxWidth:420).padding(.horizontal,16).padding(.bottom,12)
            }
        }
        .onChange(of:s.currentBeforeContext) {_,_ in clearDrag()}
        .onChange(of:mode) {_,_ in clearDrag()}
        .onDisappear {clearDrag()}
        .accessibilityElement(children:.contain)
        .accessibilityLabel("Before and After, \(mode.title), \(s.detail ? "one to one":"fit")")
    }

    @ViewBuilder private func comparison(size:CGSize)->some View {
        if let before=s.before,let after=s.preview,s.beforePreviewContext==s.currentBeforeContext {
            let pane=ComparisonLayout.paneSize(size,mode:mode)
            Group {
                if mode.isSplit {
                    split(before:before,after:after,size:pane)
                } else if mode.vertical {
                    VStack(spacing:ComparisonLayout.gap) {
                        whole(before,title:"Before · \(s.beforeLabel)",size:pane)
                        whole(after,title:"After",size:pane)
                    }
                } else {
                    HStack(spacing:ComparisonLayout.gap) {
                        whole(before,title:"Before · \(s.beforeLabel)",size:pane)
                        whole(after,title:"After",size:pane)
                    }
                }
            }.frame(width:size.width,height:size.height).clipped()
                .contentShape(Rectangle())
                .gesture(DragGesture(minimumDistance:3).onChanged {value in
                    guard s.detail,!s.rendering,!s.hasPendingEdits else {clearDrag();return}
                    if captured==nil {
                        guard let frame=s.comparisonFrame,frame.context==s.currentBeforeContext else {return}
                        captured=frame;capturedMode=mode
                    }
                    guard captured?.context==s.currentBeforeContext,capturedMode==mode else {clearDrag();return}
                    drag=value.translation
                }.onEnded {value in
                    defer {clearDrag()}
                    guard let captured,let capturedMode else {return}
                    s.panComparison(value.translation,scale:displayScale,frame:captured,mode:capturedMode)
                })
        } else {
            VStack(spacing:8) {
                if s.rendering {ProgressView("Loading comparison…").tint(.white)}
                else {
                    Text("Comparison preview unavailable").foregroundStyle(.secondary)
                    Button("Retry"){s.render(debounce:false)}
                }
            }.frame(width:size.width,height:size.height)
        }
    }

    private func whole(_ image:NSImage,title:String,size:CGSize)->some View {
        let rect=imageRect(image,size:size)
        return ZStack(alignment:.topLeading) {
            Color(white:0.06)
            imageLayer(image,rect:rect)
            caption(title)
        }.frame(width:size.width,height:size.height).clipped()
            .accessibilityLabel(title)
    }

    private func split(before:NSImage,after:NSImage,size:CGSize)->some View {
        let rect=imageRect(after,size:size)
        let boundary=ComparisonLayout.boundary(rect:rect,position:s.splitPosition,vertical:mode.vertical)
        return ZStack(alignment:.topLeading) {
            Color(white:0.06)
            imageLayer(after,rect:rect)
            imageLayer(before,rect:rect)
                .frame(width:size.width,height:size.height,alignment:.topLeading)
                .mask(alignment:.topLeading) {
                    Rectangle().frame(width:mode.vertical ? size.width:max(0,boundary),
                                      height:mode.vertical ? max(0,boundary):size.height)
                }
            if mode.vertical {
                Rectangle().fill(.white.opacity(0.85)).frame(width:rect.width,height:1)
                    .position(x:rect.midX,y:boundary)
            } else {
                Rectangle().fill(.white.opacity(0.85)).frame(width:1,height:rect.height)
                    .position(x:boundary,y:rect.midY)
            }
            caption("Before · \(s.beforeLabel)")
        }.frame(width:size.width,height:size.height).clipped()
            .overlay(alignment:mode.vertical ? .bottomTrailing:.topTrailing) {caption("After")}
    }

    private func imageLayer(_ image:NSImage,rect:CGRect)->some View {
        Image(nsImage:image).resizable().frame(width:rect.width,height:rect.height)
            .position(x:rect.midX+drag.width,y:rect.midY+drag.height)
            .accessibilityHidden(true)
    }

    private func imageRect(_ image:NSImage,size:CGSize)->CGRect {
        let pixels=image.representations.first
        let dimensions=CGSize(width:pixels?.pixelsWide ?? 1,height:pixels?.pixelsHigh ?? 1)
        return ComparisonLayout.imageRect(pixels:dimensions,available:size,detail:s.detail,scale:displayScale)
    }

    private func caption(_ text:String)->some View {
        Text(text).font(.caption.weight(.medium)).lineLimit(1).padding(6)
            .background(.ultraThinMaterial,in:RoundedRectangle(cornerRadius:5)).padding(6)
    }

    private func updatePane(_ size:CGSize) {
        s.setComparisonPane(ComparisonLayout.paneSize(size,mode:mode),scale:displayScale)
    }

    private func clearDrag() {drag = .zero;captured=nil;capturedMode=nil}
}
