// Purpose: lazy collection-tree pages and revision-safe Quick/target workflows.
// Inputs: explicit expansion, captured collection state and photo selections.
// Outputs: bounded sidebar pages, membership and atomic Quick-save requests.
// No SQL, original writes or implicit retries after another client changes target.
import Foundation

extension Store {
    func loadCollectionPage(parent: Int?,offset: Int=0) async {
        let key=parent ?? 0
        let token=(collectionPageGenerations[key] ?? 0)+1
        collectionPageGenerations[key]=token
        do {
            let result=try await Backend.call("list_collections",["parent_id":parent as Any? ?? NSNull(),"offset":offset])
            guard collectionPageGenerations[key] == token else { return }
            let items=(result["collections"] as? [[String:Any]] ?? []).compactMap(LibraryCollection.init)
            let page=CollectionPage(items:items,offset:result["offset"] as? Int ?? 0,total:result["total"] as? Int ?? 0)
            if let parent {
                guard expandedCollections.contains(parent) else { return }
                collectionPages[parent]=page
            } else {
                collections=items;collectionOffset=page.offset;collectionTotal=page.total
                collectionPages[0]=page
            }
        } catch {
            guard collectionPageGenerations[key] == token else { return }
            if let parent { collapseCollection(parent) }
            self.error=error.localizedDescription
        }
    }

    func expandCollection(_ id: Int) {
        expandedCollections.insert(id)
        Task { await loadCollectionPage(parent:id) }
    }

    func collapseCollection(_ id: Int) {
        collectionPageGenerations[id]=(collectionPageGenerations[id] ?? 0)+1
        for child in collectionPages[id]?.items ?? [] where child.kind == "set" { collapseCollection(child.id) }
        collectionPages.removeValue(forKey:id);expandedCollections.remove(id)
    }

    func turnCollectionPage(parent: Int?,offset: Int) async {
        if parent == nil { collectionOffset=offset }
        for child in collectionPages[parent ?? 0]?.items ?? [] where child.kind == "set" { collapseCollection(child.id) }
        await loadCollectionPage(parent:parent,offset:offset)
    }

    func refreshCollectionState() async {
        let ids=photos.map(\.id)
        do {
            let result=try await Backend.call("collection_state",ids.isEmpty ? [:]:["photo_ids":ids])
            guard photos.map(\.id) == ids else { return }
            if let state=CollectionState(result),state.revision >= (collectionState?.revision ?? 0) {
                if let current=collectionState,state.revision == current.revision,
                   (state.target.revision < current.target.revision || state.quick.revision < current.quick.revision) { return }
                collectionState=state
            }
        } catch { message=error.localizedDescription }
    }

    func setTargetCollection(_ collection: LibraryCollection?) async {
        guard let state=collectionState else { return }
        do {
            _=try await Backend.call("set_target_collection",["collection_id":collection?.id as Any? ?? NSNull(),
                "expected_revision":state.revision])
            await refreshCollectionState()
        } catch { self.error=error.localizedDescription }
    }

    func toggleTargetMembership(ids: [Int]?=nil) async {
        let ids=ids ?? actionPhotoIDs
        guard !ids.isEmpty,let state=collectionState else { return }
        let remove=ids.allSatisfy { state.members.contains($0) }
        do {
            _=try await Backend.call("target_membership",["collection_id":state.target.id,
                "expected_state_revision":state.revision,"expected_revision":state.target.revision,
                "photo_ids":ids,"action":remove ? "remove":"add"])
            await refreshCollections()
            if collectionID == state.target.id { await refresh() }
            message="\(remove ? "Removed from":"Added to") \(state.target.name)"
        } catch { self.error=error.localizedDescription }
    }

    func saveQuickCollection(_ source: LibraryCollection,name: String,clear: Bool) async -> Bool {
        do {
            let result=try await Backend.call("quick_collection",["expected_revision":source.revision,
                "action":"save","name":name,"clear_after":clear])
            await refreshCollections()
            if let row=result["saved"] as? [String:Any],let saved=LibraryCollection(row) { await openCollection(saved) }
            return true
        } catch { self.error=error.localizedDescription;return false }
    }

    func collectionContainsCurrentSource(_ collection: LibraryCollection) async -> Bool {
        guard let id=collectionID else { return false }
        if id == collection.id { return true }
        guard collection.kind == "set",let row=try? await Backend.call("get_collection",["collection_id":id]) else { return false }
        return (row["ancestors"] as? [[String:Any]] ?? []).contains { $0["id"] as? Int == collection.id }
    }

    func duplicateCollection(_ collection: LibraryCollection) async {
        do {
            let result=try await Backend.call("duplicate_collection",["collection_id":collection.id,
                "expected_revision":collection.revision,"name":String(collection.name.prefix(110))+" Copy"])
            await refreshCollections()
            if let saved=LibraryCollection(result) { await openCollection(saved) }
        } catch { self.error=error.localizedDescription }
    }

    func clearQuickCollection(_ source: LibraryCollection) async {
        do {
            _=try await Backend.call("quick_collection",["expected_revision":source.revision,"action":"clear"])
            await refreshCollections()
            if collectionID == source.id { await refresh() }
        } catch { self.error=error.localizedDescription }
    }
}
