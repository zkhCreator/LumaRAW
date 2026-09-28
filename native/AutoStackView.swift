// Purpose: captured-source auto-stack preview, metadata progress and confirmation.
// Inputs: one folder/collection and a duration. Outputs: fingerprint-bound service
// commands and refreshed Store pages. No SQL, date parsing, pixels or whole-library
// arrays. Late previews are rejected; a conflict requires a new explicit preview.
import SwiftUI
import AppKit

struct AutoStackSource: Hashable {
    let folder: String?
    let collectionID: Int?
    let title: String
    var params: [String:Any] {
        if let collectionID { return ["collection_id":collectionID] }
        return ["folder":folder ?? ""]
    }
}

struct AutoStackQuery: Hashable {
    let source: AutoStackSource
    let seconds: Double
    var params: [String:Any] { source.params.merging(["seconds":seconds]) { _,new in new } }
}

struct AutoStackPlan {
    let query: AutoStackQuery
    let values: [String:Any]
    var token: String { values["token"] as? String ?? "" }
    func count(_ key: String) -> Int { values[key] as? Int ?? 0 }
}

@MainActor final class AutoStackModel: ObservableObject {
    @Published var source: AutoStackSource
    @Published var seconds=1.0
    @Published var plan: AutoStackPlan?
    @Published var loading=false
    @Published var busy=false
    @Published var refreshing=false
    @Published var error: String?
    @Published var progress=""
    @Published var stopRequested=false
    private var generation=0
    var query: AutoStackQuery { AutoStackQuery(source:source,seconds:seconds) }
    var canApply: Bool { !busy && !loading && plan?.query == query && (plan?.count("known") ?? 0)>0 }

    init(source: AutoStackSource) { self.source=source }

    func preview(debounce: Bool=false) async {
        guard !busy else { return }
        generation+=1;let token=generation;let captured=query
        plan=nil;error=nil;loading=true
        defer { if token == generation { loading=false } }
        do {
            if debounce { try await Task.sleep(nanoseconds:250_000_000) }
            try Task.checkCancellation()
            let result=try await Backend.call("preview_auto_stack",captured.params)
            guard token == generation,captured == query,!Task.isCancelled else { return }
            plan=AutoStackPlan(query:captured,values:result)
        } catch is CancellationError { }
        catch { if token == generation,captured == query { self.error=error.localizedDescription } }
    }

    func refreshTimes() async {
        guard !busy else { return }
        let captured=source
        generation+=1;loading=false;plan=nil;error=nil;busy=true;refreshing=true;stopRequested=false
        let token=generation
        var cursor=0,total=0,failed=0
        do {
            repeat {
                let result=try await Backend.call("refresh_capture_times",captured.params.merging(["after_source_id":cursor]) { _,new in new })
                total+=result["processed"] as? Int ?? 0;failed+=result["failed"] as? Int ?? 0
                cursor=result["after_source_id"] as? Int ?? cursor
                progress="Read \(total) originals\(failed == 0 ? "":" · \(failed) unavailable")"
                if result["done"] as? Bool == true { break }
            } while !stopRequested && !Task.isCancelled
        } catch { self.error=error.localizedDescription }
        busy=false;refreshing=false
        if stopRequested { progress += " · Stopped" }
        if error == nil,!Task.isCancelled,token == generation { await preview() }
    }

    func apply(using store: Store) async -> Bool {
        guard canApply,let captured=plan else { return false }
        busy=true;error=nil
        defer { busy=false }
        guard await store.flushEdits() else { return false }
        do {
            _=try await Backend.call("apply_auto_stack",captured.query.params.merging(["token":captured.token]) { _,new in new })
            await store.refreshCollections();await store.refresh()
            store.message="Created \(captured.count("stacks")) capture-time stacks"
            return true
        } catch { self.error=error.localizedDescription;plan=nil;return false }
    }

    func cancel() { generation+=1;stopRequested=true }
}

extension Store {
    func prepareAutoStack() {
        guard canStack else { return }
        if let collection=activeCollection,collection.id == collectionID {
            autoStackSource=AutoStackSource(folder:nil,collectionID:collection.id,title:collection.name)
        } else if let folder=libraryFilters["folder"] as? String {
            autoStackSource=AutoStackSource(folder:folder,collectionID:nil,title:URL(fileURLWithPath:folder).lastPathComponent)
        } else if let photo {
            let folder=URL(fileURLWithPath:photo.path).deletingLastPathComponent()
            autoStackSource=AutoStackSource(folder:folder.path,collectionID:nil,title:folder.lastPathComponent)
        } else {
            autoStackSource=chooseAutoStackFolder()
        }
        showAutoStack=autoStackSource != nil
    }

    func chooseAutoStackFolder() -> AutoStackSource? {
        let panel=NSOpenPanel();panel.canChooseDirectories=true;panel.canChooseFiles=false
        panel.allowsMultipleSelection=false;panel.prompt="Choose Folder"
        panel.message="Group catalog photos in this folder by capture time. Subfolders are excluded."
        guard panel.runModal() == .OK,let url=panel.url else { return nil }
        return AutoStackSource(folder:url.path,collectionID:nil,title:url.lastPathComponent)
    }
}

struct AutoStackSheet: View {
    @EnvironmentObject var s: Store
    @Environment(\.dismiss) private var dismiss
    @StateObject private var model: AutoStackModel
    init(source: AutoStackSource) { _model=StateObject(wrappedValue:AutoStackModel(source:source)) }
    var body: some View {
        VStack(alignment:.leading,spacing:16) {
            Text("Auto-Stack by Capture Time").font(.title2)
            HStack {
                VStack(alignment:.leading,spacing:4) {
                    Label(model.source.title,systemImage:model.source.collectionID == nil ? "folder":"square.stack")
                    if let folder=model.source.folder { Text(folder).font(.caption).foregroundStyle(.secondary).textSelection(.enabled) }
                }
                Spacer()
                if model.source.collectionID == nil {
                    Button("Choose Folder…") { if let source=s.chooseAutoStackFolder() { model.source=source } }.disabled(model.busy)
                }
            }
            Text(model.source.collectionID == nil ? "All catalog photos in this folder are included. Subfolders, selection and filters do not change this scope." : "All photos in this collection are included, regardless of selection or filters.")
                .font(.callout).foregroundStyle(.secondary)
            HStack {
                Text("Time between stacks")
                TextField("Seconds",value:$model.seconds,format:.number.precision(.fractionLength(0...6))).frame(width:100)
                Text("seconds")
            }.disabled(model.busy)
            Slider(value:$model.seconds,in:0...3600,step:0.1).disabled(model.busy)
            Text("A gap equal to or longer than this duration starts a new stack.").font(.caption).foregroundStyle(.secondary)
            if model.loading { ProgressView("Calculating groups…") }
            if let plan=model.plan,plan.query == model.query {
                GroupBox {
                    VStack(alignment:.leading,spacing:8) {
                        Text("\(plan.count("stacks")) stacks · \(plan.count("stacked_photos")) stacked photos · \(plan.count("unstacked_photos")) unstacked")
                        Text("\(plan.count("photos")) photos in this source").font(.caption).foregroundStyle(.secondary)
                        if plan.count("unknown")>0 { Text("\(plan.count("unknown")) photos have no supported capture time and will remain unstacked. Refresh capture times to read available EXIF metadata.").font(.caption) }
                        if plan.count("existing_stacks")>0 { Text("This replaces \(plan.count("existing_stacks")) existing stacks in this source.").font(.callout) }
                        if let clocks=plan.values["clock_types"] as? [String:Int],(clocks["camera"] ?? 0)>0 {
                            Text("\(clocks["camera"] ?? 0) photos have no timezone offset; their camera clocks are used.").font(.caption).foregroundStyle(.secondary)
                        }
                    }.frame(maxWidth:.infinity,alignment:.leading)
                }
            }
            HStack {
                Button("Refresh Capture Times") { Task { await model.refreshTimes() } }.disabled(model.busy)
                if model.refreshing { Button("Stop") { model.stopRequested=true } }
                Spacer()
                Button("Refresh Preview") { Task { await model.preview() } }.disabled(model.busy || model.loading)
            }
            if !model.progress.isEmpty { Text(model.progress).font(.caption).foregroundStyle(.secondary) }
            if let error=model.error { Text(error).font(.callout).foregroundStyle(.red).textSelection(.enabled) }
            HStack {
                Button("Cancel",role:.cancel) { model.cancel();dismiss() }.keyboardShortcut(.cancelAction).disabled(model.busy && !model.refreshing)
                Spacer()
                Button("Stack") { Task { if await model.apply(using:s) { dismiss() } } }
                    .buttonStyle(.borderedProminent).disabled(!model.canApply)
            }
        }.padding(24).frame(width:620)
            .interactiveDismissDisabled(model.busy && !model.refreshing)
            .task(id:model.query) { await model.preview(debounce:true) }
            .onDisappear { model.cancel() }
    }
}
