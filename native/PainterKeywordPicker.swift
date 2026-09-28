// Purpose: a bounded, local multi-set keyword draft for the Library Painter.
// Inputs: revision-bound preset previews, recent IDs and explicit slot selections.
// Outputs: one shortcut replacement on confirmation; browsing/cancel never mutate
// presets, vocabulary or photos. Custom slots freeze text at selection; recent
// slots retain identities. Superseded or dismissed reads cannot retarget a draft.
import SwiftUI

struct PainterKeywordChoice: Identifiable, Equatable {
    let keywordID: Int?
    let path: String
    var id: String { keywordID.map { "id:\($0)" } ?? "path:\(path)" }
}

struct PainterKeywordSetPage {
    let state: KeywordSetState
    let choices: [PainterKeywordChoice?]
    init(_ result: [String:Any]) throws {
        guard let state=KeywordSetState(result),
              let ids=(result["selected"] as? [String:Any])?["keyword_ids"] as? [Any],ids.count == 9 else {
            throw EngineFailure(message:"Incomplete keyword set preview")
        }
        self.state=state
        choices=try state.slots.enumerated().map { index,path in
            guard !path.isEmpty else { return nil }
            let id=ids[index] as? Int
            guard state.selected.id != "recent" || id != nil else {
                throw EngineFailure(message:"Recent keyword identity is missing")
            }
            return PainterKeywordChoice(keywordID:id,path:path)
        }
    }
}

@MainActor final class PainterKeywordPickerModel: ObservableObject, Identifiable {
    let id=UUID()
    @Published private(set) var page: PainterKeywordSetPage?
    @Published private(set) var chosen: [PainterKeywordChoice]=[]
    @Published private(set) var loading=false
    @Published private(set) var saving=false
    @Published private(set) var error: String?
    private(set) var shortcutRevision: String?
    private var generation=0
    private var active=true
    private var invalid=false
    var canSave: Bool { active && !invalid && !loading && !saving && shortcutRevision != nil && !chosen.isEmpty }

    func start() async {
        guard active,page == nil,!loading else { return }
        generation+=1;let token=generation;loading=true;error=nil
        defer { if token == generation { loading=false } }
        do {
            let shortcutResult=try await Backend.call("get_keyword_shortcut")
            let result=try await Backend.call("list_keyword_sets")
            guard active,token == generation else { return }
            guard let shortcut=KeywordShortcut(shortcutResult),
                  result["keyword_revision"] as? Int == shortcut.keywordRevision else {
                throw EngineFailure(message:"Keywords changed; close and reopen the chooser")
            }
            page=try PainterKeywordSetPage(result);shortcutRevision=shortcut.revision
        } catch { if active,token == generation { self.error=error.localizedDescription;invalid=true } }
    }

    func load(setID: String?=nil,offset: Int?=nil) async {
        guard active,!saving,!invalid,let state=page?.state else { return }
        generation+=1;let token=generation;loading=true;error=nil
        defer { if token == generation { loading=false } }
        do {
            let result=try await Backend.call("get_keyword_set",["set_id":setID ?? state.selected.id,
                "offset":offset ?? state.offset,"expected_revision":state.revision])
            guard active,token == generation else { return }
            page=try PainterKeywordSetPage(result)
        } catch { if active,token == generation { self.error=error.localizedDescription;invalid=true } }
    }

    func toggle(_ choice: PainterKeywordChoice) {
        guard active,!loading,!saving,!invalid else { return }
        if let index=chosen.firstIndex(where:{$0.id == choice.id}) { chosen.remove(at:index) }
        else { add([choice]) }
    }

    func selectAll() { add(page?.choices.compactMap { $0 } ?? []) }

    private func add(_ choices: [PainterKeywordChoice]) {
        guard active,!loading,!saving,!invalid else { return }
        var merged=chosen
        for choice in choices where !merged.contains(where:{$0.id == choice.id}) { merged.append(choice) }
        guard merged.count<=100 else { error="Choose at most 100 keywords";return }
        chosen=merged;error=nil
    }

    func clear() { if active,!saving,!invalid { chosen=[];error=nil } }

    func save(using store: Store) async -> Bool {
        guard canSave,let revision=shortcutRevision else { return false }
        saving=true;defer { saving=false }
        let result=await store.saveKeywordShortcut(ids:chosen.compactMap(\.keywordID),
            additions:chosen.filter { $0.keywordID == nil }.map(\.path),revision:revision)
        if !result { error=store.error ?? "Painter is busy; wait before loading keywords" }
        return result
    }

    func invalidate() { active=false;generation+=1;loading=false }
}

struct PainterKeywordPicker: View {
    @EnvironmentObject var s: Store
    @Environment(\.dismiss) private var dismiss
    @ObservedObject var model: PainterKeywordPickerModel
    private let order=[6,7,8,3,4,5,0,1,2]
    var body: some View {
        VStack(alignment:.leading,spacing:16) {
            Text("Choose Painter Keywords").font(.title2)
            Text("Choose across keyword sets to replace the Painter's loaded keywords. Photos are tagged when you paint.").foregroundStyle(.secondary)
            if let page=model.page {
                HStack {
                    Menu(page.state.selected.name) {
                        Button("Recent Keywords") { Task { await model.load(setID:"recent") } }
                        ForEach(page.state.items) { item in
                            Button(item.name) { Task { await model.load(setID:item.id) } }
                        }
                    }.frame(maxWidth:300)
                    Spacer()
                    Button("Previous Sets") { Task { await model.load(offset:max(0,page.state.offset-30)) } }.disabled(page.state.offset == 0)
                    Button("More Sets") { Task { await model.load(offset:page.state.offset+30) } }.disabled(page.state.offset+30>=page.state.total)
                }.disabled(model.loading || model.saving)
                LazyVGrid(columns:Array(repeating:GridItem(.flexible()),count:3),spacing:8) {
                    ForEach(order,id:\.self) { index in
                        if let choice=page.choices[index] {
                            Toggle(isOn:Binding(get:{model.chosen.contains(where:{$0.id == choice.id})},set:{ _ in model.toggle(choice) })) {
                                Text(choice.path).lineLimit(3).frame(maxWidth:.infinity,minHeight:44)
                            }.toggleStyle(.button).help(choice.path)
                        } else { Text("Empty").foregroundStyle(.tertiary).frame(maxWidth:.infinity,minHeight:44) }
                    }
                }.disabled(model.loading || model.saving)
                HStack {
                    Button("Select All in This Set") { model.selectAll() }.disabled(model.loading)
                    Button("Clear Choices") { model.clear() }.disabled(model.chosen.isEmpty)
                    Spacer();Text("\(model.chosen.count) choices across sets")
                }.disabled(model.saving)
            }
            List(model.chosen) { choice in
                HStack {
                    Text(choice.path).textSelection(.enabled)
                    Spacer()
                    Button { model.toggle(choice) } label:{ Image(systemName:"minus.circle") }
                        .buttonStyle(.borderless).accessibilityLabel("Remove \(choice.path)")
                }
            }.frame(height:150).disabled(model.loading || model.saving)
            if let error=model.error { Text(error).foregroundStyle(.red).textSelection(.enabled) }
            HStack {
                Button("Cancel") { model.invalidate();dismiss() }.keyboardShortcut(.cancelAction).disabled(model.saving)
                if model.loading || model.saving { ProgressView().controlSize(.small) }
                Spacer()
                Button("Load Painter") { Task { if await model.save(using:s) { dismiss() } } }
                    .keyboardShortcut(.defaultAction).disabled(!model.canSave)
            }
        }.padding(24).frame(width:760).task { await model.start() }
            .interactiveDismissDisabled(model.saving).onDisappear { model.invalidate() }
    }
}
