// Purpose: bounded preview of the metadata a newly submitted export would use.
// Inputs: one captured photo identity, metadata policy and hierarchy preference.
// Outputs: read-only field/keyword pages; every load rejects superseded replies.
// No metadata writes, file access or promise that an already-queued job will change.
import SwiftUI

@MainActor final class ExportMetadataModel: ObservableObject {
    let photoID: Int
    let metadata: String
    let hierarchy: Bool
    @Published var kind="keywords"
    @Published var fields: [String:Any]=[:]
    @Published var items: [String]=[]
    @Published var offset=0
    @Published var total=0
    @Published var keywordRevision=0
    @Published var metadataRevision=0
    @Published var loading=false
    @Published var error: String?
    private var generation=0

    init(photoID: Int,metadata: String="catalog",hierarchy: Bool=true) {
        self.photoID=photoID;self.metadata=metadata;self.hierarchy=hierarchy
    }

    func receive(_ result: [String:Any]) {
        guard result["photo_id"] as? Int == photoID else { return }
        let nextKeyword=result["keyword_revision"] as? Int ?? 0
        let nextMetadata=result["metadata_revision"] as? Int ?? 0
        guard nextKeyword >= keywordRevision,nextMetadata >= metadataRevision else { return }
        keywordRevision=nextKeyword;metadataRevision=nextMetadata
        fields=result["fields"] as? [String:Any] ?? [:]
        items=result["items"] as? [String] ?? []
        offset=result["offset"] as? Int ?? 0;total=result["total"] as? Int ?? 0
    }

    func load(offset: Int=0) async {
        generation+=1
        let token=generation
        loading=true;error=nil
        defer { if generation == token { loading=false } }
        do {
            let result=try await Backend.call("preview_export_metadata",[
                "photo_id":photoID,"metadata":metadata,"keyword_hierarchy":hierarchy,"kind":kind,"offset":offset])
            guard generation == token else { return }
            receive(result)
        } catch {
            if generation == token { self.error=error.localizedDescription }
        }
    }

    func invalidate() { generation+=1;loading=false }

    func label(_ key: String) -> String {
        ["color_label":"Color Label","caption":"Caption","copyright":"Copyright","title":"Title","rating":"Rating"][key] ?? key.capitalized
    }

    func value(_ key: String) -> String {
        if key == "rating",fields["flag"] as? Int == -1 { return "Rejected" }
        return String(describing:fields[key] ?? "")
    }
}

struct ExportMetadataSheet: View {
    @Environment(\.dismiss) var dismiss
    @StateObject private var model: ExportMetadataModel

    init(photoID: Int,metadata: String="catalog",hierarchy: Bool=true) {
        _model=StateObject(wrappedValue:ExportMetadataModel(photoID:photoID,metadata:metadata,hierarchy:hierarchy))
    }

    var body: some View {
        VStack(alignment:.leading,spacing:16) {
            Text("Will Export").font(.title2)
            Text("Current metadata for this photo. Submitted exports retain their own snapshots.")
                .font(.callout).foregroundStyle(.secondary)
            ScrollView {
                VStack(alignment:.leading,spacing:8) {
                    ForEach(model.fields.keys.filter{$0 != "flag"}.sorted(),id:\.self) { key in
                        if key == "iptc",let values=model.fields[key] as? [String:Any] {
                            DisclosureGroup("IPTC") { IPTCValuesView(values:values) }
                        } else {
                        LabeledContent(model.label(key),value:model.value(key).isEmpty ? "(empty)":model.value(key))
                            .textSelection(.enabled)
                        }
                    }
                }
            }.frame(maxHeight:160)
            Picker("Keyword View",selection:$model.kind) {
                Text("Keywords and Synonyms").tag("keywords")
                Text("Hierarchy Paths").tag("hierarchy")
            }.disabled(model.loading).onChange(of:model.kind) { _,_ in Task { await model.load() } }
            List(Array(model.items.enumerated()),id:\.offset) { _,value in
                Text(value).textSelection(.enabled)
            }.frame(minHeight:170)
            if model.items.isEmpty && !model.loading && model.error == nil {
                Text(model.kind == "hierarchy" && !model.hierarchy ? "Hierarchy export is disabled.":"No keywords will be exported.")
                    .foregroundStyle(.secondary)
            }
            if let error=model.error { Text(error).font(.callout).foregroundStyle(.red) }
            HStack {
                Button("Previous") { Task { await model.load(offset:max(0,model.offset-60)) } }
                    .disabled(model.offset == 0 || model.loading)
                Text(model.total == 0 ? "0 items":"\(model.offset+1)–\(min(model.offset+60,model.total)) of \(model.total)")
                    .font(.caption).monospacedDigit()
                Button("Next") { Task { await model.load(offset:model.offset+60) } }
                    .disabled(model.offset+60 >= model.total || model.loading)
                Spacer()
                if model.loading { ProgressView().controlSize(.small) }
                Button("Refresh") { Task { await model.load(offset:model.offset) } }.disabled(model.loading)
                Button("Done") { dismiss() }.keyboardShortcut(.cancelAction)
            }
        }.padding(24).frame(width:640,height:520)
            .task { await model.load() }.onDisappear { model.invalidate() }
    }
}
