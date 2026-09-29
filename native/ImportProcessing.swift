// Purpose: revision-bound choices for Apply During Import, with paged preset lists.
// Inputs: a ready plan, explicit preset selections and keyword drafts. Outputs:
// persisted setting captures, new metadata presets and parent review refreshes.
// Drafts never rebase after external changes. No SQL, asset access or pixel work.
import Foundation

@MainActor final class ImportProcessingEditor: ObservableObject,Identifiable {
    let id=UUID()
    let planID: Int
    @Published private(set) var revision: Int
    @Published var developID=""
    @Published var developName=""
    @Published var metadataID=""
    @Published var metadataName=""
    @Published var keywordsText=""
    @Published var savedKeywordsText=""
    @Published var developPage: DevelopPresetPage?
    @Published var metadataPage: MetadataPresetPage?
    @Published var developSearch=""
    @Published var metadataSearch=""
    @Published var busy=false
    @Published var error: String?
    @Published var ready=false
    private var closed=false
    private var developRead=0
    private var metadataRead=0
    var onSaved: (() async -> Void)?
    var keywordsDirty: Bool { keywordsText != savedKeywordsText }
    init(plan: ImportPlan) { planID=plan.id;revision=plan.revision }

    private func receive(_ result: [String:Any],keywords: Bool) {
        revision=result["revision"] as? Int ?? revision
        developID=result["develop_id"] as? String ?? "";developName=result["develop_name"] as? String ?? ""
        metadataID=result["metadata_id"] as? String ?? "";metadataName=result["metadata_name"] as? String ?? ""
        if keywords {
            keywordsText=(result["keywords"] as? [String] ?? []).joined(separator:", ")
            savedKeywordsText=keywordsText
        }
    }

    func load() async {
        guard !busy,!closed else { return }
        busy=true;error=nil
        defer { busy=false }
        do {
            let result=try await Backend.call("get_import_processing",["plan_id":planID])
            guard !closed else { return }
            guard result["revision"] as? Int == revision,result["state"] as? String == "ready" else {
                throw EngineFailure(message:"Import review changed. Close this panel, refresh the review and reopen it.")
            }
            receive(result,keywords:true);ready=true
            await browseDevelop();await browseMetadata()
        } catch { if !closed { self.error=error.localizedDescription } }
    }

    func browseDevelop(offset: Int=0) async {
        developRead+=1;let token=developRead
        do {
            let result=try await Backend.call("list_develop_presets",["search":developSearch,"offset":offset])
            if !closed,token == developRead { developPage=DevelopPresetPage(result) }
        } catch { if !closed,token == developRead { self.error=error.localizedDescription } }
    }

    func browseMetadata(offset: Int=0) async {
        metadataRead+=1;let token=metadataRead
        do {
            let result=try await Backend.call("list_metadata_presets",["search":metadataSearch,"offset":offset])
            if !closed,token == metadataRead { metadataPage=MetadataPresetPage(result) }
        } catch { if !closed,token == metadataRead { self.error=error.localizedDescription } }
    }

    @discardableResult func set(_ changes: [String:Any]) async -> Bool {
        guard ready,!busy,!closed else { return false }
        busy=true;error=nil
        defer { busy=false }
        do {
            let result=try await Backend.call("set_import_processing",changes.merging(
                ["plan_id":planID,"expected_revision":revision],uniquingKeysWith:{$1}))
            guard !closed else { return false }
            receive(result,keywords:changes["keywords"] != nil)
            await onSaved?()
            return true
        } catch {
            if !closed { self.error=error.localizedDescription }
            // Neither stale nor uncertain settings are replayed automatically.
            return false
        }
    }

    func chooseDevelop(_ choice: DevelopPresetSelection?) async {
        let value: Any=choice.map { ["preset_id":$0.preset.id,"expected_revision":$0.revision] as Any } ?? NSNull()
        await set(["develop_preset":value])
    }

    func chooseMetadata(_ choice: MetadataPresetSelection?) async {
        let value: Any=choice.map { ["preset_id":$0.preset.id,"expected_revision":$0.revision] as Any } ?? NSNull()
        await set(["metadata_preset":value])
    }

    func saveKeywords() async {
        let values=keywordsText.components(separatedBy:CharacterSet(charactersIn:",\n"))
            .map{$0.trimmingCharacters(in:.whitespacesAndNewlines)}.filter{!$0.isEmpty}
        await set(["keywords":values])
    }

    func createMetadata(name: String,patch: [String:Any],revision: String) async -> Bool {
        guard ready,!busy,!closed else { return false }
        busy=true;error=nil
        do {
            let result=try await Backend.call("save_metadata_preset",["name":name,"patch":patch,"expected_revision":revision])
            guard !closed,let presetID=result["preset_id"] as? String,let next=result["revision"] as? String else {
                busy=false;return false
            }
            metadataPage=MetadataPresetPage(result);busy=false
            // The preset was saved even if an external plan edit prevents choosing it.
            await set(["metadata_preset":["preset_id":presetID,"expected_revision":next]])
            return true
        } catch { busy=false;if !closed { self.error=error.localizedDescription };return false }
    }

    func invalidate() { closed=true;developRead+=1;metadataRead+=1 }
}

extension ImportReviewModel {
    func openProcessing() {
        guard !busy,!loading,let plan,plan.ready else { return }
        let editor=ImportProcessingEditor(plan:plan)
        editor.onSaved={ [weak self] in await self?.load() }
        processingEditor=editor
    }
}
