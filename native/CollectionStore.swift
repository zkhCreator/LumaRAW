// Purpose: lazy collection-tree pages, color labels and revision-safe target workflows.
// Inputs: explicit expansion, captured collection revisions and photo selections.
// Outputs: bounded hierarchy/filter pages, catalog-only mutations and generation-safe
// active-set refreshes after node moves. No SQL, original writes or retries.
import Foundation

extension Store {
    func collectionNodeDrag(_ collection: LibraryCollection) -> CatalogCollectionDrag {
        CatalogCollectionDrag(
            session: ["regular", "smart", "set"].contains(collection.kind)
                ? referenceDragSession
                : "",
            collectionID: collection.id,
            revision: collection.revision
        )
    }

    func canDropCollectionNode(_ drag: CatalogCollectionDrag, to target: LibraryCollection) -> Bool {
        guard workspace == "library", !develop,
              drag.isValid(session: referenceDragSession),
              drag.collectionID != target.id,
              target.kind == "set",
              let source = visibleCollectionNode(id: drag.collectionID),
              source.revision == drag.revision,
              ["regular", "smart", "set"].contains(source.kind),
              let visibleTarget = visibleCollectionNode(id: target.id),
              visibleTarget.revision == target.revision,
              visibleTarget.kind == "set" else {
            return false
        }
        return true
    }

    private func visibleCollectionNode(id: Int) -> LibraryCollection? {
        if collectionColorFilter != "any" {
            guard !staleCollectionFilterPage,
                  let page = collectionFilteredPage,
                  page.treeRevision >= collectionTreeRevision else { return nil }
            return page.items.first { $0.id == id }
        }

        if !staleCollectionPageKeys.contains(0),
           let page = collectionPages[0],
           page.treeRevision >= collectionTreeRevision,
           let row = page.items.first(where: { $0.id == id }) {
            return row
        }
        for parent in expandedCollections.sorted() {
            guard !staleCollectionPageKeys.contains(parent),
                  let page = collectionPages[parent],
                  page.treeRevision >= collectionTreeRevision else { continue }
            if let row = page.items.first(where: { $0.id == id }) { return row }
        }
        return nil
    }

    @discardableResult
    func beginCollectionNodeDrop(
        _ drag: CatalogCollectionDrag,
        to target: LibraryCollection,
        call: ((String, [String: Any]) async throws -> [String: Any])? = nil,
        // Tests may gate this move's single list_photos request without replacing
        // the shared backend transport or any related metadata reads.
        pageCall: ((String, [String: Any]) async throws -> [String: Any])? = nil
    ) -> Task<Void, Never>? {
        guard canDropCollectionNode(drag, to: target) else { return nil }

        // Copy every gesture input before the task can suspend. The payload only
        // carries identity; mutable fields come from get_collection below.
        let sourceID = drag.collectionID
        let sourceRevision = drag.revision
        let targetID = target.id
        let targetKind = target.kind
        let commandCall: (String, [String: Any]) async throws -> [String: Any]
        if let call {
            commandCall = call
        } else {
            commandCall = { method, params in
                try await Backend.call(method, params)
            }
        }
        return Task {
            await reparentCollectionNode(
                sourceID: sourceID,
                expectedRevision: sourceRevision,
                targetID: targetID,
                targetKind: targetKind,
                call: commandCall,
                pageCall: pageCall
            )
        }
    }

    private func reparentCollectionNode(
        sourceID: Int,
        expectedRevision: Int,
        targetID: Int,
        targetKind: String,
        call: (String, [String: Any]) async throws -> [String: Any],
        pageCall: ((String, [String: Any]) async throws -> [String: Any])?
    ) async {
        do {
            guard targetKind == "set" else {
                throw EngineFailure(message: "Collections can only be dropped into a collection set")
            }
            guard let source = LibraryCollection(
                try await call("get_collection", ["collection_id": sourceID])
            ) else {
                throw EngineFailure(message: "Collection does not exist")
            }
            guard source.revision == expectedRevision else {
                throw EngineFailure(message: "Collection conflict; reload the collection before editing")
            }
            guard ["regular", "smart", "set"].contains(source.kind) else {
                throw EngineFailure(message: "This collection cannot be moved")
            }

            // Avoid the existing save path's revision bump for a same-parent drop.
            guard source.parentID != targetID else { return }

            let params: [String: Any] = [
                "collection_id": source.id,
                "expected_revision": source.revision,
                "name": source.name,
                "kind": source.kind,
                "rules": source.rules,
                "match": source.match,
                "parent_id": targetID,
            ]
            _ = try await call("save_collection", params)
            collectionNodePhotoRefreshGeneration += 1
            pendingCollectionNodePhotoRefreshGeneration = collectionNodePhotoRefreshGeneration
            await refreshLoadedCollectionPagesForTreeRevision()
            _ = await refreshPendingCollectionNodePhotos(pageCall: pageCall)
        } catch {
            self.error = error.localizedDescription
        }
    }

    @discardableResult
    func refreshPendingCollectionNodePhotos(
        expectedSourceNavigationGeneration: Int? = nil,
        allowingReviewSwitchToken: Int? = nil,
        pageCall: ((String, [String: Any]) async throws -> [String: Any])? = nil
    ) async -> Bool {
        guard let invalidation = pendingCollectionNodePhotoRefreshGeneration else { return true }
        guard workspace == "library", !develop, folderID == nil,
              let id = collectionID,
              activeCollection?.id == id, activeCollection?.kind == "set" else {
            return true
        }
        guard reviewSwitchInFlightGeneration == nil ||
                reviewSwitchInFlightGeneration == allowingReviewSwitchToken else {
            return false
        }
        guard expectedSourceNavigationGeneration == nil ||
                expectedSourceNavigationGeneration == sourceNavigationGeneration else { return false }
        let navigationGeneration = expectedSourceNavigationGeneration ?? sourceNavigationGeneration
        let reviewToken = reviewSwitchGeneration
        return await refreshPage(
            expectedSourceNavigationGeneration: navigationGeneration,
            expectedReviewSwitchGeneration: reviewToken,
            expectedCollectionID: id,
            consumingCollectionNodeRefreshGeneration: invalidation,
            guardingCollectionNodePhotoRefreshGeneration: invalidation,
            allowedReviewSwitchInFlightGeneration: allowingReviewSwitchToken,
            pageCall: pageCall
        )
    }

    func loadCollectionPage(parent: Int?,offset: Int=0) async {
        let key=parent ?? 0
        let token=(collectionPageGenerations[key] ?? 0)+1
        collectionPageGenerations[key]=token
        do {
            let result=try await Backend.call("list_collections",["parent_id":parent as Any? ?? NSNull(),"offset":offset])
            guard collectionPageGenerations[key] == token else { return }
            guard let treeRevision=result["tree_revision"] as? Int else {
                throw EngineFailure(message:"Collection listing did not include its tree revision")
            }
            if let parent,!expandedCollections.contains(parent) { return }
            guard treeRevision >= collectionTreeRevision else {
                staleCollectionPageKeys.insert(key)
                return
            }
            observeCollectionTreeRevision(treeRevision)
            let items=(result["collections"] as? [[String:Any]] ?? []).compactMap(LibraryCollection.init)
            let page=CollectionPage(items:items,offset:result["offset"] as? Int ?? 0,
                total:result["total"] as? Int ?? 0,treeRevision:treeRevision)
            staleCollectionPageKeys.remove(key)
            if let parent {
                if collectionPages[parent] != page { collectionPages[parent]=page }
            } else {
                if collections != items { collections=items }
                if collectionOffset != page.offset { collectionOffset=page.offset }
                if collectionTotal != page.total { collectionTotal=page.total }
                if collectionPages[0] != page { collectionPages[0]=page }
            }
        } catch {
            guard collectionPageGenerations[key] == token else { return }
            if let parent { collapseCollection(parent) }
            self.error=error.localizedDescription
        }
    }

    func observeCollectionTreeRevision(_ revision: Int) {
        guard revision > collectionTreeRevision else { return }
        collectionTreeRevision=revision
        for (key,page) in collectionPages where page.treeRevision < revision {
            staleCollectionPageKeys.insert(key)
        }
        if let page=collectionFilteredPage,page.treeRevision < revision {
            staleCollectionFilterPage=true
        }
    }

    func loadCollectionFilteredPage(offset: Int=0) async {
        guard collectionColorFilter != "any" else { return }
        collectionFilteredPageGeneration+=1
        let token=collectionFilteredPageGeneration
        let filter=collectionColorFilter
        var params: [String:Any] = ["offset":offset]
        if filter != "all" { params["color_label"]=filter }
        do {
            // Omitting parent_id requests the bounded flat global color-filter page.
            let result=try await Backend.call("list_collections",params)
            guard collectionFilteredPageGeneration == token,collectionColorFilter == filter else { return }
            guard let treeRevision=result["tree_revision"] as? Int else {
                throw EngineFailure(message:"Collection listing did not include its tree revision")
            }
            guard treeRevision >= collectionTreeRevision else {
                staleCollectionFilterPage=true
                return
            }
            observeCollectionTreeRevision(treeRevision)
            let page=CollectionPage(items:(result["collections"] as? [[String:Any]] ?? []).compactMap(LibraryCollection.init),
                offset:result["offset"] as? Int ?? 0,total:result["total"] as? Int ?? 0,treeRevision:treeRevision)
            collectionFilteredOffset=page.offset
            staleCollectionFilterPage=false
            if collectionFilteredPage != page { collectionFilteredPage=page }
        } catch {
            guard collectionFilteredPageGeneration == token else { return }
            self.error=error.localizedDescription
        }
    }

    func setCollectionColorFilter(_ filter: String) async {
        guard ["any","all","labeled","none","red","yellow","green","blue","purple"].contains(filter) else { return }
        guard collectionColorFilter != filter else {
            if filter != "any",collectionFilteredPage == nil { await loadCollectionFilteredPage(offset:collectionFilteredOffset) }
            return
        }
        collectionColorFilter=filter
        collectionFilteredOffset=0
        collectionFilteredPageGeneration+=1
        collectionFilteredPage=nil
        if filter == "any" {
            staleCollectionFilterPage=false
        } else {
            await loadCollectionFilteredPage(offset:0)
        }
    }

    func turnCollectionColorFilterPage(offset: Int) async {
        guard collectionColorFilter != "any" else { return }
        await loadCollectionFilteredPage(offset:max(0,offset))
    }

    func refreshLoadedCollectionPagesForTreeRevision() async {
        if let root=collectionPages[0] {
            await loadCollectionPage(parent:nil,offset:root.offset)
        } else if staleCollectionPageKeys.contains(0) {
            await loadCollectionPage(parent:nil,offset:collectionOffset)
        }
        for id in expandedCollections.sorted() {
            await loadCollectionPage(parent:id,offset:collectionPages[id]?.offset ?? 0)
        }
        if collectionColorFilter != "any" && (collectionFilteredPage != nil || staleCollectionFilterPage) {
            await loadCollectionFilteredPage(offset:collectionFilteredPage?.offset ?? collectionFilteredOffset)
        }
        if let id=collectionID,let capturedRevision=activeCollection?.revision,
           activeCollection?.id == id,
           let row=try? await Backend.call("get_collection",["collection_id":id]),
           let updated=LibraryCollection(row),collectionID == id,
           activeCollection?.id == id,activeCollection?.revision == capturedRevision,
           updated.revision >= capturedRevision,activeCollection != updated {
            activeCollection=updated
        }
    }

    func expandCollection(_ id: Int) {
        expandedCollections.insert(id)
        Task { await loadCollectionPage(parent:id) }
    }

    func collapseCollection(_ id: Int) {
        collectionPageGenerations[id]=(collectionPageGenerations[id] ?? 0)+1
        for child in collectionPages[id]?.items ?? [] where child.kind == "set" { collapseCollection(child.id) }
        collectionPages.removeValue(forKey:id);expandedCollections.remove(id);staleCollectionPageKeys.remove(id)
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
            guard let responseTreeRevision=result["tree_revision"] as? Int else {
                throw EngineFailure(message:"Collection state did not include its tree revision")
            }
            let treeChanged=responseTreeRevision > collectionTreeRevision
            observeCollectionTreeRevision(responseTreeRevision)
            if let state=CollectionState(result),collectionStateCanAdopt(state,responseTreeRevision:responseTreeRevision) {
                if collectionState != state {collectionState=state}
            }
            if treeChanged || !staleCollectionPageKeys.isEmpty || staleCollectionFilterPage {
                await refreshLoadedCollectionPagesForTreeRevision()
            }
        } catch { message=error.localizedDescription }
    }

    func collectionStateCanAdopt(_ state: CollectionState,responseTreeRevision: Int) -> Bool {
        guard responseTreeRevision >= collectionTreeRevision,
              state.revision >= (collectionState?.revision ?? 0) else { return false }
        if let current=collectionState,state.revision == current.revision {
            return state.target.revision >= current.target.revision && state.quick.revision >= current.quick.revision
        }
        return true
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

    func setCollectionColorLabel(_ collection: LibraryCollection,colorLabel: String) async -> Bool {
        await setCollectionColorLabels([collection],colorLabel:colorLabel)
    }

    func setCollectionColorLabels(_ captured: [LibraryCollection],colorLabel: String) async -> Bool {
        guard (1...60).contains(captured.count),Set(captured.map(\.id)).count == captured.count,
              captured.allSatisfy({ $0.kind != "quick" }),
              LibraryLabels.names.contains(colorLabel) else {
            error="Choose 1 to 60 unique non-Quick collections and a valid color label"
            return false
        }
        let targets=captured.map { ["collection_id":$0.id,"expected_revision":$0.revision] }
        do {
            _=try await Backend.call("set_collection_labels",["targets":targets,"color_label":colorLabel])
            await refreshCollections()
            message="Updated color labels for \(captured.count) collections"
            return true
        } catch {
            self.error=error.localizedDescription
            return false
        }
    }
}
