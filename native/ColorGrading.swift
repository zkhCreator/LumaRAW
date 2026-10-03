// Purpose: four-wheel Color Grading controls and captured native edit workflows.
// Inputs: engine recipe values, wheel/slider actions and explicit temporary modes.
// Outputs: coalesced read-only previews and one revision-bound partial edit on release.
// Temporary mute/Blending boost never enter recipes, presets or history. Selection,
// reload and revision changes cancel captures; no retarget, SQL or pixel equations.
// The clipboard is local wheel settings. Numeric fields remain keyboard accessible.
import SwiftUI
import AppKit

enum GradingFields {
    static let regions=["shadows","midtones","highlights","global"]
    static func keys(_ region:String)->[String] { ["hue","saturation","luminance"].map {"grading_"+region+"_"+$0} }
    static let keys=regions.flatMap {keys($0)}+["grading_blending","grading_balance"]
    static func limits(_ key:String)->ClosedRange<Double> {
        key.hasSuffix("_hue") ? 0...360 : (key.hasSuffix("_saturation") || key=="grading_blending" ? 0...100 : -100...100)
    }
    static func initial(_ key:String)->Double {key=="grading_blending" ? 50:0}
    static func valid(_ values:[String:Double])->Bool {
        !values.isEmpty && values.allSatisfy {key,value in keys.contains(key) && value.isFinite && limits(key).contains(value)}
    }
}

struct GradingEdit {
    let id=UUID()
    let photoID:Int,revision:Int,epoch:Int
    let baseline:[String:Double]
    let allowed:Set<String>
    let temporaryOnly:Bool
    var values:[String:Double]
    var temporary:[String:Double]=[:]
    var patch:[String:Any] {
        values.merging(temporary) {_,new in new}.filter {baseline[$0.key] != $0.value}
    }
}

struct GradingPreviewDraft {
    let photoID:Int,revision:Int
    let patch:[String:Any]
}

@MainActor final class GradingInteraction:ObservableObject {
    @Published var edit:GradingEdit?
    @Published var clipboard:[Double]?
    private(set) var epoch=0
    let previews=CurvePreviewScheduler()
    var hasPreviewRequest=false
    func invalidate() {previews.cancel();edit=nil;epoch+=1;hasPreviewRequest=false}
}

extension Store {
    var canEditGrading:Bool {
        photo != nil && photo?.id==selected && !loading && !browsing &&
        !orientationBusy && !developPresetBusy && !painterBusy && !historyBusy && !snapshotBusy &&
        !syncBusy && !maskActionBusy && !whiteBalanceSampling && !whiteBalanceArming &&
        activeMaskRecovery==nil && whiteBalanceEditRecovery==nil
    }
    var canStartGrading:Bool {canEditGrading && !hasPendingEdits}
    func gradingValue(_ key:String)->Double {
        gradingInteraction.edit?.values[key] ?? (recipe[key] as? NSNumber)?.doubleValue ?? GradingFields.initial(key)
    }
    func gradingMatches(_ capture:GradingEdit)->Bool {
        canStartGrading && capture.epoch==gradingInteraction.epoch && capture.photoID==selected &&
        capture.photoID==photo?.id && capture.revision==photo?.revision && gradingInteraction.edit?.id==capture.id
    }
    @discardableResult func beginGrading(_ keys:[String],temporaryOnly:Bool=false)->Bool {
        guard canStartGrading,gradingInteraction.edit==nil,!keys.isEmpty,Set(keys).isSubset(of:Set(GradingFields.keys)),let photo else {return false}
        cancelWhiteBalanceSelector();cancelCurveTarget(restore:false);cancelMixerTarget(restore:false)
        cancelMainPreview()
        canvasTool="view";compare=false;splitCompare=false
        let baseline=Dictionary(uniqueKeysWithValues:GradingFields.keys.map {($0,(recipe[$0] as? NSNumber)?.doubleValue ?? GradingFields.initial($0))})
        gradingInteraction.edit=GradingEdit(photoID:photo.id,revision:photo.revision,epoch:gradingInteraction.epoch,
            baseline:baseline,allowed:Set(keys),temporaryOnly:temporaryOnly,values:baseline)
        return true
    }
    func updateGrading(_ values:[String:Double],boost:Bool=false) {
        guard var edit=gradingInteraction.edit,gradingMatches(edit),GradingFields.valid(values),
              Set(values.keys).isSubset(of:edit.allowed) else {cancelGrading();return}
        let previous=edit.values,previousTemporary=edit.temporary
        edit.values.merge(values) {_,new in new}
        edit.temporary=boost ? Dictionary(uniqueKeysWithValues:GradingFields.regions.prefix(3).map {("grading_"+$0+"_saturation",100.0)}):[:]
        guard previous != edit.values || previousTemporary != edit.temporary else {return}
        gradingInteraction.edit=edit
        if edit.patch.isEmpty {
            guard gradingInteraction.hasPreviewRequest else {return}
            gradingInteraction.hasPreviewRequest=false;gradingInteraction.previews.cancel();cancelMainPreview()
            render(gradingDraft:GradingPreviewDraft(photoID:edit.photoID,revision:edit.revision,patch:["grading_blending":edit.values["grading_blending"]!]),debounce:false)
            return
        }
        gradingInteraction.hasPreviewRequest=true
        gradingInteraction.previews.requestGrading(store:self) { [weak self] in
            guard let self,let current=self.gradingInteraction.edit,self.gradingMatches(current),!current.patch.isEmpty else {return nil}
            return GradingPreviewDraft(photoID:current.photoID,revision:current.revision,patch:current.patch)
        }
    }
    @discardableResult func finishGrading()->Bool {
        guard let edit=gradingInteraction.edit else {return false}
        guard gradingMatches(edit) else {
            cancelGrading();message="Color Grading cancelled because the photo changed.";return false
        }
        let patch=edit.values.filter {edit.allowed.contains($0.key) && edit.baseline[$0.key] != $0.value}
        cancelGrading(restore:false);cancelMainPreview()
        if !edit.temporaryOnly,!patch.isEmpty {apply(patch)} else {render(debounce:false)}
        return true
    }
    func cancelGrading(restore:Bool=true) {
        let active=gradingInteraction.edit != nil
        gradingInteraction.invalidate()
        if active {cancelMainPreview();if restore {render(debounce:false)}}
    }
    func setGrading(_ key:String,_ value:Double) {
        guard GradingFields.valid([key:value]) else {error="The Color Grading value is outside its supported range";return}
        guard canEditGrading,gradingInteraction.edit==nil else {return}
        set(key,value)
    }
    func resetGrading(_ regions:[String]=GradingFields.regions,overlap:Bool=true) {
        guard regions.allSatisfy({GradingFields.regions.contains($0)}),canStartGrading,gradingInteraction.edit==nil else {return}
        let keys=regions.flatMap {GradingFields.keys($0)}+(overlap ? ["grading_blending","grading_balance"]:[])
        apply(Dictionary(uniqueKeysWithValues:keys.map {($0,GradingFields.initial($0))}))
    }
    func copyGrading(_ region:String) {
        guard GradingFields.regions.contains(region) else {return}
        gradingInteraction.clipboard=GradingFields.keys(region).map {gradingValue($0)}
    }
    func pasteGrading(_ region:String) {
        guard GradingFields.regions.contains(region),let values=gradingInteraction.clipboard,values.count==3,
              canStartGrading,gradingInteraction.edit==nil else {return}
        apply(Dictionary(uniqueKeysWithValues:zip(GradingFields.keys(region),values)))
    }
    func muteGrading(_ region:String,pressed:Bool) {
        if pressed {
            let keys=GradingFields.keys(region).filter {!$0.hasSuffix("_hue")}
            if beginGrading(keys,temporaryOnly:true) {updateGrading(Dictionary(uniqueKeysWithValues:keys.map {($0,0.0)}))}
        } else if gradingInteraction.edit?.temporaryOnly==true {_=finishGrading()}
    }
}

struct ColorGradingControls:View {
    @EnvironmentObject var s:Store
    @State private var mode:String
    init(initialMode:String="three") {
        _mode=State(initialValue:GradingFields.regions.contains(initialMode) ? initialMode:"three")
    }
    var body:some View {ColorGradingPanel(store:s,interaction:s.gradingInteraction,mode:$mode)}
}

private struct ColorGradingPanel:View {
    @ObservedObject var store:Store
    @ObservedObject var interaction:GradingInteraction
    @Binding var mode:String
    var body:some View {
        VStack(spacing:12) {
            Picker("Color Grading View",selection:$mode) {
                Text("3-Way").tag("three")
                ForEach(GradingFields.regions,id:\.self) {Text($0.capitalized).tag($0)}
            }.pickerStyle(.menu).disabled(interaction.edit != nil)
            if mode=="three" {
                wheel("midtones",diameter:116,sliders:false)
                HStack(alignment:.top,spacing:12) {
                    wheel("shadows",diameter:106,sliders:false);wheel("highlights",diameter:106,sliders:false)
                }
            } else {wheel(mode,diameter:190,sliders:true)}
            if mode != "global" {
                slider("Blending",key:"grading_blending",boost:true)
                slider("Balance",key:"grading_balance")
            }
            HStack {Spacer();Button("Reset Color Grading") {store.resetGrading()}.controlSize(.small)}
                .disabled(!store.canStartGrading || interaction.edit != nil)
        }.onDisappear {store.cancelGrading()}
        .onExitCommand {store.cancelGrading()}
    }
    func wheel(_ region:String,diameter:Double,sliders:Bool)->some View {
        VStack(spacing:6) {
            HStack {
                Text(region.capitalized).font(.caption.weight(.semibold));Spacer()
                Image(systemName:"eye").padding(3).contentShape(Rectangle())
                    .gesture(DragGesture(minimumDistance:0).onChanged {_ in
                        if interaction.edit==nil {store.muteGrading(region,pressed:true)}
                    }.onEnded {_ in store.muteGrading(region,pressed:false)})
                    .accessibilityLabel("Temporarily mute "+region)
                    .accessibilityAction {store.muteGrading(region,pressed:true)}
                    .accessibilityAction(named:Text("Restore Color Grading")) {store.muteGrading(region,pressed:false)}
                    .help("Press and hold to mute this wheel")
            }
            GradingWheel(store:store,region:region).frame(width:diameter,height:diameter)
                .contextMenu {
                    Button("Reset This Wheel") {store.resetGrading([region],overlap:false)}
                    Button("Reset 3-Way Wheels") {store.resetGrading(Array(GradingFields.regions.prefix(3)),overlap:false)}
                    Button("Reset All Wheels") {store.resetGrading()}
                    Divider();Button("Copy Wheel Settings") {store.copyGrading(region)}
                    Button("Paste Wheel Settings") {store.pasteGrading(region)}.disabled(interaction.clipboard==nil)
                }
            if sliders {
                DisclosureGroup("Hue and Saturation") {
                    slider("Hue",key:"grading_"+region+"_hue",unit:"°")
                    slider("Saturation",key:"grading_"+region+"_saturation")
                }.font(.caption)
            }
            slider("Luminance",key:"grading_"+region+"_luminance",compact:!sliders)
        }
    }
    func slider(_ title:String,key:String,unit:String="",compact:Bool=false,boost:Bool=false)->some View {
        VStack(spacing:3) {
            HStack {
                Text(title).font(.caption);Spacer()
                TextField(title,value:Binding(get:{store.gradingValue(key)},set:{store.setGrading(key,$0)}),format:.number.precision(.fractionLength(0)))
                    .textFieldStyle(.plain).multilineTextAlignment(.trailing).frame(width:38).font(.caption.monospacedDigit())
                    .disabled(interaction.edit != nil)
                if !unit.isEmpty {Text(unit).font(.caption)}
            }
            GradingSlider(store:store,key:key,boost:boost)
                .frame(height:compact ? 16:20)
                .accessibilityLabel(key.replacingOccurrences(of:"grading_",with:"").replacingOccurrences(of:"_",with:" ").capitalized)
        }
    }
}
