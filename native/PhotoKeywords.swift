// Purpose: complete paged keyword review and a local assignment-set picker.
// Inputs: captured photo revisions or complete stable keyword IDs, plus searches.
// Outputs: read-only path pages and a draft ID set returned to a parent form.
// Metadata and shortcut editors share the picker; it never mutates the catalog.
// Saving the parent form validates its captured revisions atomically.
import SwiftUI

struct KeywordPath: Identifiable {
    let id: Int
    let path: String
    init?(_ row: [String:Any]) {
        guard let id=row["id"] as? Int,let path=row["path"] as? String else { return nil }
        self.id=id;self.path=path
    }
}

struct KeywordPathPage {
    var items: [KeywordPath]=[]
    var offset=0
    var total=0
    init(_ result: [String:Any]=[:]) {
        items=(result["keywords"] as? [[String:Any]] ?? []).compactMap(KeywordPath.init)
        offset=result["offset"] as? Int ?? 0;total=result["total"] as? Int ?? 0
    }
}

@MainActor final class PhotoKeywordsModel: ObservableObject {
    let photo: Photo
    @Published var page=KeywordPathPage()
    @Published var loading=false
    @Published var error: String?
    private var generation=0
    init(photo: Photo) { self.photo=photo }
    func receive(_ result: [String:Any]) {
        guard result["photo_id"] as? Int == photo.id,
              result["metadata_revision"] as? Int == photo.metadataRevision else { return }
        page=KeywordPathPage(result)
    }
    func load(offset: Int=0) async {
        generation+=1;let token=generation;loading=true;error=nil
        defer { if token == generation { loading=false } }
        do {
            let result=try await Backend.call("get_photo_keywords",["photo_id":photo.id,
                "expected_metadata_revision":photo.metadataRevision,"offset":offset])
            if token == generation { receive(result) }
        } catch { if token == generation { self.error=error.localizedDescription } }
    }
    func invalidate() { generation+=1;loading=false }
}

struct PhotoKeywordsSheet: View {
    @Environment(\.dismiss) private var dismiss
    @StateObject private var model: PhotoKeywordsModel
    init(photo: Photo) { _model=StateObject(wrappedValue:PhotoKeywordsModel(photo:photo)) }
    var body: some View {
        VStack(alignment:.leading,spacing:16) {
            Text("Assigned Keywords").font(.title2)
            Text(model.photo.displayName).foregroundStyle(.secondary)
            List(model.page.items) { Text($0.path).textSelection(.enabled) }
            if let error=model.error { Text(error).foregroundStyle(.red) }
            HStack {
                KeywordPathPaging(page:model.page,loading:model.loading) { offset in Task { await model.load(offset:offset) } }
                Spacer()
                Button("Done") { dismiss() }.keyboardShortcut(.cancelAction)
            }
        }.padding(24).frame(width:700,height:520)
            .task { await model.load() }.onDisappear { model.invalidate() }
    }
}

@MainActor final class KeywordSelectionModel: ObservableObject {
    @Published var ids: Set<Int>
    @Published var search=""
    @Published var available=KeywordPathPage()
    @Published var chosen=KeywordPathPage()
    @Published var loadingChosen=false
    @Published var loadingSearch=false
    @Published var error: String?
    private var chosenGeneration=0
    private var searchGeneration=0
    init(ids: [Int]) { self.ids=Set(ids) }

    func loadChosen(offset: Int=0) async {
        chosenGeneration+=1;let token=chosenGeneration,captured=ids
        loadingChosen=true;error=nil
        defer { if token == chosenGeneration { loadingChosen=false } }
        do {
            let result=try await Backend.call("keyword_choices",["keyword_ids":captured.sorted(),"offset":offset])
            guard token == chosenGeneration,captured == ids else { return }
            chosen=KeywordPathPage(result)
        } catch { if token == chosenGeneration,captured == ids { self.error=error.localizedDescription } }
    }
    func loadSearch(offset: Int=0) async {
        searchGeneration+=1;let token=searchGeneration,query=search
        loadingSearch=true;error=nil
        defer { if token == searchGeneration { loadingSearch=false } }
        do {
            let result=try await Backend.call("keyword_choices",["search":query,"offset":offset])
            guard token == searchGeneration,query == search else { return }
            available=KeywordPathPage(result)
        } catch { if token == searchGeneration,query == search { self.error=error.localizedDescription } }
    }
    func toggle(_ id: Int) async {
        if ids.contains(id) { ids.remove(id) }
        else if ids.count<100 { ids.insert(id) }
        await loadChosen(offset:chosen.offset)
    }
    func clear() async { ids.removeAll();await loadChosen() }
    func invalidate() { chosenGeneration+=1;searchGeneration+=1;loadingChosen=false;loadingSearch=false }
}

struct KeywordSelectionSheet: View {
    @Environment(\.dismiss) private var dismiss
    @StateObject private var model: KeywordSelectionModel
    let accept: ([Int])->Void
    let explanation: String
    init(ids: [Int],explanation: String="This replacement set is applied when you save the metadata form.",accept: @escaping ([Int])->Void) {
        _model=StateObject(wrappedValue:KeywordSelectionModel(ids:ids));self.accept=accept;self.explanation=explanation
    }
    var body: some View {
        VStack(alignment:.leading,spacing:14) {
            Text("Choose Existing Keywords").font(.title2)
            Text(explanation).foregroundStyle(.secondary)
            HStack {
                Text("Selected · \(model.ids.count)/100").font(.headline)
                Spacer()
                Button("Clear Selection") { Task { await model.clear() } }.disabled(model.loadingChosen || model.ids.isEmpty)
            }
            List(model.chosen.items) { item in
                HStack {
                    Text(item.path).textSelection(.enabled)
                    Spacer()
                    Button("Remove") { Task { await model.toggle(item.id) } }.disabled(model.loadingChosen)
                }
            }.frame(minHeight:130)
            KeywordPathPaging(page:model.chosen,loading:model.loadingChosen) { offset in Task { await model.loadChosen(offset:offset) } }
            TextField("Find Keywords or Synonyms",text:$model.search).textFieldStyle(.roundedBorder)
            List(model.available.items) { item in
                HStack {
                    Text(item.path).textSelection(.enabled)
                    Spacer()
                    Button(model.ids.contains(item.id) ? "Remove":"Add") { Task { await model.toggle(item.id) } }
                        .disabled(model.loadingChosen || !model.ids.contains(item.id) && model.ids.count>=100)
                }
            }.frame(minHeight:130)
            KeywordPathPaging(page:model.available,loading:model.loadingSearch) { offset in Task { await model.loadSearch(offset:offset) } }
            if let error=model.error { Text(error).foregroundStyle(.red) }
            HStack {
                Button("Cancel",role:.cancel) { dismiss() }.keyboardShortcut(.cancelAction)
                Spacer()
                Button("Use Selection") { accept(model.ids.sorted());dismiss() }
                    .keyboardShortcut(.defaultAction).disabled(model.loadingChosen || model.loadingSearch)
            }
        }.padding(24).frame(width:740,height:720)
            .task { await model.loadChosen() }
            .task(id:model.search) {
                do { try await Task.sleep(nanoseconds:200_000_000) } catch { return }
                await model.loadSearch()
            }.onDisappear { model.invalidate() }
    }
}

struct KeywordPathPaging: View {
    let page: KeywordPathPage
    let loading: Bool
    let turn: (Int)->Void
    var body: some View {
        HStack {
            Button("Previous") { turn(max(0,page.offset-20)) }.disabled(loading || page.offset==0)
            Text(page.total == 0 ? "0 keywords":"\(page.offset+1)–\(min(page.offset+20,page.total)) of \(page.total)").font(.caption)
            Button("Next") { turn(page.offset+20) }.disabled(loading || page.offset+20>=page.total)
            if loading { ProgressView().controlSize(.small) }
        }
    }
}
