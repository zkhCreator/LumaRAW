// Purpose: native collection hierarchy, color labels and target integration against a real broker.
// Inputs: disposable photographs/catalog. Outputs: revision, paging and filter receipts.
// Covers captured multi-label conflicts, external refresh and quiet empty-page polling.
// Offscreen snapshots are layout evidence only; desktop/VoiceOver are NOT_VERIFIED.
import AppKit
import Combine
import Foundation
import SwiftUI

@main struct NativeCollectionRegression {
    @MainActor static func main() async {
        _ = NSApplication.shared
        let s=Store()
        var checks: [String:Bool] = [:]
        var screenshots: [String]=[]
        func check(_ value: Bool,_ name: String) throws {
            checks[name]=value;if !value { throw EngineFailure(message:name) }
        }
        func snapshot<V: View>(_ name: String,_ view: V,_ size: NSSize,_ root: URL) async throws {
            let host=NSHostingView(rootView:view.background(Color(nsColor:.windowBackgroundColor)))
            host.frame=NSRect(origin:.zero,size:size)
            host.layoutSubtreeIfNeeded()
            try await Task.sleep(nanoseconds:150_000_000)
            host.layoutSubtreeIfNeeded()
            guard let bitmap=host.bitmapImageRepForCachingDisplay(in:host.bounds) else {
                throw EngineFailure(message:"No offscreen bitmap for \(name)")
            }
            host.cacheDisplay(in:host.bounds,to:bitmap)
            guard let png=bitmap.representation(using:.png,properties:[:]) else {
                throw EngineFailure(message:"No offscreen PNG for \(name)")
            }
            try png.write(to:root.appendingPathComponent(name));screenshots.append(name)
        }
        func collectionValue(_ collection: LibraryCollection) -> [String:Any] {
            var row: [String:Any] = ["id":collection.id,"name":collection.name,"kind":collection.kind,
                "revision":collection.revision,"rules":collection.rules,"match":collection.match,
                "color_label":collection.colorLabel]
            row["parent_id"]=collection.parentID as Any? ?? NSNull()
            if let parentName=collection.parentName { row["parent_name"]=parentName }
            return row
        }
        func until(_ condition: () -> Bool) async throws {
            for _ in 0..<300 {
                if condition() { return };try await Task.sleep(nanoseconds:20_000_000)
            }
            throw EngineFailure(message:"Collection state timed out")
        }
        do {
            let fixtures=ProcessInfo.processInfo.environment["LUMARAW_TEST_FIXTURES"]!.components(separatedBy:"|")
            let snapshotRoot=URL(fileURLWithPath:ProcessInfo.processInfo.environment["LUMARAW_CATALOG"]!)
                .deletingLastPathComponent()
            await s.importPaths(fixtures);await s.refreshCollections()
            try await until { s.photo != nil && !s.loading }
            let ids=s.photos.map(\.id)
            try check(s.collectionState?.target.kind == "quick","quick_is_initial_target")
            s.selection=Set(ids.prefix(2))
            await s.toggleTargetMembership()
            try check(s.collectionState?.members == Set(ids.prefix(2)),"grid_target_adds_selected_photos")
            let quick=s.collectionState!.quick
            try check(await s.saveQuickCollection(quick,name:"Saved choices",clear:true),"quick_saved_atomically")
            try check(s.total == 2 && s.collectionState?.quick.revision == quick.revision+1,"quick_save_opens_permanent_collection_and_clears_quick")
            let saved=s.activeCollection!
            await s.setTargetCollection(saved)
            try check(s.collectionState?.target.id == saved.id,"regular_target_selected")
            let stale=s.collectionState!
            _=try await Backend.call("set_target_collection",["expected_revision":stale.revision,"collection_id":NSNull()])
            await s.toggleTargetMembership(ids:[ids[2]])
            try check(s.error?.contains("Target collection conflict") == true,"target_changed_elsewhere_rejects_captured_action")
            s.error=nil;await s.refreshCollections()
            try check(s.collectionState?.target.kind == "quick","target_change_read_back")
            try check(await s.saveCollection(name:"Trip",kind:"set",rules:[:],match:"all",original:nil),"create_set")
            let root=s.activeCollection!
            try check(await s.saveCollection(name:"Day",kind:"set",rules:[:],match:"all",original:nil,parentID:root.id),"create_nested_set")
            let child=s.activeCollection!
            s.collectionID=nil;s.offset=0;await s.refresh();s.selection=Set(ids.prefix(2))
            try check(await s.saveCollection(name:"Album",kind:"regular",rules:[:],match:"all",original:nil,parentID:child.id,includePhotos:true),"create_nested_album_with_selection")
            let album=s.activeCollection!
            s.expandCollection(root.id);s.expandCollection(child.id)
            try await until { s.collectionPages[root.id] != nil && s.collectionPages[child.id] != nil }
            try check(s.collectionPages[root.id]?.items.first?.id == child.id && s.collectionPages[child.id]?.items.first?.id == album.id,"lazy_nested_pages_loaded")
            let freshRoot=LibraryCollection(try await Backend.call("get_collection",["collection_id":root.id]))!
            await s.openCollection(freshRoot)
            try check(s.total == 2,"set_displays_descendant_photos")
            await s.duplicateCollection(freshRoot)
            try check(s.activeCollection?.name == "Trip Copy" && s.total == 2,"subtree_duplicate_preserves_photos")
            await s.openCollection(album)
            await s.setTargetCollection(album)
            let deletion=LibraryCollection(try await Backend.call("get_collection",["collection_id":root.id]))!
            await s.deleteCollection(deletion)
            try check(s.collectionID == nil && s.total == ids.count,"subtree_delete_returns_deleted_source_to_catalog")
            try check(s.collectionState?.target.kind == "quick","deleted_target_falls_back_to_quick")
            try check(!s.expandedCollections.contains(root.id) && !s.expandedCollections.contains(child.id),"deleted_tree_releases_sidebar_pages")
            let reloaded=Store();await reloaded.refreshCollections()
            try check(reloaded.collectionState?.quick.id == quick.id && reloaded.collections.contains { $0.name == "Trip Copy" },"state_survives_new_native_store")

            let flatBaseline=try await Backend.call("list_collections",["offset":0])
            let labelSet=LibraryCollection(try await Backend.call("save_collection",["name":"Color Parent","kind":"set"]))!
            _=try await Backend.call("save_collection",["name":"Color Nested","kind":"regular","parent_id":labelSet.id])
            for index in 0..<61 {
                _=try await Backend.call("save_collection",["name":String(format:"Color Regression %02d",index),"kind":"regular"])
            }
            await s.refreshCollections()
            s.expandCollection(labelSet.id)
            try await until { s.collectionPages[labelSet.id] != nil }
            let rootCount=s.collectionTotal
            let batch=CollectionLabelBatchModel()
            await batch.load(using:s,offset:0)
            try check(batch.page?.total == (flatBaseline["total"] as? Int ?? -100)+63 && batch.page!.total > rootCount,
                "batch_browser_pages_the_flat_collection_tree")
            let firstPage=batch.page!.items
            let firstTarget=firstPage.first(where:{$0.kind != "quick"})!
            await batch.turnPage(60,using:s)
            try check(batch.page?.offset == 60,"batch_browser_loads_next_global_page")
            let secondPage=batch.page!.items
            let secondTarget=secondPage.first(where:{$0.kind != "quick"})!
            try check((firstPage+secondPage).first(where:{$0.id == labelSet.id}) != nil &&
                (firstPage+secondPage).first(where:{$0.id == labelSet.id})?.kind == "set" &&
                (firstPage+secondPage).first(where:{$0.name == "Color Nested"})?.parentName == labelSet.name,
                "flat_batch_rows_include_nested_parent_context")
            let limitBatch=CollectionLabelBatchModel()
            await limitBatch.load(using:s,offset:0)
            let limitFirstPage=limitBatch.page!.items
            await limitBatch.turnPage(60,using:s)
            let limitCandidates=(limitFirstPage+limitBatch.page!.items).filter { $0.kind != "quick" }
            for collection in limitCandidates.prefix(61) { limitBatch.toggle(collection) }
            try check(limitCandidates.count>=61 && limitBatch.selected.count==60 &&
                limitBatch.error?.contains("at most 60") == true,"batch_selection_is_capped_at_sixty")
            batch.toggle(firstTarget);batch.toggle(secondTarget)
            try check(batch.selected.count == 2 && batch.selected[firstTarget.id]?.revision == firstTarget.revision,
                "batch_selection_keeps_captured_targets_across_pages")
            try await snapshot("collection-label-batch.png",CollectionLabelBatchSheet(model:batch).environmentObject(s),
                NSSize(width:700,height:720),snapshotRoot)
            try check(await batch.apply(using:s),"batch_labels_two_captured_collections_atomically")
            let firstLabeled=LibraryCollection(try await Backend.call("get_collection",["collection_id":firstTarget.id]))!
            let secondLabeled=LibraryCollection(try await Backend.call("get_collection",["collection_id":secondTarget.id]))!
            try check(firstLabeled.colorLabel == "red" && secondLabeled.colorLabel == "red","batch_label_values_persist")

            let normalPages=s.collectionPages
            let normalExpansion=s.expandedCollections
            await s.setCollectionColorFilter("red")
            try check(s.collectionFilteredPage?.total == 2 &&
                Set(s.collectionFilteredPage?.items.map(\.id) ?? []) == Set([firstTarget.id,secondTarget.id]),
                "red_filter_uses_separate_flat_global_page")
            try await snapshot("collection-color-filter-row.png",
                CollectionColorFilteredRow(collection:s.collectionFilteredPage!.items.first(where:{$0.id == firstLabeled.id})!)
                    .environmentObject(s),NSSize(width:360,height:48),snapshotRoot)
            await s.setCollectionColorFilter("any")
            try check(s.collectionColorFilter == "any" && s.collectionPages == normalPages &&
                s.expandedCollections == normalExpansion && s.collectionPages[labelSet.id] != nil,
                "leaving_color_filter_restores_existing_tree_pages_and_expansion")

            batch.selected.removeAll()
            await batch.setFilter("red",using:s)
            let redTargets=batch.page!.items.filter { $0.id == firstTarget.id || $0.id == secondTarget.id }
            redTargets.forEach { batch.toggle($0) }
            let capturedTargets=batch.selectedTargets
            batch.label="yellow"
            let conflictTarget=capturedTargets.first!
            let externalCurrent=LibraryCollection(try await Backend.call("get_collection",["collection_id":conflictTarget.id]))!
            _=try await Backend.call("set_collection_labels",["targets":[["collection_id":externalCurrent.id,
                "expected_revision":externalCurrent.revision]],"color_label":"blue"])
            await batch.load(using:s,offset:0)
            try check(batch.page?.items.contains(where:{$0.id == conflictTarget.id}) == false &&
                batch.selected[conflictTarget.id]?.revision == conflictTarget.revision,
                "filtering_out_changed_target_keeps_captured_selection")
            try check(!(await batch.apply(using:s)) && batch.selected.count == 2 &&
                batch.selected[conflictTarget.id]?.revision == conflictTarget.revision &&
                s.error?.localizedCaseInsensitiveContains("conflict") == true,
                "stale_batch_conflict_preserves_all_captured_targets")
            let otherAfterConflict=LibraryCollection(try await Backend.call("get_collection",["collection_id":capturedTargets.last!.id]))!
            let changedAfterConflict=LibraryCollection(try await Backend.call("get_collection",["collection_id":conflictTarget.id]))!
            try check(changedAfterConflict.colorLabel == "blue" && otherAfterConflict.colorLabel == "red",
                "stale_batch_applies_no_partial_label_changes")
            await batch.setFilter("blue",using:s)
            let refreshedConflictTarget=batch.page!.items.first(where:{$0.id == conflictTarget.id})!
            batch.toggle(refreshedConflictTarget);batch.toggle(refreshedConflictTarget)
            try check(batch.selected[conflictTarget.id]?.revision == refreshedConflictTarget.revision,
                "reload_then_reselect_captures_fresh_collection_revision")
            try check(await batch.apply(using:s),"reselected_batch_applies_after_conflict")
            let yellowFirst=LibraryCollection(try await Backend.call("get_collection",["collection_id":firstTarget.id]))!
            let yellowSecond=LibraryCollection(try await Backend.call("get_collection",["collection_id":secondTarget.id]))!
            try check(yellowFirst.colorLabel == "yellow" && yellowSecond.colorLabel == "yellow",
                "reselected_batch_updates_both_collections")

            await s.setCollectionColorFilter("labeled")
            try check(s.collectionFilteredPage?.total == 2 &&
                Set(s.collectionFilteredPage?.items.map(\.id) ?? []) == Set([firstTarget.id,secondTarget.id]),
                "labeled_filter_tracks_new_labels")
            await s.setCollectionColorFilter("any")
            let activeCandidate=LibraryCollection(try await Backend.call("get_collection",["collection_id":firstTarget.id]))!
            await s.openCollection(activeCandidate)
            let activeBefore=activeCandidate.revision
            let externalActive=LibraryCollection(try await Backend.call("get_collection",["collection_id":firstTarget.id]))!
            _=try await Backend.call("set_collection_labels",["targets":[["collection_id":externalActive.id,
                "expected_revision":externalActive.revision]],"color_label":"purple"])
            await s.refreshCollectionState()
            try check(s.activeCollection?.colorLabel == "purple" && (s.activeCollection?.revision ?? 0)>activeBefore,
                "tree_revision_refreshes_active_collection_without_rebasing_edit_forms")

            let emptyStore=Store()
            emptyStore.search="LUMARAW_NATIVE_EMPTY_\(UUID().uuidString)"
            await emptyStore.refresh()
            await emptyStore.refreshCollections()
            try await until { emptyStore.collectionPages[0] != nil && emptyStore.collectionState != nil }
            try check(emptyStore.photos.isEmpty,"empty_page_test_uses_an_actual_empty_filter")
            let emptyRoot=emptyStore.collectionPages[0]!
            let emptyTarget=emptyRoot.items.first(where:{$0.kind == "regular"})!
            let emptyTargetCurrent=LibraryCollection(try await Backend.call("get_collection",["collection_id":emptyTarget.id]))!
            let oldTreeRevision=emptyStore.collectionTreeRevision
            _=try await Backend.call("set_collection_labels",["targets":[["collection_id":emptyTargetCurrent.id,
                "expected_revision":emptyTargetCurrent.revision]],"color_label":"purple"])
            await emptyStore.refreshVisibleSummaries()
            try check(emptyStore.photos.isEmpty && emptyStore.collectionTreeRevision>oldTreeRevision &&
                emptyStore.collectionPages[0]?.items.first(where:{$0.id == emptyTarget.id})?.colorLabel == "purple",
                "empty_catalog_poll_refreshes_external_collection_labels")
            let currentTree=emptyStore.collectionTreeRevision
            let currentState=emptyStore.collectionState!
            let lateState=CollectionState(["revision":currentState.revision,"quick":collectionValue(currentState.quick),
                "target":collectionValue(currentState.target),"members":Array(currentState.members)])!
            try check(!emptyStore.collectionStateCanAdopt(lateState,responseTreeRevision:currentTree-1),
                "late_state_reply_cannot_regress_independent_tree_revision")
            let beforeQuietPageGeneration=emptyStore.collectionPageGenerations[0] ?? 0
            var publications=0
            let subscription=emptyStore.objectWillChange.sink { _ in publications+=1 }
            await emptyStore.refreshVisibleSummaries()
            try check((emptyStore.collectionPageGenerations[0] ?? 0) == beforeQuietPageGeneration && publications == 0,
                "unchanged_empty_page_poll_does_not_reload_or_republish_store")
            withExtendedLifetime(subscription) {}

            let old=LibraryCollection(try await Backend.call("save_collection",["name":"Old source","kind":"regular"]))!
            _=try await Backend.call("delete_collection",["collection_id":old.id,"expected_revision":old.revision])
            let replacement=LibraryCollection(try await Backend.call("save_collection",["name":"New source","kind":"regular"]))!
            try check(replacement.id > old.id,"deleted_collection_identity_is_not_reused")
            try check(!(await s.saveCollection(name:"Stale rename",kind:"regular",rules:[:],match:"all",original:old)),"stale_native_editor_cannot_retarget_new_collection")
            try check(s.error?.contains("does not exist") == true,"stale_collection_error_is_visible")
            s.error=nil
            let unchanged=LibraryCollection(try await Backend.call("get_collection",["collection_id":replacement.id]))!
            try check(unchanged.name == "New source" && unchanged.revision == 0,"replacement_collection_remains_unchanged")
            let report:[String:Any]=["ok":true,"passed":checks.count,"checks":checks,
                "offscreen_screenshots":screenshots,"desktop_ui":"NOT_VERIFIED"]
            print(String(data:try JSONSerialization.data(withJSONObject:report,options:[.prettyPrinted,.sortedKeys]),encoding:.utf8)!)
            exit(0)
        } catch {
            print(String(data:try! JSONSerialization.data(withJSONObject:["ok":false,"checks":checks,
                "error":error.localizedDescription,"store_error":s.error ?? "",
                "offscreen_screenshots":screenshots,"desktop_ui":"NOT_VERIFIED"],options:.prettyPrinted),encoding:.utf8)!)
            exit(1)
        }
    }
}
