// Purpose: native one-click interaction for the engine's white-balance sampler.
// Inputs: revision-bound preview identity, active-After image geometry and one
// normalized pointer event. Outputs: one paired Temperature/Tint recipe patch.
// The engine owns decoding, geometry reversal, sampling and solving; this file
// performs no pixel work and never samples on hover.
// An uncertain save retains concurrent slider drafts for explicit recovery.
import SwiftUI

struct WhiteBalancePreviewIdentity:Equatable {
    let context:BeforePreviewContext
    let sourceFingerprint:String
    let fullWidth:Int,fullHeight:Int
    let roiX:Int,roiY:Int,roiWidth:Int,roiHeight:Int
}

struct WhiteBalanceDisplayGeometry:Equatable {
    let available:CGSize
    let imageRect:CGRect
    let displayScale:Double
    let role:String
    let after:Bool
}

struct WhiteBalanceEditRecovery:Identifiable {
    let id=UUID()
    let photoID:Int
    let revision:Int
    let message:String
}

enum WhiteBalancePointMapping {
    static func fullPoint(_ local:CGPoint,preview:WhiteBalancePreviewIdentity)->CGPoint? {
        guard local.x.isFinite,local.y.isFinite,(0...1).contains(local.x),(0...1).contains(local.y),
              preview.fullWidth>0,preview.fullHeight>0,preview.roiWidth>0,preview.roiHeight>0 else {return nil}
        let x=(Double(preview.roiX)+Double(local.x)*Double(preview.roiWidth))/Double(preview.fullWidth)
        let y=(Double(preview.roiY)+Double(local.y)*Double(preview.roiHeight))/Double(preview.fullHeight)
        guard x.isFinite,y.isFinite,(0...1).contains(x),(0...1).contains(y) else {return nil}
        return CGPoint(x:CGFloat(x),y:CGFloat(y))
    }

    static func localPoint(_ location:CGPoint,imageRect:CGRect)->CGPoint? {
        guard location.x.isFinite,location.y.isFinite,imageRect.width>0,imageRect.height>0,
              imageRect.contains(location) else {return nil}
        let point=CGPoint(x:(location.x-imageRect.minX)/imageRect.width,
                          y:(location.y-imageRect.minY)/imageRect.height)
        return (0...1).contains(point.x) && (0...1).contains(point.y) ? point:nil
    }
}

typealias WhiteBalanceCommandCall = @MainActor (String,[String:Any]) async throws -> [String:Any]

extension Store {
    var whiteBalanceTargetActive:Bool {workspace=="library" && develop && canvasTool=="white-balance"}

    var whiteBalancePreviewIdentity:WhiteBalancePreviewIdentity? {
        guard develop,workspace=="library",let photo,photo.id==selected,
              let context=currentBeforeContext,context.photoID==photo.id,context.revision==photo.revision,
              let frame=activeViewportFrame,frame.context==context,preview != nil,
              let fingerprint=previewSourceFingerprint,Self.isWhiteBalanceFingerprint(fingerprint) else {return nil}
        return WhiteBalancePreviewIdentity(context:context,sourceFingerprint:fingerprint,
            fullWidth:frame.fullWidth,fullHeight:frame.fullHeight,
            roiX:Int(frame.roi.minX),roiY:Int(frame.roi.minY),
            roiWidth:Int(frame.roi.width),roiHeight:Int(frame.roi.height))
    }

    var canStartWhiteBalanceSelector:Bool {
        workspace=="library" && develop && selected != nil && photo?.id==selected &&
        !loading && !browsing && !orientationBusy && !historyBusy && !snapshotBusy && !developPresetBusy &&
        whiteBalanceEditRecovery == nil &&
        !whiteBalanceSampling && !whiteBalanceArming
    }

    func whiteBalanceCanvasToolDidChange(_ tool:String) {
        if whiteBalanceArming {
            if tool != "view" {cancelWhiteBalanceSelector()}
        } else if tool != "white-balance" {
            cancelWhiteBalanceSelector()
        }
    }

    func whiteBalanceComparisonDidChange(_ mode:BeforeAfterMode) {
        if (canvasTool=="white-balance" || whiteBalanceSampling || whiteBalanceArming),mode != .after {
            cancelWhiteBalanceSelector()
        }
    }

    func whiteBalanceDisplayDidChange(_ display:WhiteBalanceDisplayGeometry?) {
        guard display != whiteBalanceDisplayGeometry else {return}
        let wasRegistered=whiteBalanceDisplayGeometry != nil
        whiteBalanceDisplayGeometry=display
        if wasRegistered && (whiteBalanceTargetActive || whiteBalanceSampling || whiteBalanceArming) {
            cancelWhiteBalanceSelector()
        }
    }

    private static func isWhiteBalanceFingerprint(_ value:String)->Bool {
        value.count==24 && value.utf8.allSatisfy { (48...57).contains($0) || (97...102).contains($0) }
    }

    func armWhiteBalanceSelector() async {
        guard canStartWhiteBalanceSelector,let photoID=selected else {return}
        cancelWhiteBalanceSelector()
        whiteBalanceInteractionGeneration+=1
        whiteBalanceArming=true
        let token=whiteBalanceInteractionGeneration
        guard !Task.isCancelled,await flushEdits(),!Task.isCancelled,
              token==whiteBalanceInteractionGeneration,
              selected==photoID,workspace=="library",develop else {
            if token==whiteBalanceInteractionGeneration {
                whiteBalanceArming=false
                whiteBalanceArmPreview=nil
            }
            return
        }

        cancelCurveTarget(restore:false);cancelMixerTarget(restore:false)
        curveTargetFrame=nil;mixerTargetFrame=nil
        clearColorReadout()
        if canvasTool != "view" {canvasTool="view"}
        if comparisonMode != .after {comparisonMode = .after}
        if activeViewportFrame?.context != currentBeforeContext {render(debounce:false)}

        // A commit may have started a matching render. Wait for that bounded
        // preview instead of capturing the pre-edit frame or forcing a retry.
        var ready=false
        for _ in 0..<500 {
            guard !Task.isCancelled,token==whiteBalanceInteractionGeneration,
                  selected==photoID,workspace=="library",develop else {
                if token==whiteBalanceInteractionGeneration {
                    whiteBalanceArming=false
                    whiteBalanceArmPreview=nil
                }
                return
            }
            if !loading && !rendering,whiteBalancePreviewIdentity?.context.photoID==photoID {ready=true;break}
            try? await Task.sleep(nanoseconds:20_000_000)
        }
        guard !Task.isCancelled,ready,let identity=whiteBalancePreviewIdentity,identity.context.photoID==photoID,
              token==whiteBalanceInteractionGeneration else {
            if token==whiteBalanceInteractionGeneration {
                whiteBalanceArming=false
                whiteBalanceArmPreview=nil
                if !Task.isCancelled {
                    error="The current After preview is not ready for white-balance sampling. Wait for it to finish and try again."
                }
            }
            return
        }
        whiteBalanceArming=false
        canvasTool="white-balance"
        whiteBalanceArmPreview=identity
        whiteBalanceTargetPoint=nil
        error=nil
    }

    func cancelWhiteBalanceSelector() {
        guard whiteBalanceTargetActive || whiteBalanceSampling || whiteBalanceArming || whiteBalanceArmPreview != nil else {return}
        whiteBalanceInteractionGeneration+=1
        let token=whiteBalanceInteractionGeneration
        whiteBalanceArmPreview=nil;whiteBalanceTargetPoint=nil;whiteBalanceSampling=false;whiteBalanceArming=false
        whiteBalanceDisplayCapture=nil;whiteBalanceDisplayGeometry=nil
        if canvasTool=="white-balance" {canvasTool="view"}
        Task { _=try? await Backend.call("cancel_preview",["client_id":whiteBalanceClient,"generation":token]) }
    }

    func sampleWhiteBalance(localPoint:CGPoint,previewIdentity:WhiteBalancePreviewIdentity,
                            display:WhiteBalanceDisplayGeometry,
                            call:WhiteBalanceCommandCall?=nil) async ->Bool {
        guard whiteBalanceTargetActive,comparisonMode == .after,!whiteBalanceSampling,
              display.role=="active",display.after,
              canStartWhiteBalanceSelector,let fullPoint=WhiteBalancePointMapping.fullPoint(localPoint,preview:previewIdentity),
              whiteBalanceDisplayGeometry==display,
              whiteBalanceArmPreview==previewIdentity,whiteBalancePreviewIdentity==previewIdentity,
              let p=photo,p.id==previewIdentity.context.photoID,p.revision==previewIdentity.context.revision,
              previewIdentity.context.orientation==p.orientation else {return false}

        let token=whiteBalanceInteractionGeneration
        let capturedPreview=previewIdentity,capturedDisplay=display,capturedLocalPoint=localPoint
        whiteBalanceTargetPoint=localPoint;whiteBalanceDisplayCapture=display
        whiteBalanceSampling=true;clearColorReadout();error=nil
        let send:WhiteBalanceCommandCall=call ?? {method,params in try await Backend.call(method,params)}
        var applying=false
        do {
            let receipt=try await send("sample_white_balance",[
                "photo_id":p.id,"expected_revision":p.revision,
                "expected_source_fingerprint":previewIdentity.sourceFingerprint,
                "point":["x":Double(fullPoint.x),"y":Double(fullPoint.y)],
                "client_id":whiteBalanceClient,"generation":token
            ])
            guard isCurrentWhiteBalanceRequest(token:token,preview:capturedPreview,display:capturedDisplay,
                                               localPoint:capturedLocalPoint) else {return false}
            guard receipt["photo_id"] as? Int==p.id,receipt["revision"] as? Int==p.revision,
                  receipt["source_fingerprint"] as? String==capturedPreview.sourceFingerprint,
                  let temperature=(receipt["temperature"] as? NSNumber)?.doubleValue,
                  let tint=(receipt["tint"] as? NSNumber)?.doubleValue,
                  temperature.isFinite,tint.isFinite,(-100...100).contains(temperature),(-100...100).contains(tint) else {
                error="The white-balance sample was invalid or no longer matches the displayed photo. Try another point."
                cancelWhiteBalanceSelector()
                return false
            }

            // The sample is one-shot. Retire its cancellable worker identity
            // before applying the paired revision-bound edit.
            cancelWhiteBalanceSelector()
            editing=true;applying=true
            let row=try await send("edit_photo",[
                "photo_id":p.id,"expected_revision":p.revision,
                "expected_source_fingerprint":capturedPreview.sourceFingerprint,
                "patch":["temperature":temperature,"tint":tint]
            ])
            editing=false
            guard let updated=Photo(row),updated.id==p.id,updated.revision>=p.revision,
                  (updated.recipe["temperature"] as? NSNumber)?.doubleValue==temperature,
                  (updated.recipe["tint"] as? NSNumber)?.doubleValue==tint else {
                recordWhiteBalanceEditFailure(EngineFailure(message:"The service returned an invalid white-balance update; its outcome is unknown."),photoID:p.id)
                return false
            }
            if !(await adoptWhiteBalanceEdit(updated,expectedRevision:p.revision)),selected==p.id {
                error="White balance was saved to the captured photo, but the visible revision changed. Reload before continuing."
            }
            return true
        } catch {
            if applying {
                editing=false
                recordWhiteBalanceEditFailure(error,photoID:p.id)
            } else {
                guard isCurrentWhiteBalanceRequest(token:token,preview:capturedPreview,display:capturedDisplay,
                                                   localPoint:capturedLocalPoint) else {return false}
                self.error=error.localizedDescription
                cancelWhiteBalanceSelector()
            }
            return false
        }
    }

    private func isCurrentWhiteBalanceRequest(token:Int,preview:WhiteBalancePreviewIdentity,
                                              display:WhiteBalanceDisplayGeometry,localPoint:CGPoint)->Bool {
        whiteBalanceTargetActive && whiteBalanceSampling && token==whiteBalanceInteractionGeneration &&
        comparisonMode == .after &&
        whiteBalanceArmPreview==preview && whiteBalancePreviewIdentity==preview &&
        whiteBalanceDisplayCapture==display && whiteBalanceDisplayGeometry==display &&
        whiteBalanceTargetPoint==localPoint && display.role=="active" && display.after &&
        selected==preview.context.photoID && photo?.revision==preview.context.revision
    }
}

struct WhiteBalanceTargetOverlay:View {
    @EnvironmentObject private var s:Store
    @Environment(\.displayScale) private var displayScale
    let imageSize:CGSize
    let available:CGSize
    let fitted:Bool
    let role:String
    let after:Bool

    private var imageRect:CGRect {CurveTargetOverlay.imageRect(image:imageSize,available:available,fitted:fitted)}
    private var preview:WhiteBalancePreviewIdentity? {s.whiteBalancePreviewIdentity}
    private var display:WhiteBalanceDisplayGeometry {
        WhiteBalanceDisplayGeometry(available:available,imageRect:imageRect,displayScale:displayScale,role:role,after:after)
    }

    var body:some View {
        ZStack {
            Canvas {context,_ in
                if let point=s.whiteBalanceTargetPoint {
                    let center=CGPoint(x:imageRect.minX+point.x*imageRect.width,y:imageRect.minY+point.y*imageRect.height)
                    let ring=Path(ellipseIn:CGRect(x:center.x-10,y:center.y-10,width:20,height:20))
                    context.stroke(ring,with:.color(.black),lineWidth:4)
                    context.stroke(ring,with:.color(.white),lineWidth:2)
                    var cross=Path();cross.move(to:CGPoint(x:center.x-17,y:center.y));cross.addLine(to:CGPoint(x:center.x+17,y:center.y))
                    cross.move(to:CGPoint(x:center.x,y:center.y-17));cross.addLine(to:CGPoint(x:center.x,y:center.y+17))
                    context.stroke(cross,with:.color(.black),lineWidth:4)
                    context.stroke(cross,with:.color(.white),lineWidth:1)
                }
            }.allowsHitTesting(false)
            Color.clear.contentShape(Rectangle())
                .gesture(SpatialTapGesture().onEnded {value in
                    guard let preview,let local=WhiteBalancePointMapping.localPoint(value.location,imageRect:imageRect) else {return}
                    Task { _=await s.sampleWhiteBalance(localPoint:local,previewIdentity:preview,display:display) }
                })
            VStack {
                Spacer()
                Label(s.whiteBalanceSampling ? "Sampling neutral point…":"Click a neutral area in the active After image",
                      systemImage:s.whiteBalanceSampling ? "hourglass":"eyedropper")
                    .font(.caption).padding(8).background(.ultraThinMaterial,in:Capsule()).padding(10)
            }.allowsHitTesting(false)
        }
        .onAppear {s.whiteBalanceDisplayDidChange(display)}
        .onChange(of:display) {_,value in s.whiteBalanceDisplayDidChange(value)}
        .onDisappear {s.whiteBalanceDisplayDidChange(nil)}
        .onChange(of:available) {_,_ in s.cancelWhiteBalanceSelector()}
        .onChange(of:displayScale) {_,_ in s.cancelWhiteBalanceSelector()}
        .onChange(of:imageSize) {_,_ in s.cancelWhiteBalanceSelector()}
        .onChange(of:preview) {_,_ in if s.whiteBalanceTargetActive {s.cancelWhiteBalanceSelector()} }
        .accessibilityElement()
        .accessibilityLabel("White Balance Selector")
        .accessibilityValue(s.whiteBalanceSampling ? "Sampling neutral point":"Click a neutral area in the active After image")
        .accessibilityHint("Press Escape to cancel. The Reference and Before images are not sampled.")
    }
}
