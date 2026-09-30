// Purpose: native forms for collections, library filters and catalog metadata.
// Inputs: bounded Store values and captured form targets. Outputs: service actions.
// Boundaries: no file metadata writes, pixel algorithms or hidden whole-library loads.
import SwiftUI

struct LibraryToolbar: View {
    @EnvironmentObject var s: Store
    var body: some View {
        HStack(spacing:12) {
            if s.mode == "previous_import" {
                Label("Previous Import",systemImage:"square.and.arrow.down").lineLimit(1)
            }
            if let folder=s.activeFolder,folder.id == s.folderID {
                Label(folder.name,systemImage:"folder").lineLimit(1).help(folder.path)
            }
            Button { s.showLibraryFilters=true } label: {
                Label(s.libraryFilters.isEmpty ? "Filter":"Filter (\(s.libraryFilters.count))",systemImage:"line.3.horizontal.decrease.circle")
            }
            if !s.libraryFilters.isEmpty {
                Button("Clear") { s.libraryFilters=[:];s.offset=0;Task { await s.refresh() } }
            }
            Menu("Organize") {
                Button("Create Virtual Copies") { Task { await s.createVirtualCopies() } }.disabled(s.copyBusy)
                Button("Remove Virtual Copies from Catalog…") { Task { await s.prepareCopyRemoval() } }.disabled(s.copyBusy)
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
                if let collection=s.activeCollection,collection.id == s.collectionID,["regular","quick"].contains(collection.kind) {
                    Button("Remove from Collection") { Task { await s.changeMembership(collection,action:"remove") } }
                }
            }.disabled(s.selection.isEmpty)
            Spacer()
            Picker("Sort",selection:Binding(get:{s.librarySort},set:{value in
                s.librarySort=value;s.offset=0;Task { await s.refresh() }
            })) {
                Text("Import Order").tag("imported");Text("Filename").tag("name")
                Text("Rating").tag("rating");Text("Capture Time").tag("captured");Text("Color Label").tag("color")
            }.frame(width:180)
            Button {
                s.sortDescending.toggle();s.offset=0;Task { await s.refresh() }
            } label: { Image(systemName:s.sortDescending ? "arrow.down":"arrow.up") }
                .help(s.sortDescending ? "Descending; click for ascending":"Ascending; click for descending")
                .accessibilityLabel(s.sortDescending ? "Sort descending":"Sort ascending")
        }.controlSize(.small).padding(.horizontal,20).padding(.vertical,8)
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
        Picker("Snapshot status",selection:$draft.snapshotPresence) {
            Text("Any").tag("any");Text("Have snapshots").tag("present");Text("No snapshots").tag("absent")
        }
        Text("Snapshot status is shared by each original and its virtual copies.").font(.caption).foregroundStyle(.secondary)
        Picker("Photo type",selection:$draft.virtualType) {
            Text("All photos").tag("all");Text("Master photos").tag("masters");Text("Virtual copies").tag("copies")
        }
        TextField("Copy name contains",text:$draft.copyName)
        TextField("Text contains",text:$draft.text)
        TextField("Camera model matches",text:$draft.camera)
        TextField("Folder and subfolders",text:$draft.folder)
        Text("Text searches filenames, copy names, titles, captions, copyright and keywords. Camera and capture dates become available after updating the library index.")
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
    @State private var parentID: Int?
    @State private var parentName="None"
    @State private var choosingParent=false
    @State private var includePhotos=false

    init(original: LibraryCollection?,kind: String="regular",parentID: Int?=nil) {
        self.original=original
        _name=State(initialValue:original?.name ?? "")
        _kind=State(initialValue:original?.kind ?? kind)
        _parentID=State(initialValue:original?.parentID ?? parentID)
        _match=State(initialValue:original?.match ?? "all")
        _draft=State(initialValue:LibraryFilterDraft(original?.rules ?? [:]))
    }

    var body: some View {
        VStack(alignment:.leading,spacing:16) {
            Text(original == nil ? "New Collection":"Edit Collection").font(.title2)
            Form {
                TextField("Name",text:$name)
                Picker("Type",selection:$kind) {
                    Text("Collection").tag("regular"); Text("Smart Collection").tag("smart"); Text("Collection Set").tag("set")
                }.disabled(original != nil)
                Button("Inside: \(parentName)") { choosingParent=true }
                if original == nil,kind == "regular" { Toggle("Include selected photos",isOn:$includePhotos).disabled(s.selection.isEmpty) }
                if kind == "smart" {
                    Picker("Match",selection:$match) { Text("All rules").tag("all"); Text("Any rule").tag("any") }
                    LibraryFilterFields(draft:$draft)
                } else if kind == "set" {
                    Text("Sets contain collections and other sets. Select a set to view its combined photos.").font(.caption).foregroundStyle(.secondary)
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
                        if await s.saveCollection(name:name,kind:kind,rules:kind == "smart" ? draft.rules:[:],match:match,original:original,parentID:parentID,includePhotos:includePhotos && kind == "regular") { dismiss() }
                        saving=false
                    }
                }.keyboardShortcut(.defaultAction).disabled(saving || name.trimmingCharacters(in:.whitespaces).isEmpty)
            }
        }.padding(24).frame(width:520,height:kind == "smart" ? 800:380)
        .sheet(isPresented:$choosingParent){CollectionLocationPicker(selection:$parentID,excludedID:original?.id)}
        .task(id:parentID) {
            if let parentID,let row=try? await Backend.call("get_collection",["collection_id":parentID]) { parentName=row["name"] as? String ?? "Collection Set" }
            else { parentName="None" }
        }
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
        }.padding(24).frame(width:520,height:710)
    }
}

struct MetadataEditor: View {
    @EnvironmentObject var s: Store
    @Environment(\.dismiss) private var dismiss
    let targets: [Photo]
    @State private var copyName: String
    @State private var title: String
    @State private var caption: String
    @State private var copyright: String
    @State private var iptcValues: [String:Any]
    @State private var keywords: String
    @State private var keywordIDs: [Int]?
    @State private var choosingKeywords=false
    @State private var label: String
    @State private var fields: Set<String>
    @State private var saving=false

    init(targets: [Photo]) {
        self.targets=targets
        let first=targets.first
        _copyName=State(initialValue:first?.copyName ?? "")
        _title=State(initialValue:first?.title ?? "")
        _caption=State(initialValue:first?.caption ?? "")
        _copyright=State(initialValue:first?.copyright ?? "")
        _iptcValues=State(initialValue:MetadataDraft.flatten(["iptc":first?.iptc ?? [:]]))
        _keywords=State(initialValue:first?.keywords.joined(separator:", ") ?? "")
        _keywordIDs=State(initialValue:first?.keywordsDeferred == true ? first?.keywordIDs:nil)
        _label=State(initialValue:first?.colorLabel ?? "none")
        _fields=State(initialValue:targets.count == 1 ? ["copy_name","title","caption","copyright","keywords","color_label"]:[])
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
                Toggle("Apply copy name",isOn:enabled("copy_name")); TextField("Copy name",text:$copyName).disabled(!fields.contains("copy_name"))
                Toggle("Apply title",isOn:enabled("title")); TextField("Title",text:$title).disabled(!fields.contains("title"))
                Toggle("Apply caption",isOn:enabled("caption")); TextField("Caption",text:$caption,axis:.vertical).lineLimit(3...5).disabled(!fields.contains("caption"))
                Toggle("Apply copyright",isOn:enabled("copyright")); TextField("Copyright",text:$copyright).disabled(!fields.contains("copyright"))
                Toggle("Apply keywords",isOn:enabled("keywords"))
                if let keywordIDs { Text("\(keywordIDs.count) existing keywords selected").font(.caption) }
                Button("Choose Existing Keywords…") { choosingKeywords=true }.disabled(!fields.contains("keywords"))
                TextField(keywordIDs == nil ? "Keywords, separated by commas":"Additional keyword paths, separated by commas",text:$keywords)
                    .disabled(!fields.contains("keywords"))
                Toggle("Apply color label",isOn:enabled("color_label"))
                Picker("Color label",selection:$label) {
                    ForEach(LibraryLabels.names,id:\.self) { Text($0.capitalized).tag($0) }
                }.disabled(!fields.contains("color_label"))
                MetadataFieldsEditor(fields:s.iptcFields,values:$iptcValues,selected:$fields)
            }.formStyle(.grouped)
            HStack {
                Button("Cancel",role:.cancel) { dismiss() }.keyboardShortcut(.cancelAction)
                Spacer()
                Button("Save Metadata") {
                    var patch: [String: Any] = [:]
                    for (key,value) in [("copy_name",copyName),("title",title),("caption",caption),("copyright",copyright),("color_label",label)] where fields.contains(key) { patch[key]=value }
                    patch.merge(MetadataDraft.patch(values:iptcValues,selected:fields,fields:s.iptcFields)) { _,new in new }
                    if fields.contains("keywords") {
                        if let keywordIDs {
                            patch.merge(metadataKeywordIdentityReplacement(keywordIDs,additions:keywords,original:targets.first?.keywordIDs ?? [],targetCount:targets.count)) { _,new in new }
                        } else if let values=metadataKeywordReplacement(keywords,original:targets.first?.keywords ?? [],targetCount:targets.count) {
                            patch["keywords"]=values
                        }
                    }
                    if patch.isEmpty { dismiss();return }
                    saving=true
                    Task { if await s.saveMetadata(targets:targets,patch:patch) { dismiss() }; saving=false }
                }.keyboardShortcut(.defaultAction).disabled(fields.isEmpty || saving)
            }
        }.padding(24).frame(width:560,height:720)
            .sheet(isPresented:$choosingKeywords) {
                KeywordSelectionSheet(ids:keywordIDs ?? targets.first?.keywordIDs ?? []) { ids in
                    if keywordIDs == nil,keywords == targets.first?.keywords.joined(separator:", ") { keywords="" }
                    keywordIDs=ids
                }
            }
    }
}
