// Purpose: exercise collection-node reparent admission and catalog outcomes through native Store hooks.
// Inputs: five generated photos, revision-bearing collection rows and captured node payloads.
// Outputs: move/no-op/conflict receipts plus original/member preservation evidence.
// Photo drag and Reference compatibility remain covered by their separate existing suites.
// Offscreen snapshots are layout evidence only; native drag hover/drop remains NOT_VERIFIED.
import AppKit
import Foundation
import SwiftUI

private actor CollectionNodeSaveGate {
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

@main struct NativeCollectionNodeDropRegression {
    @MainActor static func main() async {
        _ = NSApplication.shared
        let s = Store()
        var checks: [String: Bool] = [:]
        var screenshots: [String] = []

        func check(_ value: Bool, _ name: String) throws {
            checks[name] = value
            if !value { throw EngineFailure(message: name) }
        }

        func snapshot<V: View>(_ name: String, _ view: V, _ size: NSSize, _ root: URL) async throws {
            let host = NSHostingView(rootView: view.background(Color(nsColor: .windowBackgroundColor)))
            host.frame = NSRect(origin: .zero, size: size)
            host.layoutSubtreeIfNeeded()
            try await Task.sleep(nanoseconds: 150_000_000)
            host.layoutSubtreeIfNeeded()
            guard let bitmap = host.bitmapImageRepForCachingDisplay(in: host.bounds) else {
                throw EngineFailure(message: "No offscreen bitmap for \(name)")
            }
            host.cacheDisplay(in: host.bounds, to: bitmap)
            guard let png = bitmap.representation(using: .png, properties: [:]) else {
                throw EngineFailure(message: "No offscreen PNG for \(name)")
            }
            try png.write(to: root.appendingPathComponent(name))
            screenshots.append(name)
        }

        func createCollection(_ name: String, kind: String = "regular", parentID: Int? = nil,
                              rules: [String: Any] = [:], match: String = "all",
                              photoIDs: [Int] = []) async throws -> LibraryCollection {
            var params: [String: Any] = [
                "name": name, "kind": kind, "rules": rules, "match": match,
                "parent_id": parentID as Any? ?? NSNull(),
            ]
            if !photoIDs.isEmpty { params["photo_ids"] = photoIDs }
            guard let collection = LibraryCollection(try await Backend.call("save_collection", params)) else {
                throw EngineFailure(message: "Could not create collection \(name)")
            }
            return collection
        }

        func readCollection(_ id: Int) async throws -> LibraryCollection {
            guard let collection = LibraryCollection(try await Backend.call("get_collection", ["collection_id": id])) else {
                throw EngineFailure(message: "Collection \(id) disappeared")
            }
            return collection
        }

        func collectionPhotos(_ id: Int) async throws -> Set<Int> {
            let result = try await Backend.call("list_photos", ["collection_id": id, "stacked": false])
            return Set((result["photos"] as? [[String: Any]] ?? []).compactMap { $0["id"] as? Int })
        }

        func treeRevision() async throws -> Int {
            let result = try await Backend.call("collection_state")
            guard let revision = result["tree_revision"] as? Int else {
                throw EngineFailure(message: "Collection state omitted its tree revision")
            }
            return revision
        }

        // Page refreshes can fill decoder metadata caches; compare authored state.
        func photoState(_ id: Int) async throws -> Data {
            let row = try await Backend.call("get_photo", ["photo_id": id])
            let keys = ["id", "name", "path", "revision", "source_revision", "orientation", "rating", "flag",
                        "title", "caption", "copyright", "color_label", "metadata_revision", "recipe", "iptc", "keywords", "keyword_ids", "copy_name"]
            let state = Dictionary(uniqueKeysWithValues: keys.map { ($0, row[$0] ?? NSNull()) })
            return try JSONSerialization.data(withJSONObject: state, options: [.sortedKeys])
        }

        func waitForCollectionRows(_ parentID: Int) async throws {
            for _ in 0..<300 {
                if s.collectionPages[parentID]?.treeRevision == s.collectionTreeRevision { return }
                try await Task.sleep(nanoseconds: 20_000_000)
            }
            throw EngineFailure(message: "Collection page for set \(parentID) did not settle")
        }

        func waitForCurrentCollection(_ id: Int, total: Int, photoIDs: Set<Int>) async throws {
            for _ in 0..<300 {
                if s.collectionID == id && s.activeCollection?.id == id && s.total == total &&
                    Set(s.photos.map(\.id)) == photoIDs && !s.loading { return }
                try await Task.sleep(nanoseconds: 20_000_000)
            }
            throw EngineFailure(message: "Current set page did not update: \(s.error ?? "no error")")
        }

        do {
            guard let fixtureValue = ProcessInfo.processInfo.environment["LUMARAW_TEST_FIXTURES"] else {
                throw EngineFailure(message: "Missing generated photo fixtures")
            }
            let paths = fixtureValue.components(separatedBy: "|")
            guard paths.count == 5 else {
                throw EngineFailure(message: "This regression requires the runner's five generated fixtures")
            }
            let originals = try paths.map { try Data(contentsOf: URL(fileURLWithPath: $0)) }
            let snapshotRoot = URL(fileURLWithPath: ProcessInfo.processInfo.environment["LUMARAW_CATALOG"]!)
                .deletingLastPathComponent()
            _ = try await Backend.call("import_photos", ["paths": paths])
            let page = try await Backend.call("list_photos", ["stacked": false])
            let ids = (page["photos"] as? [[String: Any]] ?? []).compactMap { $0["id"] as? Int }
            try check(ids.count == 5 && page["total"] as? Int == 5, "five_generated_photos_imported")
            var originalPhotoStates: [Int: Data] = [:]
            for id in ids { originalPhotoStates[id] = try await photoState(id) }

            let targetA = try await createCollection("Node target A", kind: "set")
            let targetB = try await createCollection("Node target B", kind: "set")
            let invalidTarget = try await createCollection("Node regular target")
            var regular = try await createCollection("Member source", photoIDs: Array(ids.prefix(2)))
            let destinationArrival = try await createCollection("Destination arrival", photoIDs: [ids[4]])
            let smartRules: [String: Any] = ["rating_min": 2]
            let smart = try await createCollection("Smart source", kind: "smart", rules: smartRules, match: "any")
            let subtree = try await createCollection("Movable subtree", kind: "set")
            let subtreeChild = try await createCollection("Subtree member", parentID: subtree.id, photoIDs: [ids[2]])

            let labelResult = try await Backend.call("set_collection_labels", [
                "targets": [["collection_id": regular.id, "expected_revision": regular.revision]],
                "color_label": "blue",
            ])
            guard let labeledRows = labelResult["collections"] as? [[String: Any]],
                  let labeledRegular = labeledRows.first.flatMap(LibraryCollection.init) else {
                throw EngineFailure(message: "Could not label the member source")
            }
            regular = labeledRegular
            await s.refreshCollections()

            // The transferable contains only captured identity, and malformed or foreign sessions are rejected.
            let regularDrag = s.collectionNodeDrag(regular)
            let encodedDrag = try JSONEncoder().encode(regularDrag)
            let dragObject = try JSONSerialization.jsonObject(with: encodedDrag) as? [String: Any] ?? [:]
            let malformedID = CatalogCollectionDrag(session: s.referenceDragSession, collectionID: 0, revision: regular.revision)
            let malformedRevision = CatalogCollectionDrag(session: s.referenceDragSession, collectionID: regular.id, revision: -1)
            let foreign = CatalogCollectionDrag(session: "foreign-session", collectionID: regular.id, revision: regular.revision)
            let malformedJSON = Data(#"{"session":"x","collectionID":"not-an-id","revision":0}"#.utf8)
            let malformedDecoded = (try? JSONDecoder().decode(CatalogCollectionDrag.self, from: malformedJSON)) != nil
            try check(regularDrag.session == s.referenceDragSession && regularDrag.collectionID == regular.id &&
                      regularDrag.revision == regular.revision && Set(dragObject.keys) == Set(["session", "collectionID", "revision"]) &&
                      !malformedID.isValid(session: s.referenceDragSession) &&
                      !malformedRevision.isValid(session: s.referenceDragSession) && !malformedDecoded,
                      "node_payload_contains_only_valid_captured_identity")
            try check(!s.canDropCollectionNode(foreign, to: targetA), "foreign_session_rejected")
            try check(!s.canDropCollectionNode(regularDrag, to: invalidTarget), "regular_collection_is_not_a_node_drop_target")
            let priorWorkspace = s.workspace
            s.workspace = "exports"
            let rejectedOutsideLibrary = !s.canDropCollectionNode(regularDrag, to: targetA)
            s.workspace = priorWorkspace
            try check(rejectedOutsideLibrary, "node_drop_requires_library_workspace")
            guard let quick = s.collectionState?.quick else {
                throw EngineFailure(message: "Quick Collection state was not loaded")
            }
            let quickDrag = s.collectionNodeDrag(quick)
            let forgedQuickDrag = CatalogCollectionDrag(session: s.referenceDragSession,
                                                        collectionID: quick.id, revision: quick.revision)
            let quickDropTask = s.beginCollectionNodeDrop(forgedQuickDrag, to: targetA)
            let quickDropWasRejected: Bool
            if let quickDropTask {
                await quickDropTask.value
                quickDropWasRejected = false
            } else {
                quickDropWasRejected = true
            }
            let quickTargetTask = s.beginCollectionNodeDrop(regularDrag, to: quick)
            let quickTargetWasRejected: Bool
            if let quickTargetTask {
                await quickTargetTask.value
                quickTargetWasRejected = false
            } else {
                quickTargetWasRejected = true
            }
            try check(!s.canDropCollectionNode(quickDrag, to: targetA) &&
                      !s.canDropCollectionNode(forgedQuickDrag, to: targetA) && quickDropWasRejected &&
                      !s.canDropCollectionNode(regularDrag, to: quick) && quickTargetWasRejected,
                      "quick_source_and_target_rejected_synchronously")
            try await snapshot("collection-node-drop-tree.png",
                VStack(alignment: .leading, spacing: 12) { CollectionsSidebar() }
                    .padding(16).environmentObject(s), NSSize(width: 360, height: 600), snapshotRoot)

            // Hold the captured mutation while navigation completes, then release it.
            await s.openCollection(regular)
            try await waitForCurrentCollection(regular.id, total: 2, photoIDs: Set(ids.prefix(2)))
            s.selection = Set(ids.prefix(2))
            let navigationTarget = try await readCollection(targetB.id)
            let saveGate = CollectionNodeSaveGate()
            guard let capturedTask = s.beginCollectionNodeDrop(regularDrag, to: targetA, call: { method, params in
                if method == "save_collection", params["collection_id"] as? Int == regular.id {
                    await saveGate.hold()
                }
                return try await Backend.call(method, params)
            }) else {
                throw EngineFailure(message: "Visible regular source was not accepted")
            }
            s.selection = Set([ids[4]])
            var saveWasBlocked = false
            for _ in 0..<300 {
                if await saveGate.isBlocked() {
                    saveWasBlocked = true
                    break
                }
                try await Task.sleep(nanoseconds: 20_000_000)
            }
            guard saveWasBlocked else {
                await saveGate.release()
                await capturedTask.value
                throw EngineFailure(message: "Captured collection save did not reach the test gate")
            }
            await s.openCollection(navigationTarget)
            let navigatedSelection = s.selection
            let navigatedPhotoIDs = Set(s.photos.map(\.id))
            let navigatedTotal = s.total
            await saveGate.release()
            await capturedTask.value
            let movedRegular = try await readCollection(regular.id)
            let regularMembers = try await collectionPhotos(regular.id)
            try check(s.error == nil && movedRegular.parentID == targetA.id && movedRegular.name == regular.name &&
                      movedRegular.kind == regular.kind && movedRegular.rules.isEmpty && movedRegular.match == regular.match &&
                      movedRegular.colorLabel == "blue" && regularMembers == Set(ids.prefix(2)) &&
                      s.selection == navigatedSelection && s.collectionID == targetB.id &&
                      s.activeCollection?.id == targetB.id && s.total == navigatedTotal &&
                      Set(s.photos.map(\.id)) == navigatedPhotoIDs,
                      "captured_node_destination_preserves_fields_members_and_later_selection")

            // If navigation enters the affected destination while save is held,
            // completion refreshes that current set without changing the selection.
            let regularPage = try await readCollection(regular.id)
            await s.openCollection(regularPage)
            try await waitForCurrentCollection(regular.id, total: 2, photoIDs: Set(ids.prefix(2)))
            let arrivalRow = try await readCollection(destinationArrival.id)
            let arrivalTarget = try await readCollection(targetA.id)
            let arrivalDrag = s.collectionNodeDrag(arrivalRow)
            try check(s.canDropCollectionNode(arrivalDrag, to: arrivalTarget),
                      "destination_refresh_source_and_target_are_visible")
            let arrivalGate = CollectionNodeSaveGate()
            guard let arrivalTask = s.beginCollectionNodeDrop(arrivalDrag, to: arrivalTarget, call: { method, params in
                if method == "save_collection", params["collection_id"] as? Int == destinationArrival.id {
                    await arrivalGate.hold()
                }
                return try await Backend.call(method, params)
            }) else {
                throw EngineFailure(message: "Visible destination source was not admitted")
            }
            var arrivalSaveWasBlocked = false
            for _ in 0..<300 {
                if await arrivalGate.isBlocked() {
                    arrivalSaveWasBlocked = true
                    break
                }
                try await Task.sleep(nanoseconds: 20_000_000)
            }
            guard arrivalSaveWasBlocked else {
                await arrivalGate.release()
                await arrivalTask.value
                throw EngineFailure(message: "Destination collection save did not reach the test gate")
            }
            await s.openCollection(arrivalTarget)
            try await waitForCurrentCollection(targetA.id, total: 2, photoIDs: Set(ids.prefix(2)))
            let destinationSelection = s.selection
            await arrivalGate.release()
            await arrivalTask.value
            try await waitForCurrentCollection(targetA.id, total: 3,
                                               photoIDs: Set([ids[0], ids[1], ids[4]]))
            try check(s.error == nil && s.collectionID == targetA.id && s.activeCollection?.id == targetA.id &&
                      s.selection == destinationSelection && s.total == 3 &&
                      Set(s.photos.map(\.id)) == Set([ids[0], ids[1], ids[4]]),
                      "gated_move_refreshes_newly_active_destination_and_keeps_selection")

            // A drop back onto the current set does not change either row or the tree revision.
            s.error = nil
            s.expandCollection(targetA.id)
            await s.refreshCollections()
            try await waitForCollectionRows(targetA.id)
            let sameParentSource = try await readCollection(regular.id)
            let sameParentTarget = try await readCollection(targetA.id)
            let sameParentTreeRevision = try await treeRevision()
            guard let sameParentTask = s.beginCollectionNodeDrop(
                s.collectionNodeDrag(sameParentSource), to: sameParentTarget) else {
                throw EngineFailure(message: "Same-parent node was not admitted")
            }
            await sameParentTask.value
            let sameParentAfter = try await readCollection(regular.id)
            let sameParentTreeAfter = try await treeRevision()
            try check(s.error == nil && sameParentAfter.parentID == targetA.id &&
                      sameParentAfter.revision == sameParentSource.revision &&
                      sameParentTreeAfter == sameParentTreeRevision,
                      "same_parent_drop_is_a_true_noop")

            // A smart collection's rule fields survive the same reparent path.
            s.error = nil
            let currentSmart = try await readCollection(smart.id)
            let currentTargetA = try await readCollection(targetA.id)
            guard let smartTask = s.beginCollectionNodeDrop(s.collectionNodeDrag(currentSmart), to: currentTargetA) else {
                throw EngineFailure(message: "Visible smart source was not admitted")
            }
            await smartTask.value
            let movedSmart = try await readCollection(smart.id)
            try check(s.error == nil && movedSmart.parentID == targetA.id && movedSmart.kind == "smart" &&
                      NSDictionary(dictionary: movedSmart.rules).isEqual(to: smartRules) && movedSmart.match == "any",
                      "smart_collection_rules_and_match_survive_reparent")

            // Moving a set leaves its nested child and photo membership attached to that set.
            s.error = nil
            let movedSubtree = try await readCollection(subtree.id)
            let currentTargetB = try await readCollection(targetB.id)
            guard let subtreeTask = s.beginCollectionNodeDrop(s.collectionNodeDrag(movedSubtree), to: currentTargetB) else {
                throw EngineFailure(message: "Visible set source was not admitted")
            }
            await subtreeTask.value
            let subtreeAfter = try await readCollection(subtree.id)
            let subtreeChildAfter = try await readCollection(subtreeChild.id)
            let subtreeMembersAfter = try await collectionPhotos(subtreeChild.id)
            try check(s.error == nil && subtreeAfter.parentID == targetB.id && subtreeAfter.kind == "set" &&
                      subtreeChildAfter.parentID == subtree.id &&
                      subtreeMembersAfter == Set([ids[2]]),
                      "set_reparent_preserves_descendants_and_membership")

            // Moving a child out of the currently open source set updates its page without changing source.
            let currentSourceSet = try await createCollection("Currently open source", kind: "set")
            let departingChild = try await createCollection("Departing photo", parentID: currentSourceSet.id,
                                                            photoIDs: [ids[3]])
            let incomingChild = try await createCollection("Incoming photo", photoIDs: [ids[4]])
            await s.refreshCollections()
            s.expandCollection(currentSourceSet.id)
            await s.refreshCollections()
            try await waitForCollectionRows(currentSourceSet.id)
            let currentSourceRow = try await readCollection(currentSourceSet.id)
            await s.openCollection(currentSourceRow)
            try await waitForCurrentCollection(currentSourceSet.id, total: 1, photoIDs: [ids[3]])
            let departingRow = try await readCollection(departingChild.id)
            let departingDrag = s.collectionNodeDrag(departingRow)
            let destinationBeforeDeparture = try await readCollection(targetB.id)
            guard let departTask = s.beginCollectionNodeDrop(departingDrag, to: destinationBeforeDeparture) else {
                throw EngineFailure(message: "Visible child in the current source set was not admitted")
            }
            await departTask.value
            try await waitForCurrentCollection(currentSourceSet.id, total: 0, photoIDs: [])
            try check(s.error == nil && s.collectionID == currentSourceSet.id &&
                      s.activeCollection?.id == currentSourceSet.id,
                      "moving_child_out_refreshes_current_source_without_navigating")

            // The currently open destination set gains the incoming child's photos and remains selected.
            let destinationRow = try await readCollection(targetB.id)
            await s.openCollection(destinationRow)
            try await waitForCurrentCollection(targetB.id, total: 2, photoIDs: Set([ids[2], ids[3]]))
            let incomingRow = try await readCollection(incomingChild.id)
            let incomingDrag = s.collectionNodeDrag(incomingRow)
            let currentDestination = try await readCollection(targetB.id)
            guard let incomingTask = s.beginCollectionNodeDrop(incomingDrag, to: currentDestination) else {
                throw EngineFailure(message: "Visible incoming child was not admitted into the current destination")
            }
            await incomingTask.value
            try await waitForCurrentCollection(targetB.id, total: 3, photoIDs: Set([ids[2], ids[3], ids[4]]))
            try check(s.error == nil && s.collectionID == targetB.id && s.activeCollection?.id == targetB.id,
                      "moving_child_into_current_destination_refreshes_its_photos")

            // The UI row may be stale after an external edit; its captured revision must not be silently rebased.
            s.error = nil
            let staleSource = try await createCollection("Stale source")
            await s.refreshCollections()
            let staleTarget = try await readCollection(targetB.id)
            let staleDrag = s.collectionNodeDrag(staleSource)
            _ = try await Backend.call("save_collection", [
                "collection_id": staleSource.id, "expected_revision": staleSource.revision,
                "name": "External rename", "kind": staleSource.kind, "rules": staleSource.rules,
                "match": staleSource.match, "parent_id": NSNull(),
            ])
            guard let staleTask = s.beginCollectionNodeDrop(staleDrag, to: staleTarget) else {
                throw EngineFailure(message: "Captured stale source should reach revision validation")
            }
            await staleTask.value
            let staleAfter = try await readCollection(staleSource.id)
            try check(s.error?.localizedCaseInsensitiveContains("conflict") == true &&
                      staleAfter.name == "External rename" && staleAfter.parentID == nil &&
                      staleAfter.revision == staleSource.revision + 1,
                      "stale_source_revision_rejected_without_rebase_or_retry")

            // Engine validation rejects cycles before writing any part of the tree.
            s.error = nil
            let cycleRoot = try await createCollection("Cycle root", kind: "set")
            let cycleChild = try await createCollection("Cycle child", kind: "set", parentID: cycleRoot.id)
            let cycleLeaf = try await createCollection("Cycle leaf", kind: "set", parentID: cycleChild.id)
            s.expandCollection(cycleRoot.id)
            s.expandCollection(cycleChild.id)
            await s.refreshCollections()
            try await waitForCollectionRows(cycleChild.id)
            let cycleRootBefore = try await readCollection(cycleRoot.id)
            let cycleChildBefore = try await readCollection(cycleChild.id)
            let cycleLeafBefore = try await readCollection(cycleLeaf.id)
            let cycleRevisionBefore = try await treeRevision()
            guard let cycleTask = s.beginCollectionNodeDrop(s.collectionNodeDrag(cycleRootBefore), to: cycleLeafBefore) else {
                throw EngineFailure(message: "Visible cycle target was not admitted for engine validation")
            }
            await cycleTask.value
            let cycleRootAfter = try await readCollection(cycleRoot.id)
            let cycleChildAfter = try await readCollection(cycleChild.id)
            let cycleLeafAfter = try await readCollection(cycleLeaf.id)
            let cycleRevisionAfter = try await treeRevision()
            try check(s.error != nil && cycleRootAfter.parentID == cycleRootBefore.parentID &&
                      cycleRootAfter.revision == cycleRootBefore.revision &&
                      cycleChildAfter.parentID == cycleChildBefore.parentID &&
                      cycleChildAfter.revision == cycleChildBefore.revision &&
                      cycleLeafAfter.parentID == cycleLeafBefore.parentID &&
                      cycleLeafAfter.revision == cycleLeafBefore.revision &&
                      cycleRevisionAfter == cycleRevisionBefore,
                      "cycle_rejected_atomically_without_tree_revision_change")

            // A target at the supported nesting limit cannot accept another node.
            s.error = nil
            var depthIDs: [Int] = []
            var parentID: Int?
            for depth in 1...32 {
                let row = try await createCollection("Depth \(depth)", kind: "set", parentID: parentID)
                depthIDs.append(row.id)
                parentID = row.id
            }
            let depthSource = try await createCollection("Depth source")
            await s.refreshCollections()
            // Expand ancestors in user order; this case tests the depth rule,
            // not simultaneous submission beyond the transport's command limit.
            for id in depthIDs.dropLast() {
                s.expandCollection(id)
                try await waitForCollectionRows(id)
            }
            try await waitForCollectionRows(depthIDs[depthIDs.count - 2])
            let depthSourceBefore = try await readCollection(depthSource.id)
            let depthTarget = try await readCollection(depthIDs.last!)
            let depthRevisionBefore = try await treeRevision()
            guard let depthTask = s.beginCollectionNodeDrop(s.collectionNodeDrag(depthSourceBefore), to: depthTarget) else {
                throw EngineFailure(message: "Visible depth-limit target was not admitted for engine validation")
            }
            await depthTask.value
            let depthSourceAfter = try await readCollection(depthSource.id)
            let depthTargetAfter = try await readCollection(depthTarget.id)
            let depthRevisionAfter = try await treeRevision()
            try check(s.error != nil && depthSourceAfter.parentID == nil &&
                      depthSourceAfter.revision == depthSourceBefore.revision &&
                      depthTargetAfter.revision == depthTarget.revision &&
                      depthRevisionAfter == depthRevisionBefore,
                      "depth_limit_rejected_atomically_without_tree_revision_change")

            var photosUnchanged = true
            for id in ids {
                if try await photoState(id) != originalPhotoStates[id] { photosUnchanged = false }
            }
            try check(photosUnchanged, "collection_node_moves_preserve_photo_metadata_and_recipes")
            try check(try paths.map { try Data(contentsOf: URL(fileURLWithPath: $0)) } == originals,
                      "collection_node_moves_preserve_original_bytes")
            print(String(data: try JSONSerialization.data(withJSONObject: [
                "ok": true, "checks": checks, "offscreen_screenshots": screenshots,
                "photo_drag_compatibility": "COVERED_BY_NativeCollectionDropRegression",
                "reference_drag_compatibility": "COVERED_BY_NativeReferenceRegression",
                "desktop_drag_drop": "NOT_VERIFIED", "voiceover": "NOT_VERIFIED",
            ], options: [.prettyPrinted, .sortedKeys]), encoding: .utf8)!)
            exit(0)
        } catch {
            print(String(data: try! JSONSerialization.data(withJSONObject: [
                "ok": false, "checks": checks, "offscreen_screenshots": screenshots,
                "error": error.localizedDescription, "store_error": s.error ?? "",
                "desktop_drag_drop": "NOT_VERIFIED",
            ], options: [.prettyPrinted, .sortedKeys]), encoding: .utf8)!)
            exit(1)
        }
    }
}
