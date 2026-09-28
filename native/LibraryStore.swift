// Purpose: native collection and descriptive metadata workflows over shared APIs.
// Inputs: captured selections, expected metadata/collection revisions and forms.
// Outputs: refreshed bounded pages and catalog-only mutations; originals untouched.
// Recipe state and recipe revisions are never adopted from metadata write replies.
import Foundation

extension Store {
    func refreshCollections() async {
        do {
            let requestedOffset=collectionOffset
            let result=try await Backend.call("list_collections", ["offset":requestedOffset])
            guard requestedOffset == collectionOffset else { return }
            collections=(result["collections"] as? [[String: Any]] ?? []).compactMap(LibraryCollection.init)
            collectionTotal=result["total"] as? Int ?? 0
            if collections.isEmpty && collectionOffset > 0 {
                collectionOffset=max(0,collectionOffset-60)
                await refreshCollections()
            }
        } catch { self.error=error.localizedDescription }
    }

    func openCollection(_ collection: LibraryCollection) {
        collectionID=collection.id; mode="all"; workspace="library"; offset=0
        Task { await refresh() }
    }

    func editCollection(_ collection: LibraryCollection? = nil) {
        editingCollection=collection
        showCollectionEditor=true
    }

    func saveCollection(name: String, kind: String, rules: [String: Any], match: String,
                        original: LibraryCollection?) async -> Bool {
        var params: [String: Any] = ["name":name, "kind":kind, "rules":rules, "match":match]
        if let original {
            params["collection_id"]=original.id
            params["expected_revision"]=original.revision
        }
        do {
            let result=try await Backend.call("save_collection", params)
            await refreshCollections()
            if let saved=LibraryCollection(result) { openCollection(saved) }
            return true
        } catch { self.error=error.localizedDescription; return false }
    }

    func changeMembership(_ collection: LibraryCollection, action: String) async {
        let ids=selection.sorted()
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
        do {
            _=try await Backend.call("delete_collection", ["collection_id":collection.id,
                "expected_revision":collection.revision])
            if collectionID == collection.id { collectionID=nil; offset=0 }
            await refreshCollections()
            await refresh()
            message="Collection removed; photos remain in the library"
        } catch { self.error=error.localizedDescription }
    }

    func prepareMetadataEditor() async {
        guard !selection.isEmpty, await flushEdits() else { return }
        let ids=selection.sorted()
        do {
            var targets: [Photo] = []
            for id in ids {
                let result=try await Backend.call("get_photo", ["photo_id":id])
                if let target=Photo(result) { targets.append(target) }
            }
            guard selection.sorted() == ids else { return }
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
        let targets=photos.filter { selection.contains($0.id) }
        Task { _=await saveMetadata(targets:targets, patch:["color_label":label]) }
    }
}
