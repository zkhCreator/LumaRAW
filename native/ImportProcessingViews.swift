// Purpose: Apply During Import preset browsing and explicit keyword draft saving.
// Inputs: captured editor state and shared metadata field descriptors. Outputs:
// preset choices, None, named metadata creation and saved keyword additions.
// No photo writes before import, implicit draft saves or preset payload ownership.
import SwiftUI

struct ImportProcessingSheet: View {
    @ObservedObject var model: ImportProcessingEditor
    @Environment(\.dismiss) private var dismiss
    @State private var newMetadata: MetadataPresetEditorSource?
    var body: some View {
        VStack(alignment:.leading,spacing:14) {
            Text("Apply During Import").font(.title2)
            Text("These choices apply to checked photos. Later preset edits will not change this import.")
                .foregroundStyle(.secondary)
            HStack(alignment:.top,spacing:22) {
                develop
                Divider()
                metadata
            }.frame(height:300)
            Divider()
            Text("Additional Keywords").font(.headline)
            TextField("Separate keywords with commas; use Parent | Child for a hierarchy",text:$model.keywordsText,axis:.vertical)
                .lineLimit(2...4).textFieldStyle(.roundedBorder).disabled(!model.ready)
            HStack {
                Text("Keywords append to existing file metadata and the selected preset.").font(.caption).foregroundStyle(.secondary)
                Spacer()
                Button("Discard Draft") { model.keywordsText=model.savedKeywordsText }.disabled(!model.keywordsDirty)
                Button("Save Keywords") { Task { await model.saveKeywords() } }.disabled(!model.keywordsDirty || !model.ready)
            }
            if let error=model.error { Text(error).foregroundStyle(.red).font(.caption).textSelection(.enabled) }
            if model.keywordsDirty { Text("Save or discard the keyword draft before closing.").font(.caption).foregroundStyle(.secondary) }
            HStack {
                if model.busy { ProgressView().controlSize(.small) }
                Spacer()
                Button("Done") { dismiss() }.keyboardShortcut(.cancelAction).disabled(model.keywordsDirty)
            }
        }.padding(22).frame(width:850).frame(minHeight:580).disabled(model.busy)
            .task { await model.load() }.onDisappear { model.invalidate() }
            .interactiveDismissDisabled(model.busy || model.keywordsDirty)
            .sheet(item:$newMetadata) { source in ImportMetadataPresetForm(model:model,source:source) }
    }

    var develop: some View {
        VStack(alignment:.leading,spacing:8) {
            HStack {
                Text("Develop Settings").font(.headline);Spacer()
                Button("None") { Task { await model.chooseDevelop(nil) } }.disabled(model.developID.isEmpty || !model.ready)
            }
            Text(model.developName.isEmpty ? "None":model.developName).font(.caption).foregroundStyle(.secondary)
            TextField("Search Develop presets",text:$model.developSearch).textFieldStyle(.roundedBorder)
                .onChange(of:model.developSearch) { _,_ in Task { await model.browseDevelop() } }
            if let page=model.developPage {
                List(page.items) { item in
                    Button { Task { await model.chooseDevelop(DevelopPresetSelection(preset:item,revision:page.revision)) } } label: {
                        HStack { VStack(alignment:.leading) { Text(item.name);Text(item.group).font(.caption).foregroundStyle(.secondary) };Spacer();if item.id == model.developID { Image(systemName:"checkmark") } }
                    }.buttonStyle(.plain).disabled(!model.ready)
                }
                HStack {
                    Button("Previous") { Task { await model.browseDevelop(offset:max(0,page.offset-30)) } }.disabled(page.offset == 0)
                    Text("\(page.total) presets").font(.caption);Spacer()
                    Button("Next") { Task { await model.browseDevelop(offset:page.offset+30) } }.disabled(page.offset+30>=page.total)
                }
            } else { Spacer() }
            Button("Refresh Develop List") { Task { await model.browseDevelop() } }
        }.frame(maxWidth:.infinity)
    }

    var metadata: some View {
        VStack(alignment:.leading,spacing:8) {
            HStack {
                Text("Metadata").font(.headline);Spacer()
                Button("None") { Task { await model.chooseMetadata(nil) } }.disabled(model.metadataID.isEmpty || !model.ready)
            }
            Text(model.metadataName.isEmpty ? "None":model.metadataName).font(.caption).foregroundStyle(.secondary)
            TextField("Search metadata presets",text:$model.metadataSearch).textFieldStyle(.roundedBorder)
                .onChange(of:model.metadataSearch) { _,_ in Task { await model.browseMetadata() } }
            if let page=model.metadataPage {
                List(page.items) { item in
                    Button { Task { await model.chooseMetadata(MetadataPresetSelection(preset:item,revision:page.revision)) } } label: {
                        HStack { Text(item.name);Spacer();if item.id == model.metadataID { Image(systemName:"checkmark") } }
                    }.buttonStyle(.plain).disabled(!model.ready)
                }
                HStack {
                    Button("Previous") { Task { await model.browseMetadata(offset:max(0,page.offset-30)) } }.disabled(page.offset == 0)
                    Text("\(page.total) presets").font(.caption);Spacer()
                    Button("Next") { Task { await model.browseMetadata(offset:page.offset+30) } }.disabled(page.offset+30>=page.total)
                }
                HStack {
                    Button("Refresh Metadata List") { Task { await model.browseMetadata() } }
                    Spacer()
                    Button("New…") {
                        newMetadata=MetadataPresetEditorSource(original:nil,revision:page.revision,fields:page.fields,values:[:],checked:[])
                    }.disabled(!model.ready)
                }
            } else { Spacer() }
        }.frame(maxWidth:.infinity)
    }
}

struct ImportMetadataPresetForm: View {
    @ObservedObject var model: ImportProcessingEditor
    let source: MetadataPresetEditorSource
    @Environment(\.dismiss) private var dismiss
    @State private var name=""
    @State private var values: [String:Any]=[:]
    @State private var checked: Set<String>=[]
    var body: some View {
        VStack(alignment:.leading,spacing:14) {
            Text("New Metadata Preset").font(.title2)
            TextField("Preset Name",text:$name).textFieldStyle(.roundedBorder)
            ScrollView { MetadataFieldsEditor(fields:source.fields,values:$values,selected:$checked) }
            if let error=model.error { Text(error).font(.caption).foregroundStyle(.red) }
            HStack {
                Button("Cancel") { dismiss() }.keyboardShortcut(.cancelAction);Spacer()
                Button("Save and Choose") { Task {
                    if await model.createMetadata(name:name,patch:MetadataDraft.patch(values:values,selected:checked,fields:source.fields),revision:source.revision) { dismiss() }
                } }.buttonStyle(.borderedProminent).disabled(checked.isEmpty || name.trimmingCharacters(in:.whitespaces).isEmpty)
            }
        }.padding(22).frame(width:560,height:650).disabled(model.busy).interactiveDismissDisabled(model.busy)
    }
}
