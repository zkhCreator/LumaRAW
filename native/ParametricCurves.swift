// Purpose: typed parametric-curve controls, display geometry and captured edits.
// Inputs: recipe amounts/splits and native actions. Outputs: partial patches and
// a graph of the portable curve's four smooth monotone warps. No image processing.
// Regions are independent of point/legacy curves; stale gestures never rebase.
import Foundation

struct ParametricCurveValues:Equatable {
    static let keys=["parametric_shadows","parametric_darks","parametric_lights","parametric_highlights"]
    static let labels=["Shadows","Darks","Lights","Highlights"]
    static let defaults=ParametricCurveValues()
    var amounts:[Double]=[0,0,0,0]
    var splits:[Double]=[0.25,0.5,0.75]
    init() {}
    init(recipe:[String:Any]) {
        amounts=Self.keys.map { (recipe[$0] as? NSNumber)?.doubleValue ?? 0 }
        splits=recipe["parametric_splits"] as? [Double] ?? [0.25,0.5,0.75]
    }
    var valid:Bool {
        guard amounts.count == 4,amounts.allSatisfy({$0.isFinite && (-100...100).contains($0)}),
              splits.count == 3,splits.allSatisfy({$0.isFinite && (0.01...0.99).contains($0)}) else {return false}
        let edges=[0]+splits+[1]
        return (0..<4).allSatisfy {edges[$0+1]-edges[$0]>=0.01-1e-12}
    }
    var patch:[String:Any] {
        var result:[String:Any]=["parametric_splits":splits]
        for i in 0..<4 {result[Self.keys[i]]=amounts[i]}
        return result
    }
    func region(_ x:Double) -> Int {splits.firstIndex(where:{x<$0}) ?? 3}
    func movedSplit(_ index:Int,to value:Double) -> Self {
        guard valid,splits.indices.contains(index),value.isFinite else {return self}
        var result=self
        let lower=index == 0 ? 0.01:splits[index-1]+0.01
        let upper=index == 2 ? 0.99:splits[index+1]-0.01
        result.splits[index]=min(upper,max(lower,value))
        return result
    }
    func adjusted(_ index:Int,to value:Double) -> Self {
        guard amounts.indices.contains(index),value.isFinite else {return self}
        var result=self;result.amounts[index]=min(100,max(-100,value));return result
    }
    func draggedRegion(_ index:Int,input:Double,target:Double) -> Self {
        guard valid,amounts.indices.contains(index),input.isFinite,(0...1).contains(input),target.isFinite else {return self}
        var lower = -100.0,upper=100.0
        let low=adjusted(index,to:lower).output(input),high=adjusted(index,to:upper).output(input)
        guard high-low>1e-12 else {return self}
        if target<=low {return adjusted(index,to:lower)}
        if target>=high {return adjusted(index,to:upper)}
        // The selected amount is monotone. Solve for the dragged output value
        // so graph movement follows the pointer, independently of region width.
        for _ in 0..<24 {
            let middle=(lower+upper)/2
            if adjusted(index,to:middle).output(input)<target {lower=middle} else {upper=middle}
        }
        return adjusted(index,to:(lower+upper)/2)
    }
    // Display-only counterpart to parametric.evaluate; fixtures check drift.
    func output(_ input:Double) -> Double {
        let edges=[0]+splits+[1]
        let centers=(0..<4).map {(edges[$0]+edges[$0+1])/2}
        var value=input
        for i in 0..<4 where amounts[i] != 0 {
            let lo=i == 0 ? 0:centers[i-1],hi=i == 3 ? 1:centers[i+1],center=centers[i]
            let amplitude=0.5*min(center-lo,hi-center)*amounts[i]/100
            let t=min(1,max(0,value<=center ? (value-lo)/(center-lo):(hi-value)/(hi-center)))
            value+=amplitude*t*t*(3-2*t)
        }
        return value
    }
    static func label(_ key:String) -> String? {
        if key == "parametric_splits" {return "Parametric Region Splits"}
        guard let index=keys.firstIndex(of:key) else {return nil}
        return "Parametric "+labels[index]
    }
}

struct ParametricCurveCapture {
    let photoID:Int
    let revision:Int
    let values:ParametricCurveValues
    func preview(_ draft:ParametricCurveValues) -> CurvePreviewDraft {
        CurvePreviewDraft(photoID:photoID,revision:revision,patch:draft.patch)
    }
}

extension Store {
    var parametricCurve:ParametricCurveValues {ParametricCurveValues(recipe:recipe)}
    func setParametricCurve(_ values:ParametricCurveValues) {
        guard canEditPointCurves else {return}
        guard values.valid else {error="Use amounts inside −100–100 and ordered region splits at least 1% apart";return}
        let current=parametricCurve
        for i in 0..<4 where values.amounts[i] != current.amounts[i] {set(ParametricCurveValues.keys[i],values.amounts[i])}
        if values.splits != current.splits {set("parametric_splits",values.splits)}
    }
    func captureParametricCurve() -> ParametricCurveCapture? {
        guard canEditPointCurves,!hasPendingEdits,let photo,parametricCurve.valid else {return nil}
        return ParametricCurveCapture(photoID:photo.id,revision:photo.revision,values:parametricCurve)
    }
    @discardableResult func commitParametricCurve(_ capture:ParametricCurveCapture,_ draft:ParametricCurveValues) -> Bool {
        guard canEditPointCurves,!hasPendingEdits,photo?.id == capture.photoID,
              photo?.revision == capture.revision,parametricCurve == capture.values else {
            error="The photo changed during this curve gesture. Review the current curve and try again.";return false
        }
        guard draft.valid else {error="Invalid parametric curve";return false}
        cancelMainPreview();setParametricCurve(draft)
        if !hasPendingEdits {render()}
        return true
    }
}
