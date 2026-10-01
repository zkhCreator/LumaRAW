// Purpose: verify last-import navigation and its persisted preference over IPC.
// Inputs: isolated generated originals and native Store/import models. Outputs:
// checked batch focus, retained sources, filters, edits and external refreshes.
// No rendered desktop, pointer/keyboard or VoiceOver acceptance is implied.
import AppKit
import Foundation

@main struct NativePreviousImportRegression {
    @MainActor static func main() async {
        _=NSApplication.shared
        let s=Store()
        var checks: [String:Bool]=[:]
        func check(_ value: Bool,_ name: String) throws {
            checks[name]=value
            if !value { throw EngineFailure(message:name) }
        }
        func settled(_ condition: () -> Bool) async throws {
            for _ in 0..<300 {
                if condition() && !s.browsing && !s.loading { return }
                try await Task.sleep(nanoseconds:20_000_000)
            }
            throw EngineFailure(message:"Native import navigation did not settle")
        }
        do {
            let paths=ProcessInfo.processInfo.environment["LUMARAW_TEST_FIXTURES"]!.components(separatedBy:"|")
            let originals=try paths.map { try Data(contentsOf:URL(fileURLWithPath:$0)) }
            await s.openLibraryMode("previous_import")
            try check(s.photos.isEmpty && s.total == 0 && s.selected == nil,"new_catalog_has_empty_previous_import")
            await s.importPaths(Array(paths.prefix(2)))
            try check(s.mode == "previous_import" && s.total == 2 && !s.develop && s.libraryView == .grid,"default_import_opens_previous_import_grid")
            await s.setImportNavigation(false)
            try check(!s.selectPreviousImport && !s.importPreferenceBusy,"preference_write_is_acknowledged")
            let reopened=Store();await reopened.refreshMemory()
            try check(!reopened.selectPreviousImport,"preference_survives_new_native_store")
            let folder=LibraryFolder(try await Backend.call("get_folder",["photo_id":1]))!
            await s.openFolder(folder);s.search="not-present";s.libraryFilters=["rating_min":5];await s.refresh()
            let beforeRevision=s.photoFolderRevision
            await s.reviewImport([paths[2]])
            let review=s.importReview!
            await review.load(initial:true);await review.scan();await review.apply()
            try await settled { s.photoFolderRevision != beforeRevision }
            try check(s.folderID == folder.id && s.mode == "all" && s.search == "not-present" && s.libraryFilters["rating_min"] as? Int == 5,"disabled_preference_keeps_folder_and_filters")
            try check(s.total == 0 && s.selected == nil,"retained_filter_can_hide_new_import")
            review.invalidate();s.importReview=nil
            await s.openLibraryMode("previous_import",clearFilters:true)
            try check(s.photos.map(\.id) == [3] && s.folderID == nil && s.collectionID == nil,"manual_previous_import_clears_source_identity")
            let recipeRevision=s.photo!.revision
            s.set("exposure",0.5)
            await s.setImportNavigation(true)
            await s.reviewImport([paths[3]])
            let saved=try await Backend.call("get_photo",["photo_id":3])
            try check(saved["revision"] as? Int == recipeRevision+1,"opening_import_flushes_pending_edit")
            let next=s.importReview!
            await next.load(initial:true);await next.scan();await next.apply()
            try await settled { s.photos.map(\.id) == [4] }
            try check(s.mode == "previous_import" && s.search.isEmpty && s.libraryFilters.isEmpty,"enabled_preference_opens_only_completed_batch")
            try check(s.selection == [4] && s.photo?.id == 4,"new_batch_removes_old_selection_and_inspector")
            next.invalidate();s.importReview=nil
            _=try await Backend.call("import_photos",["paths":[paths[4]]])
            await s.refreshVisibleSummaries()
            try check(s.photos.map(\.id) == [5] && s.selected == 5,"external_import_refreshes_viewed_previous_source")
            s.libraryFilters=["rating_min":5];await s.refresh()
            try check(s.total == 0,"previous_source_intersects_metadata_filter")
            let extra=URL(fileURLWithPath:paths[0]).deletingLastPathComponent().appendingPathComponent("extra.png")
            try FileManager.default.copyItem(atPath:paths[0],toPath:extra.path)
            _=try await Backend.call("import_photos",["paths":[extra.path]])
            _=try await Backend.call("rate_photo",["photo_id":6,"rating":5])
            await s.refreshVisibleSummaries()
            try check(s.photos.map(\.id) == [6],"empty_source_poll_observes_new_matching_batch")
            await s.openLibraryMode("all",clearFilters:true)
            let last=extra.deletingLastPathComponent().appendingPathComponent("last.png")
            try FileManager.default.copyItem(atPath:paths[0],toPath:last.path)
            _=try await Backend.call("import_photos",["paths":[last.path]])
            await s.refreshVisibleSummaries()
            try check(s.mode == "all" && s.total == 7,"external_import_does_not_steal_source_navigation")
            await s.finishImport(0)
            try check(s.mode == "all","empty_import_does_not_navigate")
            s.thumbnailRenderer.request([]);s.cancelMainPreview()
            // Synchronization deliberately rejects concurrent image work. Wait
            // for this test's own preview cancellation before applying its plan.
            for _ in 0..<200 {
                let status=try await Backend.call("status")
                if status["active"] is NSNull { break }
                try await Task.sleep(nanoseconds:20_000_000)
            }
            let synchronized=last.deletingLastPathComponent().appendingPathComponent("sync.png")
            try FileManager.default.copyItem(atPath:paths[0],toPath:synchronized.path)
            let sync=FolderSyncModel(folder:folder)
            await sync.reload()
            let sourceState=try await Backend.call("library_state")
            await sync.prepare(revision:sourceState["folder_revision"] as! Int);await sync.scan()
            for _ in 0..<3 {
                await sync.apply(using:s)
                if sync.plan?.state == "applied" { break }
                // A queued preview can enter after the idle observation. Retry
                // only the documented, definite no-mutation admission refusal;
                // never replay an uncertain transport or other domain failure.
                guard sync.plan?.state == "ready",sync.plan?.text("error") == "Image processing is active; synchronize after it finishes" else { break }
                let unchanged=try await Backend.call("status")
                try check(unchanged["photos"] as? Int == 7,"busy_sync_admission_does_not_partially_import")
                for _ in 0..<200 {
                    let status=try await Backend.call("status")
                    if status["active"] is NSNull { break }
                    try await Task.sleep(nanoseconds:20_000_000)
                }
            }
            try check(sync.plan?.state == "applied" && s.mode == "previous_import" && s.photos.map(\.id) == [8],"folder_sync_import_uses_same_navigation_preference")
            await s.openLibraryMode("all");await sync.apply(using:s)
            try check(s.mode == "all","completed_sync_receipt_does_not_repeat_navigation")
            sync.invalidate()
            await s.reviewImport([extra.path])
            let cancel=s.importReview!;await cancel.load(initial:true);await cancel.scan();await cancel.cancel()
            let previous=try await Backend.call("list_photos",["mode":"previous_import","stacked":false])
            try check((previous["photos"] as? [[String:Any]])?.first?["id"] as? Int == 8,"cancelled_review_preserves_previous_batch")
            cancel.invalidate();s.importReview=nil
            try check(try paths.map { try Data(contentsOf:URL(fileURLWithPath:$0)) } == originals,"import_navigation_preserves_original_bytes")
            s.thumbnailRenderer.request([]);s.cancelMainPreview()
            print(String(data:try JSONSerialization.data(withJSONObject:["ok":true,"checks":checks,"desktop_ui":"NOT_VERIFIED"],options:[.prettyPrinted,.sortedKeys]),encoding:.utf8)!)
            exit(0)
        } catch {
            print(String(data:try! JSONSerialization.data(withJSONObject:["ok":false,"checks":checks,"error":error.localizedDescription,"store_error":s.error ?? ""],options:.prettyPrinted),encoding:.utf8)!)
            exit(1)
        }
    }
}
