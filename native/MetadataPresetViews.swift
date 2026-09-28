// Purpose: metadata preset browsing, captured local forms and explicit application.
// Inputs: bounded Store pages and portable field descriptors. Outputs: saved preset
// drafts, scoped apply or loaded Painter configuration. Browsing/cancel never tags
// photos. Empty checked values clear fields; unchecked values are preserved.
import SwiftUI

struct MetadataPresetNameSource: Identifiable {
    let id=UUID()
    let action: String
    let selection: MetadataPresetSelection
}

struct MetadataPresetBrowser: View {
    @EnvironmentObject var s: Store
    @Environment(\.dismiss) var dismiss
    @State private var selected: String?
    @State private var naming: MetadataPresetNameSource?
    @State private var deleting: MetadataPresetSelection?
    var choice: MetadataPresetSelection? {
        guard let page=s.metadataPresetPage,let item=page.items.first(where: { $0.id == selected }) else { return nil }
        return MetadataPresetSelection(preset:item,revision:page.revision)
    }
    var body: some View {
        VStack(alignment:.leading,spacing:14) {
            HStack {
                Text("Metadata Presets").font(.title2)
                Spacer()
                Menu("New Preset") {
                    Button("Blank Preset…") { Task { await s.prepareMetadataPresetEditor() } }
                    Button("From Current Photo…") { Task { await s.prepareMetadataPresetEditor(fromPhoto:true) } }.disabled(s.photo == nil)
                }
                Button("Refresh") { Task { await s.refreshMetadataPresets() } }
            }
            TextField("Search presets",text:Binding(get:{s.metadataPresetQuery["search"] as? String ?? ""},set:{value in
                Task { await s.refreshMetadataPresets(["search":value,"offset":0]) }
            })).textFieldStyle(.roundedBorder)
            if let page=s.metadataPresetPage {
                List(selection:$selected) {
                    ForEach(page.items) { item in
                        VStack(alignment:.leading,spacing:4) {
                            Text(item.name).font(.headline)
                            Text("\(item.fieldCount) checked fields").font(.caption).foregroundStyle(.secondary)
                        }.tag(item.id)
                    }
                }.frame(minHeight:230)
                HStack {
                    Text("\(page.total) presets").font(.caption)
                    Spacer()
                    Button("Previous") { move(max(0,page.offset-30)) }.disabled(page.offset == 0)
                    Button("Next") { move(page.offset+30) }.disabled(page.offset+30>=page.total)
                }
                Toggle("Store Metadata Presets with This Catalog",isOn:Binding(get:{page.local},set:{value in
                    Task { await s.metadataPresetAction("storage",revision:page.revision,values:["store_with_catalog":value]) }
                }))
                Text("Switching storage keeps existing presets in their original location.").font(.caption).foregroundStyle(.secondary)
                HStack {
                    Menu("Manage Selected") {
                        if let choice {
                            Button("Edit Preset…") { Task { await s.prepareMetadataPresetEditor(choice) } }
                            Button("Rename…") { naming=MetadataPresetNameSource(action:"rename",selection:choice) }
                            Button("Duplicate…") { naming=MetadataPresetNameSource(action:"duplicate",selection:choice) }
                            Button("Delete…",role:.destructive) { deleting=choice }
                        }
                    }.disabled(choice == nil)
                    Spacer()
                    Button("Load Painter") { if let choice { s.loadPainterMetadataPreset(choice);dismiss() } }.disabled(choice == nil || !s.painterInGrid)
                    Button("Apply to Photos") { if let choice { s.applyMetadataPreset(choice) } }
                        .buttonStyle(.borderedProminent).disabled(choice == nil || !s.canApplyMetadataPreset)
                }
            } else { ProgressView().frame(maxWidth:.infinity,minHeight:230) }
            Text("Checked metadata fields replace their values. Keywords are appended; unchecked fields are preserved.").font(.caption).foregroundStyle(.secondary)
            if let error=s.error { Text(error).foregroundStyle(.red).font(.caption).textSelection(.enabled) }
            HStack {
                if s.metadataPresetBusy { ProgressView().controlSize(.small) }
                Spacer();Button("Done") { dismiss() }.keyboardShortcut(.cancelAction)
            }
        }.padding(22).frame(width:720,height:600).disabled(s.metadataPresetBusy)
            .task { await s.refreshMetadataPresets() }
            .onDisappear { s.metadataPresetEditorGeneration+=1;s.metadataPresetEditor=nil }
            .sheet(item:$s.metadataPresetEditor) { MetadataPresetEditor(source:$0) }
            .sheet(item:$naming) { MetadataPresetNameForm(source:$0) }
            .confirmationDialog("Delete metadata preset?",isPresented:Binding(get:{deleting != nil},set:{if !$0 {deleting=nil}}),titleVisibility:.visible) {
                if let deleting { Button("Delete \(deleting.preset.name)",role:.destructive) { Task { await s.metadataPresetAction("delete",revision:deleting.revision,values:["preset_id":deleting.preset.id]) };self.deleting=nil } }
            } message: { Text("Photo metadata and queued exports remain unchanged.") }
    }
    func move(_ offset: Int) {
        var query=s.metadataPresetQuery;query["offset"]=offset
        Task { await s.refreshMetadataPresets(query) }
    }
}

struct MetadataPresetEditor: View {
    @EnvironmentObject var s: Store
    @Environment(\.dismiss) var dismiss
    let source: MetadataPresetEditorSource
    @State private var name: String
    @State private var values: [String:Any]
    @State private var checked: Set<String>
    init(source: MetadataPresetEditorSource) {
        self.source=source
        _name=State(initialValue:source.original?.name ?? "")
        _values=State(initialValue:source.values);_checked=State(initialValue:source.checked)
    }
    var body: some View {
        VStack(alignment:.leading,spacing:14) {
            Text(source.original == nil ? "New Metadata Preset":"Edit Metadata Preset").font(.title2)
            TextField("Preset Name",text:$name).textFieldStyle(.roundedBorder)
            ScrollView { MetadataFieldsEditor(fields:source.fields,values:$values,selected:$checked).padding(.trailing,8) }
            Text("Checked empty text clears that field. Keywords append; an empty keyword list leaves assignments unchanged. Saving does not change photos.")
                .font(.caption).foregroundStyle(.secondary)
            if let error=s.error { Text(error).font(.caption).foregroundStyle(.red).textSelection(.enabled) }
            HStack {
                Button("Cancel") { dismiss() }.keyboardShortcut(.cancelAction)
                Spacer()
                Button("Save Preset") { Task {
                    let patch=MetadataDraft.patch(values:values,selected:checked,fields:source.fields)
                    if await s.saveMetadataPreset(source,name:name,patch:patch) { dismiss() }
                } }.buttonStyle(.borderedProminent).keyboardShortcut(.defaultAction)
                    .disabled(checked.isEmpty || name.trimmingCharacters(in:.whitespaces).isEmpty)
            }
        }.padding(22).frame(width:560,height:650).disabled(s.metadataPresetBusy)
    }
}

struct MetadataPresetNameForm: View {
    @EnvironmentObject var s: Store
    @Environment(\.dismiss) var dismiss
    let source: MetadataPresetNameSource
    @State private var name: String
    init(source: MetadataPresetNameSource) {
        self.source=source
        _name=State(initialValue:source.selection.preset.name+(source.action == "duplicate" ? " Copy":""))
    }
    var body: some View {
        VStack(alignment:.leading,spacing:16) {
            Text(source.action.capitalized+" Metadata Preset").font(.title2)
            TextField("Name",text:$name).textFieldStyle(.roundedBorder)
            if let error=s.error { Text(error).font(.caption).foregroundStyle(.red) }
            HStack {
                Button("Cancel") { dismiss() }.keyboardShortcut(.cancelAction)
                Spacer();Button("Save") { Task {
                    if await s.metadataPresetAction(source.action,revision:source.selection.revision,
                        values:["preset_id":source.selection.preset.id,"name":name]) { dismiss() }
                } }.buttonStyle(.borderedProminent).keyboardShortcut(.defaultAction)
                    .disabled(name.trimmingCharacters(in:.whitespaces).isEmpty)
            }
        }.padding(22).frame(width:460).disabled(s.metadataPresetBusy)
    }
}
