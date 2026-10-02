// Purpose: native Copy filename template editor and explicit preview/save flow.
// Inputs: bounded token drafts, template pages and service-calculated filenames.
// Outputs: ordered token edits and revision-bound commands. No filename rendering
// or filesystem work. Discarding a draft preserves the saved import configuration.
import SwiftUI

struct ImportNamingSheet: View {
    @ObservedObject var model: ImportNamingEditor
    @Environment(\.dismiss) private var dismiss
    @State private var showDiscard=false
    @State private var showDelete=false
    @State private var showImportSequence=false
    @State private var insertKind="literal"
    var body: some View {
        content.task { await model.load() }.onDisappear { model.invalidate() }
            .interactiveDismissDisabled(model.busy || model.dirty)
            .confirmationDialog("Discard unsaved filename changes?",isPresented:$showDiscard) {
                Button("Discard Changes",role:.destructive) { dismiss() }
            }
            .confirmationDialog("Delete this saved template?",isPresented:$showDelete) {
                Button("Delete Template",role:.destructive) { Task { await model.deleteTemplate() } }
            } message: { Text("Previously saved import settings are preserved.") }
            .sheet(isPresented:$showImportSequence,onDismiss: {
                Task { await model.preview(offset:model.previewOffset) }
            }) { CatalogImportSequenceSheet() }
    }
    var content: some View {
        VStack(alignment:.leading,spacing:12) {
            Text("File Renaming").font(.title2)
            Text("Rename copies using filename, text, sequence and capture information.").foregroundStyle(.secondary)
            Toggle("Rename Files",isOn:$model.enabled).disabled(model.busy || !model.ready)
            HStack(alignment:.top,spacing:12) {
                ImportSequenceReadout(sequence:model.sequence)
                Spacer(minLength:8)
                Button("Edit Catalog Counters…") { showImportSequence=true }
                    .disabled(model.busy || !model.ready)
            }
            HStack(alignment:.top,spacing:20) {
                VStack(alignment:.leading,spacing:10) {
                    Menu("Built-in Templates") {
                        ForEach(Array(model.builtins.enumerated()),id:\.offset) { _,row in
                            Button(row["name"] as? String ?? "Template") { model.chooseBuiltin(row) }
                        }
                    }
                    HStack {
                        Text("Saved in This Catalog").font(.headline)
                        Spacer()
                        Button { Task { await model.browse(offset:model.libraryOffset) } } label: { Image(systemName:"arrow.clockwise") }
                            .accessibilityLabel("Refresh filename templates")
                    }
                    ScrollView {
                        VStack(alignment:.leading,spacing:6) {
                            ForEach(Array(model.templates.enumerated()),id:\.offset) { _,row in
                                Button { Task { await model.chooseSaved(row) } } label: {
                                    HStack {
                                        Text(row["name"] as? String ?? "").lineLimit(2)
                                        Spacer()
                                        if row["id"] as? String == model.templateID { Image(systemName:"checkmark") }
                                    }.contentShape(Rectangle())
                                }.buttonStyle(.plain).padding(6)
                            }
                            if model.templates.isEmpty { Text("No saved templates").foregroundStyle(.secondary) }
                        }
                    }.frame(minHeight:80,maxHeight:170)
                    HStack {
                        Button("Previous") { Task { await model.browse(offset:max(0,model.libraryOffset-30)) } }.disabled(model.libraryOffset == 0)
                        Spacer()
                        Button("Next") { Task { await model.browse(offset:model.libraryOffset+30) } }.disabled(model.libraryOffset+30>=model.libraryTotal)
                    }
                    VStack(alignment:.leading,spacing:3) {
                        Text("Template Name").font(.caption).foregroundStyle(.secondary)
                        TextField("Template Name",text:$model.templateName)
                    }
                    HStack {
                        Button("Save as New") { Task { await model.saveTemplate(asNew:true) } }.disabled(model.templateName.isEmpty)
                        Button("Update") { Task { await model.saveTemplate(asNew:false) } }.disabled(model.templateID == nil || model.templateName.isEmpty)
                        Button(role:.destructive) { showDelete=true } label: { Image(systemName:"trash") }
                            .disabled(model.templateID == nil).accessibilityLabel("Delete saved filename template")
                    }
                    Text("Update saves both the name and tokens. Choosing or editing a template does not change this import until you save its settings.")
                        .font(.caption).foregroundStyle(.secondary)
                }.frame(width:285)
                Divider()
                VStack(alignment:.leading,spacing:10) {
                    Text("Filename Tokens").font(.headline)
                    ScrollView {
                        VStack(spacing:6) {
                            ForEach(Array(model.tokens.enumerated()),id:\.element.id) { index,token in
                                HStack {
                                    Text(label(token.kind)).frame(width:115,alignment:.leading)
                                    if token.kind == "literal" { TextField("Text",text:$model.tokens[index].text) }
                                    else if token.numbered {
                                        Picker("Digits",selection:$model.tokens[index].digits) {
                                            ForEach(1...10,id:\.self) { Text(String($0)).tag($0) }
                                        }.frame(width:115)
                                        Spacer()
                                    } else { Spacer() }
                                    Button { model.tokens.swapAt(index,index-1) } label: { Image(systemName:"arrow.up") }
                                        .disabled(index == 0).accessibilityLabel("Move \(label(token.kind)) earlier")
                                    Button { model.tokens.swapAt(index,index+1) } label: { Image(systemName:"arrow.down") }
                                        .disabled(index+1 == model.tokens.count).accessibilityLabel("Move \(label(token.kind)) later")
                                    Button { model.tokens.remove(at:index) } label: { Image(systemName:"minus.circle") }
                                        .disabled(model.tokens.count == 1).accessibilityLabel("Remove \(label(token.kind))")
                                }
                            }
                        }
                    }.frame(height:170)
                    HStack {
                        Picker("Insert",selection:$insertKind) { ForEach(model.kinds,id:\.self) { Text(label($0)).tag($0) } }
                        Button("Add Token") { model.tokens.append(FilenameToken(kind:insertKind)) }.disabled(model.tokens.count>=48)
                    }
                    HStack {
                        VStack(alignment:.leading,spacing:3) {
                            Text("Custom Text").font(.caption).foregroundStyle(.secondary)
                            TextField("Custom Text",text:$model.customText)
                        }
                        VStack(alignment:.leading,spacing:3) {
                            Text("Shoot Name").font(.caption).foregroundStyle(.secondary)
                            TextField("Shoot Name",text:$model.shootName)
                        }
                    }
                    HStack {
                        VStack(alignment:.leading,spacing:3) {
                            Text("Start Number").font(.caption).foregroundStyle(.secondary)
                            TextField("Start Number",text:$model.start)
                        }.frame(width:180)
                        Picker("Extension",selection:$model.extensionCase) {
                            Text("Preserve").tag("preserve");Text("Lowercase").tag("lower");Text("Uppercase").tag("upper")
                        }
                    }
                    Text("Sequence follows checked filenames in ascending order, regardless of review sorting. Import # identifies the Copy batch; Image # follows newly cataloged photos. Capture tokens use the camera's local date and time.")
                        .font(.caption).foregroundStyle(.secondary)
                }.frame(maxWidth:.infinity)
            }.disabled(model.busy || !model.ready)
            Divider()
            HStack {
                Button("Preview Names") { Task { await model.preview() } }.disabled(model.busy || !model.ready)
                if !model.previewRows.isEmpty && !model.previewCurrent { Text("Draft changed — refresh the preview").font(.caption).foregroundStyle(.orange) }
                Spacer()
                Button("Previous") { Task { await model.preview(offset:max(0,model.previewOffset-60)) } }.disabled(model.busy || !model.previewCurrent || model.previewOffset == 0)
                Text("\(model.previewTotal) checked").font(.caption)
                Button("Next") { Task { await model.preview(offset:model.previewOffset+60) } }.disabled(model.busy || !model.previewCurrent || model.previewOffset+60>=model.previewTotal)
            }
            ScrollView {
                LazyVStack(alignment:.leading,spacing:8) {
                    ForEach(Array(model.previewRows.enumerated()),id:\.offset) { _,row in
                        VStack(alignment:.leading,spacing:2) {
                            Text(URL(fileURLWithPath:row["source"] as? String ?? "").lastPathComponent).font(.caption)
                            if let error=row["error"] as? String { Text(error).foregroundStyle(.red).font(.caption) }
                            else { Text(row["destination"] as? String ?? "").font(.caption).textSelection(.enabled) }
                        }
                    }
                }
            }.frame(height:125).opacity(model.previewCurrent ? 1:0.5)
            Text("Missing values must be fixed before copying. Destination collisions are checked across all selected files before any copy begins.")
                .font(.caption).foregroundStyle(.secondary)
            if let error=model.error { Text(error).foregroundStyle(.red).font(.caption).textSelection(.enabled) }
            HStack {
                Button("Cancel") { if model.dirty { showDiscard=true } else { dismiss() } }.keyboardShortcut(.cancelAction).disabled(model.busy)
                Spacer()
                if model.busy { ProgressView().controlSize(.small) }
                Button("Save Import Settings") { Task { if await model.save() { dismiss() } } }
                    .buttonStyle(.borderedProminent).keyboardShortcut(.defaultAction).disabled(model.busy || !model.ready)
            }
        }.padding(22).frame(width:960)
    }
    private func label(_ kind: String) -> String {
        ["literal":"Text","filename":"Filename","original_number":"Original Number","folder":"Folder Name",
         "custom_text":"Custom Text","shoot_name":"Shoot Name","sequence":"Sequence","index":"Position",
         "total":"Total Checked","import_number":"Import #","image_number":"Image #",
         "year":"Year","month":"Month","day":"Day","hour":"Hour",
         "minute":"Minute","second":"Second","camera":"Camera Model"][kind] ?? kind
    }
}
