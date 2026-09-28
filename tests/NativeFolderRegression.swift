// Purpose: real native folder sources, lazy pages and external-change adoption.
// Inputs: five isolated rasters in nested folders and a real service. Outputs:
// state/IPC assertions. No desktop, Finder automation or original filesystem edits.
import AppKit
import Foundation

@main struct NativeFolderRegression {
    @MainActor static func main() async {
        _ = NSApplication.shared
        let s=Store()
        var checks: [String:Bool]=[:]
        func check(_ value: Bool,_ name: String) throws {
            checks[name]=value
            if !value { throw EngineFailure(message:name) }
        }
        do {
            let paths=ProcessInfo.processInfo.environment["LUMARAW_TEST_FIXTURES"]!.components(separatedBy:"|")
            await s.importPaths(paths)
            try check(s.total == 5 && s.folderPages[0]?.items.count == 2,"import_populates_folder_roots")
            let root=LibraryFolder(try await Backend.call("get_folder",["photo_id":1]))!
            let child=LibraryFolder(try await Backend.call("get_folder",["photo_id":2]))!
            try check(root.directCount == 1 && root.totalCount == 3,"root_counts_direct_and_descendant_photos")
            s.expandedFolders.insert(root.id);await s.loadFolderPage(parent:root.id)
            try check(s.folderPages[root.id]?.items.first?.id == child.id,"lazy_child_page_loaded")
            await s.openFolder(root)
            try check(s.folderID == root.id && s.collectionID == nil && s.total == 3,"folder_source_includes_descendants_by_default")
            await s.changeSubfolderInclusion(false)
            try check(s.total == 1 && s.photos.first?.id == 1,"direct_folder_view_excludes_descendants")
            s.libraryFilters=["rating_min":5];await s.refresh()
            try check(s.total == 0 && s.activeFolder?.id == root.id,"empty_filter_keeps_folder_source")
            _=try await Backend.call("rate_photo",["photo_id":2,"rating":5])
            await s.changeSubfolderInclusion(true)
            try check(s.total == 1 && s.photos.first?.id == 2,"metadata_filter_intersects_folder_source")
            s.prepareAutoStack()
            try check(s.autoStackSource?.folder == root.path,"auto_stack_captures_folder_source")
            let album=LibraryCollection(try await Backend.call("save_collection",["name":"Folder test","kind":"regular","photo_ids":[4]]))!
            await s.openCollection(album)
            try check(s.folderID == nil && s.collectionID == album.id && s.total == 0,"collection_clears_folder_but_preserves_filters")
            await s.openLibraryMode("all",clearFilters:true)
            try check(s.folderID == nil && s.collectionID == nil && s.total == 5,"all_photos_clears_sources_explicitly")
            await s.changeFolder(child,patch:["favorite":true,"color_label":"red"])
            s.folderFavorites=true;await s.refreshFolders(reset:true)
            try check(s.folderPages[0]?.items.map(\.id) == [child.id],"favorite_filter_returns_nested_folder")
            try check(s.folderPages[0]?.items.first?.color == "red","folder_color_adopted")
            await s.changeFolder(child,patch:["favorite":false])
            try check(s.error?.contains("Folder conflict") == true,"stale_folder_metadata_fails_visibly")
            s.error=nil;s.folderFavorites=false;await s.refreshFolders(reset:true)
            await s.changeFolderRoot(root,action:"show_parent")
            let parent=s.folderPages[0]!.items.first!
            try check(s.folderPages[0]?.items.count == 1 && parent.totalCount == 5,"show_parent_coalesces_visible_roots")
            await s.changeFolderRoot(parent,action:"hide_parent")
            try check(s.folderPages[0]?.items.count == 2,"hide_empty_parent_restores_children")
            s.expandedFolders.insert(root.id);await s.loadFolderPage(parent:root.id)
            s.collapseFolder(root.id)
            try check(!s.expandedFolders.contains(root.id) && s.folderPages[root.id] == nil,"collapse_releases_child_page")
            let photo=Photo(try await Backend.call("get_photo",["photo_id":2]))!
            s.folderSearch="not found";s.libraryFilters=["rating_min":1]
            await s.showPhotoFolder(photo)
            try check(s.folderID == child.id && s.selected == 2 && s.libraryFilters.isEmpty,"go_to_folder_locates_photo_and_clears_filters")
            try check(!s.showStacks && !s.includeSubfolders && s.folderSearch.isEmpty,"go_to_folder_exposes_individual_photo")
            try check(s.expandedFolders.contains(root.id) && s.folderPages[root.id]?.items.first?.id == child.id,"go_to_folder_reveals_tree_branch")
            s.libraryFilters=["rating_min":5];await s.openFolder(root)
            s.includeSubfolders=false;await s.refresh()
            try check(s.photos.isEmpty,"external_import_check_starts_with_empty_page")
            _=try await Backend.call("create_virtual_copies",["targets":[["photo_id":1,"expected_revision":0,"expected_metadata_revision":0]]])
            _=try await Backend.call("rate_photo",["photo_id":6,"rating":5])
            await s.refreshVisibleSummaries()
            try check(s.total == 1 && s.photos.first?.id == 6,"empty_page_poll_observes_external_folder_membership")
            try check(s.activeFolder?.directCount == 2 && s.activeFolder?.totalCount == 4,"external_copy_updates_sidebar_counts")
            var extra: [String]=[]
            for index in 0..<64 {
                let destination=URL(fileURLWithPath:paths[0]).deletingLastPathComponent().appendingPathComponent("late-\(index).png")
                try FileManager.default.copyItem(atPath:paths[0],toPath:destination.path)
                extra.append(destination.path)
            }
            _=try await Backend.call("import_photos",["paths":extra])
            let oldest=Photo(try await Backend.call("get_photo",["photo_id":1]))!
            s.librarySort="name";s.folderSearch="not found"
            await s.showPhotoFolder(oldest)
            try check(s.offset == 60 && s.selected == 1 && s.photos.contains(where:{$0.id==1}),"go_to_folder_finds_photo_beyond_first_page")
            try check(s.photos.count <= 60 && s.activeFolder?.directCount == 66,"large_source_stays_bounded_and_counts_are_current")
            print(String(data:try JSONSerialization.data(withJSONObject:["ok":true,"checks":checks,
                "desktop_ui":"NOT_VERIFIED"],options:[.prettyPrinted,.sortedKeys]),encoding:.utf8)!)
            exit(0)
        } catch {
            print(String(data:try! JSONSerialization.data(withJSONObject:["ok":false,"checks":checks,
                "error":error.localizedDescription,"store_error":s.error ?? ""],options:.prettyPrinted),encoding:.utf8)!)
            exit(1)
        }
    }
}
