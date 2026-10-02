// Purpose: bounded native collection color-label browsing and batch assignment.
// Inputs: flat collection pages and captured per-collection revisions.
// Outputs: explicit filters, labels and atomic label commands; no tree-wide load.
// Reloading never rebases captured targets; changed rows require explicit reselection.
import SwiftUI

@MainActor final class CollectionLabelBatchModel: ObservableObject {
    @Published var page: CollectionPage?
    @Published var filter="all"
    @Published var label="red"
    @Published var selected: [Int:LibraryCollection]=[:]
    @Published var loading=false
    @Published var applying=false
    @Published var conflictNeedsReselect=false
    @Published var error: String?
    private var generation=0

    var selectedTargets: [LibraryCollection] { selected.values.sorted { $0.id < $1.id } }

    func load(using store: Store,offset requested: Int?=nil) async {
        guard !applying else { return }
        generation+=1;let token=generation
        loading=true
        defer { if generation == token { loading=false } }
        var params: [String:Any] = ["offset":requested ?? page?.offset ?? 0]
        if filter != "all" { params["color_label"]=filter }
        do {
            let result=try await Backend.call("list_collections",params)
            guard generation == token else { return }
            guard let treeRevision=result["tree_revision"] as? Int else {
                error="Collection listing did not include its tree revision"
                return
            }
            guard treeRevision >= store.collectionTreeRevision else {
                error="Collections changed while this page was loading. Reload before choosing more targets."
                return
            }
            store.observeCollectionTreeRevision(treeRevision)
            page=CollectionPage(items:(result["collections"] as? [[String:Any]] ?? []).compactMap(LibraryCollection.init),
                offset:result["offset"] as? Int ?? 0,total:result["total"] as? Int ?? 0,treeRevision:treeRevision)
            self.error=nil
        } catch {
            guard generation == token else { return }
            self.error=error.localizedDescription
        }
    }

    func setFilter(_ value: String,using store: Store) async {
        guard !applying else { return }
        guard ["all","labeled","none","red","yellow","green","blue","purple"].contains(value) else { return }
        guard filter != value else { return }
        filter=value
        page=nil
        await load(using:store,offset:0)
    }

    func turnPage(_ offset: Int,using store: Store) async {
        await load(using:store,offset:max(0,offset))
    }

    func toggle(_ collection: LibraryCollection) {
        guard !applying else { return }
        error=nil
        if selected[collection.id] != nil {
            selected.removeValue(forKey:collection.id)
            return
        }
        guard collection.kind != "quick" else {
            error="Quick Collection cannot receive a color label."
            return
        }
        guard selected.count < 60 else {
            error="Select at most 60 collections per change."
            return
        }
        selected[collection.id]=collection
    }

    func apply(using store: Store) async -> Bool {
        guard !applying,!selected.isEmpty else { return false }
        applying=true;defer { applying=false }
        let captured=selectedTargets
        let capturedLabel=label
        let applied=await store.setCollectionColorLabels(captured,colorLabel:capturedLabel)
        if !applied {
            let reason=store.error ?? "The collection labels could not be updated."
            error=reason
            conflictNeedsReselect=reason.localizedCaseInsensitiveContains("conflict") || reason.localizedCaseInsensitiveContains("stale")
        } else { error=nil;conflictNeedsReselect=false }
        return applied
    }
}

@MainActor struct CollectionLabelBatchSheet: View {
    @EnvironmentObject var s: Store
    @Environment(\.dismiss) private var dismiss
    @StateObject private var model: CollectionLabelBatchModel

    init(model: CollectionLabelBatchModel? = nil) {
        _model=StateObject(wrappedValue:model ?? CollectionLabelBatchModel())
    }

    var body: some View {
        VStack(alignment:.leading,spacing:12) {
            Text("Label Multiple Collections").font(.title2)
            Text("Choose up to 60 collections. Changes apply together; if a collection changes elsewhere, review your selection before trying again.")
                .font(.callout).foregroundStyle(.secondary)
            HStack {
                Picker("Show",selection:Binding(get:{model.filter},set:{value in Task { await model.setFilter(value,using:s) }})) {
                    Text("All Collections").tag("all")
                    Text("Labeled").tag("labeled")
                    ForEach(LibraryLabels.names,id:\.self) { Text($0.capitalized).tag($0) }
                }.frame(width:190).disabled(model.applying || model.loading)
                Picker("Apply Label",selection:$model.label) {
                    ForEach(LibraryLabels.names,id:\.self) { Text($0.capitalized).tag($0) }
                }.frame(width:190).disabled(model.applying)
                Spacer()
                Button("Reload Page") { Task { await model.load(using:s) } }.disabled(model.loading || model.applying)
            }
            HStack {
                Text("Selected \(model.selected.count) of 60").font(.caption).foregroundStyle(.secondary)
                Spacer()
                Button("Clear Selection") { model.selected.removeAll();model.conflictNeedsReselect=false }.disabled(model.selected.isEmpty || model.applying)
            }
            if !model.selectedTargets.isEmpty {
                ScrollView(.horizontal) {
                    HStack(spacing:6) {
                        ForEach(model.selectedTargets) { collection in
                            HStack(spacing:5) {
                                CollectionColorMark(label:collection.colorLabel)
                                VStack(alignment:.leading,spacing:1) {
                                    Text(collection.name).lineLimit(1)
                                    Text(collection.parentName ?? collection.parentID.map { "Set #\($0)" } ?? "Top Level")
                                        .font(.caption2).foregroundStyle(.secondary).lineLimit(1)
                                }
                                Button { model.selected.removeValue(forKey:collection.id) } label: {
                                    Image(systemName:"xmark.circle.fill")
                                }.buttonStyle(.plain).disabled(model.applying).help("Remove \(collection.name) from this change")
                            }.font(.caption).padding(.horizontal,8).padding(.vertical,5)
                                .background(.quaternary,in:Capsule())
                        }
                    }
                }.frame(height:28)
            }
            if let error=model.error {
                Text(error).font(.caption).foregroundStyle(.red)
            }
            if model.conflictNeedsReselect {
                Text("Reload the page, then remove and reselect changed collections. Reloading does not update captured selections.")
                    .font(.caption).foregroundStyle(.secondary)
            }
            Group {
                if let page=model.page {
                    ScrollView {
                        LazyVStack(alignment:.leading,spacing:2) {
                            ForEach(page.items) { collection in
                                collectionRow(collection)
                            }
                        }.frame(maxWidth:.infinity,alignment:.leading)
                    }
                    HStack {
                        Button("Previous") { Task { await model.turnPage(max(0,page.offset-60),using:s) } }
                            .disabled(page.offset==0 || model.loading || model.applying)
                        Text("\(page.total == 0 ? 0:page.offset+1)–\(min(page.offset+page.items.count,page.total)) of \(page.total)")
                            .font(.caption).foregroundStyle(.secondary)
                        Button("Next") { Task { await model.turnPage(page.offset+60,using:s) } }
                            .disabled(page.offset+60>=page.total || model.loading || model.applying)
                        Spacer()
                        if model.loading { ProgressView().controlSize(.small) }
                    }
                } else {
                    ProgressView("Loading collections…").frame(maxWidth:.infinity,maxHeight:.infinity)
                }
            }
            HStack {
                Button("Cancel",role:.cancel) { dismiss() }.keyboardShortcut(.cancelAction).disabled(model.applying)
                Spacer()
                Button("Apply Label to \(model.selected.count) Collections") {
                    Task { if await model.apply(using:s) { dismiss() } }
                }.keyboardShortcut(.defaultAction).disabled(model.selected.isEmpty || model.loading || model.applying)
            }
        }
        .padding(20).frame(width:680,height:700)
        .task { if model.page == nil { await model.load(using:s) } }
    }

    @ViewBuilder private func collectionRow(_ collection: LibraryCollection) -> some View {
        let selected=model.selected[collection.id] != nil
        Button { model.toggle(collection) } label: {
            HStack(spacing:8) {
                Image(systemName:selected ? "checkmark.square.fill":"square")
                    .foregroundStyle(selected ? Color.accentColor:Color.secondary)
                CollectionColorMark(label:collection.colorLabel)
                VStack(alignment:.leading,spacing:1) {
                    Text(collection.name).lineLimit(1)
                    Text(collection.parentName ?? collection.parentID.map { "Set #\($0)" } ?? "Top Level")
                        .font(.caption2).foregroundStyle(.secondary).lineLimit(1)
                }
                Spacer()
                Text(collection.kind == "set" ? "Set":collection.kind == "smart" ? "Smart Collection":collection.kind == "quick" ? "Quick Collection":"Collection")
                    .font(.caption).foregroundStyle(.secondary)
            }.contentShape(Rectangle()).padding(.vertical,4)
        }.buttonStyle(.plain)
            .disabled(collection.kind == "quick" || model.loading || model.applying || (!selected && model.selected.count>=60))
            .help(collection.kind == "quick" ? "Quick Collection cannot receive a color label.":"Select \(collection.name) for the captured label change")
            .accessibilityLabel("\(selected ? "Selected":"Select") \(collection.kind) \(collection.name), color label \(collection.colorLabel)")
    }
}

struct CollectionColorMark: View {
    let label: String
    var body: some View {
        Circle().fill(label == "none" ? Color.clear:LibraryLabels.color(label))
            .overlay(Circle().stroke(label == "none" ? Color.secondary.opacity(0.55):Color.clear,lineWidth:1))
            .frame(width:9,height:9)
            .help(label == "none" ? "No color label":"\(label.capitalized) color label")
            .accessibilityLabel(label == "none" ? "No color label":"\(label.capitalized) color label")
    }
}
