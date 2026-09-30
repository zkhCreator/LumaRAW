// Purpose: eight-band HSL and Black & White Mix controls over shared recipes.
// Inputs: native slider/text actions, targeted drafts and current recipe values.
// Outputs: partial edits, target selection and scoped resets through Store.
// Hue is displayed on a -100…100 scale while stored degree values stay compatible.
// No pixel algorithms, inferred colors, SQL or Adobe parameter-file translation.
import SwiftUI

enum MixerFields {
    static let bands=["red","orange","yellow","green","aqua","blue","purple","magenta"]
    static let components=["hue","sat","lum"]
    static func keys(monochrome: Bool) -> [String] {
        bands.flatMap { band in (monochrome ? ["bw"]:components).map { band+"_"+$0 } }
    }
    static func label(_ key: String) -> String {
        let parts=key.split(separator:"_").map(String.init)
        guard parts.count == 2,bands.contains(parts[0]),
              let component=["hue":"Hue","sat":"Saturation","lum":"Luminance","bw":"Black & White Mix"][parts[1]] else {
            return key.replacingOccurrences(of:"_",with:" ").capitalized
        }
        return parts[0].capitalized+" "+component
    }
    static func color(_ band: String) -> Color {
        switch band {
        case "red":return .red
        case "orange":return .orange
        case "yellow":return .yellow
        case "green":return .green
        case "aqua":return .cyan
        case "blue":return .blue
        case "purple":return .purple
        default:return .pink
        }
    }
}

extension Store {
    func mixerValue(_ key: String) -> Double {
        let value=(recipe[key] as? NSNumber)?.doubleValue ?? 0
        return key.hasSuffix("_hue") ? value/0.3:value
    }
    func setMixer(_ key: String,_ value: Double) {
        guard (MixerFields.keys(monochrome:false)+MixerFields.keys(monochrome:true)).contains(key),
              value.isFinite,(-100...100).contains(value) else {
            error="Mixer values must be between -100 and 100";return
        }
        set(key,key.hasSuffix("_hue") ? value*0.3:value)
    }
    func resetMixer(monochrome: Bool,component: String?=nil,band: String?=nil) {
        for key in MixerFields.keys(monochrome:monochrome) {
            if let component,!key.hasSuffix("_"+component) { continue }
            if let band,!key.hasPrefix(band+"_") { continue }
            set(key,0.0)
        }
    }
}

struct ColorMixerControls: View {
    @EnvironmentObject var s:Store
    @State private var mode="HSL"
    @State private var component="hue"
    @State private var band="all"
    var monochrome: Bool { s.recipe["monochrome"] as? Bool ?? false }
    var body: some View {
        VStack(spacing:12) {
            HStack {
                if s.canvasTool == "mixer" {
                    Button("Done Targeting") {s.setMixerTargeting(nil)}
                } else if monochrome {
                    Button {s.setMixerTargeting("bw")} label:{Label("Adjust in Photo",systemImage:"scope")}
                } else {
                    Menu {
                        Button("Hue") {component="hue";s.setMixerTargeting("hue")}
                        Button("Saturation") {component="sat";s.setMixerTargeting("sat")}
                        Button("Luminance") {component="lum";s.setMixerTargeting("lum")}
                    } label:{Label("Adjust in Photo",systemImage:"scope")}
                }
                Spacer()
            }.disabled(!s.canEditPointCurves || s.hasPendingEdits)
            if s.mixerTargetActive,let sample=s.mixerTargetSample {
                Text(sample.weights.isEmpty ? "Select an area with color to adjust the mix.":sample.label)
                    .font(.caption).foregroundStyle(.secondary).frame(maxWidth:.infinity,alignment:.leading)
            }
            if !monochrome {
                Picker("Adjust",selection:$mode) { Text("HSL").tag("HSL");Text("Color").tag("Color") }.pickerStyle(.segmented)
                if mode == "HSL" {
                    Picker("Component",selection:$component) {
                        Text("Hue").tag("hue");Text("Saturation").tag("sat");Text("Luminance").tag("lum");Text("All").tag("all")
                    }.pickerStyle(.segmented)
                } else {
                    HStack(spacing:5) {
                        Button("All") { band="all" }.buttonStyle(.borderless)
                            .accessibilityAddTraits(band == "all" ? .isSelected:[])
                        ForEach(MixerFields.bands,id:\.self) { value in
                            Button { band=value } label: {
                                Circle().fill(MixerFields.color(value)).frame(width:19,height:19)
                                    .overlay(Circle().stroke(band == value ? Color.primary:Color.clear,lineWidth:2).padding(-3))
                            }.buttonStyle(.plain).help(value.capitalized)
                                .accessibilityLabel(value.capitalized+" channels")
                                .accessibilityAddTraits(band == value ? .isSelected:[])
                        }
                    }.padding(.vertical,4)
                }
            }
            if monochrome {
                ForEach(MixerFields.bands,id:\.self) { value in row(value,"bw") }
            } else if mode == "HSL" {
                ForEach(component == "all" ? MixerFields.components:[component],id:\.self) { kind in
                    if component == "all" { Text(["hue":"Hue","sat":"Saturation","lum":"Luminance"][kind]!).font(.headline).frame(maxWidth:.infinity,alignment:.leading) }
                    ForEach(MixerFields.bands,id:\.self) { value in row(value,kind) }
                }
            } else {
                ForEach(band == "all" ? MixerFields.bands:[band],id:\.self) { value in
                    Text(value.capitalized).font(.headline).frame(maxWidth:.infinity,alignment:.leading)
                    ForEach(MixerFields.components,id:\.self) { kind in row(value,kind) }
                }
            }
            HStack {
                if !monochrome,(mode == "HSL" && component != "all" || mode == "Color" && band != "all") {
                    Button("Reset Shown") { s.resetMixer(monochrome:false,component:mode == "HSL" ? component:nil,band:mode == "Color" ? band:nil) }
                }
                Spacer()
                Button(monochrome ? "Reset Black & White Mix":"Reset Color Mixer") { s.resetMixer(monochrome:monochrome) }
            }.controlSize(.small)
        }
        .onChange(of:s.mixerTargetComponent) {_,value in if s.canvasTool == "mixer" {mode="HSL";component=value}}
        .onChange(of:s.canvasTool) {_,value in if value == "mixer" {mode="HSL";component=s.mixerTargetComponent}}
        .onAppear {if s.canvasTool == "mixer" {mode="HSL";component=s.mixerTargetComponent}}
        .onChange(of:component) {_,value in
            if s.canvasTool == "mixer",value != "all",value != s.mixerTargetComponent {s.setMixerTargeting(value)}
        }
    }
    func row(_ band: String,_ component: String) -> some View {
        let key=band+"_"+component
        return ParameterRow(label:MixerFields.label(key),value:Binding(get:{s.displayedMixerValue(key)},set:{s.setMixer(key,$0)}),range:-100...100)
    }
}
