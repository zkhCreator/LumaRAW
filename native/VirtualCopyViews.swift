// Purpose: virtual-copy contextual actions and explicit catalog-removal confirmation.
// Inputs: captured photo targets. Outputs: Store domain actions. Never deletes files.
// Copy badges distinguish multiple edits of one file in grid and filmstrip views.
import SwiftUI

struct VirtualCopyActions: View {
    @EnvironmentObject var s: Store
    let photo: Photo
    var body: some View {
        Button("Create Virtual Copy") { Task { await s.createVirtualCopies(ids:[photo.id]) } }
        Button("Show Master and Copies") { Task { await s.showPhotoFamily(photo) } }
        if photo.isVirtual {
            Button("Go to Master Photo") { Task { await s.showPhotoFamily(photo,masterOnly:true) } }
            Button("Set Copy as Master") { Task { await s.setCopyAsMaster(photo) } }
            Button("Remove Virtual Copy from Catalog…",role:.destructive) { Task { await s.prepareCopyRemoval(ids:[photo.id]) } }
        }
    }
}

struct VirtualCopyBadge: View {
    let photo: Photo
    var body: some View {
        if photo.isVirtual {
            Image(systemName:"doc.on.doc.fill").font(.caption).padding(4)
                .background(.black.opacity(0.65),in:RoundedRectangle(cornerRadius:3)).foregroundStyle(.white)
                .accessibilityLabel("Virtual copy: \(photo.copyName)")
        }
    }
}

struct VirtualCopyRemovalSheet: View {
    @EnvironmentObject var s: Store
    @Environment(\.dismiss) private var dismiss
    let targets: [Photo]
    @State private var removing=false
    var body: some View {
        VStack(alignment:.leading,spacing:16) {
            Text("Remove Virtual Copies?").font(.title2)
            Text("This removes these copies, their private edit history and collection memberships from the catalog. Originals, other copies, shared snapshots and submitted exports remain. This removal cannot be undone.")
            List(targets) { photo in Text(photo.displayName).lineLimit(2) }
            HStack {
                Button("Cancel",role:.cancel) { dismiss() }.keyboardShortcut(.cancelAction)
                Spacer()
                Button("Remove \(targets.count) Copies",role:.destructive) {
                    removing=true
                    Task { if await s.removeVirtualCopies(targets) { dismiss() };removing=false }
                }.disabled(removing)
            }
        }.padding(24).frame(width:560,height:380)
    }
}
