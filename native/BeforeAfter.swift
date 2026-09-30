// Purpose: native comparison controls and context-safe Before image reuse.
// Inputs: current photo/view state and explicit copy/swap actions. Outputs:
// ordinary service mutations and on-demand comparison previews. Stored recipes,
// geometry alignment, history and cache keys belong to the portable engine.
import SwiftUI

struct BeforePreviewContext:Equatable {
    let photoID:Int,revision:Int,orientation:Int
    let detail:Bool,cx:Double,cy:Double,gamut:Bool,proofSHA:String
}

extension Store {
    var currentBeforeContext:BeforePreviewContext? {
        guard let p=photo,p.id==selected else {return nil}
        return BeforePreviewContext(photoID:p.id,revision:p.revision,orientation:p.orientation,
                                    detail:detail,cx:detail ? cx:0.5,cy:detail ? cy:0.5,
                                    gamut:gamut,proofSHA:proof["sha256"] as? String ?? "")
    }
    var needsBeforePreview:Bool {develop && (compare || splitCompare)}
    func setComparisonMode(_ mode:String) {
        guard ["after","before","split"].contains(mode),photo != nil,!loading,!browsing else {return}
        let hadDraft=curveTargetGesture != nil || mixerTargetGesture != nil
        cancelCurveTarget(restore:false);cancelMixerTarget(restore:false);canvasTool="view"
        compare=mode=="before";splitCompare=mode=="split"
        if splitCompare {detail=false}
        if hadDraft || needsBeforePreview && (before==nil || beforePreviewContext != currentBeforeContext || rendering) {
            render(debounce:false)
        }
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
            Button("After Only"){s.setComparisonMode("after")}
            Button("Before Only"){s.setComparisonMode("before")}
            Button("Left/Right Split"){s.setComparisonMode("split")}
            Divider()
            BeforeAfterActions().disabled(!s.historyReady)
        } label:{Label("Before / After",systemImage:"rectangle.lefthalf.inset.filled")}
        .disabled(s.photo==nil || s.loading || s.browsing)
        .help("Before / After · Backslash toggles Before")
    }
}
