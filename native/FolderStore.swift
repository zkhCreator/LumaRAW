// Purpose: lazy folder presentation and source navigation over the portable API.
// Inputs: explicit source/expansion, bounded folder pages and captured revisions.
// Outputs: native tree state and catalog-only folder actions. No SQL, filesystem
// traversal or original writes. Late pages and superseded navigation are ignored.
import Foundation

struct LibraryFolder: Identifiable {
    let id: Int
    let path: String
    let name: String
    let parentPath: String?
    let directCount: Int
    let totalCount: Int
    let revision: Int
    let isRoot: Bool
    let hasChildren: Bool
    let missing: Bool
    let favorite: Bool
    let color: String
    let pageOffset: Int

    init?(_ row: [String:Any]) {
        guard let id=row["id"] as? Int,let path=row["path"] as? String,let name=row["name"] as? String else { return nil }
        self.id=id;self.path=path;self.name=name;parentPath=row["parent_path"] as? String
        directCount=row["direct_count"] as? Int ?? 0;totalCount=row["total_count"] as? Int ?? 0
        revision=row["revision"] as? Int ?? 0;isRoot=(row["is_root"] as? Int ?? 0) != 0
        hasChildren=row["has_children"] as? Bool ?? false;missing=row["missing"] as? Bool ?? false
        favorite=(row["favorite"] as? Int ?? 0) != 0;color=row["color_label"] as? String ?? "none"
        pageOffset=row["page_offset"] as? Int ?? 0
    }
}

struct FolderPage {
    let items: [LibraryFolder]
    let offset: Int
    let total: Int
}

struct FolderQuery: Hashable {
    let search: String
    let favorites: Bool
    let color: String
    var filtered: Bool { !search.isEmpty || favorites || color != "any" }
}

extension Store {
    var folderQuery: FolderQuery { FolderQuery(search:folderSearch,favorites:folderFavorites,color:folderColor) }

    func scheduleFolderSearch() {
        folderSearchTask?.cancel()
        folderSearchTask=Task {
            do { try await Task.sleep(nanoseconds:200_000_000) } catch { return }
            await refreshFolders(reset:true)
        }
    }

    func loadFolderPage(parent: Int?, offset: Int=0) async {
        let key=parent ?? 0
        let token=(folderPageGenerations[key] ?? 0)+1
        folderPageGenerations[key]=token
        let query=folderQuery
        var params: [String:Any]=["offset":offset]
        if let parent { params["parent_id"]=parent }
        else {
            params["search"]=query.search;params["favorites"]=query.favorites
            if query.color != "any" { params["color_label"]=query.color }
        }
        do {
            let result=try await Backend.call("list_folders",params)
            guard folderPageGenerations[key] == token,query == folderQuery else { return }
            if let parent, !expandedFolders.contains(parent) { return }
            let rows=(result["folders"] as? [[String:Any]] ?? []).compactMap(LibraryFolder.init)
            folderPages[key]=FolderPage(items:rows,offset:result["offset"] as? Int ?? 0,total:result["total"] as? Int ?? 0)
            if parent == nil { folderRevision=result["folder_revision"] as? Int ?? folderRevision }
        } catch {
            guard folderPageGenerations[key] == token,query == folderQuery else { return }
            self.error=error.localizedDescription
        }
    }

    func refreshFolders(reset: Bool=false) async {
        if reset {
            for id in Array(expandedFolders) { collapseFolder(id) }
            folderPages.removeAll()
        }
        await loadFolderPage(parent:nil,offset:reset ? 0:folderPages[0]?.offset ?? 0)
        if !folderQuery.filtered {
            for id in expandedFolders.sorted() {
                await loadFolderPage(parent:id,offset:folderPages[id]?.offset ?? 0)
            }
        }
        if let id=folderID,let row=try? await Backend.call("get_folder",["folder_id":id]),folderID == id {
            activeFolder=LibraryFolder(row)
        }
    }

    func expandFolder(_ id: Int) {
        expandedFolders.insert(id)
        Task { await loadFolderPage(parent:id) }
    }

    func collapseFolder(_ id: Int) {
        folderPageGenerations[id]=(folderPageGenerations[id] ?? 0)+1
        for child in folderPages[id]?.items ?? [] { collapseFolder(child.id) }
        folderPages.removeValue(forKey:id);expandedFolders.remove(id)
    }

    func turnFolderPage(parent: Int?,offset: Int) async {
        for child in folderPages[parent ?? 0]?.items ?? [] { collapseFolder(child.id) }
        await loadFolderPage(parent:parent,offset:offset)
    }

    func openFolder(_ folder: LibraryFolder) async {
        sourceNavigationGeneration+=1;let token=sourceNavigationGeneration
        guard await flushEdits(),token == sourceNavigationGeneration else { return }
        folderID=folder.id;activeFolder=folder;collectionID=nil;activeCollection=nil
        mode="all";workspace="library";offset=0;showStacks=true
        await refresh()
    }

    func changeSubfolderInclusion(_ value: Bool) async {
        includeSubfolders=value
        if folderID != nil { offset=0;await refresh() }
    }

    func openLibraryMode(_ value: String,clearFilters: Bool=false) async {
        sourceNavigationGeneration+=1;let token=sourceNavigationGeneration
        guard await flushEdits(),token == sourceNavigationGeneration else { return }
        folderID=nil;activeFolder=nil;collectionID=nil;activeCollection=nil
        mode=value;workspace="library";offset=0;showStacks=true
        if clearFilters { libraryFilters=[:];search="" }
        await refresh()
    }

    func changeFolder(_ folder: LibraryFolder,patch: [String:Any]) async {
        do {
            _=try await Backend.call("edit_folder",["folder_id":folder.id,"expected_revision":folder.revision,"patch":patch])
            await refreshFolders()
        } catch { self.error=error.localizedDescription }
    }

    func changeFolderRoot(_ folder: LibraryFolder,action: String) async {
        let revision=folderRevision
        do {
            _=try await Backend.call("set_folder_visibility",["folder_id":folder.id,"expected_revision":revision,"action":action])
            await refreshFolders(reset:true)
        } catch { self.error=error.localizedDescription }
    }

    func showPhotoFolder(_ target: Photo) async {
        sourceNavigationGeneration+=1;let token=sourceNavigationGeneration
        guard await flushEdits(),token == sourceNavigationGeneration else { return }
        do {
            let result=try await Backend.call("get_folder",["photo_id":target.id])
            guard token == sourceNavigationGeneration,let folder=LibraryFolder(result) else { return }
            folderSearchTask?.cancel()
            folderSearch="";folderFavorites=false;folderColor="any"
            folderID=folder.id;activeFolder=folder;collectionID=nil;activeCollection=nil
            libraryFilters=[:];search="";mode="all";workspace="library";develop=false
            includeSubfolders=false;showStacks=false;librarySort="imported";sortDescending=true
            offset=result["photo_offset"] as? Int ?? 0
            await refresh()
            guard token == sourceNavigationGeneration else { return }
            choose(target.id)
            let ancestors=(result["ancestors"] as? [[String:Any]] ?? []).compactMap(LibraryFolder.init)
            let chain=ancestors+[folder]
            if let start=chain.firstIndex(where: { $0.isRoot }) {
                await loadFolderPage(parent:nil,offset:chain[start].pageOffset)
                for index in start..<(chain.count-1) {
                    guard token == sourceNavigationGeneration else { return }
                    expandedFolders.insert(chain[index].id)
                    await loadFolderPage(parent:chain[index].id,offset:chain[index+1].pageOffset)
                }
            }
            message="Showing this photo's folder with filters cleared and stacks expanded as individual photos"
        } catch { if token == sourceNavigationGeneration { self.error=error.localizedDescription } }
    }
}
