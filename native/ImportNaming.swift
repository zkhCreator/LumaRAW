// Purpose: revision-bound filename drafts and catalog-local template management.
// Inputs: a ready Copy plan, explicit token/text choices and bounded service pages.
// Outputs: saved naming captures and engine-calculated previews. Drafts survive
// conflicts. UI never computes filenames, rebases mutations or writes originals.
import Foundation

struct FilenameToken: Identifiable {
    let id=UUID()
    var kind: String
    var text=""
    var digits=4
    var numbered: Bool { ["sequence","index","total"].contains(kind) }
    var value: [String:Any] {
        if kind == "literal" { return ["kind":kind,"text":text] }
        if numbered { return ["kind":kind,"digits":digits] }
        return ["kind":kind]
    }
    init(kind: String) { self.kind=kind }
    init(_ value: [String:Any]) {
        kind=value["kind"] as? String ?? "filename";text=value["text"] as? String ?? ""
        digits=value["digits"] as? Int ?? 1
    }
}

@MainActor final class ImportNamingEditor: ObservableObject,Identifiable {
    let id=UUID()
    let planID: Int
    @Published private(set) var revision: Int
    @Published var enabled=false
    @Published var tokens=[FilenameToken(kind:"filename")]
    @Published var customText=""
    @Published var shootName=""
    @Published var start="1"
    @Published var extensionCase="preserve"
    @Published var builtins: [[String:Any]]=[]
    @Published var kinds: [String]=[]
    @Published var templates: [[String:Any]]=[]
    @Published var libraryRevision=0
    @Published var libraryOffset=0
    @Published var libraryTotal=0
    @Published var templateID: String?
    @Published var templateRevision=0
    @Published var templateName=""
    @Published var previewRows: [[String:Any]]=[]
    @Published var previewOffset=0
    @Published var previewTotal=0
    @Published var previewDraft=""
    @Published var savedDraft=""
    @Published var busy=false
    @Published var ready=false
    @Published var error: String?
    private var closed=false
    var onSaved: (() async -> Void)?
    init(plan: ImportPlan) { planID=plan.id;revision=plan.revision }
    var settings: [String:Any] {
        ["enabled":enabled,"template":tokens.map(\.value),"custom_text":customText,
         "shoot_name":shootName,"start":Int(start) ?? 0,"extension":extensionCase]
    }
    var draftKey: String {
        guard let bytes=try? JSONSerialization.data(withJSONObject:settings,options:.sortedKeys) else { return "" }
        return String(decoding:bytes,as:UTF8.self)
    }
    var dirty: Bool { draftKey != savedDraft }
    var previewCurrent: Bool { !previewDraft.isEmpty && previewDraft == draftKey }

    private func receive(_ result: [String:Any]) {
        guard let value=result["settings"] as? [String:Any] else { return }
        revision=result["revision"] as? Int ?? revision
        enabled=value["enabled"] as? Bool ?? false
        tokens=(value["template"] as? [[String:Any]] ?? []).map(FilenameToken.init)
        customText=value["custom_text"] as? String ?? "";shootName=value["shoot_name"] as? String ?? ""
        start=String(value["start"] as? Int ?? 1);extensionCase=value["extension"] as? String ?? "preserve"
        builtins=result["builtins"] as? [[String:Any]] ?? [];kinds=result["tokens"] as? [String] ?? []
        savedDraft=draftKey
    }
    private func receiveLibrary(_ result: [String:Any]) {
        templates=result["items"] as? [[String:Any]] ?? [];libraryRevision=result["revision"] as? Int ?? 0
        libraryOffset=result["offset"] as? Int ?? 0;libraryTotal=result["total"] as? Int ?? 0
    }
    func load() async {
        guard !busy,!closed else { return };busy=true;error=nil
        defer { busy=false }
        do {
            let result=try await Backend.call("get_import_naming",["plan_id":planID])
            guard !closed else { return }
            guard result["revision"] as? Int == revision,result["state"] as? String == "ready" else {
                throw EngineFailure(message:"Import review changed. Close this panel, refresh and reopen it.")
            }
            receive(result);ready=true
            let library=try await Backend.call("list_filename_templates")
            if !closed { receiveLibrary(library) }
        } catch { if !closed { self.error=error.localizedDescription } }
    }
    func chooseBuiltin(_ row: [String:Any]) {
        guard ready,!busy else { return }
        tokens=(row["template"] as? [[String:Any]] ?? []).map(FilenameToken.init)
        templateID=nil;templateName=row["name"] as? String ?? "";enabled=true
    }
    func chooseSaved(_ row: [String:Any]) async {
        guard ready,!busy,!closed,let key=row["id"] as? String else { return }
        busy=true;error=nil;defer { busy=false }
        do {
            let value=try await Backend.call("get_filename_template",["template_id":key,"expected_revision":libraryRevision])
            guard !closed else { return }
            tokens=(value["template"] as? [[String:Any]] ?? []).map(FilenameToken.init)
            templateID=key;templateRevision=libraryRevision;templateName=value["name"] as? String ?? "";enabled=true
        } catch { if !closed { self.error=error.localizedDescription } }
    }
    func browse(offset: Int) async {
        guard !busy,!closed else { return };busy=true;defer { busy=false }
        do {
            let value=try await Backend.call("list_filename_templates",["offset":offset])
            if !closed { receiveLibrary(value) }
        } catch { if !closed { self.error=error.localizedDescription } }
    }
    func saveTemplate(asNew: Bool) async {
        guard ready,!busy,!closed else { return };busy=true;error=nil;defer { busy=false }
        var params: [String:Any]=["name":templateName,"template":tokens.map(\.value),"expected_revision":libraryRevision]
        if !asNew,let templateID { params["template_id"]=templateID;params["expected_revision"]=templateRevision }
        do {
            let value=try await Backend.call("save_filename_template",params)
            if !closed { receiveLibrary(value);templateID=value["template_id"] as? String;templateRevision=libraryRevision }
        } catch { if !closed { self.error=error.localizedDescription } }
    }
    func deleteTemplate() async {
        guard ready,!busy,!closed,let templateID else { return };busy=true;error=nil;defer { busy=false }
        do {
            let value=try await Backend.call("delete_filename_template",["template_id":templateID,"expected_revision":templateRevision])
            if !closed { receiveLibrary(value);self.templateID=nil }
        } catch { if !closed { self.error=error.localizedDescription } }
    }
    func preview(offset: Int=0) async {
        guard ready,!busy,!closed else { return };busy=true;error=nil;defer { busy=false }
        let draft=draftKey
        do {
            let value=try await Backend.call("preview_import_naming",["plan_id":planID,"expected_revision":revision,"settings":settings,"offset":offset])
            guard !closed else { return }
            previewRows=value["items"] as? [[String:Any]] ?? [];previewOffset=value["offset"] as? Int ?? 0
            previewTotal=value["total"] as? Int ?? 0;previewDraft=draft
        } catch { if !closed { self.error=error.localizedDescription } }
    }
    @discardableResult func save() async -> Bool {
        guard ready,!busy,!closed else { return false };busy=true;error=nil;defer { busy=false }
        do {
            let value=try await Backend.call("set_import_naming",["plan_id":planID,"expected_revision":revision,"settings":settings])
            guard !closed else { return false }
            receive(value);await onSaved?();return true
        } catch { if !closed { self.error=error.localizedDescription };return false }
    }
    func invalidate() { closed=true }
}

extension ImportReviewModel {
    func openNaming() {
        guard !busy,!loading,let plan,plan.ready,plan.isCopy else { return }
        let editor=ImportNamingEditor(plan:plan)
        editor.onSaved={ [weak self] in await self?.load() };namingEditor=editor
    }
}
