// Purpose: verify collection-node saves do not retarget active Develop or Reference photos.
// Inputs: five generated originals, selected photos in moved children, and gated save calls.
// Outputs: active recipe/reference identity receipts plus current-set refresh on return to Library.
// This is native Store/backend coverage; desktop drag gestures and rendered app behavior are not verified.
import AppKit
import Foundation

private actor NodeDropSaveGate {
    private var blocked = false
    private var released = false
    private var continuation: CheckedContinuation<Void, Never>?

    func hold() async {
        blocked = true
        guard !released else { return }
        await withCheckedContinuation { continuation = $0 }
    }

    func isBlocked() -> Bool { blocked }

    func release() {
        released = true
        continuation?.resume()
        continuation = nil
    }
}

@main struct NativeCollectionNodeDevelopDropRegression {
    @MainActor static func main() async {
        _ = NSApplication.shared
        let s = Store()
        var checks: [String: Bool] = [:]

        func check(_ value: Bool, _ name: String) throws {
            checks[name] = value
            if !value { throw EngineFailure(message: name) }
        }

        func createCollection(_ name: String, kind: String = "regular", parentID: Int? = nil,
                              photoIDs: [Int] = []) async throws -> LibraryCollection {
            var params: [String: Any] = [
                "name": name, "kind": kind, "rules": [String: Any](), "match": "all",
                "parent_id": parentID as Any? ?? NSNull(),
            ]
            if !photoIDs.isEmpty { params["photo_ids"] = photoIDs }
            guard let row = LibraryCollection(try await Backend.call("save_collection", params)) else {
                throw EngineFailure(message: "Could not create collection \(name)")
            }
            return row
        }

        func readCollection(_ id: Int) async throws -> LibraryCollection {
            guard let row = LibraryCollection(try await Backend.call("get_collection", ["collection_id": id])) else {
                throw EngineFailure(message: "Collection \(id) disappeared")
            }
            return row
        }

        func waitForCollection(_ id: Int, count: Int, photoIDs: Set<Int>) async throws {
            for _ in 0..<400 {
                if s.collectionID == id && s.activeCollection?.id == id && s.total == count &&
                    Set(s.photos.map(\.id)) == photoIDs && !s.loading && !s.browsing { return }
                try await Task.sleep(nanoseconds: 25_000_000)
            }
            throw EngineFailure(message: "Collection page did not settle: \(s.error ?? "no error")")
        }

        func waitForActivePhoto(_ id: Int, exposure: Double) async throws {
            for _ in 0..<400 {
                let current = (s.photo?.recipe["exposure"] as? NSNumber)?.doubleValue
                if s.selected == id && s.photo?.id == id && current == exposure && !s.loading && !s.editing {
                    return
                }
                try await Task.sleep(nanoseconds: 25_000_000)
            }
            let actualExposure = (s.photo?.recipe["exposure"] as? NSNumber)?.doubleValue
            let actualExposureText = actualExposure.map { String($0) } ?? "nil"
            throw EngineFailure(message: "Active photo did not settle: expected=\(id)/\(exposure), " +
                "selected=\(s.selected.map { String($0) } ?? "nil"), photo=\(s.photo.map { String($0.id) } ?? "nil"), " +
                "exposure=\(actualExposureText), develop=\(s.develop), reference=\(s.referencePhoto.map { String($0.id) } ?? "nil"), " +
                "error=\(s.error ?? "no error")")
        }

        func waitForNodeCallGate(_ gate: NodeDropSaveGate, task: Task<Void, Never>) async throws {
            for _ in 0..<400 {
                if await gate.isBlocked() { return }
                try await Task.sleep(nanoseconds: 25_000_000)
            }
            await gate.release()
            await task.value
            throw EngineFailure(message: "Collection operation did not reach the test gate")
        }

        func prepareMove(sourceSet: LibraryCollection, childID: Int, targetID: Int,
                         photoID: Int, remainingPhotoID: Int,
                         exposure: Double) async throws -> (CatalogCollectionDrag, LibraryCollection) {
            await s.refreshCollections()
            s.expandCollection(sourceSet.id)
            await s.refreshCollections()
            guard let childRow = s.collectionPages[sourceSet.id]?.items.first(where: { $0.id == childID }),
                  let targetRow = s.collections.first(where: { $0.id == targetID }) else {
                throw EngineFailure(message: "Source child or destination set is not visible")
            }
            let members = try await Backend.call("list_photos", ["collection_id": sourceSet.id, "stacked": false])
            let memberIDs = Set((members["photos"] as? [[String: Any]] ?? []).compactMap { $0["id"] as? Int })
            let childMembers = try await Backend.call("list_photos", ["collection_id": childID, "stacked": false])
            let childPhotoIDs = Set((childMembers["photos"] as? [[String: Any]] ?? []).compactMap { $0["id"] as? Int })
            try check(memberIDs == Set([photoID, remainingPhotoID]) && childPhotoIDs == [photoID],
                      "selected_photo_belongs_only_to_the_moved_child_\(sourceSet.name)")

            let currentSource = try await readCollection(sourceSet.id)
            await s.openCollection(currentSource)
            try await waitForCollection(sourceSet.id, count: 2, photoIDs: [photoID, remainingPhotoID])
            s.choose(photoID)
            try await waitForActivePhoto(photoID, exposure: 0)
            s.set("exposure", exposure)
            try check(await s.flushEdits(), "active_recipe_flushes_before_node_drop_\(sourceSet.name)")
            try await waitForActivePhoto(photoID, exposure: exposure)
            let drag = s.collectionNodeDrag(childRow)
            try check(s.canDropCollectionNode(drag, to: targetRow), "visible_child_can_move_\(sourceSet.name)")
            return (drag, targetRow)
        }

        do {
            guard let fixtureValue = ProcessInfo.processInfo.environment["LUMARAW_TEST_FIXTURES"] else {
                throw EngineFailure(message: "Missing generated photo fixtures")
            }
            let paths = fixtureValue.components(separatedBy: "|")
            guard paths.count == 5 else {
                throw EngineFailure(message: "This regression requires the runner's five generated fixtures")
            }
            let originalBytes = try paths.map { try Data(contentsOf: URL(fileURLWithPath: $0)) }
            await s.importPaths(paths)
            let listing = try await Backend.call("list_photos", ["stacked": false])
            let photoIDs = (listing["photos"] as? [[String: Any]] ?? []).compactMap { $0["id"] as? Int }
            try check(photoIDs.count == 5, "five_generated_photos_imported")

            let developSet = try await createCollection("Develop source set", kind: "set")
            let developChild = try await createCollection("Develop-only child", parentID: developSet.id,
                                                           photoIDs: [photoIDs[0]])
            _ = try await createCollection("Develop remaining child", parentID: developSet.id,
                                           photoIDs: [photoIDs[1]])
            let developTarget = try await createCollection("Develop destination", kind: "set")
            let referenceSet = try await createCollection("Reference source set", kind: "set")
            let referenceChild = try await createCollection("Reference-only child", parentID: referenceSet.id,
                                                             photoIDs: [photoIDs[2]])
            _ = try await createCollection("Reference remaining child", parentID: referenceSet.id,
                                           photoIDs: [photoIDs[3]])
            let referenceTarget = try await createCollection("Reference destination", kind: "set")
            await s.refreshCollections()

            // Develop remains bound to its selected child photo while that child moves out.
            await s.openLibraryMode("all", clearFilters: true)
            await s.setReferencePhoto(photoIDs[4])
            s.referenceLocked = true
            let heldReferenceID = s.referencePhoto?.id
            let heldReferenceRevision = s.referencePhoto?.revision
            try check(heldReferenceID == photoIDs[4] && heldReferenceID != photoIDs[0],
                      "develop_case_starts_with_distinct_reference_identity")
            let (developDrag, developTargetRow) = try await prepareMove(
                sourceSet: developSet, childID: developChild.id, targetID: developTarget.id,
                photoID: photoIDs[0], remainingPhotoID: photoIDs[1], exposure: 0.65)
            await s.startDevelop()
            let developDrop = s.beginCollectionNodeDrop(developDrag, to: developTargetRow, call: { method, params in
                if method == "save_collection" {
                    throw EngineFailure(message: "Develop must reject collection-node drops")
                }
                return try await Backend.call(method, params)
            })
            let rejectedWhileDevelop = !s.canDropCollectionNode(developDrag, to: developTargetRow) && developDrop == nil
            if let developDrop { await developDrop.value }
            try check(rejectedWhileDevelop, "collection_node_drop_is_not_admitted_in_develop")
            s.error = nil
            await s.switchLibraryView(.grid)
            try await waitForCollection(developSet.id, count: 2, photoIDs: [photoIDs[0], photoIDs[1]])
            let developGate = NodeDropSaveGate()
            guard let developTask = s.beginCollectionNodeDrop(developDrag, to: developTargetRow, call: { method, params in
                if method == "save_collection", params["collection_id"] as? Int == developChild.id {
                    await developGate.hold()
                }
                return try await Backend.call(method, params)
            }) else {
                throw EngineFailure(message: "Develop child was not admitted for reparenting")
            }
            try await waitForNodeCallGate(developGate, task: developTask)
            await s.startDevelop()
            try await waitForActivePhoto(photoIDs[0], exposure: 0.65)
            await developGate.release()
            await developTask.value
            try await waitForActivePhoto(photoIDs[0], exposure: 0.65)
            let developPhoto = try await Backend.call("get_photo", ["photo_id": photoIDs[0]])
            let developRecipe = (developPhoto["recipe"] as? [String: Any]) ?? [:]
            try check(s.develop && s.workspace == "library" && s.selected == photoIDs[0] &&
                      s.photo?.id == photoIDs[0] && s.referencePhoto?.id == heldReferenceID &&
                      s.referencePhoto?.revision == heldReferenceRevision &&
                      (developRecipe["exposure"] as? NSNumber)?.doubleValue == 0.65,
                      "gated_drop_preserves_develop_photo_recipe_and_reference_identity")
            await s.switchLibraryView(.grid)
            try await waitForCollection(developSet.id, count: 1, photoIDs: [photoIDs[1]])
            try check(!s.develop && s.collectionID == developSet.id && s.total == 1 &&
                      Set(s.photos.map(\.id)) == [photoIDs[1]],
                      "return_from_develop_refreshes_the_current_set_page")

            // Reference keeps its independent identity while the active photo's only
            // membership in this source set moves out in another gated save.
            await s.openLibraryMode("all", clearFilters: true)
            await s.setReferencePhoto(photoIDs[4])
            let referenceID = s.referencePhoto?.id
            let referenceRevision = s.referencePhoto?.revision
            let (referenceDrag, referenceTargetRow) = try await prepareMove(
                sourceSet: referenceSet, childID: referenceChild.id, targetID: referenceTarget.id,
                photoID: photoIDs[2], remainingPhotoID: photoIDs[3], exposure: -0.4)
            let referenceGate = NodeDropSaveGate()
            guard let referenceTask = s.beginCollectionNodeDrop(referenceDrag, to: referenceTargetRow, call: { method, params in
                if method == "save_collection", params["collection_id"] as? Int == referenceChild.id {
                    await referenceGate.hold()
                }
                return try await Backend.call(method, params)
            }) else {
                throw EngineFailure(message: "Reference child was not admitted for reparenting")
            }
            try await waitForNodeCallGate(referenceGate, task: referenceTask)
            await s.startReferenceView()
            try await waitForActivePhoto(photoIDs[2], exposure: -0.4)
            for _ in 0..<400 {
                if s.referenceRenderer.frame?.request.context.photoID == referenceID &&
                    !s.referenceRenderer.loading { break }
                try await Task.sleep(nanoseconds: 25_000_000)
            }
            await referenceGate.release()
            await referenceTask.value
            try await waitForActivePhoto(photoIDs[2], exposure: -0.4)
            let referencePhoto = try await Backend.call("get_photo", ["photo_id": photoIDs[2]])
            let referenceRecipe = (referencePhoto["recipe"] as? [String: Any]) ?? [:]
            try check(s.isReferenceView && s.selected == photoIDs[2] && s.photo?.id == photoIDs[2] &&
                      s.referencePhoto?.id == referenceID && s.referencePhoto?.revision == referenceRevision &&
                      s.referenceRenderer.frame?.request.context.photoID == referenceID &&
                      (referenceRecipe["exposure"] as? NSNumber)?.doubleValue == -0.4,
                      "gated_drop_preserves_reference_identity_and_active_photo_recipe")
            await s.switchLibraryView(.grid)
            try await waitForCollection(referenceSet.id, count: 1, photoIDs: [photoIDs[3]])
            try check(!s.develop && !s.isReferenceView && s.collectionID == referenceSet.id &&
                      s.total == 1 && Set(s.photos.map(\.id)) == [photoIDs[3]],
                      "return_from_reference_refreshes_the_current_set_page")

            // An older page response cannot consume a newer move's invalidation.
            let generationSet = try await createCollection("Generation source set", kind: "set")
            let olderChild = try await createCollection("Older move child", parentID: generationSet.id,
                                                        photoIDs: [photoIDs[0]])
            let newerChild = try await createCollection("Newer move child", parentID: generationSet.id,
                                                        photoIDs: [photoIDs[1]])
            _ = try await createCollection("Generation resident child", parentID: generationSet.id,
                                           photoIDs: [photoIDs[2]])
            await s.refreshCollections()
            let generationSetSnapshot = try await readCollection(generationSet.id)
            await s.openCollection(generationSetSnapshot)
            try await waitForCollection(generationSet.id, count: 3,
                                        photoIDs: Set([photoIDs[0], photoIDs[1], photoIDs[2]]))
            s.expandCollection(generationSet.id)
            await s.refreshCollections()
            guard let olderRow = s.collectionPages[generationSet.id]?.items.first(where: { $0.id == olderChild.id }),
                  let newerTarget = s.collections.first(where: { $0.id == developTarget.id }) else {
                throw EngineFailure(message: "Older move source or target was not visible")
            }
            let pageBeforeMoves = Set(s.photos.map(\.id))
            let olderGate = NodeDropSaveGate()
            guard let olderTask = s.beginCollectionNodeDrop(s.collectionNodeDrag(olderRow), to: newerTarget,
                pageCall: { method, params in
                    let reply = try await Backend.call(method, params)
                    if method == "list_photos" { await olderGate.hold() }
                    return reply
                }) else {
                throw EngineFailure(message: "Older generation move was not admitted")
            }
            try await waitForNodeCallGate(olderGate, task: olderTask)
            guard let olderGeneration = s.pendingCollectionNodePhotoRefreshGeneration else {
                await olderGate.release()
                await olderTask.value
                throw EngineFailure(message: "Acknowledged move did not leave its photo refresh pending")
            }

            await s.refreshCollections()
            guard let newerRow = s.collectionPages[generationSet.id]?.items.first(where: { $0.id == newerChild.id }),
                  let newerTargetAfterRefresh = s.collections.first(where: { $0.id == referenceTarget.id }) else {
                await olderGate.release()
                await olderTask.value
                throw EngineFailure(message: "Newer move source or target was not visible")
            }
            let newerDrag = s.collectionNodeDrag(newerRow)
            try check(s.canDropCollectionNode(newerDrag, to: newerTargetAfterRefresh),
                      "second_move_remains_admissible_while_older_page_is_waiting")
            guard let newerTask = s.beginCollectionNodeDrop(newerDrag, to: newerTargetAfterRefresh,
                pageCall: { _, _ in
                    throw EngineFailure(message: "Controlled current-page read failure")
                }) else {
                await olderGate.release()
                await olderTask.value
                throw EngineFailure(message: "Newer generation move was not admitted")
            }
            await newerTask.value
            guard let newerGeneration = s.pendingCollectionNodePhotoRefreshGeneration else {
                await olderGate.release()
                await olderTask.value
                throw EngineFailure(message: "Failed current-page read cleared the newer invalidation")
            }
            try check(newerGeneration > olderGeneration && s.error != nil,
                      "failed_newer_page_keeps_advanced_invalidation")
            s.error = nil
            await olderGate.release()
            await olderTask.value
            try check(s.pendingCollectionNodePhotoRefreshGeneration == newerGeneration &&
                      s.total == 3 && Set(s.photos.map(\.id)) == pageBeforeMoves,
                      "older_late_page_cannot_adopt_or_consume_newer_invalidation")

            await s.switchLibraryView(.compare)
            try await waitForCollection(generationSet.id, count: 1, photoIDs: [photoIDs[2]])
            try check(s.libraryView == .compare && s.reviewPhotoIDs == [photoIDs[2]] &&
                      s.pendingCollectionNodePhotoRefreshGeneration == nil,
                      "compare_return_uses_fresh_current_set_before_seeding_review")

            // A late page reply abandoned by a newer Develop transition leaves
            // the move pending until Survey returns with a fresh current page.
            let surveyChild = try await createCollection("Survey move child", parentID: generationSet.id,
                                                          photoIDs: [photoIDs[3]])
            await s.refreshCollections()
            await s.openLibraryMode("all", clearFilters: true)
            let surveySetSnapshot = try await readCollection(generationSet.id)
            await s.openCollection(surveySetSnapshot)
            try await waitForCollection(generationSet.id, count: 2, photoIDs: [photoIDs[2], photoIDs[3]])
            s.choose(photoIDs[3])
            try await waitForActivePhoto(photoIDs[3], exposure: 0)
            s.set("exposure", 0.25)
            try check(await s.flushEdits(), "survey_case_active_recipe_flushes")
            try await waitForActivePhoto(photoIDs[3], exposure: 0.25)
            await s.refreshCollections()
            guard let surveyRow = s.collectionPages[generationSet.id]?.items.first(where: { $0.id == surveyChild.id }),
                  let surveyTarget = s.collections.first(where: { $0.id == developTarget.id }) else {
                throw EngineFailure(message: "Survey move source or target was not visible")
            }
            let surveyPageGate = NodeDropSaveGate()
            guard let surveyTask = s.beginCollectionNodeDrop(s.collectionNodeDrag(surveyRow), to: surveyTarget,
                pageCall: { method, params in
                    let reply = try await Backend.call(method, params)
                    if method == "list_photos" { await surveyPageGate.hold() }
                    return reply
                }) else {
                throw EngineFailure(message: "Survey move was not admitted")
            }
            try await waitForNodeCallGate(surveyPageGate, task: surveyTask)
            await s.startDevelop()
            await surveyPageGate.release()
            await surveyTask.value
            guard let surveyGeneration = s.pendingCollectionNodePhotoRefreshGeneration else {
                throw EngineFailure(message: "Aborted late page reply consumed the pending survey invalidation")
            }
            try check(s.develop && s.pendingCollectionNodePhotoRefreshGeneration == surveyGeneration &&
                      s.selected == photoIDs[3] && s.photo?.id == photoIDs[3] &&
                      (s.photo?.recipe["exposure"] as? NSNumber)?.doubleValue == 0.25 &&
                      Set(s.photos.map(\.id)) == Set([photoIDs[2], photoIDs[3]]),
                      "develop_transition_aborts_late_page_without_retargeting_or_clearing_pending")
            await s.switchLibraryView(.survey)
            try await waitForCollection(generationSet.id, count: 1, photoIDs: [photoIDs[2]])
            try check(s.libraryView == .survey && s.reviewPhotoIDs == [photoIDs[2]] &&
                      s.pendingCollectionNodePhotoRefreshGeneration == nil,
                      "survey_return_uses_fresh_current_set_page")
            try check(try paths.map { try Data(contentsOf: URL(fileURLWithPath: $0)) } == originalBytes,
                      "develop_reference_and_refresh_races_preserve_original_bytes")

            print(String(data: try JSONSerialization.data(withJSONObject: [
                "ok": true, "checks": checks,
                "desktop_drag_drop": "NOT_VERIFIED", "develop_window": "NOT_VERIFIED",
                "reference_window": "NOT_VERIFIED",
            ], options: [.prettyPrinted, .sortedKeys]), encoding: .utf8)!)
            exit(0)
        } catch {
            print(String(data: try! JSONSerialization.data(withJSONObject: [
                "ok": false, "checks": checks, "error": error.localizedDescription,
                "store_error": s.error ?? "", "desktop_drag_drop": "NOT_VERIFIED",
            ], options: [.prettyPrinted, .sortedKeys]), encoding: .utf8)!)
            exit(1)
        }
    }
}
