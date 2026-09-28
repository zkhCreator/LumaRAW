// Purpose: native collection and descriptive metadata workflows over shared APIs.
// Inputs: captured selections, expected metadata/collection revisions and forms.
// Outputs: refreshed bounded pages and catalog-only mutations; originals untouched.
// Recipe state and recipe revisions are never adopted from metadata write replies.
import Foundation

extension Store {
    func refreshCollections() async {
        await loadCollectionPage(parent:nil,offset:collectionOffset)
        for id in expandedCollections.sorted() {
            await loadCollectionPage(parent:id,offset:collectionPages[id]?.offset ?? 0)
        }
        await refreshCollectionState()
        if let id=collectionID,let row=try? await Backend.call("get_collection",["collection_id":id]),collectionID == id {
            activeCollection=LibraryCollection(row)
        }
    }

    func openCollection(_ collection: LibraryCollection) async {
        activeCollection=collection
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

    func changeMembership(_ collection: LibraryCollection, action: String, ids requested: [Int]?=nil) async {
        let ids=requested ?? selection.sorted()
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
        guard !actionPhotoIDs.isEmpty, await flushEdits() else { return }
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

    func saveMetadata(targets: [Photo], patch: [String: Any]) async -> Bool {
        guard !targets.isEmpty, !patch.isEmpty else { return false }
        do {
            let result=try await Backend.call("edit_metadata", ["targets":targets.map {
                ["photo_id":$0.id, "expected_metadata_revision":$0.metadataRevision]
            }, "patch":patch])
            let accepted=result["patch"] as? [String: Any] ?? [:]
            for row in result["updated"] as? [[String: Any]] ?? [] {
                guard let id=row["photo_id"] as? Int,let revision=row["metadata_revision"] as? Int else { continue }
                if var current=photo, current.id == id {
                    current.adoptLibraryPatch(accepted,revision:revision); photo=current
                }
                if let index=photos.firstIndex(where: { $0.id == id }) {
                    photos[index].adoptLibraryPatch(accepted,revision:revision)
                }
            }
            await refresh()
            message="Updated metadata for \(targets.count) photos"
            return true
        } catch { self.error=error.localizedDescription; return false }
    }

    func labelSelection(_ label: String) {
        let ids=Set(actionPhotoIDs)
        let targets=photos.filter { ids.contains($0.id) }
        Task { _=await saveMetadata(targets:targets, patch:["color_label":label]) }
    }
}
