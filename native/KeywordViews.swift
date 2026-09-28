// Purpose: native keyword list, assignment controls and hierarchy editing forms.
// Inputs: bounded keyword pages and captured revisions. Outputs: explicit catalog
// actions. Parent picking is lazy and paged; original files are never rewritten.
// Editing and parent selection resolve complete revision-bound keyword details.
import SwiftUI

struct KeywordsSidebar: View {
    @EnvironmentObject var s: Store
    var body: some View {
        Section("Keyword List") {
            HStack {
                TextField("Filter Keywords",text:Binding(get:{s.keywordSearch},set:{s.keywordSearch=$0;s.scheduleKeywordSearch()}))
                    .textFieldStyle(.roundedBorder)
                Menu {
                    Button("Create Keyword…") { Task { await s.editKeyword() } }
                    Button("Refresh Keywords") { Task { await s.refreshKeywords() } }
                    Divider()
                    KeywordExchangeActions().environmentObject(s)
                } label: { Image(systemName:"plus") }.help("Keyword Options")
                    .disabled(s.keywordRevision < 0 || s.keywordBusy || s.keywordEditorLoading)
                if s.keywordEditorLoading { ProgressView().controlSize(.small).help("Reading keyword details") }
            }
            KeywordBranch(parent:nil)
            Text("Counts show directly tagged photos. Show Photos includes nested keywords.")
                .font(.caption2).foregroundStyle(.secondary)
        }
        .task(id:s.keywordSelectionKey) { await s.refreshKeywords() }
    }
}

struct KeywordBranch: View {
    @EnvironmentObject var s: Store
    let parent: Int?
    var body: some View {
        if let page=s.keywordPages[parent ?? 0] {
            ForEach(page.items) { KeywordTreeRow(keyword:$0) }
            if page.items.isEmpty { Text("No keywords").font(.caption).foregroundStyle(.secondary) }
            if page.total > 60 {
                HStack {
                    Button("Previous") { Task { await s.turnKeywordPage(parent:parent,offset:max(0,page.offset-60)) } }
                        .disabled(page.offset == 0)
                    Text("\(page.offset+1)–\(min(page.offset+60,page.total))").monospacedDigit()
                    Button("Next") { Task { await s.turnKeywordPage(parent:parent,offset:page.offset+60) } }
                        .disabled(page.offset+60 >= page.total)
                }.font(.caption)
            }
        } else { ProgressView().controlSize(.small) }
    }
}

struct KeywordTreeRow: View {
    @EnvironmentObject var s: Store
    let keyword: LibraryKeyword
    @State private var deleting=false
    var allSelected: Bool { !keyword.selection.isEmpty && keyword.selectedCount == keyword.selection.count }
    var body: some View {
        Group {
            if keyword.hasChildren && s.keywordSearch.isEmpty {
                DisclosureGroup(isExpanded:Binding(get:{s.expandedKeywords.contains(keyword.id)},set:{value in
                    if value { s.expandedKeywords.insert(keyword.id);Task { await s.loadKeywordPage(parent:keyword.id) } }
                    else { s.collapseKeyword(keyword.id) }
                })) { AnyView(KeywordBranch(parent:keyword.id)) } label: { row }
            } else { row }
        }
        .contextMenu {
            Button("Show Photos") { Task { await s.showKeywordPhotos(keyword) } }
            Button("Edit Keyword…") { Task { await s.editKeyword(keyword) } }
            Button("Create Keyword Inside…") { Task { await s.editKeyword(parent:keyword) } }
            Divider()
            Button("Delete Keyword and Children…",role:.destructive) { deleting=true }
        }
        .confirmationDialog("Delete \(keyword.name) and all nested keywords?",isPresented:$deleting,titleVisibility:.visible) {
            Button("Delete Keywords",role:.destructive) { Task { await s.deleteKeyword(keyword) } }
        } message: { Text("Their tags will be removed from every photo. Photos and originals remain in the catalog.") }
    }
    var row: some View {
        HStack(spacing:5) {
            Button { Task { await s.changeKeyword(keyword,action:allSelected ? "remove":"add") } } label: {
                Image(systemName:allSelected ? "checkmark.square":keyword.selectedCount > 0 ? "minus.square":"square")
            }.buttonStyle(.plain)
                .disabled(s.keywordBusy || keyword.selection.isEmpty || keyword.selection != s.actionPhotoIDs)
                .accessibilityLabel("\(keyword.name), \(keyword.selectedCount) of \(keyword.selection.count) selected photos tagged; \(allSelected ? "remove":"add") tag")
            Text(keyword.name).lineLimit(1).help(keyword.path + (keyword.detailsDeferred ? "\nComplete path and synonyms are available in Edit Keyword.":""))
            Spacer(minLength:2)
            Text("\(keyword.photoCount)").font(.caption).monospacedDigit()
            Button { Task { await s.showKeywordPhotos(keyword) } } label: { Image(systemName:"arrow.right.circle") }
                .buttonStyle(.plain).help("Show photos tagged with \(keyword.path), including nested keywords")
                .accessibilityLabel("Show Photos: \(keyword.path)")
        }
    }
}

struct KeywordEditor: View {
    @EnvironmentObject var s: Store
    @Environment(\.dismiss) var dismiss
    let original: LibraryKeyword?
    let revision: Int
    let targets: [Photo]
    @State private var includePhotos=false
    @State private var name: String
    @State private var synonyms: String
    @State private var includeExport: Bool
    @State private var exportContaining: Bool
    @State private var exportSynonyms: Bool
    @State private var isPerson: Bool
    @State private var parentID: Int?
    @State private var parentName: String
    @State private var choosingParent=false
    @State private var saving=false

    init(original: LibraryKeyword?,parent: LibraryKeyword?,revision: Int,targets: [Photo]) {
        self.original=original;self.revision=revision;self.targets=targets
        _name=State(initialValue:original?.name ?? "")
        _synonyms=State(initialValue:original?.synonyms.joined(separator:", ") ?? "")
        _includeExport=State(initialValue:original?.includeExport ?? true)
        _exportContaining=State(initialValue:original?.exportContaining ?? true)
        _exportSynonyms=State(initialValue:original?.exportSynonyms ?? true)
        _isPerson=State(initialValue:original?.isPerson ?? false)
        _parentID=State(initialValue:original?.parentID ?? parent?.id)
        let oldPath=original?.parentPath ?? ""
        _parentName=State(initialValue:parent?.path ?? (oldPath.isEmpty ? "None":oldPath))
    }

    var body: some View {
        VStack(alignment:.leading,spacing:16) {
            Text(original == nil ? "Create Keyword":"Edit Keyword").font(.title2)
            Form {
                TextField("Keyword",text:$name)
                TextField("Synonyms, separated by commas",text:$synonyms)
                LabeledContent("Inside") {
                    HStack {
                        ScrollView { Text(parentName).frame(maxWidth:.infinity,alignment:.leading).textSelection(.enabled) }
                            .frame(maxHeight:70)
                        Button("Choose…") { choosingParent=true }
                    }
                }
                Toggle("Include on Export",isOn:$includeExport)
                Toggle("Export Containing Keywords",isOn:$exportContaining)
                Toggle("Export Synonyms",isOn:$exportSynonyms).disabled(!includeExport)
                Toggle("Person Keyword",isOn:$isPerson)
                if original == nil {
                    Toggle("Add to \(targets.count) Selected Photos",isOn:$includePhotos).disabled(targets.isEmpty)
                }
            }
            Text("Renaming or moving a keyword updates its path for every tagged photo. Changes are saved in this catalog.")
                .font(.caption).foregroundStyle(.secondary)
            HStack {
                Button("Cancel") { dismiss() }.keyboardShortcut(.cancelAction)
                Spacer()
                Button("Save") {
                    saving=true
                    Task {
                        let aliases=synonyms.components(separatedBy:",").map { $0.trimmingCharacters(in:.whitespacesAndNewlines) }.filter { !$0.isEmpty }
                        if await s.saveKeyword(name:name,synonyms:aliases,parentID:parentID,original:original,revision:revision,targets:includePhotos ? targets:[],includeExport:includeExport,exportContaining:exportContaining,exportSynonyms:exportSynonyms,isPerson:isPerson) { dismiss() }
                        saving=false
                    }
                }.keyboardShortcut(.defaultAction).disabled(name.trimmingCharacters(in:.whitespacesAndNewlines).isEmpty)
            }
        }.padding(24).frame(width:500).disabled(saving)
            .sheet(isPresented:$choosingParent) { KeywordParentPicker(excluding:original?.id,revision:revision) { id,path in parentID=id;parentName=path } }
    }
}

struct KeywordParentPicker: View {
    @Environment(\.dismiss) var dismiss
    let excluding: Int?
    let choose: (Int?,String)->Void
    @StateObject private var model: KeywordParentModel

    init(excluding: Int?,revision: Int,choose: @escaping (Int?,String)->Void) {
        self.excluding=excluding;self.choose=choose
        _model=StateObject(wrappedValue:KeywordParentModel(revision:revision))
    }

    func select(_ keyword: LibraryKeyword?) {
        Task {
            if let value=await model.choose(keyword) { choose(value.id,value.path);dismiss() }
        }
    }

    var body: some View {
        VStack(alignment:.leading,spacing:14) {
            Text("Choose Parent Keyword").font(.title2)
            ScrollView { Text(model.parents.last?.path ?? "Keyword roots").font(.caption).textSelection(.enabled) }.frame(maxHeight:70)
            HStack {
                Button("Up") { Task { await model.up() } }.disabled(model.parents.isEmpty || model.loading)
                Button("Use This Parent") { select(model.parents.last) }.disabled(model.loading || model.error != nil)
                if model.loading { ProgressView().controlSize(.small) }
            }
            List(model.items) { keyword in
                HStack {
                    Button(keyword.name) { select(keyword) }.help(keyword.path)
                    Spacer()
                    if keyword.hasChildren {
                        Button { Task { await model.browse(keyword) } } label: { Image(systemName:"chevron.right") }
                            .accessibilityLabel("Browse \(keyword.name)")
                    }
                }.disabled(keyword.id == excluding || model.loading || model.error != nil)
            }
            if let error=model.error { Text(error).foregroundStyle(.red).font(.caption) }
            HStack {
                Button("Previous") { Task { await model.load(offset:max(0,model.offset-60)) } }.disabled(model.offset == 0 || model.loading)
                Button("Next") { Task { await model.load(offset:model.offset+60) } }.disabled(model.offset+60 >= model.total || model.loading)
                Spacer();Button("Cancel") { dismiss() }.keyboardShortcut(.cancelAction)
            }
        }.padding(20).frame(width:480,height:420).task { await model.load() }
            .onDisappear { model.cancel() }
    }
}
