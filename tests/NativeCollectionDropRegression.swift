// Purpose: validate bounded, revision-safe photo drops into regular and Quick collections.
// Inputs: five disposable originals, captured drag payloads and an isolated catalog.
// Outputs: membership receipts, payload compatibility, rejection checks and unchanged originals.
// The 60-ID capture boundary uses in-memory Photo values; no extra originals are created.
// Quick controls are rendered in a standalone stack for offscreen layout evidence.
// This cannot establish native List rendering or desktop drag/hover acceptance.
import AppKit
import Foundation
import SwiftUI

@main struct NativeCollectionDropRegression {
    @MainActor static func main() async {
        _ = NSApplication.shared
        let s=Store();var checks:[String:Bool]=[:]
        var screenshots:[String]=[]
        func check(_ value:Bool,_ name:String)throws {
            checks[name]=value
            if !value { throw EngineFailure(message:name) }
        }
        func snapshot<V:View>(_ name:String,_ view:V,_ size:NSSize,_ root:URL) async throws {
            let host=NSHostingView(rootView:view.background(Color(nsColor:.windowBackgroundColor)))
            host.frame=NSRect(origin:.zero,size:size)
            host.layoutSubtreeIfNeeded()
            try await Task.sleep(nanoseconds:150_000_000)
            host.layoutSubtreeIfNeeded()
            guard let bitmap=host.bitmapImageRepForCachingDisplay(in:host.bounds) else {
                throw EngineFailure(message:"No bitmap for \(name)")
            }
            host.cacheDisplay(in:host.bounds,to:bitmap)
            guard let png=bitmap.representation(using:.png,properties:[:]) else {
                throw EngineFailure(message:"No PNG for \(name)")
            }
            try png.write(to:root.appendingPathComponent(name));screenshots.append(name)
        }
        func until(_ condition:()->Bool) async throws {
            for _ in 0..<300 {
                if condition() { return }
                try await Task.sleep(nanoseconds:20_000_000)
            }
            throw EngineFailure(message:"Collection drop state timed out: \(s.error ?? "no error")")
        }
        func collectionPhotos(_ collectionID:Int) async throws -> Set<Int> {
            let result=try await Backend.call("list_photos",["collection_id":collectionID,"stacked":false])
            return Set((result["photos"] as? [[String:Any]] ?? []).compactMap { $0["id"] as? Int })
        }
        func photoState(_ photoID:Int) async throws -> Data {
            let row=try await Backend.call("get_photo",["photo_id":photoID])
            let keys=["id","name","path","revision","source_revision","orientation","rating","flag",
                "title","caption","copyright","color_label","metadata_revision","recipe","metadata","keywords"]
            let state=Dictionary(uniqueKeysWithValues:keys.map { ($0,row[$0] ?? NSNull()) })
            return try JSONSerialization.data(withJSONObject:state,options:[.sortedKeys])
        }
        func waitForCollectionPhotos(_ collectionID:Int,_ expected:Set<Int>) async throws {
            for _ in 0..<300 {
                if try await collectionPhotos(collectionID)==expected { return }
                try await Task.sleep(nanoseconds:20_000_000)
            }
            throw EngineFailure(message:"Collection membership did not settle")
        }
        func readCollection(_ id:Int) async throws -> LibraryCollection {
            guard let row=LibraryCollection(try await Backend.call("get_collection",["collection_id":id])) else {
                throw EngineFailure(message:"Collection disappeared during drop regression")
            }
            return row
        }
        do {
            let paths=ProcessInfo.processInfo.environment["LUMARAW_TEST_FIXTURES"]!.components(separatedBy:"|")
            let snapshotRoot=URL(fileURLWithPath:ProcessInfo.processInfo.environment["LUMARAW_CATALOG"]!)
                .deletingLastPathComponent()
            let originalBytes=try paths.map { try Data(contentsOf:URL(fileURLWithPath:$0)) }
            await s.importPaths(paths);await s.refreshCollections()
            try await until { s.photos.count==paths.count && !s.loading && s.collectionState != nil }
            let ids=s.photos.map(\.id)
            try check(ids.count==5,"five_visible_real_photos")
            var originalPhotoStates:[Int:Data]=[:]
            for id in ids { originalPhotoStates[id]=try await photoState(id) }

            guard let target=LibraryCollection(try await Backend.call("save_collection",[
                "name":"Drop target","kind":"regular","rules":[:],"match":"all"])) else {
                throw EngineFailure(message:"Could not create regular collection")
            }
            guard let setTarget=LibraryCollection(try await Backend.call("save_collection",[
                "name":"Drop set","kind":"set","rules":[:],"match":"all"])) else {
                throw EngineFailure(message:"Could not create collection set")
            }
            guard let smartTarget=LibraryCollection(try await Backend.call("save_collection",[
                "name":"Drop smart","kind":"smart","rules":[:],"match":"all"])) else {
                throw EngineFailure(message:"Could not create smart collection")
            }
            let quick=s.collectionState!.quick
            let quickBefore=try await collectionPhotos(quick.id)

            s.selection=Set([ids[0],ids[1]])
            let captured=s.libraryPhotoDrag(ids[0])
            let capturedIDs=captured.photoIDs ?? [captured.photoID]
            try check(captured.session==s.referenceDragSession && captured.photoID==ids[0] &&
                Set(capturedIDs)==Set([ids[0],ids[1]]) && capturedIDs.count==2,
                "grid_drag_captures_visible_selection_and_anchor")
            let workspace=s.workspace
            s.workspace="exports"
            let quickRejectedOutsideLibrary = !s.canDropInCollection(captured,to:quick)
            s.workspace=workspace
            try check(s.canDropInCollection(captured,to:target) &&
                s.canDropInCollection(captured,to:quick) &&
                !s.canDropInCollection(captured,to:setTarget) &&
                !s.canDropInCollection(captured,to:smartTarget) &&
                quickRejectedOutsideLibrary,"regular_and_quick_only_accept_library_photo_drops")

            let legacyJSON=try JSONSerialization.data(withJSONObject:[
                "session":captured.session,"photoID":ids[4],
            ])
            let decodedLegacy=try JSONDecoder().decode(CatalogPhotoDrag.self,from:legacyJSON)
            let encodedSelection=try JSONEncoder().encode(captured)
            let decodedSelection=try JSONDecoder().decode(CatalogPhotoDrag.self,from:encodedSelection)
            try check(decodedLegacy.photoIDs==nil && decodedLegacy.resolvedPhotoIDs==[ids[4]] &&
                decodedSelection==captured,"legacy_and_multi_photo_payloads_roundtrip")

            let savedView=s.libraryView
            s.libraryView = .loupe
            let loupeDrag=s.libraryPhotoDrag(ids[0])
            s.libraryView=savedView
            s.develop=true
            let developDrag=s.libraryPhotoDrag(ids[0])
            s.develop=false
            try check(loupeDrag.photoIDs==nil && loupeDrag.resolvedPhotoIDs==[ids[0]] &&
                developDrag.photoIDs==nil && developDrag.resolvedPhotoIDs==[ids[0]],
                "non_grid_and_develop_drags_capture_only_anchor")

            let foreign=CatalogPhotoDrag(session:"foreign-session",photoID:ids[0],photoIDs:[ids[0]])
            let staleAnchor=CatalogPhotoDrag(session:captured.session,photoID:999_999,photoIDs:[999_999])
            let empty=CatalogPhotoDrag(session:captured.session,photoID:ids[0],photoIDs:[])
            let duplicate=CatalogPhotoDrag(session:captured.session,photoID:ids[0],photoIDs:[ids[0],ids[0]])
            let missingAnchor=CatalogPhotoDrag(session:captured.session,photoID:ids[2],photoIDs:[ids[0],ids[1]])
            let offPage=CatalogPhotoDrag(session:captured.session,photoID:ids[0],photoIDs:[ids[0],999_999])
            let overLimit=CatalogPhotoDrag(session:captured.session,photoID:ids[0],photoIDs:Array(1...61))
            try check([foreign,staleAnchor,empty,duplicate,missingAnchor,offPage,overLimit]
                .allSatisfy { !s.canDropInCollection($0,to:target) },
                "foreign_stale_and_malformed_payloads_are_rejected")
            try check(!s.canDropInCollection(overLimit,to:quick),"quick_drop_rejects_over_bound_payload")
            let legacyAnchor=CatalogPhotoDrag(session:captured.session,photoID:ids[4])
            try check(s.canDropInCollection(legacyAnchor,to:target),"legacy_anchor_only_payload_remains_valid")

            let savedPhotos=s.photos,savedSelection=s.selection
            s.photos=(1...60).map { Photo(["id":$0])! }
            s.selection=Set(1...61)
            let sixty=s.libraryPhotoDrag(1)
            try check(sixty.photoIDs?.count==60 && Set(sixty.photoIDs ?? [])==Set(1...60) &&
                sixty.photoIDs?.contains(61)==false,"capture_is_capped_to_sixty_visible_ids")
            s.photos=savedPhotos;s.selection=savedSelection

            let visiblePage=s.photos
            s.selection=Set([ids[0],ids[1]])
            let stalePageDrag=s.libraryPhotoDrag(ids[0])
            s.photos=visiblePage.filter { $0.id != ids[1] }
            let stalePageRejected=s.beginCollectionDrop(stalePageDrag,to:target)==nil
            s.photos=visiblePage
            try check(stalePageRejected,"drop_entry_rejects_ids_missing_from_current_visible_page")

            s.selection=Set([ids[2]])
            let fallback=s.libraryPhotoDrag(ids[1])
            try check(fallback.photoID==ids[1] && fallback.photoIDs==nil && fallback.resolvedPhotoIDs==[ids[1]],
                "unselected_drag_anchor_falls_back_to_that_photo")
            guard let fallbackTarget=LibraryCollection(try await Backend.call("save_collection",[
                "name":"Fallback target","kind":"regular","rules":[:],"match":"all"])) else {
                throw EngineFailure(message:"Could not create fallback collection")
            }
            guard let fallbackTask=s.beginCollectionDrop(fallback,to:fallbackTarget) else {
                throw EngineFailure(message:"Visible fallback anchor was not accepted")
            }
            await fallbackTask.value
            try await waitForCollectionPhotos(fallbackTarget.id,Set([ids[1]]))

            // The drag payload, rather than mutable Store.selection, is the write input.
            s.selection=Set([ids[0],ids[1]])
            let selectionSnapshot=s.libraryPhotoDrag(ids[0])
            s.selection=Set([ids[2]])
            guard let task=s.beginCollectionDrop(selectionSnapshot,to:target) else {
                throw EngineFailure(message:"Captured regular collection drop was rejected")
            }
            await task.value
            try await waitForCollectionPhotos(target.id,Set([ids[0],ids[1]]))
            let membersAfterCapture=try await collectionPhotos(target.id)
            try check(s.selection==Set([ids[2]]) && membersAfterCapture==Set([ids[0],ids[1]]),
                "selection_change_after_capture_does_not_change_submitted_ids")

            // The Quick row is the drop destination even if another collection is now targeted.
            let regularBeforeQuickDrop=try await collectionPhotos(target.id)
            await s.setTargetCollection(target)
            await s.refreshCollections()
            try await snapshot("quick-collection-drop-controls.png",
                VStack(alignment:.leading,spacing:12) { CollectionsSidebar() }
                    .padding(16).environmentObject(s),
                NSSize(width:360,height:540),snapshotRoot)
            let quickExpected=quickBefore.union(Set(capturedIDs))
            guard let quickTask=s.beginCollectionDrop(captured,to:quick) else {
                throw EngineFailure(message:"Captured Quick Collection drop was rejected")
            }
            await quickTask.value
            try await waitForCollectionPhotos(quick.id,quickExpected)
            let regularAfterQuickDrop=try await collectionPhotos(target.id)
            let quickAfterTargetDrop=try await collectionPhotos(quick.id)
            try check(s.collectionState?.target.id==target.id &&
                regularAfterQuickDrop==regularBeforeQuickDrop &&
                quickAfterTargetDrop==quickExpected,
                "quick_drop_ignores_changed_target_and_adds_only_to_quick")

            let quickForRepeat=try await readCollection(quick.id)
            let revisionBeforeRepeat=quickForRepeat.revision
            guard let repeatedQuickTask=s.beginCollectionDrop(captured,to:quickForRepeat) else {
                throw EngineFailure(message:"Repeated Quick Collection add was rejected")
            }
            await repeatedQuickTask.value
            let quickAfterRepeat=try await readCollection(quick.id)
            let membersAfterRepeat=try await collectionPhotos(quick.id)
            try check(membersAfterRepeat==quickExpected && quickAfterRepeat.revision==revisionBeforeRepeat+1,
                "repeated_quick_add_preserves_members_and_advances_revision")

            guard let membershipTarget=LibraryCollection(try await Backend.call("save_collection",[
                "name":"Selection capture target","kind":"regular","rules":[:],"match":"all"])) else {
                throw EngineFailure(message:"Could not create selection capture collection")
            }
            s.selection=Set([ids[2],ids[3]])
            guard let membershipTask=s.beginCollectionMembership(membershipTarget,action:"add") else {
                throw EngineFailure(message:"Selected-photo membership task was not created")
            }
            s.selection=Set([ids[4]])
            await membershipTask.value
            try await waitForCollectionPhotos(membershipTarget.id,Set([ids[2],ids[3]]))
            let capturedMembership=try await collectionPhotos(membershipTarget.id)
            try check(capturedMembership==Set([ids[2],ids[3]]),
                "membership_task_uses_synchronous_selection_snapshot")

            // A concurrent Quick edit invalidates the captured Quick row; no stale drop is retried.
            let staleQuick=try await readCollection(quick.id)
            s.selection=Set([ids[3],ids[4]])
            let staleQuickDrag=s.libraryPhotoDrag(ids[3])
            _=try await Backend.call("collection_membership",[
                "collection_id":quick.id,"expected_revision":staleQuick.revision,
                "photo_ids":[ids[2]],"action":"add"])
            s.error=nil
            guard let staleQuickTask=s.beginCollectionDrop(staleQuickDrag,to:staleQuick) else {
                throw EngineFailure(message:"Captured stale Quick drop should reach revision validation")
            }
            await staleQuickTask.value
            let quickAfterConflict=try await collectionPhotos(quick.id)
            let regularBeforeStaleQuick=try await collectionPhotos(target.id)
            try check(s.error?.localizedCaseInsensitiveContains("conflict")==true &&
                quickAfterConflict==quickExpected.union([ids[2]]) &&
                regularBeforeStaleQuick==Set([ids[0],ids[1]]),
                "stale_quick_drop_conflicts_without_retry_or_partial_membership")

            // A captured collection revision must fail atomically after another client changes it.
            let staleTarget=try await readCollection(target.id)
            let stalePayload:CatalogPhotoDrag
            s.selection=Set([ids[3],ids[4]])
            stalePayload=s.libraryPhotoDrag(ids[3])
            _=try await Backend.call("collection_membership",[
                "collection_id":staleTarget.id,"expected_revision":staleTarget.revision,
                "photo_ids":[ids[2]],"action":"add"])
            s.error=nil
            guard let conflictTask=s.beginCollectionDrop(stalePayload,to:staleTarget) else {
                throw EngineFailure(message:"Visible payload should reach stale-revision validation")
            }
            await conflictTask.value
            let finalMembers=try await collectionPhotos(target.id)
            try check(s.error?.localizedCaseInsensitiveContains("conflict")==true &&
                finalMembers==Set([ids[0],ids[1],ids[2]]),
                "stale_regular_target_conflicts_without_retry_or_partial_membership")

            var photosUnchanged=true
            for id in ids {
                if try await photoState(id) != originalPhotoStates[id] { photosUnchanged=false }
            }
            try check(photosUnchanged,"collection_drops_preserve_photo_metadata_and_recipe_state")
            try check(try paths.map { try Data(contentsOf:URL(fileURLWithPath:$0)) }==originalBytes,
                "collection_drops_preserve_original_bytes")
            print(String(data:try JSONSerialization.data(withJSONObject:[
                "ok":true,"checks":checks,"offscreen_screenshots":screenshots,
                "desktop_ui":"NOT_VERIFIED","voiceover":"NOT_VERIFIED",
            ],options:[.prettyPrinted,.sortedKeys]),encoding:.utf8)!)
            exit(0)
        } catch {
            print(String(data:try! JSONSerialization.data(withJSONObject:[
                "ok":false,"checks":checks,"offscreen_screenshots":screenshots,
                "error":error.localizedDescription,"store_error":s.error ?? "",
            ],options:.prettyPrinted),encoding:.utf8)!)
            exit(1)
        }
    }
}
