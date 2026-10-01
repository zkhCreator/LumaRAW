// Purpose: accessible recipe controls and entry points for catalog metadata review.
// Inputs: the active photo and bounded recipe values. Outputs: partial recipe
// patches and explicit metadata/edit/export-preview workflows through Store.
// Temperature is relative to camera white balance; lens controls are manual.
// Crop bounds and mask coordinates follow the independent displayed orientation.
import SwiftUI

struct InspectorView:View {
    @EnvironmentObject var s:Store
    @State private var light=true
    @State private var color=true
    @State private var reset=false
    @State private var exportMetadataPhoto: Int?
    @State private var keywordPhoto: Photo?
    var body:some View {
        ScrollView {
            VStack(alignment:.leading,spacing:18){
                HStack{Text("Adjustments").font(.title3.weight(.semibold));Spacer();Menu{Button("Snapshots…"){s.showVersions=true};Button("Export Recipe Bundle…"){s.recipeFile(save:true)};Button("Import Recipe Bundle…"){s.recipeFile(save:false)};Button("Full Recipe Editor…"){s.showRecipe=true};Divider();Button("Reset All Adjustments",role:.destructive){reset=true}}label:{Image(systemName:"ellipsis.circle")}.menuStyle(.borderlessButton).frame(width:25)}
                HistogramView(data:s.histogram)
                    .contextMenu {ColorReadoutModeMenu(state:s.colorReadouts)}
                if s.develop {ColorReadoutView(state:s.colorReadouts)}
                if let p=s.photo {
                    VStack(alignment:.leading,spacing:6) {
                        if p.isVirtual { Label(p.copyName.isEmpty ? "Virtual Copy":p.copyName,systemImage:"doc.on.doc") }
                        Menu("Photo Variants") { VirtualCopyActions(photo:p) }
                        if !p.title.isEmpty { Text(p.title).font(.headline) }
                        if !p.keywords.isEmpty { Text(p.keywords.joined(separator:", ")).font(.caption).foregroundStyle(.secondary) }
                        if p.keywordsDeferred {
                            Button("Review \(p.keywordCount) Keywords…") { keywordPhoto=p }
                        }
                        Button("Edit Metadata…") { Task { await s.prepareMetadataEditor() } }
                        Button("Metadata Presets…") { s.showMetadataPresets=true }
                        Button("Will Export…") { exportMetadataPhoto=p.id }
                        Button("Go to Folder in Library") { Task { await s.showPhotoFolder(p) } }
                    }
                    HStack(spacing:7){ForEach(1..<6){value in Button{s.rate(p.rating==value ? 0:value)}label:{Image(systemName:p.rating>=value ? "star.fill":"star").foregroundStyle(p.rating>=value ? Color.yellow:Color.secondary)}.accessibilityLabel("Rate \(value) \(value == 1 ? "star" : "stars")")};Spacer();Button{s.flag(p.flag==1 ? 0:1)}label:{Image(systemName:p.flag==1 ? "flag.fill":"flag")}}
                        .buttonStyle(.plain).help("1–5 to rate, P to flag as a pick")
                }
                Button { s.showDevelopPresets=true } label: { Label("Develop Presets…",systemImage:"camera.filters") }.frame(maxWidth:.infinity)
                DevelopHistoryPanel()
                SnapshotsPanel()
                Divider()
                DisclosureGroup("Light",isExpanded:$light){VStack(spacing:12){
                    edit("Exposure","exposure",-5...5,0.05,"EV")
                    edit("Contrast","contrast",-100...100)
                    edit("Highlights","highlights",-100...100)
                    edit("Shadows","shadows",-100...100)
                    edit("Whites","whites",-100...100)
                    edit("Blacks","blacks",-100...100)
                    Toggle("RAW Highlight Recovery",isOn:bool("highlight_recovery")).font(.callout)
                }.padding(.top,12)}
                Divider()
                DisclosureGroup("Color",isExpanded:$color){VStack(spacing:12){
                    Text("Adjust relative to as-shot white balance").font(.caption).foregroundStyle(.secondary).frame(maxWidth:.infinity,alignment:.leading)
                    edit("Temperature","temperature",-100...100)
                    edit("Tint","tint",-100...100)
                    edit("Vibrance","vibrance",-100...100)
                    edit("Saturation","saturation",-100...100)
                    Picker("Treatment",selection:bool("monochrome")) { Text("Color").tag(false);Text("Black & White").tag(true) }
                }.padding(.top,12)}
                section("Tone Curve"){ToneCurveControls()}
                section((s.recipe["monochrome"] as? Bool ?? false) ? "Black & White Mix":"Color Mixer") { ColorMixerControls() }
                section("Detail"){
                    edit("Luminance Noise Reduction","luma_noise",0...100)
                    edit("Color Noise Reduction","chroma_noise",0...100)
                    edit("Sharpening","sharpen",0...150)
                    edit("Sharpening Radius","sharpen_radius",0.3...3,0.1,"px")
                    edit("Detail Protection","detail_protect",0...100)
                    edit("Defringe","defringe",0...100)
                    Toggle("Full-Resolution 1:1 View",isOn:$s.detail).onChange(of:s.detail){_,_ in s.render()}
                    if s.detail {Slider(value:$s.cx,in:0...1,onEditingChanged:{if !$0{s.render()}}){Text("Horizontal Viewport Position")};Slider(value:$s.cy,in:0...1,onEditingChanged:{if !$0{s.render()}}){Text("Vertical Viewport Position")}}
                }
                section("Composition"){
                    HStack{Button{s.orientSelection("rotate_left")}label:{Label("Rotate Left",systemImage:"rotate.left")};Button{s.orientSelection("rotate_right")}label:{Label("Rotate Right",systemImage:"rotate.right")}}.disabled(!s.canOrientPhotos)
                    Picker("Ratio",selection:Binding(get:{PhotoOrientation.ratio(s.recipe["crop"] as? String ?? "original",orientation:s.photo?.orientation ?? 0)},set:{s.set("crop",PhotoOrientation.ratio($0,orientation:s.photo?.orientation ?? 0))})){Text("Original Ratio").tag("original");ForEach(["1:1","3:2","2:3","4:5","5:4","16:9","9:16"],id:\.self){Text($0).tag($0)}}
                    CropControls()
                    edit("Straighten","straighten",-20...20,0.1,"°")
                    edit("Vertical Perspective","perspective_v",-50...50)
                    edit("Horizontal Perspective","perspective_h",-50...50)
                    edit("Geometry Scale","geometry_scale",1...2,0.01,"×")
                }
                section("Manual Lens Corrections"){
                    edit("Distortion","distortion",-100...100)
                    edit("Vignette Correction","vignette",-100...100)
                    edit("Red Chromatic Aberration","ca_red",-50...50)
                    edit("Blue Chromatic Aberration","ca_blue",-50...50)
                    Text("Manual coefficients; no automatic lens database").font(.caption).foregroundStyle(.secondary)
                }
                section("Local Masks"){MaskControls()}
                section("Color Profiles and LUT"){
                    Button("Load Camera Profile…"){s.asset("profile")}
                    Button("Fit Color Chart…"){s.showCalibration=true}
                    Text((s.recipe["camera_profile"] as? [String:Any])?["name"] as? String ?? "No camera profile applied").font(.caption).foregroundStyle(.secondary)
                    Button("Load .cube LUT…"){s.asset("lut")}
                    edit("LUT Amount","lut_amount",0...100)
                    HStack{Button("Clear LUT"){s.set("lut",[:])};Button("Clear Camera Profile"){s.set("camera_profile",[:])}}.font(.caption)
                    Divider()
                    Toggle("Gamut Warning",isOn:$s.gamut).onChange(of:s.gamut){_,_ in s.render()}
                    Button("ICC Soft Proof…"){s.asset("icc")}
                    if !s.proof.isEmpty {Text(s.proof["title"] as? String ?? "ICC").font(.caption);Button("Disable Soft Proof"){s.proof=[:];s.render()}}
                    Text("Previews use sRGB. Wide-gamut source data is retained until export conversion.").font(.caption).foregroundStyle(.secondary)
                }
                section("Photo Information"){
                    ForEach(s.metadata.keys.sorted(),id:\.self){key in HStack(alignment:.top){Text(key).foregroundStyle(.secondary);Spacer();Text(String(describing:s.metadata[key] ?? "")).multilineTextAlignment(.trailing).textSelection(.enabled)}.font(.caption)}
                    if let p=s.photo{Text(p.path).font(.caption2).foregroundStyle(.secondary).textSelection(.enabled)}
                }
            }.padding(18).disabled(s.photo==nil || s.browsing || s.loading || s.orientationBusy || s.developPresetBusy)
        }.background(.background)
        .sheet(isPresented:Binding(get:{exportMetadataPhoto != nil},set:{if !$0 { exportMetadataPhoto=nil }})) {
            if let exportMetadataPhoto { ExportMetadataSheet(photoID:exportMetadataPhoto) }
        }
        .sheet(item:$keywordPhoto) { PhotoKeywordsSheet(photo:$0) }
        .confirmationDialog("Reset all adjustments for this photo?",isPresented:$reset,titleVisibility:.visible){Button("Reset Adjustments",role:.destructive){s.apply(s.defaults)};Button("Cancel",role:.cancel){}}message:{Text("The original is unchanged. You can undo this action.")}
    }
    func bool(_ key:String)->Binding<Bool>{Binding(get:{s.recipe[key] as? Bool ?? false},set:{s.set(key,$0)})}
    func edit(_ label:String,_ key:String,_ range:ClosedRange<Double>,_ step:Double=1,_ unit:String="")->some View {
        ParameterRow(label:label,value:Binding(get:{(s.recipe[key] as? NSNumber)?.doubleValue ?? (s.defaults[key] as? NSNumber)?.doubleValue ?? 0},set:{s.set(key,$0)}),range:range,step:step,unit:unit)
    }
    func section<C:View>(_ title:String,@ViewBuilder content:@escaping ()->C)->some View {
        VStack(spacing:15){Divider();DisclosureGroup(title){VStack(spacing:12){content()}.padding(.top,12)}}
    }
}
struct ParameterRow:View {
    let label:String
    @Binding var value:Double
    let range:ClosedRange<Double>
    var step:Double=1
    var unit:String=""
    var body:some View {
        VStack(spacing:5){HStack{Text(label).font(.callout);Spacer();TextField(label,value:$value,format:.number.precision(.fractionLength(step<1 ? 2:0))).multilineTextAlignment(.trailing).textFieldStyle(.plain).frame(width:55).font(.callout.monospacedDigit());if !unit.isEmpty{Text(unit).font(.caption).foregroundStyle(.secondary)}};Slider(value:$value,in:range,step:step).labelsHidden().accessibilityLabel(label)}
    }
}
struct CropControls:View {
    @EnvironmentObject var s:Store
    var box:[Double]{PhotoOrientation.box(s.recipe["crop_box"] as? [Double] ?? [0,0,1,1],orientation:s.photo?.orientation ?? 0)}
    var body:some View {
        VStack(alignment:.leading,spacing:8){Text("Freeform Crop · Normalized Bounds").font(.caption).foregroundStyle(.secondary)
            ForEach(0..<4){i in ParameterRow(label:["Left","Top","Right","Bottom"][i],value:Binding(get:{box[i]},set:{v in var b=box;b[i]=v;if b[2]-b[0]>=0.01 && b[3]-b[1]>=0.01{s.set("crop_box",PhotoOrientation.box(b,orientation:s.photo?.orientation ?? 0,inverse:true))}}),range:0...1,step:0.01)}
            Button("Restore Full Frame"){s.set("crop_box",[0.0,0.0,1.0,1.0]);s.set("crop","original")}
        }
    }
}
struct MaskControls:View {
    @EnvironmentObject var s:Store
    @State private var selected=0
    var masks:[[String:Any]]{s.recipe["masks"] as? [[String:Any]] ?? []}
    func update(_ key:String,_ value:Any){var m=masks;guard m.indices.contains(selected)else{return};m[selected][key]=value;s.set("masks",m)}
    func add(_ name: String,kind: String) {
        var rows=masks
        guard rows.count<12 else { return }
        let end=PhotoOrientation.inverse(CGPoint(x:0.5,y:1),orientation:s.photo?.orientation ?? 0)
        rows.append(["name":name,"kind":kind,"exposure":0.5,"x":0.5,"y":0.5,
                     "x2":end.x,"y2":end.y,"radius":0.25,"points":[[0.5,0.5]]])
        s.set("masks",rows);selected=rows.count-1
    }
    var body:some View {
        VStack(alignment:.leading,spacing:12){
            HStack{Menu("Add Mask"){ForEach([("Radial","radial"),("Gradient","linear"),("Luminance Range","luminance"),("Brush Point","brush")],id:\.1){name,kind in Button(name){add(name,kind:kind)}}};Spacer();Text("\(masks.count)/12").font(.caption).foregroundStyle(.secondary)}
            if !masks.isEmpty {
                Picker("Mask",selection:$selected){ForEach(masks.indices,id:\.self){i in Text(masks[i]["name"] as? String ?? "Mask \(i+1)").tag(i)}}
                if masks.indices.contains(selected){
                    Toggle("Enabled",isOn:Binding(get:{masks[selected]["enabled"] as? Bool ?? true},set:{update("enabled",$0)}))
                    Toggle("Invert",isOn:Binding(get:{masks[selected]["invert"] as? Bool ?? false},set:{update("invert",$0)}))
                    maskRow("Exposure","exposure",-4...4,0.05,0)
                    maskRow("Saturation","saturation",-100...100,1,0)
                    if masks[selected]["kind"] as? String == "luminance" {maskRow("Lower Limit","low",0...1,0.01,0);maskRow("Upper Limit","high",0...1,0.01,1)}
                    else{coordinateRow("Center X",axis:0);coordinateRow("Center Y",axis:1);maskRow("Radius","radius",0.01...1,0.01,0.25)}
                    if masks[selected]["kind"] as? String == "linear" {coordinateRow("End X",axis:0,end:true);coordinateRow("End Y",axis:1,end:true)}
                    maskRow("Feather","feather",0.01...1,0.01,0.5)
                    if masks[selected]["kind"] as? String == "brush" {Text("Use the full recipe editor to set brush path points.").font(.caption);Button("Edit Brush Path…"){s.showRecipe=true}}
                    Button("Delete This Mask",role:.destructive){var m=masks;m.remove(at:selected);selected=max(0,selected-1);s.set("masks",m)}
                }
            }
        }.font(.callout)
    }
    func maskRow(_ label:String,_ key:String,_ range:ClosedRange<Double>,_ step:Double,_ initial:Double)->some View{
        ParameterRow(label:label,value:Binding(get:{(masks[selected][key] as? NSNumber)?.doubleValue ?? initial},set:{update(key,$0)}),range:range,step:step)
    }
    func coordinateRow(_ label: String,axis: Int,end: Bool=false) -> some View {
        let xKey=end ? "x2":"x",yKey=end ? "y2":"y"
        func displayed() -> CGPoint {
            let row=masks[selected]
            return PhotoOrientation.forward(CGPoint(x:(row[xKey] as? NSNumber)?.doubleValue ?? 0.5,
                y:(row[yKey] as? NSNumber)?.doubleValue ?? (end ? 1:0.5)),orientation:s.photo?.orientation ?? 0)
        }
        return ParameterRow(label:label,value:Binding(get:{
            let point=displayed();return Double(axis == 0 ? point.x:point.y)
        },set:{ value in
            var point=displayed()
            if axis == 0 { point.x=value } else { point.y=value }
            let canonical=PhotoOrientation.inverse(point,orientation:s.photo?.orientation ?? 0)
            var rows=masks
            rows[selected][xKey]=canonical.x;rows[selected][yKey]=canonical.y
            s.set("masks",rows)
        }),range:0...1,step:0.01)
    }
}
