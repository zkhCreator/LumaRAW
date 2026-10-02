// Purpose: bounded import-preset browsing and revision-bound management on Mac.
// Inputs: an optional ready review, saved option summaries and explicit choices.
// Outputs: save/update/rename/delete commands and a source-neutral parent choice.
// Full recipes and SQL stay in the engine. Pagination never rebases selected drafts.
// Applying to an existing review explicitly rescans and resets checked selections.
// Copy date-folder layout is included in saved options and its human-readable summary.
import Foundation
import SwiftUI

@MainActor final class ImportPresetEditor: ObservableObject,Identifiable {
    let id=UUID()
    let plan: ImportPlan?
    @Published var rows: [[String:Any]]=[]
    @Published var offset=0
    @Published var total=0
    @Published var revision=0
    @Published var selected: [String:Any]?
    @Published var name=""
    @Published var busy=false
    @Published var ready=false
    @Published var error: String?
    private var draftRevision=0
    private var closed=false
    var onUse: (([String:Any]) async -> Bool)?
    init(plan: ImportPlan?) { self.plan=plan }
    var canSave: Bool { ready && !busy && plan?.ready == true && !name.trimmingCharacters(in:.whitespacesAndNewlines).isEmpty }
    var canUse: Bool { ready && !busy && selected != nil && (plan == nil || plan?.active == false || plan?.ready == true) }
    var selection: [String:Any]? {
        guard let selected,let key=selected["id"] as? String,let revision=selected["revision"] as? Int else {return nil}
        return ["preset_id":key,"expected_revision":revision]
    }
    private func receive(_ value:[String:Any]) {
        rows=value["items"] as? [[String:Any]] ?? [];offset=value["offset"] as? Int ?? 0
        total=value["total"] as? Int ?? 0;revision=value["revision"] as? Int ?? 0
    }
    func browse(offset: Int=0,reset: Bool=false) async {
        guard !busy,!closed else {return};busy=true;error=nil;defer {busy=false}
        do {
            let value=try await Backend.call("list_import_presets",["offset":offset])
            guard !closed else {return};receive(value)
            if !ready || reset {draftRevision=revision;selected=nil;name=""};ready=true
        } catch {if !closed {self.error=error.localizedDescription}}
    }
    func choose(_ row:[String:Any]) async {
        guard !busy,!closed,let key=row["id"] as? String else {return};busy=true;error=nil;defer {busy=false}
        do {
            let value=try await Backend.call("get_import_preset",["preset_id":key,"expected_revision":revision])
            guard !closed else {return};selected=value;name=value["name"] as? String ?? "";draftRevision=revision
        } catch {if !closed {self.error=error.localizedDescription}}
    }
    func save(update: Bool=false) async {
        guard canSave,!closed,let plan else {return}
        if update && selection == nil {return}
        busy=true;error=nil;defer {busy=false}
        var params: [String:Any]=["name":name,"plan_id":plan.id,"expected_plan_revision":plan.revision,"expected_revision":draftRevision]
        if update,let selection {params.merge(selection,uniquingKeysWith:{$1})}
        do {
            let value=try await Backend.call("save_import_preset",params)
            guard !closed else {return};receive(value);draftRevision=revision
            if let key=value["preset_id"] as? String {
                selected=try await Backend.call("get_import_preset",["preset_id":key,"expected_revision":revision])
            }
        } catch {if !closed {self.error=error.localizedDescription}}
    }
    func action(_ action:String) async {
        guard ready,!busy,!closed,let selection else {return};busy=true;error=nil;defer {busy=false}
        do {
            var params=selection;params["action"]=action
            if action == "rename" {params["name"]=name}
            let value=try await Backend.call("import_preset_action",params)
            guard !closed else {return};receive(value);draftRevision=revision
            if action == "delete" {selected=nil;name=""}
            else if let key=selection["preset_id"] {
                selected=try await Backend.call("get_import_preset",["preset_id":key,"expected_revision":revision])
            }
        } catch {if !closed {self.error=error.localizedDescription}}
    }
    func use() async -> Bool {
        guard canUse,!closed,let selected else {return false};busy=true;error=nil;defer {busy=false}
        return await onUse?(selected) ?? false
    }
    func invalidate() {closed=true}
}

struct ImportPresetSheet: View {
    @ObservedObject var model: ImportPresetEditor
    @Environment(\.dismiss) private var dismiss
    @State private var confirmDelete=false
    var body: some View {
        content.task {await model.browse()}.onDisappear {model.invalidate()}
            .interactiveDismissDisabled(model.busy)
            .confirmationDialog("Delete this import preset? Existing reviews keep their captured settings.",isPresented:$confirmDelete) {
                Button("Delete Preset",role:.destructive) {Task {await model.action("delete")}}
            }
    }
    var content: some View {
        VStack(alignment:.leading,spacing:14) {
            HStack {Text("Import Presets").font(.title2);Spacer();if model.busy {ProgressView().controlSize(.small)}}
            Text("Save the import method, destinations, naming, processing and keywords. Sources and checked photos are chosen for each import.")
                .font(.caption).foregroundStyle(.secondary)
            HStack(alignment:.top,spacing:20) {
                VStack(alignment:.leading) {
                    ScrollView {
                        VStack(alignment:.leading,spacing:6) {
                            ForEach(Array(model.rows.enumerated()),id:\.offset) { _,row in
                                Button {Task {await model.choose(row)}} label: {
                                    HStack {Text(row["name"] as? String ?? "").lineLimit(2);Spacer();Text((row["mode"] as? String ?? "").capitalized).font(.caption)}
                                        .padding(7).frame(maxWidth:.infinity,alignment:.leading)
                                        .background((row["id"] as? String) == (model.selected?["id"] as? String) ? Color.accentColor.opacity(0.15):Color.clear)
                                }.buttonStyle(.plain)
                            }
                            if model.rows.isEmpty {Text("No saved import presets").foregroundStyle(.secondary)}
                        }
                    }.frame(minHeight:220)
                    HStack {
                        Button("Previous") {Task {await model.browse(offset:max(0,model.offset-30))}}.disabled(model.offset == 0)
                        Text("\(model.total) presets").font(.caption)
                        Button("Next") {Task {await model.browse(offset:model.offset+30)}}.disabled(model.offset+30>=model.total)
                    }
                }.frame(width:280)
                Divider()
                VStack(alignment:.leading,spacing:10) {
                    TextField("Preset Name",text:$model.name)
                    HStack {
                        Button("Save Current as New") {Task {await model.save()}}.disabled(!model.canSave)
                        Button("Update Selected") {Task {await model.save(update:true)}}.disabled(!model.canSave || model.selected == nil)
                    }
                    HStack {
                        Button("Rename") {Task {await model.action("rename")}}.disabled(model.selected == nil || model.name.trimmingCharacters(in:.whitespacesAndNewlines).isEmpty)
                        Button("Delete…",role:.destructive) {confirmDelete=true}.disabled(model.selected == nil)
                    }
                    Divider()
                    ScrollView {
                      VStack(alignment:.leading,spacing:8) {
                       if let selected=model.selected,let options=selected["options"] as? [String:Any] {
                        Text("Method: \((options["mode"] as? String ?? "").capitalized)")
                        Text(options["include_subfolders"] as? Bool == true ? "Include subfolders":"Selected folder only")
                        Text(options["skip_duplicates"] as? Bool == true ? "Skip suspected duplicates":"Include suspected duplicates")
                        if let destination=options["destination"] as? String {Text("To: \(destination)").lineLimit(2).help(destination)}
                        if let organization=options["organization"] as? String {
                            Text("Organize: \(["flat":"Into One Folder","source":"By Original Folders","date":"By Capture Date"][organization] ?? organization)")
                            if organization == "date" {
                                let format=options["date_format"] as? String ?? "year_date"
                                Text("Date Format: \(dateFormatLabel(format))")
                            }
                        }
                        if let folder=options["subfolder"] as? String,!folder.isEmpty {Text("Subfolder: \(folder)").lineLimit(2).help(folder)}
                        if let backup=options["second_copy_destination"] as? String {Text("Second copy: \(backup)").lineLimit(2).help(backup)}
                        Text(selected["renaming"] as? Bool == true ? "File renaming enabled":"Original filenames")
                        if let settings=selected["processing"] as? [String:Any] {
                            ForEach(["develop_name","metadata_name"],id:\.self) {key in
                                if let text=settings[key] as? String,!text.isEmpty {Text(text)}
                            }
                            Text("\(settings["keyword_count"] as? Int ?? 0) additional keywords")
                        }
                       }
                      }.frame(maxWidth:.infinity,alignment:.leading)
                    }
                }.font(.caption)
            }.disabled(model.busy)
            if model.plan?.ready == true {
                Text("Use & Rescan replaces this review and resets checked selections. Review the new list before importing.").font(.caption).foregroundStyle(.secondary)
            } else {Text("To save current settings, scan sources and configure the ready review first.").font(.caption).foregroundStyle(.secondary)}
            if let error=model.error {Text(error).font(.caption).foregroundStyle(.red).textSelection(.enabled)}
            HStack {
                Button("Done") {dismiss()}.keyboardShortcut(.cancelAction).disabled(model.busy)
                Button("Reload Library") {Task {await model.browse(reset:true)}}.disabled(model.busy)
                Spacer()
                Button(model.plan?.ready == true ? "Use & Rescan":"Use Preset") {Task {if await model.use() {dismiss()}}}
                    .buttonStyle(.borderedProminent).disabled(!model.canUse)
            }
        }.padding(22).frame(width:800,height:510)
    }

    private func dateFormatLabel(_ value:String) -> String {
        switch value {
        case "year_month_day": return "YYYY/MM/DD"
        case "date": return "YYYY-MM-DD"
        default: return "YYYY/YYYY-MM-DD"
        }
    }
}
