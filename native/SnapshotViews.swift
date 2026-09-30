// Purpose: native snapshot panel, browser and captured name forms.
// Inputs: bounded summaries and explicit actions. Outputs: Store commands.
// All copies of a source share snapshots. Destructive replacement/removal is
// confirmed against the captured identity; refresh never rebases an open form.
// This view does not load recipes, preview hovering states or implement undo.
import SwiftUI

struct SnapshotsPanel:View {
    @EnvironmentObject var s:Store
    var body:some View {
        DisclosureGroup("Snapshots",isExpanded:$s.snapshotExpanded) {
            SnapshotList().padding(.top,10)
        }.onChange(of:s.snapshotExpanded) {_,value in
            if value {Task {await s.readVersions()}}
        }
    }
}

struct VersionsSheet:View {
    @EnvironmentObject var s:Store
    @Environment(\.dismiss) var dismiss
    var body:some View {
        VStack(alignment:.leading,spacing:16) {
            Text("Snapshots").font(.title2.weight(.semibold))
            Text(s.photo?.displayName ?? "Select a photo").foregroundStyle(.secondary)
            SnapshotList(expanded:true)
            HStack {Spacer();Button("Done"){dismiss()}.keyboardShortcut(.cancelAction)}
        }.padding(24).frame(width:560,height:540)
            .task {await s.readVersions()}
            .modifier(SnapshotNamePresentation(inBrowser:true))
    }
}

struct SnapshotNamePresentation:ViewModifier {
    @EnvironmentObject var s:Store
    var inBrowser=false
    func body(content:Content)->some View {
        content.sheet(item:Binding(get:{s.showVersions == inBrowser ? s.snapshotDraft:nil},
                                   set:{s.snapshotDraft=$0})) {draft in
            SnapshotNameSheet(draft:draft)
        }
    }
}

struct SnapshotNameSheet:View {
    @EnvironmentObject var s:Store
    @Environment(\.dismiss) var dismiss
    let draft:SnapshotDraft
    @State private var name:String
    init(draft:SnapshotDraft) {self.draft=draft;_name=State(initialValue:draft.name)}
    var body:some View {
        VStack(alignment:.leading,spacing:16) {
            Text(draft.version == nil ? "New Snapshot":"Rename Snapshot").font(.title2.weight(.semibold))
            Text(draft.stepID == nil ? "Snapshots are shared by this original and its virtual copies.":"Save the selected history step without changing current adjustments.")
                .foregroundStyle(.secondary)
            TextField("Snapshot Name",text:$name).textFieldStyle(.roundedBorder)
            if !s.snapshotBusy && !s.snapshotCaptureValid(draft) {
                Text("The photo changed. Close this form and refresh before trying again.").foregroundStyle(.red)
            }
            if let error=s.snapshotError {Text(error).foregroundStyle(.red).textSelection(.enabled)}
            HStack {
                Spacer()
                Button("Cancel"){dismiss()}.keyboardShortcut(.cancelAction).disabled(s.snapshotBusy)
                Button(s.snapshotBusy ? "Saving…":"Save") {
                    Task {if await s.applySnapshotDraft(draft,name:name) {dismiss()}}
                }.keyboardShortcut(.defaultAction).buttonStyle(.borderedProminent)
                    .disabled(!s.snapshotCaptureValid(draft) || name.trimmingCharacters(in:.whitespacesAndNewlines).isEmpty)
            }
        }.padding(24).frame(width:480).interactiveDismissDisabled(s.snapshotBusy)
    }
}

struct SnapshotList:View {
    @EnvironmentObject var s:Store
    var expanded=false
    @State private var destructive:SnapshotDraft?
    @State private var destructiveAction="delete_version"
    var body:some View {
        VStack(alignment:.leading,spacing:8) {
            HStack {
                Button {s.prepareSnapshot()} label:{Label("Create…",systemImage:"plus")}.disabled(!s.snapshotReady)
                Spacer()
                Button {Task {await s.refreshSnapshotPhoto()}} label:{Image(systemName:"arrow.clockwise")}
                    .help("Refresh Photo and Snapshots").accessibilityLabel("Refresh Photo and Snapshots")
                    .disabled(!s.snapshotReady || s.snapshotLoading)
            }
            if let page=s.snapshotPage,page.photoID==s.selected {
                if page.entries.isEmpty {Text("No snapshots yet").font(.callout).foregroundStyle(.secondary)}
                ScrollView {
                    LazyVStack(alignment:.leading,spacing:3) {
                        ForEach(page.entries) {entry in
                            let capture=SnapshotDraft(page:page,version:entry)
                            HStack {
                                Button {Task {await s.performSnapshot("restore_version",captured:capture)}} label:{
                                    VStack(alignment:.leading,spacing:2) {
                                        Text(entry.name).lineLimit(2)
                                        if expanded {Text(Date(timeIntervalSince1970:entry.created),format:.dateTime.month().day().year().hour().minute().second()).font(.caption2).foregroundStyle(.secondary)}
                                    }.frame(maxWidth:.infinity,alignment:.leading).contentShape(Rectangle())
                                }.buttonStyle(.plain).help("Restore \(entry.name)")
                                    .accessibilityLabel("Restore snapshot \(entry.name)")
                                Menu {actions(entry,page:page,capture:capture)} label:{Image(systemName:"ellipsis")}
                                    .menuStyle(.borderlessButton).frame(width:24).accessibilityLabel("Actions for \(entry.name)")
                            }.padding(5).disabled(!s.snapshotCaptureValid(capture))
                                .contextMenu {actions(entry,page:page,capture:capture)}
                        }
                    }
                }.frame(maxHeight:expanded ? .infinity:220)
                HStack {
                    if s.snapshotAfter != nil {Button("First Page"){Task {await s.readVersions()}}}
                    Spacer()
                    if let next=page.nextAfter {Button("Next Page"){Task {await s.readVersions(after:next)}}}
                }.disabled(s.snapshotLoading || !s.snapshotReady)
            }
            if s.snapshotLoading || s.snapshotBusy {ProgressView().controlSize(.small)}
            if let error=s.snapshotError {Text(error).font(.caption).foregroundStyle(.red).textSelection(.enabled)}
            Text("Alphabetical · Shared by original and virtual copies").font(.caption).foregroundStyle(.secondary)
        }
        .confirmationDialog(destructiveAction == "delete_version" ? "Delete this snapshot?":"Update this snapshot with current settings?",
                            isPresented:Binding(get:{destructive != nil},set:{if !$0 {destructive=nil}}),titleVisibility:.visible) {
            Button(destructiveAction == "delete_version" ? "Delete Snapshot":"Update Snapshot",role:.destructive) {
                if let capture=destructive {let action=destructiveAction;Task {await s.performSnapshot(action,captured:capture)}}
                destructive=nil
            }
            Button("Cancel",role:.cancel){destructive=nil}
        } message: {
            Text("“\(destructive?.version?.name ?? "")” is shared by this original and its virtual copies. This cannot be undone. Current adjustments, copied Before settings and queued exports stay unchanged.")
        }
    }
    @ViewBuilder private func actions(_ entry:SnapshotEntry,page:SnapshotPage,capture:SnapshotDraft)->some View {
        Button("Restore Snapshot"){Task {await s.performSnapshot("restore_version",captured:capture)}}
        Button("Rename…"){s.prepareSnapshotRename(entry,page:page)}
        Button("Update with Current Settings…"){destructiveAction="update_version";destructive=capture}
        Button("Copy Snapshot Settings to Before"){Task {await s.performSnapshot("before_after",captured:capture)}}
        Divider()
        Button("Delete…",role:.destructive){destructiveAction="delete_version";destructive=capture}
    }
}
