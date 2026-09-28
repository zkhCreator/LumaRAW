// Purpose: native forms for collections, library filters and catalog metadata.
// Inputs: bounded Store values and captured form targets. Outputs: service actions.
// Boundaries: no file metadata writes, pixel algorithms or hidden whole-library loads.
import SwiftUI

struct LibraryToolbar: View {
    @EnvironmentObject var s: Store
    var body: some View {
        HStack(spacing:12) {
            Button { s.showLibraryFilters=true } label: {
                Label(s.libraryFilters.isEmpty ? "Filter":"Filter (\(s.libraryFilters.count))",systemImage:"line.3.horizontal.decrease.circle")
            }
            if !s.libraryFilters.isEmpty {
                Button("Clear") { s.libraryFilters=[:];s.offset=0;Task { await s.refresh() } }
            }
            Menu("Organize") {
                Button("Edit Metadata…") { Task { await s.prepareMetadataEditor() } }
                Menu("Color Label") {
                    ForEach(LibraryLabels.names,id:\.self) { label in
                        Button(label.capitalized) { s.labelSelection(label) }
                    }
                }
                Menu("Add to Collection") {
                    ForEach(s.collections.filter { $0.kind == "regular" }) { collection in
                        Button(collection.name) { Task { await s.changeMembership(collection,action:"add") } }
                    }
                }
                if let collection=s.collections.first(where: { $0.id == s.collectionID && $0.kind == "regular" }) {
                    Button("Remove from Collection") { Task { await s.changeMembership(collection,action:"remove") } }
                }
            }.disabled(s.selection.isEmpty)
            Spacer()
            Picker("Sort",selection:$s.librarySort) {
                Text("Import Order").tag("imported");Text("Filename").tag("name")
                Text("Rating").tag("rating");Text("Capture Time").tag("captured");Text("Color Label").tag("color")
            }.frame(width:180).onChange(of:s.librarySort) { _,_ in s.offset=0;Task { await s.refresh() } }
            Button {
                s.sortDescending.toggle();s.offset=0;Task { await s.refresh() }
            } label: { Image(systemName:s.sortDescending ? "arrow.down":"arrow.up") }
                .help(s.sortDescending ? "Descending; click for ascending":"Ascending; click for descending")
                .accessibilityLabel(s.sortDescending ? "Sort descending":"Sort ascending")
        }.controlSize(.small).padding(.horizontal,20).padding(.vertical,8)
    }
}

struct CollectionsSidebar: View {
    @EnvironmentObject var s: Store
    @State private var deleting: LibraryCollection?
    var body: some View {
        Section("Collections") {
            Button { s.editCollection() } label: { Label("New Collection…", systemImage:"plus") }
            ForEach(s.collections) { collection in
                Button { Task { await s.openCollection(collection) } } label: {
                    HStack {
                        Label(collection.name, systemImage:collection.kind == "smart" ? "gearshape.2":"square.stack")
                            .lineLimit(1)
                        Spacer()
                        if s.collectionID == collection.id { Image(systemName:"checkmark").font(.caption) }
                    }
                }
                .accessibilityAddTraits(s.collectionID == collection.id ? .isSelected:[])
                .contextMenu {
                    Button("Edit Collection…") { s.editCollection(collection) }
                    if collection.kind == "regular" {
                        Button("Add Selected Photos") { Task { await s.changeMembership(collection,action:"add") } }
                            .disabled(s.selection.isEmpty)
                        Button("Remove Selected Photos") { Task { await s.changeMembership(collection,action:"remove") } }
                            .disabled(s.selection.isEmpty)
                    }
                    Button("Delete Collection…", role:.destructive) { deleting=collection }
                }
            }
            if s.collectionTotal > 60 {
                HStack {
                    Button("Previous") { s.collectionOffset=max(0,s.collectionOffset-60); Task { await s.refreshCollections() } }
                        .disabled(s.collectionOffset == 0)
                    Spacer()
                    Button("Next") { s.collectionOffset+=60; Task { await s.refreshCollections() } }
                        .disabled(s.collectionOffset+60 >= s.collectionTotal)
                }.font(.caption)
            }
        }
        .confirmationDialog("Delete \(deleting?.name ?? "collection")?",
                            isPresented:Binding(get:{deleting != nil},set:{if !$0 { deleting=nil }})) {
            Button("Delete Collection",role:.destructive) {
                if let collection=deleting { Task { await s.deleteCollection(collection) } }
                deleting=nil
            }
        } message: { Text("Photos and originals will remain in your library.") }
    }
}

struct LibraryFilterFields: View {
    @Binding var draft: LibraryFilterDraft
    var body: some View {
        Picker("Minimum rating", selection:$draft.minimum) {
            Text("Any").tag(-1)
            ForEach(0..<6) { Text("\($0) stars").tag($0) }
        }
        Picker("Maximum rating", selection:$draft.maximum) {
            Text("Any").tag(-1)
            ForEach(0..<6) { Text("\($0) stars").tag($0) }
        }
        Picker("Pick flag", selection:$draft.flag) {
            Text("Any").tag(2); Text("Pick").tag(1); Text("Unflagged").tag(0); Text("Rejected").tag(-1)
        }
        Picker("Color label", selection:$draft.color) {
            Text("Any").tag("any")
            ForEach(LibraryLabels.names,id:\.self) { Text($0.capitalized).tag($0) }
        }
        TextField("Keyword matches",text:$draft.keyword)
        Picker("Keywords", selection:$draft.keywordPresence) {
            Text("Any").tag("any"); Text("Has keywords").tag("present"); Text("Without keywords").tag("absent")
        }
        TextField("Text contains",text:$draft.text)
        TextField("Camera model matches",text:$draft.camera)
        TextField("Folder and subfolders",text:$draft.folder)
        Text("Text searches names, titles, captions, copyright and keywords. Camera and capture dates become available after updating the library index.")
            .font(.caption).foregroundStyle(.secondary)
    }
}

struct CollectionEditor: View {
    @EnvironmentObject var s: Store
    @Environment(\.dismiss) private var dismiss
    let original: LibraryCollection?
    @State private var name: String
    @State private var kind: String
    @State private var match: String
    @State private var draft: LibraryFilterDraft
    @State private var saving=false

    init(original: LibraryCollection?) {
        self.original=original
        _name=State(initialValue:original?.name ?? "")
        _kind=State(initialValue:original?.kind ?? "regular")
        _match=State(initialValue:original?.match ?? "all")
        _draft=State(initialValue:LibraryFilterDraft(original?.rules ?? [:]))
    }

    var body: some View {
        VStack(alignment:.leading,spacing:16) {
            Text(original == nil ? "New Collection":"Edit Collection").font(.title2)
            Form {
                TextField("Name",text:$name)
                Picker("Type",selection:$kind) {
                    Text("Collection").tag("regular"); Text("Smart Collection").tag("smart")
                }.disabled(original != nil)
                if kind == "smart" {
                    Picker("Match",selection:$match) { Text("All rules").tag("all"); Text("Any rule").tag("any") }
                    LibraryFilterFields(draft:$draft)
                } else {
                    Text("Add photos using the collection's contextual menu. A photo can belong to more than one collection.")
                        .font(.caption).foregroundStyle(.secondary)
                }
            }.formStyle(.grouped)
            HStack {
                Button("Cancel",role:.cancel) { dismiss() }.keyboardShortcut(.cancelAction)
                Spacer()
                Button("Save") {
                    saving=true
                    Task {
                        if await s.saveCollection(name:name,kind:kind,rules:kind == "smart" ? draft.rules:[:],match:match,original:original) { dismiss() }
                        saving=false
                    }
                }.keyboardShortcut(.defaultAction).disabled(saving || name.trimmingCharacters(in:.whitespaces).isEmpty)
            }
        }.padding(24).frame(width:520,height:kind == "smart" ? 690:320)
    }
}

struct LibraryFilterSheet: View {
    @EnvironmentObject var s: Store
    @Environment(\.dismiss) private var dismiss
    @State var draft: LibraryFilterDraft
    var body: some View {
        VStack(alignment:.leading,spacing:16) {
            Text("Library Filters").font(.title2)
            Form { LibraryFilterFields(draft:$draft) }.formStyle(.grouped)
            HStack {
                Button("Cancel",role:.cancel) { dismiss() }.keyboardShortcut(.cancelAction)
                Button("Clear") { draft=LibraryFilterDraft() }
                Spacer()
                Button("Apply") {
                    s.libraryFilters=draft.rules; s.offset=0
                    Task { await s.refresh() }; dismiss()
                }.keyboardShortcut(.defaultAction)
            }
        }.padding(24).frame(width:520,height:610)
    }
}

struct MetadataEditor: View {
    @EnvironmentObject var s: Store
    @Environment(\.dismiss) private var dismiss
    let targets: [Photo]
    @State private var title: String
    @State private var caption: String
    @State private var copyright: String
    @State private var keywords: String
    @State private var label: String
    @State private var fields: Set<String>
    @State private var saving=false

    init(targets: [Photo]) {
        self.targets=targets
        let first=targets.first
        _title=State(initialValue:first?.title ?? "")
        _caption=State(initialValue:first?.caption ?? "")
        _copyright=State(initialValue:first?.copyright ?? "")
        _keywords=State(initialValue:first?.keywords.joined(separator:", ") ?? "")
        _label=State(initialValue:first?.colorLabel ?? "none")
        _fields=State(initialValue:targets.count == 1 ? ["title","caption","copyright","keywords","color_label"]:[])
    }

    func enabled(_ key: String) -> Binding<Bool> {
        Binding(get:{fields.contains(key)},set:{if $0 { fields.insert(key) } else { fields.remove(key) }})
    }

    var body: some View {
        VStack(alignment:.leading,spacing:16) {
            Text("Metadata · \(targets.count) photos").font(.title2)
            Text("Only checked fields will be applied to every selected photo. Keywords replace the existing set. Changes stay in this catalog.")
                .font(.callout).foregroundStyle(.secondary)
            Form {
                Toggle("Apply title",isOn:enabled("title")); TextField("Title",text:$title).disabled(!fields.contains("title"))
                Toggle("Apply caption",isOn:enabled("caption")); TextField("Caption",text:$caption,axis:.vertical).lineLimit(3...5).disabled(!fields.contains("caption"))
                Toggle("Apply copyright",isOn:enabled("copyright")); TextField("Copyright",text:$copyright).disabled(!fields.contains("copyright"))
                Toggle("Apply keywords",isOn:enabled("keywords")); TextField("Keywords, separated by commas",text:$keywords).disabled(!fields.contains("keywords"))
                Toggle("Apply color label",isOn:enabled("color_label"))
                Picker("Color label",selection:$label) {
                    ForEach(LibraryLabels.names,id:\.self) { Text($0.capitalized).tag($0) }
                }.disabled(!fields.contains("color_label"))
            }.formStyle(.grouped)
            HStack {
                Button("Cancel",role:.cancel) { dismiss() }.keyboardShortcut(.cancelAction)
                Spacer()
                Button("Save Metadata") {
                    var patch: [String: Any] = [:]
                    for (key,value) in [("title",title),("caption",caption),("copyright",copyright),("color_label",label)] where fields.contains(key) { patch[key]=value }
                    if fields.contains("keywords") {
                        patch["keywords"]=keywords.components(separatedBy:CharacterSet(charactersIn:",\n")).map { $0.trimmingCharacters(in:.whitespacesAndNewlines) }.filter { !$0.isEmpty }
                    }
                    saving=true
                    Task { if await s.saveMetadata(targets:targets,patch:patch) { dismiss() }; saving=false }
                }.keyboardShortcut(.defaultAction).disabled(fields.isEmpty || saving)
            }
        }.padding(24).frame(width:560,height:650)
    }
}
