// Purpose: native comparison controls and context-safe Before image reuse.
// Inputs: photo/view state, captured pan/viewport events and copy/swap actions.
// Outputs: bounded on-demand comparison previews and ordinary service mutations.
// Paired layouts share zoom/pan; stored recipes, pixel geometry alignment, history
// and cache keys belong to the portable engine. No native image processing.
import SwiftUI

enum BeforeAfterMode:String,CaseIterable {
    case after,before,leftRight,topBottom,leftRightSplit,topBottomSplit
    var isPaired:Bool {self != .after && self != .before}
    var isSplit:Bool {self == .leftRightSplit || self == .topBottomSplit}
    var vertical:Bool {self == .topBottom || self == .topBottomSplit}
    var title:String {
        switch self {
        case .after:return "After Only"
        case .before:return "Before Only"
        case .leftRight:return "Left/Right"
        case .topBottom:return "Top/Bottom"
        case .leftRightSplit:return "Left/Right Split"
        case .topBottomSplit:return "Top/Bottom Split"
        }
    }
}

struct BeforePreviewContext:Equatable {
    let photoID:Int,revision:Int,orientation:Int
    let detail:Bool,cx:Double,cy:Double,gamut:Bool,proofSHA:String
    let width:Int,height:Int
}

struct BeforeAfterFrame {
    let context:BeforePreviewContext
    let fullWidth:Int,fullHeight:Int
    let roi:CGRect
    init?(_ result:[String:Any],context:BeforePreviewContext) {
        guard let width=result["full_width"] as? Int,let height=result["full_height"] as? Int,
              width>0,height>0 else {return nil}
        // Fit receipts have no ROI; their complete proxy is the displayed frame.
        // Detail receipts must provide the real, clamped full-resolution ROI.
        let region=context.detail ? result["roi"] as? [Int]:[0,0,width,height]
        guard let rect=region,rect.count==4,
              rect[0]>=0,rect[1]>=0,rect[2]>0,rect[3]>0,
              rect[0]+rect[2]<=width,rect[1]+rect[3]<=height else {return nil}
        self.context=context;fullWidth=width;fullHeight=height
        roi=CGRect(x:rect[0],y:rect[1],width:rect[2],height:rect[3])
    }
    func panned(_ translation:CGSize,scale:Double)->CGPoint? {
        guard translation.width.isFinite,translation.height.isFinite,scale.isFinite,scale>0 else {return nil}
        // Start from the rendered ROI, not an out-of-bounds requested center.
        let x=min(Double(fullWidth)-roi.width/2,max(roi.width/2,roi.midX-translation.width*scale))
        let y=min(Double(fullHeight)-roi.height/2,max(roi.height/2,roi.midY-translation.height*scale))
        return CGPoint(x:x/Double(fullWidth),y:y/Double(fullHeight))
    }
}

extension Store {
    var detailPixelWidth:Int {isReferenceView ? referencePixelWidth:(comparisonMode.isPaired ? comparisonPixelWidth:1600)}
    var detailPixelHeight:Int {isReferenceView ? referencePixelHeight:(comparisonMode.isPaired ? comparisonPixelHeight:1100)}
    var currentBeforeContext:BeforePreviewContext? {
        guard let p=photo,p.id==selected else {return nil}
        return BeforePreviewContext(photoID:p.id,revision:p.revision,orientation:p.orientation,
                                    detail:detail,cx:detail ? cx:0.5,cy:detail ? cy:0.5,
                                    gamut:gamut,proofSHA:proof["sha256"] as? String ?? "",
                                    width:detail ? detailPixelWidth:0,height:detail ? detailPixelHeight:0)
    }
    var needsBeforePreview:Bool {develop && (compare || splitCompare)}
    func setComparisonMode(_ mode:String) {
        guard let value=BeforeAfterMode(rawValue:mode == "split" ? "leftRightSplit":mode) else {return}
        setComparisonMode(value)
    }
    func setComparisonMode(_ mode:BeforeAfterMode) {
        clearColorReadout()
        whiteBalanceComparisonDidChange(mode)
        guard photo != nil,!loading,!browsing else {return}
        let hadDraft=curveTargetGesture != nil || mixerTargetGesture != nil
        let oldDetailSize=(detailPixelWidth,detailPixelHeight)
        if mode.isPaired {endReferenceView()}
        cancelCurveTarget(restore:false);cancelMixerTarget(restore:false);canvasTool="view"
        comparisonMode=mode
        if hadDraft || detail && oldDetailSize != (detailPixelWidth,detailPixelHeight) ||
            needsBeforePreview && (before==nil || beforePreviewContext != currentBeforeContext || rendering) {
            render(debounce:false)
        }
    }
    func setComparisonPane(_ size:CGSize,scale:Double) {
        guard size.width.isFinite,size.height.isFinite,scale.isFinite,scale>0 else {return}
        let width=Int(min(2048,max(1,(size.width*scale).rounded())))
        let height=Int(min(1536,max(1,(size.height*scale).rounded())))
        guard width != comparisonPixelWidth || height != comparisonPixelHeight else {return}
        comparisonPixelWidth=width;comparisonPixelHeight=height
        if comparisonMode.isPaired && detail {render()}
    }
    func panComparison(_ translation:CGSize,scale:Double,frame:BeforeAfterFrame,mode:BeforeAfterMode) {
        guard develop,detail,comparisonMode==mode,mode.isPaired,
              !loading,!browsing,!hasPendingEdits,!rendering,
              frame.context==currentBeforeContext,
              let point=frame.panned(translation,scale:scale) else {return}
        cx=point.x;cy=point.y;render(debounce:false)
    }
    func comparisonShortcut(_ modifiers:EventModifiers)->Bool {
        guard develop,photo != nil else {return false}
        let mode:BeforeAfterMode
        switch modifiers {
        case []:mode = .leftRight
        case .option:mode = .topBottom
        case .shift:mode = comparisonMode.vertical ? .topBottomSplit:.leftRightSplit
        default:return false
        }
        setComparisonMode(comparisonMode==mode ? .after:mode)
        return true
    }
    func beforeAfter(_ action:String,step:Int?=nil,captured:DevelopHistoryPage?=nil) {
        moveDevelopHistory("before_after",step:step,action:action,captured:captured)
    }
}

struct BeforeAfterActions:View {
    @EnvironmentObject var s:Store
    var body:some View {
        Button("Copy After Settings to Before"){s.beforeAfter("after_to_before")}
        Button("Copy Before Settings to After"){s.beforeAfter("before_to_after")}
        Button("Swap Before and After Settings"){s.beforeAfter("swap")}
    }
}

struct BeforeAfterMenu:View {
    @EnvironmentObject var s:Store
    var body:some View {
        Menu {
            ForEach(BeforeAfterMode.allCases,id:\.self) {mode in
                Button {s.setComparisonMode(mode)} label:{
                    if s.comparisonMode==mode {Label(mode.title,systemImage:"checkmark")} else {Text(mode.title)}
                }
            }
            Divider()
            BeforeAfterActions().disabled(!s.historyReady)
        } label:{Label("Before / After",systemImage:"rectangle.lefthalf.inset.filled")}
        .disabled(s.photo==nil || s.loading || s.browsing)
        .help("Before / After · Backslash toggles Before")
    }
}
