// Purpose: show complete scanned metadata without enlarging folder review pages.
// Inputs: a captured plan/item/revision and bounded read-only detail responses.
// Outputs: full descriptive fields and twenty complete keyword paths per page.
// No writes or automatic revision adoption; changed plans require a fresh review.
import SwiftUI

@MainActor final class FolderSyncMetadataModel: ObservableObject {
    let planID: Int
    let itemID: Int
    let revision: Int
    @Published var item: FolderSyncItem?
    @Published var offset=0
    @Published var total=0
    @Published var loading=false
    @Published var error: String?
    private var generation=0
    init(planID: Int,itemID: Int,revision: Int) {
        self.planID=planID;self.itemID=itemID;self.revision=revision
    }
    func receive(_ result: [String:Any]) {
        guard result["plan_id"] as? Int == planID,result["revision"] as? Int == revision,
              let row=result["item"] as? [String:Any],let next=FolderSyncItem(row),next.id == itemID else { return }
        item=next;offset=result["offset"] as? Int ?? 0;total=result["total"] as? Int ?? 0
    }
    func load(offset: Int=0) async {
        generation+=1;let token=generation;loading=true;error=nil
        defer { if token == generation { loading=false } }
        do {
            let result=try await Backend.call("get_folder_sync_metadata",[
                "plan_id":planID,"item_id":itemID,"expected_revision":revision,"offset":offset])
            if token == generation { receive(result) }
        } catch { if token == generation { self.error=error.localizedDescription } }
    }
    func invalidate() { generation+=1;loading=false }
}

struct FolderSyncMetadataSheet: View {
    @Environment(\.dismiss) private var dismiss
    @StateObject private var model: FolderSyncMetadataModel
    init(planID: Int,itemID: Int,revision: Int) {
        _model=StateObject(wrappedValue:FolderSyncMetadataModel(planID:planID,itemID:itemID,revision:revision))
    }
    var body: some View {
        VStack(alignment:.leading,spacing:16) {
            Text("Scanned Metadata").font(.title2)
            Text("These are the values saved in this synchronization review.").foregroundStyle(.secondary)
            ScrollView {
                if let item=model.item {
                    VStack(alignment:.leading,spacing:12) {
                        Text(item.path).font(.caption).textSelection(.enabled)
                        ForEach(item.metadataKeys.filter{$0 != "keyword_paths"},id:\.self) { key in
                            VStack(alignment:.leading,spacing:4) {
                                Text(item.label(key)).font(.headline)
                                Text(item.value(key).isEmpty ? "(empty)":item.value(key)).textSelection(.enabled)
                            }
                        }
                        if let paths=item.patch["keyword_paths"] as? [[String]] {
                            Text("Keywords").font(.headline)
                            if paths.isEmpty { Text("No keywords").foregroundStyle(.secondary) }
                            ForEach(Array(paths.enumerated()),id:\.offset) { _,path in
                                Text(path.joined(separator:" | ")).textSelection(.enabled)
                            }
                        }
                        ForEach(item.notes,id:\.self) { Text($0).foregroundStyle(.secondary) }
                        if !item.error.isEmpty { Text(item.error).foregroundStyle(.red) }
                    }.frame(maxWidth:.infinity,alignment:.leading)
                }
            }
            if let error=model.error { Text(error).foregroundStyle(.red) }
            HStack {
                if model.total>20 {
                    Button("Previous") { Task { await model.load(offset:max(0,model.offset-20)) } }
                        .disabled(model.loading || model.offset==0)
                    Text("\(model.offset+1)–\(min(model.offset+20,model.total)) of \(model.total) keywords").font(.caption)
                    Button("Next") { Task { await model.load(offset:model.offset+20) } }
                        .disabled(model.loading || model.offset+20>=model.total)
                }
                Spacer()
                if model.loading { ProgressView().controlSize(.small) }
                Button("Done") { dismiss() }.keyboardShortcut(.cancelAction)
            }
        }.padding(24).frame(width:700,height:600)
            .task { await model.load() }.onDisappear { model.invalidate() }
    }
}
