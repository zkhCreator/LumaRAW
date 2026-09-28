// Purpose: native keyword-set picker, nine buttons and explicit preset editing.
// Inputs: bounded preset state and local text drafts. Outputs: Store actions.
// Change edits the current draft; Update Preset/Save as New Preset persist it.
// Recent Keywords is read-only but can seed a new preset. No inferred keywords.
import SwiftUI

struct KeywordSetEditorSource: Identifiable {
    let id=UUID()
    let state: KeywordSetState
    let slots: [String]
    let newSet: Bool
    let revision: String
}

struct KeywordSetsSidebar: View {
    @EnvironmentObject var s: Store
    @State private var editor: KeywordSetEditorSource?
    @State private var deleting: KeywordSetState?
    var body: some View {
        Section("Keyword Set") {
            if let state=s.keywordSets {
                Menu {
                    Button("Recent Keywords") { Task { _=await s.keywordSetAction("select",id:"recent") } }
                    ForEach(state.items) { item in
                        Button(item.name) { Task { _=await s.keywordSetAction("select",id:item.id) } }
                    }
                    if state.total > 30 {
                        Divider()
                        Button("Previous Sets") { Task { await s.refreshKeywordSets(offset:max(0,state.offset-30)) } }.disabled(state.offset == 0)
                        Button("More Sets") { Task { await s.refreshKeywordSets(offset:state.offset+30) } }.disabled(state.offset+30 >= state.total)
                    }
                    Divider()
                    Button("Edit Set…") { edit(state,newSet:false) }.disabled(state.selected.id == "recent")
                    Button("Save Current Settings as New Preset…") { edit(state,newSet:true) }
                    Button("New Empty Set…") { edit(state,newSet:true,empty:true) }
                    if s.keywordSetDraft != nil {
                        Button("Discard Draft") { s.keywordSetDraft=nil;s.keywordSetDraftRevision=nil }
                    }
                    Button("Delete Selected Preset…",role:.destructive) { deleting=state }.disabled(state.selected.id == "recent")
                    Button("Refresh Sets") { Task { await s.refreshKeywordSets() } }
                } label: { Text(state.selected.name + (s.keywordSetDraft == nil ? "":" (Edited)")) }
                    .disabled(s.keywordSetBusy)
                LazyVGrid(columns:Array(repeating:GridItem(.flexible(),spacing:4),count:3),spacing:4) {
                    ForEach([7,8,9,4,5,6,1,2,3],id:\.self) { slot in
                        Button { Task { await s.applyKeywordSlot(slot) } } label: {
                            VStack(spacing:2) {
                                Text(s.keywordSetSlots[slot-1].isEmpty ? "—":s.keywordSetSlots[slot-1]).lineLimit(2)
                                Text("⌥\(slot)").font(.caption2).foregroundStyle(.secondary)
                            }.frame(maxWidth:.infinity,minHeight:38)
                        }.disabled(!s.canApplyKeywordSlot(slot))
                            .help(s.keywordSetSlots[slot-1])
                            .accessibilityLabel("Apply slot \(slot): \(s.keywordSetSlots[slot-1])")
                    }
                }
                Text(state.storeWithCatalog ? "Stored with this catalog":"Shared across catalogs").font(.caption2).foregroundStyle(.secondary)
                if s.keywordSetBusy { ProgressView().controlSize(.small) }
            } else { ProgressView().controlSize(.small).task { await s.refreshKeywordSets() } }
        }
        .sheet(item:$editor) { source in
            KeywordSetEditor(source:source).environmentObject(s)
        }
        .confirmationDialog("Delete keyword set?",isPresented:Binding(get:{deleting != nil},set:{if !$0 {deleting=nil}}),titleVisibility:.visible) {
            if let captured=deleting {
                Button("Delete \(captured.selected.name)",role:.destructive) {
                    Task { _=await s.keywordSetAction("delete",id:captured.selected.id,revision:captured.revision) };deleting=nil
                }
            }
        } message: { Text("Assigned photo keywords are preserved.") }
    }
    func edit(_ state: KeywordSetState,newSet: Bool,empty: Bool=false) {
        editor=KeywordSetEditorSource(state:state,slots:empty ? Array(repeating:"",count:9):s.keywordSetSlots,
            newSet:newSet,revision:empty ? state.revision:s.keywordSetDraftRevision ?? state.revision)
    }
}

struct KeywordSetEditor: View {
    @EnvironmentObject var s: Store
    @Environment(\.dismiss) var dismiss
    let state: KeywordSetState
    let newSet: Bool
    let revision: String
    @State private var name: String
    @State private var slots: [String]
    init(source: KeywordSetEditorSource) {
        state=source.state;newSet=source.newSet;revision=source.revision
        _name=State(initialValue:source.newSet ? "":source.state.selected.name)
        _slots=State(initialValue:source.slots)
    }
    var body: some View {
        VStack(alignment:.leading,spacing:16) {
            Text(newSet ? "New Keyword Set":"Edit Keyword Set").font(.title2)
            TextField("Preset Name",text:$name).textFieldStyle(.roundedBorder)
            LazyVGrid(columns:Array(repeating:GridItem(.flexible()),count:3)) {
                ForEach([7,8,9,4,5,6,1,2,3],id:\.self) { slot in
                    VStack(alignment:.leading) {
                        Text("Option-\(slot)").font(.caption).foregroundStyle(.secondary)
                        TextField("Keyword or Parent | Child",text:$slots[slot-1]).textFieldStyle(.roundedBorder)
                    }
                }
            }
            Text("One keyword or full hierarchy path per slot. Empty slots stay unused. Change keeps a draft until you select another set; save to keep it.")
                .font(.caption).foregroundStyle(.secondary)
            HStack {
                Button("Cancel") { dismiss() }.keyboardShortcut(.cancelAction)
                Spacer()
                if !newSet {
                    Button("Change") { if s.changeKeywordSetDraft(slots,revision:revision) { dismiss() } }
                    Button("Save as New Preset") { save(id:nil) }.disabled(name.trimmingCharacters(in:.whitespaces).isEmpty)
                }
                Button(newSet ? "Save Preset":"Update Preset") { save(id:newSet ? nil:state.selected.id) }
                    .keyboardShortcut(.defaultAction).disabled(name.trimmingCharacters(in:.whitespaces).isEmpty)
            }.disabled(s.keywordSetBusy)
        }.padding(24).frame(width:640)
    }
    func save(id: String?) {
        Task { if await s.saveKeywordSet(name:name,slots:slots,id:id,revision:revision) { dismiss() } }
    }
}
