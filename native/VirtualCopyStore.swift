// Purpose: native virtual-copy actions with captured selection and confirmation.
// Inputs: service-owned photo identities/revisions, current source and user actions.
// Outputs: bounded refreshed pages, independent variants and catalog-only removal.
// Edits flush before copying; stale confirmations fail without replacing newer work.
import Foundation

extension Store {
    func captureCopyTargets(_ ids: [Int]) async throws -> [Photo] {
        let result=try await Backend.call("photo_summaries",["photo_ids":ids])
        let rows=(result["photos"] as? [[String:Any]] ?? []).compactMap(Photo.init)
        guard Set(rows.map(\.id)) == Set(ids) else { throw EngineFailure(message:"A selected photo no longer exists") }
        return rows
    }

    func createVirtualCopies(ids requested: [Int]?=nil) async {
        let ids=requested ?? actionPhotoIDs
        let active=selected
        let source=collectionID
        let collection=activeCollection
        guard !ids.isEmpty,!copyBusy else { return }
        copyBusy=true
        defer { copyBusy=false }
        guard await flushEdits() else { return }
        do {
            let targets=try await captureCopyTargets(ids)
            var params: [String:Any] = ["targets":targets.map { $0.copyTarget() }]
            if let collection,source == collection.id,["regular","quick"].contains(collection.kind) {
                params["collection_id"]=collection.id;params["expected_collection_revision"]=collection.revision
            }
            let result=try await Backend.call("create_virtual_copies",params)
            let copies=(result["photos"] as? [[String:Any]] ?? []).compactMap(Photo.init)
            await refreshCollections()
            await refresh()
            if selected == active,collectionID == source,let first=copies.first,photos.contains(where: { $0.id == first.id }) {
                choose(first.id)
                selection=Set(copies.map(\.id)).intersection(Set(photos.map(\.id)))
                reviewSelectionChanged()
            }
            message="Created \(copies.count) virtual \(copies.count == 1 ? "copy":"copies"). Copies may be hidden by the current filters or page."
        } catch { self.error=error.localizedDescription }
    }

    func setCopyAsMaster(_ captured: Photo?=nil) async {
        guard let id=(captured ?? photo)?.id,!copyBusy else { return }
        copyBusy=true
        defer { copyBusy=false }
        guard await flushEdits(),let target=photo?.id == id ? photo : captured,target.isVirtual else { return }
        do {
            let result=try await Backend.call("set_copy_as_master",target.copyTarget(includeSource:true))
            if selected == target.id,let updated=Photo(result) { photo=updated }
            await refresh()
            message="Set copy as master; each photo keeps its adjustments and collections"
        } catch { self.error=error.localizedDescription }
    }

    func prepareCopyRemoval(ids requested: [Int]?=nil) async {
        let ids=requested ?? actionPhotoIDs
        guard !ids.isEmpty,!copyBusy else { return }
        copyBusy=true
        defer { copyBusy=false }
        guard await flushEdits() else { return }
        do {
            let targets=try await captureCopyTargets(ids)
            guard targets.allSatisfy(\.isVirtual) else {
                error="Select only virtual copies to remove from the catalog";return
            }
            copyRemovalTargets=targets;showCopyRemoval=true
        } catch { self.error=error.localizedDescription }
    }

    func removeVirtualCopies(_ targets: [Photo]) async -> Bool {
        guard !targets.isEmpty,!copyBusy else { return false }
        copyBusy=true
        defer { copyBusy=false }
        guard await flushEdits() else { return false }
        do {
            _=try await Backend.call("remove_virtual_copies",["targets":targets.map { $0.copyTarget(includeSource:true) }])
            await refreshCollections()
            await refresh()
            message="Removed \(targets.count) virtual copies; originals and shared snapshots remain"
            return true
        } catch { self.error=error.localizedDescription;return false }
    }

    func showPhotoFamily(_ target: Photo,masterOnly: Bool=false) async {
        guard await flushEdits() else { return }
        collectionID=nil;activeCollection=nil;search="";mode="all";workspace="library"
        showStacks=false
        libraryFilters=["source_id":target.sourceID]
        if masterOnly { libraryFilters["is_virtual"]=false }
        librarySort="imported";sortDescending=false;offset=0
        await refresh()
    }
}

extension Photo {
    func copyTarget(includeSource: Bool=false) -> [String:Any] {
        var result: [String:Any] = ["photo_id":id,"expected_revision":revision,
                                  "expected_metadata_revision":metadataRevision]
        if includeSource { result["expected_source_revision"]=sourceRevision }
        return result
    }
}
