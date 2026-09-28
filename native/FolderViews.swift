// Purpose: native catalog-folder tree, search, counts and presentation actions.
// Inputs: bounded Store folder pages. Outputs: explicit source/label/root commands.
// Finder reveal is local navigation; these controls never move or rename files.
import SwiftUI
import AppKit

struct PhotoFolderAction: View {
    @EnvironmentObject var s: Store
    let photo: Photo
    var body: some View {
        Button("Go to Folder in Library") { Task { await s.showPhotoFolder(photo) } }
    }
}

struct FoldersSidebar: View {
    @EnvironmentObject var s: Store
    var body: some View {
        Section("Folders") {
            TextField("Filter Folders",text:Binding(get:{s.folderSearch},set:{s.folderSearch=$0;s.scheduleFolderSearch()}))
                .textFieldStyle(.roundedBorder).accessibilityLabel("Filter Folders")
            Menu {
                Toggle("Favorite Folders",isOn:Binding(get:{s.folderFavorites},set:{s.folderFavorites=$0;s.scheduleFolderSearch()}))
                Picker("Color Label",selection:Binding(get:{s.folderColor},set:{s.folderColor=$0;s.scheduleFolderSearch()})) {
                    Text("Any Color").tag("any")
                    ForEach(LibraryLabels.names,id:\.self) { Text($0.capitalized).tag($0) }
                }
                Divider()
                Toggle("Include Photos from Subfolders",isOn:Binding(get:{s.includeSubfolders},set:{value in
                    Task { await s.changeSubfolderInclusion(value) }
                }))
                Button("Refresh Folders") { Task { await s.refreshFolders() } }
                Button("Resume Folder Relocation…") { s.relocationFolder=nil;s.showFolderRelocation=true }
            } label: { Label("Folder Options",systemImage:"line.3.horizontal.decrease.circle") }
                .menuStyle(.borderlessButton)
            FolderBranch(parent:nil)
        }
        .task { if s.folderPages[0] == nil { await s.refreshFolders() } }
    }
}

struct FolderBranch: View {
    @EnvironmentObject var s: Store
    let parent: Int?
    var body: some View {
        if let page=s.folderPages[parent ?? 0] {
            ForEach(page.items) { folder in FolderTreeRow(folder:folder) }
            if page.items.isEmpty { Text("No folders").font(.caption).foregroundStyle(.secondary) }
            if page.total>60 {
                HStack {
                    Button("Previous") { Task { await s.turnFolderPage(parent:parent,offset:max(0,page.offset-60)) } }
                        .disabled(page.offset==0)
                    Spacer()
                    Text("\(page.offset+1)–\(min(page.offset+60,page.total))").monospacedDigit()
                    Button("Next") { Task { await s.turnFolderPage(parent:parent,offset:page.offset+60) } }
                        .disabled(page.offset+60>=page.total)
                }.font(.caption)
            }
        } else { ProgressView().controlSize(.small) }
    }
}

struct FolderTreeRow: View {
    @EnvironmentObject var s: Store
    let folder: LibraryFolder
    var body: some View {
        Group {
            if folder.hasChildren && !s.folderQuery.filtered {
                DisclosureGroup(isExpanded:Binding(get:{s.expandedFolders.contains(folder.id)},set:{ value in
                    if value { s.expandFolder(folder.id) } else { s.collapseFolder(folder.id) }
                })) { AnyView(FolderBranch(parent:folder.id)) } label: { openButton }
            } else { openButton }
        }
        .contextMenu {
            Button("Show in Finder") { NSWorkspace.shared.selectFile(nil,inFileViewerRootedAtPath:folder.path) }.disabled(folder.missing)
            Button("Find Missing Folder…") { s.relocationFolder=folder;s.showFolderRelocation=true }.disabled(!folder.missing)
            Button(folder.favorite ? "Unmark Favorite":"Mark Favorite") {
                Task { await s.changeFolder(folder,patch:["favorite":!folder.favorite]) }
            }
            Menu("Color Label") {
                ForEach(LibraryLabels.names,id:\.self) { color in
                    Button(color.capitalized) { Task { await s.changeFolder(folder,patch:["color_label":color]) } }
                }
            }
            if folder.isRoot {
                Divider()
                Button("Show Parent Folder") { Task { await s.changeFolderRoot(folder,action:"show_parent") } }
                    .disabled(folder.parentPath == nil)
                Button("Hide This Parent") { Task { await s.changeFolderRoot(folder,action:"hide_parent") } }
                    .disabled(folder.directCount>0 || !folder.hasChildren)
            }
        }
    }
    var openButton: some View {
        Button { Task { await s.openFolder(folder) } } label: {
            HStack(spacing:5) {
                Image(systemName:folder.missing ? "folder.badge.questionmark":"folder")
                Text(folder.name).lineLimit(1)
                if folder.favorite { Image(systemName:"star.fill").font(.caption2) }
                Spacer(minLength:2)
                Text("\(s.includeSubfolders ? folder.totalCount:folder.directCount)").font(.caption).monospacedDigit()
                if folder.color != "none" { Rectangle().fill(LibraryLabels.color(folder.color)).frame(width:3,height:14) }
                if s.folderID == folder.id { Image(systemName:"checkmark").font(.caption) }
            }
        }.help(folder.path+(folder.missing ? " · Folder unavailable":""))
            .accessibilityLabel("\(folder.name), \(s.includeSubfolders ? folder.totalCount:folder.directCount) photos\(folder.missing ? ", unavailable":"")")
            .accessibilityAddTraits(s.folderID == folder.id ? .isSelected:[])
    }
}
