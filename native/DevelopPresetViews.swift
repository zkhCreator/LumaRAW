// Purpose: native preset library, group management and selected-settings editor.
// Inputs: bounded service pages and immutable editor snapshots. Outputs: explicit
// Store actions. Browsing never applies adjustments; only Apply or Painter commits.
// No pixel preview simulation, SQL, asset paths or silent stale-draft rebasing.
import SwiftUI

struct DevelopPresetForm: Identifiable {
    let id=UUID()
    let action: String
    let revision: String
    let preset: DevelopPresetItem?
    let group: DevelopPresetGroup?
}

struct DevelopPresetBrowser: View {
    @EnvironmentObject var s: Store
    @Environment(\.dismiss) var dismiss
    @State private var selected: String?
    @State private var form: DevelopPresetForm?
    @State private var deleting: DevelopPresetSelection?
    var page: DevelopPresetPage? { s.developPresetPage }
    var choice: DevelopPresetSelection? {
        guard let page,let row=page.items.first(where: { $0.id == selected }) else { return nil }
        return DevelopPresetSelection(preset:row,revision:page.revision)
    }
    var body: some View {
        VStack(alignment:.leading,spacing:14) {
            HStack {
                Text("Develop Presets").font(.title2)
                Spacer()
                Button("Create Preset…") { Task { await s.prepareDevelopPresetEditor() } }.disabled(s.photo == nil || s.developPresetBusy)
                Button("Refresh") { Task { await s.refreshDevelopPresets() } }
            }
            HStack {
                TextField("Search preset or group",text:Binding(get:{s.developPresetQuery["search"] as? String ?? ""},set:{change("search",$0)}))
                Toggle("Favorites",isOn:Binding(get:{s.developPresetQuery["favorites"] as? Bool ?? false},set:{change("favorites",$0)}))
                Toggle("Include Hidden",isOn:Binding(get:{s.developPresetQuery["include_hidden"] as? Bool ?? false},set:{change("include_hidden",$0)}))
            }
            if let page {
                List(selection:$selected) {
                    ForEach(page.items) { item in
                        HStack {
                            VStack(alignment:.leading,spacing:3) {
                                Text(item.name).font(.headline)
                                Text("\(item.group) · \(item.fieldCount) settings\(item.builtin ? " · Built-in":"")").font(.caption).foregroundStyle(.secondary)
                            }
                            Spacer()
                            Button { Task { await s.developPresetAction("favorite",revision:page.revision,values:["preset_id":item.id,"favorite":!item.favorite]) } } label: {
                                Image(systemName:item.favorite ? "star.fill":"star")
                            }.buttonStyle(.borderless).help(item.favorite ? "Remove from Favorites":"Add to Favorites")
                                .accessibilityLabel(item.favorite ? "Remove \(item.name) from Favorites":"Add \(item.name) to Favorites")
                        }.tag(item.id)
                    }
                }.frame(minHeight:210)
                HStack {
                    Text("\(page.total) presets").font(.caption).foregroundStyle(.secondary)
                    Spacer()
                    Button("Previous") { change("offset",max(0,page.offset-30),reset:false) }.disabled(page.offset == 0)
                    Button("Next") { change("offset",page.offset+30,reset:false) }.disabled(page.offset+30>=page.total)
                }
                DisclosureGroup("Manage Groups and Storage") {
                    VStack(alignment:.leading,spacing:6) {
                        ScrollView { VStack(spacing:6) { ForEach(page.groups) { group in
                            HStack {
                                Toggle(group.name,isOn:Binding(get:{group.visible},set:{value in Task { await s.developPresetAction("group_visibility",revision:page.revision,values:["group_id":group.id,"visible":value]) } }))
                                Spacer()
                                Button("Filter") { change("group_id",group.id) }
                                Button("Rename…") { form=DevelopPresetForm(action:"group_rename",revision:page.revision,preset:nil,group:group) }.disabled(group.builtin)
                            }
                        } } }.frame(maxHeight:140)
                        HStack {
                            Button("All Groups") { var query=s.developPresetQuery;query.removeValue(forKey:"group_id");query["offset"]=0;Task { await s.refreshDevelopPresets(query) } }
                            Spacer()
                            Button("Previous Groups") { change("group_offset",max(0,page.groupOffset-30),reset:false) }.disabled(page.groupOffset == 0)
                            Button("More Groups") { change("group_offset",page.groupOffset+30,reset:false) }.disabled(page.groupOffset+30>=page.groupTotal)
                        }
                        Toggle("Store Develop Presets with This Catalog",isOn:Binding(get:{page.local},set:{value in Task { await s.developPresetAction("storage",revision:page.revision,values:["store_with_catalog":value]) } }))
                        Text("Switching storage keeps existing presets in their original location.").font(.caption).foregroundStyle(.secondary)
                    }.padding(.top,8)
                }
                HStack {
                    Menu("Manage Selected") {
                        if let choice {
                            Button("Update With Current Settings…") { Task { await s.prepareDevelopPresetEditor(choice) } }.disabled(choice.preset.builtin || s.photo == nil)
                            Button("Duplicate…") { form=DevelopPresetForm(action:"duplicate",revision:choice.revision,preset:choice.preset,group:nil) }
                            Button("Rename…") { form=DevelopPresetForm(action:"rename",revision:choice.revision,preset:choice.preset,group:nil) }.disabled(choice.preset.builtin)
                            Button("Move to Group…") { form=DevelopPresetForm(action:"move",revision:choice.revision,preset:choice.preset,group:nil) }.disabled(choice.preset.builtin)
                            Button("Delete…",role:.destructive) { deleting=choice }.disabled(choice.preset.builtin)
                        }
                    }.disabled(choice == nil)
                    Spacer()
                    Button("Load Painter") { if let choice { s.loadPainterDevelopPreset(choice);dismiss() } }.disabled(choice == nil || !s.painterInGrid)
                    Button("Apply to Photos") { if let choice { s.applyDevelopPreset(choice) } }.buttonStyle(.borderedProminent).disabled(choice == nil || !s.canApplyDevelopPreset)
                }
            } else { ProgressView().frame(maxWidth:.infinity,minHeight:250) }
            HStack {
                if s.developPresetBusy { ProgressView().controlSize(.small) }
                Text("Only saved settings are applied. Originals and queued exports are preserved.").font(.caption).foregroundStyle(.secondary)
                Spacer();Button("Done") { dismiss() }.keyboardShortcut(.cancelAction)
            }
        }.padding(22).frame(width:720,height:700).disabled(s.developPresetBusy)
            .task { await s.refreshDevelopPresets() }
            .onDisappear { s.developPresetEditorGeneration+=1;s.developPresetEditor=nil }
            .sheet(item:$s.developPresetEditor) { DevelopPresetEditor(source:$0) }
            .sheet(item:$form) { DevelopPresetNameForm(source:$0) }
            .confirmationDialog("Delete preset?",isPresented:Binding(get:{deleting != nil},set:{if !$0 {deleting=nil}}),titleVisibility:.visible) {
                if let deleting { Button("Delete \(deleting.preset.name)",role:.destructive) { Task { await s.developPresetAction("delete",revision:deleting.revision,values:["preset_id":deleting.preset.id]) };self.deleting=nil } }
            } message: { Text("Existing photo adjustments and exports remain unchanged.") }
    }
    func change(_ key: String,_ value: Any,reset: Bool=true) {
        var query=s.developPresetQuery
        query[key]=value
        if reset { query["offset"]=0 }
        Task { await s.refreshDevelopPresets(query) }
    }
}

struct DevelopPresetEditor: View {
    @EnvironmentObject var s: Store
    @Environment(\.dismiss) var dismiss
    let source: DevelopPresetEditorSource
    @State private var name: String
    @State private var group: String
    @State private var fields: Set<String>
    @State private var policy="error"
    init(source: DevelopPresetEditorSource) {
        self.source=source
        _name=State(initialValue:source.original?.name ?? "")
        _group=State(initialValue:source.original?.group ?? "User Presets")
        _fields=State(initialValue:source.fields)
    }
    var body: some View {
        VStack(alignment:.leading,spacing:14) {
            Text(source.original == nil ? "New Develop Preset":"Update Develop Preset").font(.title2)
            Text("Settings captured from \(source.photo.displayName)").font(.caption).foregroundStyle(.secondary)
            TextField("Preset Name",text:$name).textFieldStyle(.roundedBorder)
            TextField("Group",text:$group).textFieldStyle(.roundedBorder)
            HStack {
                Button("Check All") { fields=Set(source.fieldGroups.values.flatMap { $0 }) }
                Button("Check None") { fields=[] }
                Spacer();Text("\(fields.count) settings").font(.caption)
            }
            ScrollView {
                VStack(alignment:.leading,spacing:10) {
                    ForEach(source.fieldGroups.keys.sorted(),id:\.self) { key in
                        DisclosureGroup(key) {
                            ForEach(source.fieldGroups[key] ?? [],id:\.self) { field in
                                Toggle(ParametricCurveValues.label(field) ?? (PointCurveFields.keys.contains(field) ? PointCurveFields.label(field)+" Point Curve":MixerFields.label(field)),isOn:Binding(get:{fields.contains(field)},set:{value in if value {fields.insert(field)} else {fields.remove(field)} }))
                            }.padding(.leading,12)
                        }
                    }
                }
            }.frame(minHeight:200)
            Picker("Existing Name",selection:$policy) {
                Text("Report Conflict").tag("error");Text("Keep Both").tag("duplicate")
                if source.original == nil { Text("Replace Existing").tag("replace") }
            }
            Text("Unchecked settings are preserved when applying this preset. Catalog rotation and flips are independent.").font(.caption).foregroundStyle(.secondary)
            HStack {
                Button("Cancel") { dismiss() }.keyboardShortcut(.cancelAction)
                Spacer()
                Button("Save Preset") { Task { if await s.saveDevelopPreset(source,name:name,group:group,fields:fields,policy:policy) { dismiss() } } }
                    .buttonStyle(.borderedProminent).keyboardShortcut(.defaultAction)
                    .disabled(fields.isEmpty || name.trimmingCharacters(in:.whitespaces).isEmpty || group.trimmingCharacters(in:.whitespaces).isEmpty)
            }
        }.padding(22).frame(width:510,height:620).disabled(s.developPresetBusy)
    }
}

struct DevelopPresetNameForm: View {
    @EnvironmentObject var s: Store
    @Environment(\.dismiss) var dismiss
    let source: DevelopPresetForm
    @State private var name: String
    @State private var group: String
    init(source: DevelopPresetForm) {
        self.source=source
        _name=State(initialValue:source.action == "duplicate" ? (source.preset?.name ?? "Preset")+" Copy":source.preset?.name ?? source.group?.name ?? "")
        _group=State(initialValue:source.preset?.builtin == true ? "User Presets":source.preset?.group ?? "User Presets")
    }
    var body: some View {
        VStack(alignment:.leading,spacing:16) {
            Text(source.action.replacingOccurrences(of:"_",with:" ").capitalized).font(.title2)
            if source.action != "move" { TextField("Name",text:$name).textFieldStyle(.roundedBorder) }
            if ["move","duplicate"].contains(source.action) { TextField("Group",text:$group).textFieldStyle(.roundedBorder) }
            HStack {
                Button("Cancel") { dismiss() }.keyboardShortcut(.cancelAction)
                Spacer();Button("Save") { Task {
                    var values: [String:Any]=[:]
                    if let item=source.preset { values["preset_id"]=item.id }
                    if let item=source.group { values["group_id"]=item.id }
                    if source.action != "move" { values["name"]=name }
                    if ["move","duplicate"].contains(source.action) { values["group_name"]=group }
                    if await s.developPresetAction(source.action,revision:source.revision,values:values) { dismiss() }
                } }.buttonStyle(.borderedProminent).keyboardShortcut(.defaultAction)
            }
        }.padding(22).frame(width:460).disabled(s.developPresetBusy)
    }
}
