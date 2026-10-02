// Purpose: native lazy collection hierarchy, color labels and Quick-save forms.
// Inputs: bounded Store pages and captured revision-bearing collection values.
// Outputs: explicit create/move/open/label/membership actions. No eager tree load
// or photo deletion; set deletion confirms its contained collections are removed.
import SwiftUI

struct CollectionsSidebar: View {
    @EnvironmentObject var s: Store
    @State private var clearing: LibraryCollection?
    var body: some View {
        Section("Collections") {
            if let state=s.collectionState {
                Button { Task { await s.openCollection(state.quick) } } label: {
                    Label("Quick Collection\(state.target.id == state.quick.id ? " +":"")",systemImage:"circle.dashed")
                }.contextMenu {
                    Button("Set as Target Collection") { Task { await s.setTargetCollection(nil) } }
                    Button("Save Quick Collection…") { s.quickSaveSource=state.quick;s.showQuickSave=true }
                    Button("Clear Quick Collection…") { clearing=state.quick }
                }
            }
            Menu {
                Button("New Collection…") { s.editCollection() }
                Button("New Smart Collection…") { s.editCollection(kind:"smart") }
                Button("New Collection Set…") { s.editCollection(kind:"set") }
            } label: { Label("New Collection",systemImage:"plus") }.menuStyle(.borderlessButton)
            Menu {
                Menu("Filter Collections") {
                    collectionFilterOption("Any Color","any")
                    collectionFilterOption("Labeled","labeled")
                    collectionFilterOption("No Label","none")
                    Divider()
                    ForEach(["red","yellow","green","blue","purple"],id:\.self) { label in
                        collectionFilterOption(label.capitalized,label)
                    }
                }
                Button("Label Multiple Collections…") { s.showCollectionLabelBatch=true }
            } label: {
                Label(s.collectionColorFilter == "any" ? "Collection Labels":"Labels · \(collectionFilterTitle)",
                    systemImage:"tag")
            }.menuStyle(.borderlessButton)
            if s.collectionColorFilter == "any" { CollectionBranch(parent:nil) }
            else { CollectionColorFilteredBranch() }
        }
        .sheet(isPresented:$s.showCollectionLabelBatch) { CollectionLabelBatchSheet().environmentObject(s) }
        .confirmationDialog("Clear Quick Collection?",isPresented:Binding(get:{clearing != nil},set:{if !$0 { clearing=nil }})) {
            Button("Clear Quick Collection",role:.destructive) {
                if let collection=clearing { Task { await s.clearQuickCollection(collection) } }
                clearing=nil
            }
        } message: { Text("Only Quick Collection membership is cleared. Photos remain in the library.") }
    }

    private var collectionFilterTitle: String {
        s.collectionColorFilter == "labeled" ? "Labeled" : s.collectionColorFilter == "none" ? "No Label" : s.collectionColorFilter.capitalized
    }

    private func collectionFilterOption(_ title: String,_ value: String) -> some View {
        Button {
            Task { await s.setCollectionColorFilter(value) }
        } label: {
            HStack {
                Text(title)
                if s.collectionColorFilter == value { Image(systemName:"checkmark") }
            }
        }
    }
}

struct CollectionColorFilteredBranch: View {
    @EnvironmentObject var s: Store
    var body: some View {
        if let page=s.collectionFilteredPage {
            ForEach(page.items) { collection in CollectionColorFilteredRow(collection:collection) }
            if page.items.isEmpty { Text("No collections match this color label.").font(.caption).foregroundStyle(.secondary) }
            if page.total>60 {
                HStack {
                    Button("Previous") { Task { await s.turnCollectionColorFilterPage(offset:max(0,page.offset-60)) } }.disabled(page.offset==0)
                    Spacer()
                    Button("Next") { Task { await s.turnCollectionColorFilterPage(offset:page.offset+60) } }.disabled(page.offset+60>=page.total)
                }.font(.caption)
            }
        } else { ProgressView().controlSize(.small) }
    }
}

struct CollectionColorFilteredRow: View {
    let collection: LibraryCollection
    var body: some View {
        CollectionTreeRow(collection:collection,allowsExpansion:false)
    }
}

struct CollectionLabelMenu: View {
    @EnvironmentObject var s: Store
    let collection: LibraryCollection
    var body: some View {
        Menu("Color Label") {
            ForEach(LibraryLabels.names,id:\.self) { label in
                Button {
                    Task { _=await s.setCollectionColorLabel(collection,colorLabel:label) }
                } label: {
                    HStack {
                        CollectionColorMark(label:label)
                        Text(label.capitalized)
                        if collection.colorLabel == label { Image(systemName:"checkmark") }
                    }
                }
            }
        }.disabled(collection.kind == "quick")
    }
}

struct CollectionBranch: View {
    @EnvironmentObject var s: Store
    let parent: Int?
    var body: some View {
        if let page=s.collectionPages[parent ?? 0] {
            ForEach(page.items) { collection in CollectionTreeRow(collection:collection) }
            if page.total>60 {
                HStack {
                    Button("Previous") { Task { await s.turnCollectionPage(parent:parent,offset:max(0,page.offset-60)) } }.disabled(page.offset==0)
                    Spacer()
                    Button("Next") { Task { await s.turnCollectionPage(parent:parent,offset:page.offset+60) } }.disabled(page.offset+60>=page.total)
                }.font(.caption)
            }
            if page.items.isEmpty,parent != nil { Text("Empty set").font(.caption).foregroundStyle(.secondary) }
        } else { ProgressView().controlSize(.small) }
    }
}

struct CollectionTreeRow: View {
    @EnvironmentObject var s: Store
    let collection: LibraryCollection
    var allowsExpansion=true
    @State private var deleting=false
    var body: some View {
        Group {
            if collection.kind == "set",allowsExpansion {
                DisclosureGroup(isExpanded:Binding(get:{s.expandedCollections.contains(collection.id)},set:{ value in
                    if value { s.expandCollection(collection.id) } else { s.collapseCollection(collection.id) }
                })) { AnyView(CollectionBranch(parent:collection.id)) } label: { openButton }
            } else { openButton }
        }
        .contextMenu {
            Button("Edit / Move…") { s.editCollection(collection) }
            CollectionLabelMenu(collection:collection)
            Button("Duplicate") { Task { await s.duplicateCollection(collection) } }
            if collection.kind == "set" {
                Button("New Collection Inside…") { s.editCollection(parent:collection.id) }
                Button("New Set Inside…") { s.editCollection(kind:"set",parent:collection.id) }
            }
            if collection.kind == "regular" {
                Button(s.collectionState?.target.id == collection.id ? "Reset Target to Quick Collection":"Set as Target Collection") {
                    Task { await s.setTargetCollection(s.collectionState?.target.id == collection.id ? nil:collection) }
                }
                Button("Add Selected Photos") { Task { await s.changeMembership(collection,action:"add") } }.disabled(s.selection.isEmpty)
                Button("Remove Selected Photos") { Task { await s.changeMembership(collection,action:"remove") } }.disabled(s.selection.isEmpty)
            }
            Button("Delete…",role:.destructive) { deleting=true }
        }
        .confirmationDialog("Delete \(collection.name)?",isPresented:$deleting) {
            Button("Delete \(collection.kind == "set" ? "Set and Contained Collections":"Collection")",role:.destructive) {
                Task { await s.deleteCollection(collection) }
            }
        } message: {
            Text(collection.kind == "set" ? "This removes the set, all nested collections and their memberships. All photos and originals remain in the library.":"All photos and originals remain in the library.")
        }
    }
    var openButton: some View {
        Button { Task { await s.openCollection(collection) } } label: {
            HStack {
                VStack(alignment:.leading,spacing:2) {
                    Label(collection.name,systemImage:collection.symbol).lineLimit(1)
                    if !allowsExpansion {
                        Text(collection.parentName.map { "In \($0)" } ?? "Top Level")
                            .font(.caption).foregroundStyle(.secondary).lineLimit(1)
                    }
                }
                Spacer(minLength:2)
                CollectionColorMark(label:collection.colorLabel)
                if s.collectionState?.target.id == collection.id { Image(systemName:"plus").help("Target Collection") }
                if s.collectionID == collection.id { Image(systemName:"checkmark").font(.caption) }
            }
        }.accessibilityAddTraits(s.collectionID == collection.id ? .isSelected:[])
            .help("Open \(collection.name) · \(collection.colorLabel == "none" ? "No color label":"\(collection.colorLabel.capitalized) color label")")
            .accessibilityLabel("\(collection.name), \(collection.kind), \(collection.colorLabel == "none" ? "no color label":"\(collection.colorLabel.capitalized) color label")")
            .accessibilityValue(allowsExpansion ? "":collection.parentName.map { "In \($0)" } ?? "Top Level")
    }
}

struct CollectionLocationPicker: View {
    @Environment(\.dismiss) private var dismiss
    @Binding var selection: Int?
    var excludedID: Int? = nil
    @State private var path: [LibraryCollection] = []
    @State private var items: [LibraryCollection] = []
    @State private var offset=0
    @State private var total=0
    @State private var loading=false
    @State private var error: String?
    var body: some View {
        VStack(alignment:.leading,spacing:12) {
            Text("Choose Collection Set").font(.title2)
            HStack {
                Button("Back") { if !path.isEmpty { path.removeLast();offset=0;Task { await load() } } }.disabled(path.isEmpty || loading)
                Text(path.map(\.name).joined(separator:" / ").isEmpty ? "Root":path.map(\.name).joined(separator:" / ")).lineLimit(2)
            }
            List(items.filter { $0.kind == "set" }) { row in
                Button { path.append(row);offset=0;Task { await load() } } label: { Label(row.name,systemImage:"folder") }.disabled(loading || row.id == excludedID)
            }
            if let error { Text(error).font(.caption).foregroundStyle(.red) }
            HStack {
                Button("Previous") { offset=max(0,offset-60);Task { await load() } }.disabled(offset==0 || loading)
                Button("Next") { offset+=60;Task { await load() } }.disabled(offset+60>=total || loading)
                Spacer()
                Button("Cancel",role:.cancel) { dismiss() }
                Button(path.isEmpty ? "Use Root":"Use This Set") { selection=path.last?.id;dismiss() }.disabled(loading || error != nil)
            }
        }.padding(20).frame(width:450,height:400).task { await load() }
    }
    func load() async {
        loading=true;defer { loading=false }
        do {
            let row=try await Backend.call("list_collections",["parent_id":path.last?.id as Any? ?? NSNull(),"offset":offset])
            items=(row["collections"] as? [[String:Any]] ?? []).compactMap(LibraryCollection.init)
            total=row["total"] as? Int ?? 0;offset=row["offset"] as? Int ?? 0;error=nil
        } catch { self.error=error.localizedDescription }
    }
}

struct QuickCollectionSheet: View {
    @EnvironmentObject var s: Store
    @Environment(\.dismiss) private var dismiss
    let source: LibraryCollection
    @State private var name=""
    @State private var clear=false
    @State private var saving=false
    var body: some View {
        VStack(alignment:.leading,spacing:16) {
            Text("Save Quick Collection").font(.title2)
            TextField("Collection name",text:$name)
            Toggle("Clear Quick Collection after saving",isOn:$clear)
            HStack {
                Button("Cancel",role:.cancel) { dismiss() };Spacer()
                Button("Save") {
                    saving=true
                    Task { if await s.saveQuickCollection(source,name:name,clear:clear) { dismiss() };saving=false }
                }.keyboardShortcut(.defaultAction).disabled(saving || name.trimmingCharacters(in:.whitespaces).isEmpty)
            }
        }.padding(24).frame(width:440)
    }
}

struct TargetCollectionBadge: View {
    @EnvironmentObject var s: Store
    let photoID: Int
    var body: some View {
        if let state=s.collectionState {
            Button { Task { await s.toggleTargetMembership(ids:[photoID]) } } label: {
                Image(systemName:state.members.contains(photoID) ? "circle.inset.filled":"circle")
                    .foregroundStyle(.white).padding(5).background(.black.opacity(0.4),in:Circle())
            }.buttonStyle(.plain).help("\(state.members.contains(photoID) ? "Remove from":"Add to") \(state.target.name)")
                .accessibilityLabel("\(state.members.contains(photoID) ? "Remove photo from":"Add photo to") \(state.target.name)")
        }
    }
}
