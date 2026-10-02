// Purpose: bounded export-preset browsing and captured, non-destructive export drafts.
// Inputs: versioned preset replies and explicit file-panel or queue actions.
// Outputs: shared/catalog-local preset mutations and immutable export settings.
// Browsing, choosing and managing presets never queues jobs or writes photo files.
import AppKit
import Foundation
import SwiftUI

struct ExportPresetItem: Identifiable,Equatable {
    let id: String
    let name: String
    init?(_ row: [String:Any]) {
        guard let id=row["id"] as? String,let name=row["name"] as? String else { return nil }
        self.id=id;self.name=name
    }
}

struct ExportPresetPage {
    let revision: String
    let items: [ExportPresetItem]
    let total: Int
    let offset: Int
    let local: Bool
    let search: String
    init?(_ result: [String:Any],search: String) {
        guard let revision=result["revision"] as? String else { return nil }
        self.revision=revision
        items=(result["presets"] as? [[String:Any]] ?? []).compactMap(ExportPresetItem.init)
        total=result["total"] as? Int ?? 0;offset=result["offset"] as? Int ?? 0
        local=result["store_with_catalog"] as? Bool ?? false
        self.search=search
    }
}

struct ExportPresetSelection: Equatable {
    let id: String
    let name: String
    let revision: String
    let includesDestination: Bool
}

struct ExportPresetLoadReceipt {
    let selection: ExportPresetSelection
    let settings: [String:Any]
}

struct ExportDraft {
    var format="tiff16"
    var space="srgb"
    var maxEdge=0
    var quality=96
    var outputSharpen=0.0
    var name="{stem}-Luma-{seq}"
    var priority=0
    var metadata="catalog"
    var keywordHierarchy=false
    var destination=""
    var loadedPreset: ExportPresetSelection?

    var options: [String:Any] {
        ["space":space,"max_edge":maxEdge,"quality":quality,"output_sharpen":outputSharpen,
         "name":name,"priority":priority,"metadata":metadata,"keyword_hierarchy":keywordHierarchy]
    }

    func settings(includeDestination: Bool) -> [String:Any] {
        ["format":format,"options":options,
         "destination":includeDestination && !destination.isEmpty ? destination as Any:NSNull()]
    }

    mutating func apply(_ receipt: ExportPresetLoadReceipt) {
        let settings=receipt.settings
        let savedOptions=settings["options"] as? [String:Any] ?? [:]
        format=settings["format"] as? String ?? "tiff16"
        space=savedOptions["space"] as? String ?? "srgb"
        maxEdge=savedOptions["max_edge"] as? Int ?? 0
        quality=savedOptions["quality"] as? Int ?? 96
        outputSharpen=(savedOptions["output_sharpen"] as? NSNumber)?.doubleValue ?? 0
        name=savedOptions["name"] as? String ?? "{stem}-Luma-{seq}"
        priority=savedOptions["priority"] as? Int ?? 0
        metadata=savedOptions["metadata"] as? String ?? "catalog"
        keywordHierarchy=(savedOptions["keyword_hierarchy"] as? NSNumber)?.boolValue ?? false
        destination=settings["destination"] as? String ?? ""
        loadedPreset=receipt.selection
    }

    mutating func acknowledgeRename(_ renamed: ExportPresetSelection,sourceRevision: String) {
        guard let current=loadedPreset,current.id == renamed.id else { return }
        loadedPreset=ExportPresetSelection(id:current.id,name:renamed.name,
            revision:current.revision == sourceRevision ? renamed.revision:current.revision,
            includesDestination:current.includesDestination)
    }

    mutating func forgetDeletedPreset(_ id: String) {
        guard loadedPreset?.id == id else { return }
        loadedPreset=nil
    }
}

struct ExportPresetSaveSource: Identifiable {
    let id=UUID()
    let presetID: String?
    let expectedRevision: String
    let name: String
    let format: String
    let options: [String:Any]
    let destination: String
    let includeDestinationByDefault: Bool
}

struct ExportPresetMutationSource: Identifiable {
    let id=UUID()
    let item: ExportPresetItem
    let expectedRevision: String
}

enum ExportPresetEditorRoute: Identifiable {
    case save(ExportPresetSaveSource)
    case rename(ExportPresetMutationSource)

    var id: UUID {
        switch self {
        case .save(let source): return source.id
        case .rename(let source): return source.id
        }
    }
}

@MainActor final class ExportPresetLibraryModel: ObservableObject {
    @Published private(set) var page: ExportPresetPage?
    @Published var searchText=""
    @Published private(set) var appliedSearch=""
    @Published private(set) var loading=false
    @Published private(set) var loadingPreset=false
    @Published private(set) var mutating=false
    @Published var error: String?
    private(set) var listGeneration=0
    private(set) var getGeneration=0
    private var pendingSearch=""

    var busy: Bool { loading || loadingPreset || mutating }

    func refresh(offset requestedOffset: Int?=nil,search requestedSearch: String?=nil) async {
        listGeneration+=1
        let token=listGeneration
        let search=requestedSearch ?? appliedSearch
        let offset=max(0,requestedOffset ?? page?.offset ?? 0)
        pendingSearch=search
        loading=true
        defer { if listGeneration == token { loading=false } }
        do {
            let result=try await Backend.call("list_export_presets",["offset":offset,"search":search])
            _=receiveList(result,token:token,search:search)
        } catch {
            if token == listGeneration { self.error=error.localizedDescription }
        }
    }

    @discardableResult func receiveList(_ result: [String:Any],token: Int,search: String) -> Bool {
        guard token == listGeneration,pendingSearch == search else { return false }
        guard let next=ExportPresetPage(result,search:search) else {
            error="Export preset listing did not include its revision"
            return false
        }
        page=next;appliedSearch=search;error=nil
        return true
    }

    func saveSource(from draft: ExportDraft,updating: Bool) -> ExportPresetSaveSource? {
        let selected=draft.loadedPreset
        guard let revision=updating ? selected?.revision:page?.revision else {
            error=updating ? "Load an export preset before updating it.":"Reload the export preset list before saving."
            return nil
        }
        error=nil
        return ExportPresetSaveSource(presetID:updating ? selected?.id:nil,expectedRevision:revision,
            name:updating ? (selected?.name ?? ""):"",format:draft.format,options:draft.options,
            destination:draft.destination,includeDestinationByDefault:updating ? (selected?.includesDestination ?? false):false)
    }

    func mutationSource(for item: ExportPresetItem) -> ExportPresetMutationSource? {
        guard let page,page.items.contains(where:{$0.id == item.id}) else {
            error="Reload the export preset page before changing this preset."
            return nil
        }
        error=nil
        return ExportPresetMutationSource(item:item,expectedRevision:page.revision)
    }

    func load(_ item: ExportPresetItem) async -> ExportPresetLoadReceipt? {
        guard !busy,let capturedPage=page,capturedPage.items.contains(where:{$0.id == item.id}) else { return nil }
        getGeneration+=1
        let token=getGeneration
        let expectedRevision=capturedPage.revision
        let capturedListGeneration=listGeneration
        let capturedSearch=capturedPage.search
        let capturedOffset=capturedPage.offset
        loadingPreset=true
        defer { if getGeneration == token { loadingPreset=false } }
        do {
            let result=try await Backend.call("get_export_preset",["preset_id":item.id,"expected_revision":expectedRevision])
            return receivePreset(result,item:item,expectedRevision:expectedRevision,token:token,
                listToken:capturedListGeneration,search:capturedSearch,offset:capturedOffset)
        } catch {
            if token == getGeneration { self.error=error.localizedDescription }
            return nil
        }
    }

    @discardableResult func receivePreset(_ result: [String:Any],item: ExportPresetItem,
                                          expectedRevision: String,token: Int,listToken: Int?=nil,
                                          search: String?=nil,offset: Int?=nil) -> ExportPresetLoadReceipt? {
        guard token == getGeneration,(listToken == nil || listToken == listGeneration),
              page?.revision == expectedRevision,(search == nil || page?.search == search),
              (offset == nil || page?.offset == offset),
              page?.items.contains(where:{$0.id == item.id}) == true else { return nil }
        guard let row=result["preset"] as? [String:Any],let id=row["id"] as? String,
              id == item.id,let name=row["name"] as? String,
              let settings=row["settings"] as? [String:Any],let revision=result["revision"] as? String,
              revision == expectedRevision else {
            error="Export preset response was incomplete"
            return nil
        }
        let includesDestination=settings["destination"] as? String != nil
        error=nil
        return ExportPresetLoadReceipt(selection:ExportPresetSelection(id:id,name:name,revision:revision,
            includesDestination:includesDestination),settings:settings)
    }

    func invalidateReads() {
        listGeneration+=1;getGeneration+=1
        loading=false;loadingPreset=false
    }

    func save(_ source: ExportPresetSaveSource,name rawName: String,includeDestination: Bool) async -> ExportPresetSelection? {
        guard !mutating else { return nil }
        let name=rawName.trimmingCharacters(in:.whitespacesAndNewlines)
        guard !name.isEmpty else { error="Enter a preset name.";return nil }
        guard !includeDestination || !source.destination.isEmpty else {
            error="Choose an export folder before including it in this preset."
            return nil
        }
        mutating=true
        listGeneration+=1;getGeneration+=1
        let query=appliedSearch,offset=page?.offset ?? 0
        defer { mutating=false }
        var params:[String:Any]=["name":name,"settings":["format":source.format,"options":source.options,
            "destination":includeDestination ? source.destination as Any:NSNull()],"expected_revision":source.expectedRevision]
        if let presetID=source.presetID { params["preset_id"]=presetID }
        do {
            let result=try await Backend.call("save_export_preset",params)
            guard let id=result["preset_id"] as? String,let revision=result["revision"] as? String else {
                error="Saved export preset response was incomplete"
                return nil
            }
            error=nil
            await refresh(offset:offset,search:query)
            return ExportPresetSelection(id:id,name:name,revision:revision,includesDestination:includeDestination)
        } catch { self.error=error.localizedDescription;return nil }
    }

    func rename(_ source: ExportPresetMutationSource,name rawName: String) async -> ExportPresetSelection? {
        let name=rawName.trimmingCharacters(in:.whitespacesAndNewlines)
        guard !name.isEmpty else { error="Enter a preset name.";return nil }
        let result=await mutate("rename",source:source,values:["preset_id":source.item.id,"name":name])
        guard let result,let revision=result["revision"] as? String else { return nil }
        return ExportPresetSelection(id:source.item.id,name:name,revision:revision,includesDestination:false)
    }

    func delete(_ source: ExportPresetMutationSource) async -> Bool {
        await mutate("delete",source:source,values:["preset_id":source.item.id]) != nil
    }

    func setStorage(_ storeWithCatalog: Bool,expectedRevision: String) async -> Bool {
        await mutate("storage",expectedRevision:expectedRevision,values:["store_with_catalog":storeWithCatalog]) != nil
    }

    private func mutate(_ action: String,source: ExportPresetMutationSource?=nil,
                        expectedRevision: String?=nil,values: [String:Any]) async -> [String:Any]? {
        guard !mutating else { return nil }
        guard let revision=source?.expectedRevision ?? expectedRevision else {
            error="Reload export preset settings before trying again."
            return nil
        }
        mutating=true
        listGeneration+=1;getGeneration+=1
        let query=appliedSearch,offset=page?.offset ?? 0
        defer { mutating=false }
        do {
            let params=values.merging(["action":action,"expected_revision":revision]) { _,new in new }
            let result=try await Backend.call("export_preset_action",params)
            error=nil
            await refresh(offset:offset,search:query)
            return result
        } catch { self.error=error.localizedDescription;return nil }
    }
}

@MainActor struct ExportPresetBrowserSheet: View {
    @Environment(\.dismiss) private var dismiss
    @Binding var draft: ExportDraft
    @StateObject private var model: ExportPresetLibraryModel
    @State private var editorRoute: ExportPresetEditorRoute?
    @State private var deleteSource: ExportPresetMutationSource?

    init(draft: Binding<ExportDraft>,model: ExportPresetLibraryModel?=nil) {
        _draft=draft
        _model=StateObject(wrappedValue:model ?? ExportPresetLibraryModel())
    }

    var body: some View {
        VStack(alignment:.leading,spacing:14) {
            HStack { Text("Export Presets").font(.title2);Spacer();Button("Close") {
                model.invalidateReads()
                dismiss()
            } }
            if let page=model.page {
                Text(page.local ? "New presets are saved with this catalog. Existing presets stay where they were saved."
                                :"New presets are saved in the shared library. Switching storage never moves existing presets.")
                    .font(.caption).foregroundStyle(.secondary)
            }
            HStack {
                TextField("Search presets",text:$model.searchText).onSubmit { Task { await model.refresh(offset:0,search:model.searchText) } }
                    .disabled(model.busy)
                Button("Search") { Task { await model.refresh(offset:0,search:model.searchText) } }.disabled(model.busy)
                Button("Reload") { Task { await model.refresh() } }.disabled(model.busy)
            }
            if let error=model.error { Text(error).font(.caption).foregroundStyle(.red) }
            Group {
                if let page=model.page {
                    ScrollView {
                        LazyVStack(alignment:.leading,spacing:3) {
                            ForEach(page.items) { item in
                                HStack {
                                    Text(item.name).lineLimit(1)
                                    Spacer()
                                    Button("Use") { Task {
                                        if let receipt=await model.load(item) { draft.apply(receipt);dismiss() }
                                    } }.disabled(model.busy)
                                    Menu("More") {
                                        Button("Rename…") {
                                            if let source=model.mutationSource(for:item) { editorRoute = .rename(source) }
                                        }
                                        Button("Delete…",role:.destructive) { deleteSource=model.mutationSource(for:item) }
                                    }.disabled(model.busy)
                                }.padding(.vertical,3)
                            }
                        }
                    }
                    HStack {
                        Button("Previous") { Task { await model.refresh(offset:max(0,page.offset-30)) } }
                            .disabled(page.offset==0 || model.busy)
                        Text("\(page.total == 0 ? 0:page.offset+1)–\(min(page.offset+page.items.count,page.total)) of \(page.total)")
                            .font(.caption).foregroundStyle(.secondary)
                        Button("Next") { Task { await model.refresh(offset:page.offset+30) } }
                            .disabled(page.offset+30>=page.total || model.busy)
                        Spacer()
                        if model.loading || model.loadingPreset { ProgressView().controlSize(.small) }
                    }
                } else if model.loading { ProgressView("Loading export presets…").frame(maxWidth:.infinity,maxHeight:.infinity) }
                else { ContentUnavailableView("No Export Presets",systemImage:"square.and.arrow.up",description:Text("Save your current export options to reuse them.")) }
            }
            HStack {
                Button("Save Current as New…") {
                    if let source=model.saveSource(from:draft,updating:false) { editorRoute = .save(source) }
                }
                    .disabled(model.busy || model.page == nil)
                if draft.loadedPreset != nil {
                    Button("Update Current Preset…") {
                        if let source=model.saveSource(from:draft,updating:true) { editorRoute = .save(source) }
                    }
                        .disabled(model.busy)
                }
                Spacer()
                Text(draft.loadedPreset.map { "Loaded: \($0.name)" } ?? "Current export options")
                    .font(.caption).foregroundStyle(.secondary).lineLimit(1)
            }
        }
        .padding(22).frame(width:700,height:600)
        .task { if model.page == nil { await model.refresh(offset:0,search:model.searchText) } }
        .sheet(item:$editorRoute) { route in
            switch route {
            case .save(let source):
                ExportPresetSaveSheet(source:source,model:model,draft:$draft)
            case .rename(let source):
                ExportPresetRenameSheet(source:source,model:model,draft:$draft)
            }
        }
        .onDisappear { model.invalidateReads() }
        .confirmationDialog("Delete \(deleteSource?.item.name ?? "Export Preset")?",isPresented:Binding(
            get:{deleteSource != nil},set:{if !$0 { deleteSource=nil }})) {
            Button("Delete Preset",role:.destructive) {
                guard let source=deleteSource else { return }
                Task {
                    if await model.delete(source) {
                        draft.forgetDeletedPreset(source.item.id)
                        deleteSource=nil
                    }
                }
            }.disabled(model.busy)
            Button("Cancel",role:.cancel) { deleteSource=nil }
        } message: { Text("Only the preset is removed. Existing export jobs keep their submitted settings.") }
    }
}

@MainActor struct ExportPresetSaveSheet: View {
    @Environment(\.dismiss) private var dismiss
    @ObservedObject var model: ExportPresetLibraryModel
    @Binding var draft: ExportDraft
    let source: ExportPresetSaveSource
    @State private var name: String
    @State private var includeDestination: Bool

    init(source: ExportPresetSaveSource,model: ExportPresetLibraryModel,draft: Binding<ExportDraft>) {
        self.source=source;self.model=model;_draft=draft
        _name=State(initialValue:source.name)
        _includeDestination=State(initialValue:source.includeDestinationByDefault)
    }

    var body: some View {
        VStack(alignment:.leading,spacing:16) {
            Text(source.presetID == nil ? "Save Export Preset":"Update Export Preset").font(.title2)
            TextField("Preset Name",text:$name).disabled(source.presetID != nil)
            Toggle("Include export folder",isOn:$includeDestination)
            Text(source.destination.isEmpty ? "No export folder is selected." : source.destination)
                .font(.caption).foregroundStyle(.secondary).lineLimit(2).textSelection(.enabled)
            Text("The preset stores export options and an optional folder. It does not store photos, edits, or queue jobs.")
                .font(.caption).foregroundStyle(.secondary)
            if let error=model.error { Text(error).font(.caption).foregroundStyle(.red) }
            HStack {
                Button("Cancel") { dismiss() }.keyboardShortcut(.cancelAction).disabled(model.mutating)
                Spacer()
                Button("Save") { Task {
                    if let selection=await model.save(source,name:name,includeDestination:includeDestination) {
                        draft.loadedPreset=selection;dismiss()
                    }
                } }.buttonStyle(.borderedProminent).keyboardShortcut(.defaultAction)
                    .disabled(model.mutating || model.loading || model.loadingPreset || name.trimmingCharacters(in:.whitespacesAndNewlines).isEmpty || (includeDestination && source.destination.isEmpty))
            }
        }.padding(22).frame(width:500)
    }
}

@MainActor struct ExportPresetRenameSheet: View {
    @Environment(\.dismiss) private var dismiss
    @ObservedObject var model: ExportPresetLibraryModel
    @Binding var draft: ExportDraft
    let source: ExportPresetMutationSource
    @State private var name: String

    init(source: ExportPresetMutationSource,model: ExportPresetLibraryModel,draft: Binding<ExportDraft>) {
        self.source=source;self.model=model;_draft=draft
        _name=State(initialValue:source.item.name)
    }

    var body: some View {
        VStack(alignment:.leading,spacing:16) {
            Text("Rename Export Preset").font(.title2)
            TextField("Preset Name",text:$name)
            if let error=model.error { Text(error).font(.caption).foregroundStyle(.red) }
            HStack {
                Button("Cancel") { dismiss() }.keyboardShortcut(.cancelAction).disabled(model.mutating)
                Spacer()
                Button("Rename") { Task {
                    if let renamed=await model.rename(source,name:name) {
                        draft.acknowledgeRename(renamed,sourceRevision:source.expectedRevision)
                        dismiss()
                    }
                } }.buttonStyle(.borderedProminent).keyboardShortcut(.defaultAction)
                    .disabled(model.busy || name.trimmingCharacters(in:.whitespacesAndNewlines).isEmpty)
            }
        }.padding(22).frame(width:440)
    }
}

@MainActor struct ExportPresetSettingsSection: View {
    @StateObject private var model: ExportPresetLibraryModel
    init(model: ExportPresetLibraryModel?=nil) {
        _model=StateObject(wrappedValue:model ?? ExportPresetLibraryModel())
    }

    var body: some View {
        Section("Export Presets") {
            if let page=model.page {
                Toggle("Store Export Presets with This Catalog",isOn:Binding(get:{page.local},set:{value in
                    Task { _=await model.setStorage(value,expectedRevision:page.revision) }
                })).disabled(model.busy)
                Text(page.local ? "New presets use this catalog's storage. Existing presets stay where they were saved."
                                :"New presets use shared storage. Existing presets stay where they were saved.")
                    .font(.caption).foregroundStyle(.secondary)
            } else if model.loading { ProgressView("Loading export preset settings…") }
            if let error=model.error { Text(error).font(.caption).foregroundStyle(.red) }
            Button("Reload Export Preset Settings") { Task { await model.refresh(offset:0,search:"") } }
                .disabled(model.busy)
        }.task { if model.page == nil { await model.refresh(offset:0,search:"") } }
    }
}
