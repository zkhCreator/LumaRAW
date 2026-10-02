// Purpose: native collection and descriptive metadata workflows over shared APIs.
// Inputs: captured selections, expected metadata/collection revisions and forms.
// Outputs: optional refreshed bounded pages and catalog-only mutations; originals untouched.
// Recipe state and recipe revisions are never adopted from metadata write replies.
import Foundation

extension Store {
    func refreshCollections() async {
        await loadCollectionPage(parent:nil,offset:collectionOffset)
        for id in expandedCollections.sorted() {
            await loadCollectionPage(parent:id,offset:collectionPages[id]?.offset ?? 0)
        }
        if collectionColorFilter != "any" {
            await loadCollectionFilteredPage(offset:collectionFilteredPage?.offset ?? collectionFilteredOffset)
        }
        await refreshCollectionState()
        let captured=activeCollection
        if let id=collectionID,let row=try? await Backend.call("get_collection",["collection_id":id]),
           collectionID == id,activeCollection == captured,let updated=LibraryCollection(row),
           updated.revision >= (captured?.revision ?? 0),activeCollection != updated {
            activeCollection=updated
        }
    }

    func openCollection(_ collection: LibraryCollection) async {
        sourceNavigationGeneration+=1;let token=sourceNavigationGeneration
        guard await flushEdits(),token == sourceNavigationGeneration else { return }
        folderID=nil;activeFolder=nil
        activeCollection=collection
        showStacks=true
        collectionID=collection.id; mode="all"; workspace="library"; offset=0
        await refresh()
    }

    func editCollection(_ collection: LibraryCollection? = nil,kind: String="regular",parent: Int?=nil) {
        newCollectionKind=kind;newCollectionParent=parent
        editingCollection=collection
        showCollectionEditor=true
    }

    func saveCollection(name: String, kind: String, rules: [String: Any], match: String,
                        original: LibraryCollection?,parentID: Int?=nil,includePhotos: Bool=false) async -> Bool {
        var params: [String: Any] = ["name":name, "kind":kind, "rules":rules, "match":match,"parent_id":parentID as Any? ?? NSNull()]
        if let original {
            params["collection_id"]=original.id
            params["expected_revision"]=original.revision
        }
        if includePhotos,!selection.isEmpty { params["photo_ids"]=selection.sorted() }
        do {
            let result=try await Backend.call("save_collection", params)
            await refreshCollections()
            if let saved=LibraryCollection(result) { await openCollection(saved) }
            return true
        } catch { self.error=error.localizedDescription; return false }
    }

    func libraryPhotoDrag(_ id: Int) -> CatalogPhotoDrag {
        guard workspace == "library", !develop, libraryView == .grid, selection.contains(id) else {
            return CatalogPhotoDrag(session: referenceDragSession, photoID: id)
        }
        let ids = photos.map(\.id).filter(selection.contains).sorted()
        guard ids.contains(id), !ids.isEmpty, ids.count <= 60 else {
            return CatalogPhotoDrag(session: referenceDragSession, photoID: id)
        }
        return CatalogPhotoDrag(session: referenceDragSession, photoID: id, photoIDs: ids)
    }

    func canDropInCollection(_ drag: CatalogPhotoDrag, to collection: LibraryCollection) -> Bool {
        guard workspace == "library" else { return false }
        if collection.kind == "quick" {
            guard collectionState?.quick.id == collection.id else { return false }
        } else if collection.kind != "regular" {
            return false
        }
        return drag.isValid(session: referenceDragSession, visiblePhotoIDs: Set(photos.map(\.id)))
    }

    @discardableResult
    func beginCollectionDrop(_ drag: CatalogPhotoDrag, to collection: LibraryCollection) -> Task<Void, Never>? {
        guard canDropInCollection(drag, to: collection) else { return nil }
        let ids = drag.resolvedPhotoIDs
        return Task { await changeMembership(collection, action: "add", ids: ids) }
    }

    @discardableResult
    func beginCollectionMembership(_ collection: LibraryCollection, action: String, ids requested: [Int]? = nil) -> Task<Void, Never>? {
        let ids = requested ?? selection.sorted()
        guard !ids.isEmpty else { return nil }
        return Task { await changeMembership(collection, action: action, ids: ids) }
    }

    func changeMembership(_ collection: LibraryCollection, action: String, ids: [Int]) async {
        guard !ids.isEmpty else { return }
        do {
            _=try await Backend.call("collection_membership", ["collection_id":collection.id,
                "expected_revision":collection.revision, "photo_ids":ids, "action":action])
            await refreshCollections()
            await refresh()
            message=action == "add" ? "Added \(ids.count) photos to \(collection.name)" : "Removed \(ids.count) photos from \(collection.name)"
        } catch { self.error=error.localizedDescription }
    }

    func deleteCollection(_ collection: LibraryCollection) async {
        let viewed=collectionID
        let current=await collectionContainsCurrentSource(collection)
        do {
            _=try await Backend.call("delete_collection", ["collection_id":collection.id,
                "expected_revision":collection.revision])
            if current,collectionID == viewed { collectionID=nil;activeCollection=nil;offset=0 }
            collapseCollection(collection.id)
            await refreshCollections()
            await refresh()
            message="Collection removed; photos remain in the library"
        } catch { self.error=error.localizedDescription }
    }

    func prepareMetadataEditor() async {
        guard !metadataPresetBusy,!actionPhotoIDs.isEmpty, await flushEdits() else { return }
        await refreshMetadataSchema()
        guard !iptcFields.isEmpty else { return }
        let ids=actionPhotoIDs
        do {
            var targets: [Photo] = []
            for id in ids {
                let result=try await Backend.call("get_photo", ["photo_id":id])
                if let target=Photo(result) { targets.append(target) }
            }
            guard actionPhotoIDs == ids else { return }
            metadataTargets=targets
            showMetadataEditor=true
        } catch { self.error=error.localizedDescription }
    }

    func saveMetadata(
        targets: [Photo],
        patch: [String: Any],
        refreshAfter: Bool = true,
        call: CullingCommandCall? = nil,
        shouldAdopt: CullingMutationAdoption? = nil
    ) async -> Bool {
        guard !targets.isEmpty, !patch.isEmpty else { return false }
        metadataWriteGeneration += 1
        let writeGeneration = metadataWriteGeneration
        let targetIDs = Set(targets.map(\.id))
        for id in targetIDs {
            metadataWriteGenerationByPhoto[id] = writeGeneration
        }
        defer {
            for id in targetIDs where metadataWriteGenerationByPhoto[id] == writeGeneration {
                metadataWriteGenerationByPhoto.removeValue(forKey: id)
            }
        }
        do {
            let params: [String: Any] = ["targets":targets.map {
                ["photo_id":$0.id, "expected_metadata_revision":$0.metadataRevision]
            }, "patch":patch]
            let result: [String: Any]
            if let call {
                result = try await call("edit_metadata", params)
            } else {
                result = try await Backend.call("edit_metadata", params)
            }
            let accepted=result["patch"] as? [String: Any] ?? [:]
            let updates = (result["updated"] as? [[String: Any]] ?? []).compactMap { row -> (Int, Int)? in
                guard let id=row["photo_id"] as? Int,
                      let revision=row["metadata_revision"] as? Int else { return nil }
                return (id, revision)
            }
            for (id, revision) in updates {
                let pageRevision = photos.first(where: { $0.id == id })?.metadataRevision
                let activeRevision = photo?.id == id ? photo?.metadataRevision : nil
                let knownRevision = [pageRevision, activeRevision].compactMap { $0 }.max()
                guard knownRevision.map({ revision >= $0 }) ?? true else { continue }
                if var current=photo, current.id == id {
                    current.adoptLibraryPatch(accepted,revision:revision); photo=current
                }
                if let index=photos.firstIndex(where: { $0.id == id }) {
                    photos[index].adoptLibraryPatch(accepted,revision:revision)
                }
            }
            func canPresentResult() -> Bool {
                targetIDs.allSatisfy { id in
                    metadataWriteGenerationByPhoto[id] == writeGeneration
                        && (shouldAdopt.map { $0(id) } ?? true)
                }
            }
            if refreshAfter, canPresentResult() { await refresh() }
            if canPresentResult() { message="Updated metadata for \(targets.count) photos" }
            return true
        } catch {
            if targetIDs.allSatisfy({ id in
                metadataWriteGenerationByPhoto[id] == writeGeneration
                    && (shouldAdopt.map { $0(id) } ?? true)
            }) {
                self.error=error.localizedDescription
            }
            return false
        }
    }

    func labelSelection(_ label: String) {
        let ids=Set(actionPhotoIDs)
        let targets=photos.filter { ids.contains($0.id) }
        Task { _=await saveMetadata(targets:targets, patch:["color_label":label]) }
    }
}
