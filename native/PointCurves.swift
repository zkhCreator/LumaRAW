// Purpose: point-curve presentation geometry and revision-bound native edits.
// Inputs: normalized control points, control actions and captured photo state.
// Outputs: plot geometry and ordinary partial recipe patches. The spline helper
// draws control paths only; image pixels are processed by the portable engine.
// Legacy luminance curves retain their original monotone, fixed-endpoint rules.
import Foundation

enum PointCurveFields {
    static let keys=["curve_rgb_points","curve_red_points","curve_green_points","curve_blue_points"]
    static let legacy="curve_points"
    static let identity=[[0.0,0.0],[1.0,1.0]]
    static let gap=1.0/65535
    static func label(_ key: String) -> String {
        switch key {
        case "curve_rgb_points":return "RGB"
        case "curve_red_points":return "Red"
        case "curve_green_points":return "Green"
        case "curve_blue_points":return "Blue"
        default:return "Legacy Luminance"
        }
    }
    static func valid(_ points: [[Double]],legacy: Bool=false) -> Bool {
        guard (2...16).contains(points.count),points.allSatisfy({ $0.count == 2 && $0.allSatisfy { $0.isFinite && (0...1).contains($0) } }) else { return false }
        for i in 1..<points.count {
            if legacy {
                if points[i][0] <= points[i-1][0] || points[i][1] < points[i-1][1] { return false }
            } else if points[i][0]-points[i-1][0] < gap { return false }
        }
        return !legacy || points.first![0] == 0 && points.last![0] == 1
    }
    static func moved(_ points: [[Double]],index: Int,x: Double,y: Double,legacy: Bool=false) -> [[Double]] {
        guard points.indices.contains(index),x.isFinite,y.isFinite else { return points }
        var result=points
        let margin=gap+1e-12
        let lower=index == 0 ? 0:points[index-1][0]+margin
        let upper=index == points.count-1 ? 1:points[index+1][0]-margin
        if lower <= upper { result[index][0]=min(upper,max(lower,x)) }
        result[index][1]=min(1,max(0,y))
        if legacy {
            if index == 0 { result[index][0]=0 }
            if index == points.count-1 { result[index][0]=1 }
            let lowY=index == 0 ? 0:points[index-1][1]
            let highY=index == points.count-1 ? 1:points[index+1][1]
            result[index][1]=min(highY,max(lowY,y))
        }
        return valid(result,legacy:legacy) ? result:points
    }
    static func inserted(_ points: [[Double]],x: Double,y: Double,legacy: Bool=false) -> (points:[[Double]],index:Int)? {
        guard points.count<16,x.isFinite,y.isFinite,x>points[0][0],x<points.last![0] else { return nil }
        let index=points.firstIndex { $0[0]>x }!
        guard x-points[index-1][0]>=gap,points[index][0]-x>=gap else { return nil }
        var result=points
        let value=legacy ? min(points[index][1],max(points[index-1][1],y)):min(1,max(0,y))
        result.insert([x,value],at:index)
        return valid(result,legacy:legacy) ? (result,index):nil
    }
    static func removed(_ points: [[Double]],index: Int) -> [[Double]] {
        guard points.count>2,index>0,index<points.count-1 else { return points }
        var result=points;result.remove(at:index);return result
    }
}

enum PointCurvePlot {
    // PCHIP tangents for a displayed cubic Bezier path. Cross-language fixtures
    // compare this geometry to the engine's evaluated curve; no RGB image input.
    static func slopes(_ points: [[Double]]) -> [Double] {
        let n=points.count
        let h=(0..<n-1).map { points[$0+1][0]-points[$0][0] }
        let d=(0..<n-1).map { (points[$0+1][1]-points[$0][1])/h[$0] }
        if n == 2 { return [d[0],d[0]] }
        func edge(_ h0:Double,_ h1:Double,_ d0:Double,_ d1:Double) -> Double {
            let value=((2*h0+h1)*d0-h0*d1)/(h0+h1)
            if value*d0 <= 0 { return 0 }
            if d0*d1 <= 0,abs(value)>abs(3*d0) { return 3*d0 }
            return value
        }
        var m=Array(repeating:0.0,count:n)
        m[0]=edge(h[0],h[1],d[0],d[1])
        m[n-1]=edge(h[n-2],h[n-3],d[n-2],d[n-3])
        for i in 1..<n-1 where d[i-1]*d[i]>0 {
            let w1=2*h[i]+h[i-1],w2=h[i]+2*h[i-1]
            m[i]=(w1+w2)/(w1/d[i-1]+w2/d[i])
        }
        return m
    }
    static func value(_ x: Double,points: [[Double]],legacy: Bool=false) -> Double {
        if x<=points[0][0] { return points[0][1] }
        if x>=points.last![0] { return points.last![1] }
        let i=points.firstIndex { $0[0]>=x }!-1
        let width=points[i+1][0]-points[i][0],t=(x-points[i][0])/width
        if legacy { return points[i][1]+t*(points[i+1][1]-points[i][1]) }
        let m=slopes(points),a=points[i][1],b=points[i+1][1]
        let value=(2*t*t*t-3*t*t+1)*a+(t*t*t-2*t*t+t)*width*m[i]+(-2*t*t*t+3*t*t)*b+(t*t*t-t*t)*width*m[i+1]
        return min(1,max(0,value))
    }
}

struct PointCurveCapture {
    let photoID: Int
    let revision: Int
    let key: String
    let points: [[Double]]
}

extension Store {
    var canEditPointCurves: Bool {
        gradingInteraction.edit==nil && !loading && !browsing && !orientationBusy && !developPresetBusy && !painterBusy && photo != nil && photo?.id == selected
    }
    func pointCurve(_ key: String) -> [[Double]] {
        recipe[key] as? [[Double]] ?? PointCurveFields.identity
    }
    func setPointCurve(_ key: String,_ points: [[Double]]) {
        guard canEditPointCurves else { return }
        guard (PointCurveFields.keys+[PointCurveFields.legacy]).contains(key),PointCurveFields.valid(points,legacy:key == PointCurveFields.legacy) else {
            error="Use 2–16 ordered curve points with input and output inside 0–255";return
        }
        if points != pointCurve(key) { set(key,points) }
    }
    func capturePointCurve(_ key: String) -> PointCurveCapture? {
        guard canEditPointCurves,!hasPendingEdits,let photo,
              (PointCurveFields.keys+[PointCurveFields.legacy]).contains(key) else { return nil }
        return PointCurveCapture(photoID:photo.id,revision:photo.revision,key:key,points:pointCurve(key))
    }
    @discardableResult func commitPointCurve(_ captured: PointCurveCapture,_ points: [[Double]]) -> Bool {
        guard canEditPointCurves,!hasPendingEdits,photo?.id == captured.photoID,
              photo?.revision == captured.revision,pointCurve(captured.key) == captured.points else {
            error="The photo changed during this curve gesture. Review the current curve and try again.";return false
        }
        guard PointCurveFields.valid(points,legacy:captured.key == PointCurveFields.legacy) else { return false }
        cancelMainPreview()
        setPointCurve(captured.key,points)
        if !hasPendingEdits {render()}
        return true
    }
    func resetRGBPointCurves() {
        for key in PointCurveFields.keys { setPointCurve(key,PointCurveFields.identity) }
    }
    func loadPointCurvePresets() async {
        do {
            let schema=try await Backend.call("recipe_schema")
            pointCurvePresets=schema["point_curve_presets"] as? [String:[[Double]]] ?? [:]
        } catch { self.error=error.localizedDescription }
    }
}
