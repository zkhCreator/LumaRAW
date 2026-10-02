// Purpose: bounded, read-only transfer receipts for a captured Copy import.
// Inputs: plan identity and explicit page requests. Outputs: source/destination
// status and Finder reveal on user action. No copying, recovery or file deletion.
// Each receipt distinguishes catalog-bound primary copies from original backups.
import SwiftUI
import AppKit

struct ImportCopyReceipts: View {
    let planID: Int
    @Environment(\.dismiss) private var dismiss
    @State private var items: [[String:String]]=[]
    @State private var offset=0
    @State private var total=0
    @State private var loading=false
    @State private var error: String?
    var body: some View {
        VStack(alignment:.leading,spacing:14) {
            Text("Copy Transfer Details").font(.title2)
            Text("Completed files remain at their destinations after cancellation.").foregroundStyle(.secondary)
            List(Array(items.enumerated()),id:\.offset) { _,item in
                VStack(alignment:.leading,spacing:5) {
                    Text((item["role"] == "second" ? "Second Copy · ":"Main Copy · ")+item["state",default:""]).fontWeight(.semibold)
                    Text("From: \(item["source",default:""])").font(.caption).textSelection(.enabled)
                    Text("To: \(item["target",default:""])").font(.caption).textSelection(.enabled)
                    if item["state"] == "published",let path=item["target"] {
                        Button("Show in Finder") { NSWorkspace.shared.activateFileViewerSelecting([URL(fileURLWithPath:path)]) }
                    }
                }
            }
            if let error { Text(error).foregroundStyle(.red) }
            HStack {
                Button("Done") { dismiss() }.keyboardShortcut(.cancelAction)
                Spacer()
                Button("Previous") { offset=max(0,offset-60) }.disabled(loading || offset == 0)
                Text(total == 0 ? "No transfers":"\(offset+1)–\(min(offset+60,total)) of \(total)")
                Button("Next") { offset+=60 }.disabled(loading || offset+60>=total)
                Button("Refresh") { Task { await load() } }.disabled(loading)
            }
        }.padding(22).frame(width:760,height:540).task(id:offset) { await load() }
    }
    private func load() async {
        loading=true;error=nil
        defer { loading=false }
        do {
            let result=try await Backend.call("get_import_copies",["plan_id":planID,"offset":offset])
            guard !Task.isCancelled else { return }
            items=result["items"] as? [[String:String]] ?? [];total=result["total"] as? Int ?? 0
        } catch { if !Task.isCancelled { self.error=error.localizedDescription } }
    }
}
