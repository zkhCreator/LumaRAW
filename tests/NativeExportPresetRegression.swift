// Purpose: verify bounded export-preset browsing, captured drafts and immutable queue settings.
// Inputs: two disposable photographs, isolated catalog/shared storage and packaged Backend IPC.
// Outputs: preset lifecycle/conflict assertions, queued option snapshots and offscreen UI images.
// Offscreen snapshots are layout evidence only; desktop interaction is NOT_VERIFIED.
import AppKit
import Foundation
import SwiftUI

@main struct NativeExportPresetRegression {
    @MainActor static func main() async {
        _ = NSApplication.shared
        let store = Store()
        var checks: [String: Bool] = [:]
        var screenshots: [String] = []
        var createdJobIDs: [Int] = []

        func check(_ value: Bool, _ name: String) throws {
            checks[name] = value
            if !value { throw EngineFailure(message: name) }
        }

        func snapshot<V: View>(_ name: String, _ view: V, _ size: NSSize, _ root: URL) async throws {
            let host = NSHostingView(rootView: view.background(Color(nsColor: .windowBackgroundColor)))
            host.frame = NSRect(origin: .zero, size: size)
            host.layoutSubtreeIfNeeded()
            try await Task.sleep(nanoseconds: 100_000_000)
            host.layoutSubtreeIfNeeded()
            guard let bitmap = host.bitmapImageRepForCachingDisplay(in: host.bounds),
                  host.bounds.width > 0, host.bounds.height > 0 else {
                throw EngineFailure(message: "No offscreen bitmap for \(name)")
            }
            host.cacheDisplay(in: host.bounds, to: bitmap)
            guard let png = bitmap.representation(using: .png, properties: [:]) else {
                throw EngineFailure(message: "No offscreen PNG for \(name)")
            }
            try png.write(to: root.appendingPathComponent(name))
            screenshots.append(name)
        }

        func revision(_ result: [String: Any]) throws -> String {
            guard let value = result["revision"] as? String, value.count == 64 else {
                throw EngineFailure(message: "Missing opaque export-preset revision")
            }
            return value
        }

        func isNil<T>(_ value: T?) -> Bool {
            if case .none = value { return true }
            return false
        }

        func optionsEqual(_ actual: [String: Any], _ expected: [String: Any]) -> Bool {
            guard Set(actual.keys) == Set(expected.keys) else { return false }
            for key in expected.keys {
                if key == "output_sharpen" {
                    guard let a = actual[key] as? NSNumber, let b = expected[key] as? NSNumber,
                          abs(a.doubleValue - b.doubleValue) < 0.000001 else { return false }
                } else if key == "keyword_hierarchy" {
                    guard (actual[key] as? NSNumber)?.boolValue == (expected[key] as? NSNumber)?.boolValue else { return false }
                } else if String(describing: actual[key]!) != String(describing: expected[key]!) {
                    return false
                }
            }
            return true
        }

        do {
            let paths = ProcessInfo.processInfo.environment["LUMARAW_TEST_FIXTURES"]!
                .components(separatedBy: "|")
            try check(paths.count == 2, "runner_supplies_two_export_photos")
            let originalBytes = try paths.map { try Data(contentsOf: URL(fileURLWithPath: $0)) }
            let root = URL(fileURLWithPath: ProcessInfo.processInfo.environment["LUMARAW_CATALOG"]!)
                .deletingLastPathComponent()
            let destination = root.appendingPathComponent("未创建的 Export Folder").path
            let oldDestination = root.appendingPathComponent("Old Folder To Clear").path
            let prefix = "Native Export \(UUID().uuidString.prefix(8))"

            await store.importPaths(paths)
            store.selection = [1, 2]
            store.selected = 1
            await store.load(1)
            _ = try await Backend.call("queue_control", ["action": "pause"])
            let initialJobs = try await Backend.call("list_jobs")
            try check((initialJobs["jobs"] as? [[String: Any]] ?? []).isEmpty,
                "preset_workflow_starts_without_queue_jobs")

            let model = ExportPresetLibraryModel()
            await model.refresh(offset: 0, search: prefix)
            try check(model.page?.total == 0 && model.page?.local == false,
                "export_preset_library_starts_shared_and_empty")

            var draft = ExportDraft()
            draft.format = "jpeg"
            draft.space = "prophoto"
            draft.maxEdge = 4321
            draft.quality = 73
            draft.outputSharpen = 42.75
            draft.name = "{stem}-Native-{seq}"
            draft.priority = 7
            draft.metadata = "catalog"
            draft.keywordHierarchy = true
            draft.destination = destination
            let allOptions = draft.options
            let saveSource = model.saveSource(from: draft, updating: false)!
            guard let saved = await model.save(saveSource, name: "\(prefix) Main", includeDestination: true) else {
                throw EngineFailure(message: model.error ?? "Could not save export preset")
            }
            draft.loadedPreset = saved
            try check(model.page?.items.contains(where: { $0.id == saved.id }) == true,
                "save_current_export_settings_as_preset")

            guard let mainItem = model.page?.items.first(where: { $0.id == saved.id }) else {
                throw EngineFailure(message: "Saved export preset did not appear in its bounded page")
            }
            let pageRevision = model.page!.revision
            let captured = try await Backend.call("get_export_preset", [
                "preset_id": saved.id, "expected_revision": pageRevision
            ])
            let capturedRow = captured["preset"] as! [String: Any]
            let capturedSettings = capturedRow["settings"] as! [String: Any]
            let capturedOptions = capturedSettings["options"] as! [String: Any]
            try check(Set(capturedSettings.keys) == Set(["format", "options", "destination"])
                && capturedRow["id"] as? String == saved.id
                && capturedSettings["format"] as? String == "jpeg"
                && capturedSettings["destination"] as? String == destination
                && optionsEqual(capturedOptions, allOptions),
                "backend_stores_exact_format_destination_and_all_eight_export_options")
            try check(capturedRow["selected_photos"] == nil && capturedRow["photo_ids"] == nil
                && capturedRow["recipe"] == nil && capturedRow["request_key"] == nil,
                "preset_contains_no_photo_selection_recipe_or_queue_identity")

            var applied = ExportDraft()
            applied.destination = oldDestination
            let selectedBeforeUse = store.selection
            let jobsBeforeUse = try await Backend.call("list_jobs")
            guard let receipt = await model.load(mainItem) else {
                throw EngineFailure(message: model.error ?? "Could not load saved export preset")
            }
            applied.apply(receipt)
            try check(applied.loadedPreset?.id == saved.id && applied.destination == destination
                && applied.format == "jpeg" && optionsEqual(applied.options, allOptions),
                "preset_load_restores_destination_and_all_export_options")
            let jobsAfterUse = try await Backend.call("list_jobs")
            try check(store.selection == selectedBeforeUse
                && (jobsAfterUse["jobs"] as? [[String: Any]] ?? []).count
                    == (jobsBeforeUse["jobs"] as? [[String: Any]] ?? []).count,
                "choosing_preset_preserves_selection_and_never_queues")

            let emptyFolderDraft = ExportDraft()
            var noDestination = emptyFolderDraft
            noDestination.destination = oldDestination
            let noFolderSource = model.saveSource(from: noDestination, updating: false)!
            guard let noFolder = await model.save(noFolderSource, name: "\(prefix) No Folder", includeDestination: false),
                  let noFolderItem = model.page?.items.first(where: { $0.id == noFolder.id }),
                  let noFolderReceipt = await model.load(noFolderItem) else {
                throw EngineFailure(message: model.error ?? "Could not save or read folder-free preset")
            }
            var cleared = ExportDraft()
            cleared.destination = oldDestination
            cleared.apply(noFolderReceipt)
            try check(cleared.destination.isEmpty && !noFolderReceipt.selection.includesDestination,
                "loading_null_destination_clears_previous_export_folder")
            try check(!FileManager.default.fileExists(atPath: destination)
                && !FileManager.default.fileExists(atPath: oldDestination),
                "saving_or_loading_literal_folders_does_not_touch_the_filesystem")

            let binding = Binding<ExportDraft>(get: { draft }, set: { draft = $0 })
            try await snapshot("export-preset-browser.png",
                ExportPresetBrowserSheet(draft: binding, model: model), NSSize(width: 760, height: 620), root)
            let settingsModel = ExportPresetLibraryModel()
            await settingsModel.refresh(offset: 0, search: "")
            try await snapshot("export-preset-settings.png",
                Form { ExportPresetSettingsSection(model: settingsModel) }, NSSize(width: 620, height: 220), root)
            let editorSource = model.saveSource(from: draft, updating: false)!
            try await snapshot("export-preset-save-editor.png",
                ExportPresetSaveSheet(source: editorSource, model: model, draft: binding),
                NSSize(width: 560, height: 300), root)
            try await snapshot("export-sheet-offscreen.png",
                ExportSheet().environmentObject(store), NSSize(width: 720, height: 900), root)

            // Read responses are bound to the page/filter generations that requested them.
            let staleListToken = model.listGeneration
            let staleList = try await Backend.call("list_export_presets", ["offset": 0, "search": prefix])
            await model.refresh(offset: 0, search: "no-match-\(prefix)")
            let emptySearchPage = model.page
            try check(!model.receiveList(staleList, token: staleListToken, search: prefix)
                && model.page?.search == emptySearchPage?.search && model.page?.items.isEmpty == true,
                "late_list_reply_cannot_replace_new_search_page")
            await model.refresh(offset: 0, search: prefix)
            guard let currentItem = model.page?.items.first(where: { $0.id == saved.id }) else {
                throw EngineFailure(message: "Main preset missing after search reload")
            }
            let currentPageRevision = model.page!.revision
            let goodGet = try await Backend.call("get_export_preset", [
                "preset_id": saved.id, "expected_revision": currentPageRevision
            ])
            let priorGetToken = model.getGeneration
            let priorListToken = model.listGeneration
            model.invalidateReads()
            let rejectedGet = model.receivePreset(goodGet, item: currentItem, expectedRevision: currentPageRevision,
                token: priorGetToken, listToken: priorListToken, search: prefix, offset: 0)
            try check(!model.loading && !model.loadingPreset
                && model.receiveList(staleList, token: staleListToken, search: prefix) == false
                && isNil(rejectedGet),
                "closing_browser_invalidates_late_list_and_get_replies")
            await model.refresh(offset: 0, search: prefix)
            guard let reloadedItem = model.page?.items.first(where: { $0.id == saved.id }) else {
                throw EngineFailure(message: "Main preset missing after explicit browser reload")
            }
            let strictPageRevision = model.page!.revision
            var mismatchedGet = try await Backend.call("get_export_preset", [
                "preset_id": saved.id, "expected_revision": strictPageRevision
            ])
            mismatchedGet["revision"] = String(repeating: "f", count: 64)
            let rejectedMismatchedGet = model.receivePreset(mismatchedGet, item: reloadedItem,
                expectedRevision: strictPageRevision, token: model.getGeneration,
                listToken: model.listGeneration, search: prefix, offset: 0)
            try check(isNil(rejectedMismatchedGet),
                "get_reply_must_match_captured_page_revision")
            guard let currentMainReceipt = await model.load(reloadedItem) else {
                throw EngineFailure(message: model.error ?? "Current export preset reply was rejected")
            }
            applied.apply(currentMainReceipt)
            try check(applied.loadedPreset?.revision == strictPageRevision,
                "current_page_get_reply_is_accepted")

            // Updating uses its loaded revision and snapshots the complete option dictionary.
            let mainDraft = applied
            let renameDraftRevision = mainDraft.loadedPreset!.revision
            let staleUpdate = model.saveSource(from: mainDraft, updating: true)!
            var nativeUpdateDraft = applied
            nativeUpdateDraft.quality = 69
            let validUpdateSource = model.saveSource(from: nativeUpdateDraft, updating: true)!
            guard let updatedSelection = await model.save(validUpdateSource,
                name: validUpdateSource.name, includeDestination: true) else {
                throw EngineFailure(message: model.error ?? "Could not update current export preset")
            }
            nativeUpdateDraft.loadedPreset = updatedSelection
            let updatedRevision = model.page!.revision
            let validUpdateReceipt = try await Backend.call("get_export_preset", [
                "preset_id": saved.id, "expected_revision": updatedRevision
            ])
            let validUpdatedSettings = ((validUpdateReceipt["preset"] as? [String: Any])?["settings"] as? [String: Any])!
            try check(updatedSelection.id == saved.id && updatedSelection.revision == updatedRevision
                && (validUpdatedSettings["options"] as? [String: Any])?["quality"] as? Int == 69
                && nativeUpdateDraft.loadedPreset?.revision == updatedRevision,
                "current_update_preset_saves_options_and_advances_only_its_successful_draft")

            // A rename after a later external settings update may update the label, never its stale data token.
            var externallyChangedDraft = draft
            externallyChangedDraft.maxEdge = 2048
            let externalPageRevision = model.page!.revision
            let externalUpdate = try await Backend.call("save_export_preset", [
                "name": "\(prefix) Main", "preset_id": saved.id,
                "settings": externallyChangedDraft.settings(includeDestination: true),
                "expected_revision": externalPageRevision
            ])
            let afterExternalUpdateRevision = try revision(externalUpdate)
            await model.refresh(offset: 0, search: prefix)
            guard let renameItem = model.page?.items.first(where: { $0.id == saved.id }),
                  let renameSource = model.mutationSource(for: renameItem),
                  let renamed = await model.rename(renameSource, name: "\(prefix) Main Renamed") else {
                throw EngineFailure(message: model.error ?? "Could not rename export preset")
            }
            var staleApplied = applied
            staleApplied.acknowledgeRename(renamed, sourceRevision: renameSource.expectedRevision)
            try check(renameSource.expectedRevision == afterExternalUpdateRevision
                && staleApplied.loadedPreset?.name == renamed.name
                && staleApplied.loadedPreset?.revision == renameDraftRevision,
                "rename_does_not_rebase_draft_with_older_settings")
            let staleUpdateResult = await model.save(staleUpdate, name: staleUpdate.name, includeDestination: true)
            let afterStaleUpdate = try await Backend.call("get_export_preset", [
                "preset_id": saved.id, "expected_revision": model.page!.revision
            ])
            let afterStaleSettings = ((afterStaleUpdate["preset"] as? [String: Any])?["settings"] as? [String: Any])!
            let afterStaleRow = afterStaleUpdate["preset"] as? [String: Any] ?? [:]
            try check(staleUpdateResult == nil && model.error?.localizedCaseInsensitiveContains("changed") == true
                && afterStaleRow["name"] as? String == renamed.name
                && (afterStaleSettings["options"] as? [String: Any])?["max_edge"] as? Int == 2048,
                "stale_loaded_settings_cannot_overwrite_external_update_after_rename")

            // Every open mutation form retains its captured revision and fails visibly after another writer.
            await model.refresh(offset: 0, search: prefix)
            guard let currentMain = model.page?.items.first(where: { $0.id == saved.id }),
                  let freshReceipt = await model.load(currentMain) else {
                throw EngineFailure(message: model.error ?? "Could not reload current preset capture")
            }
            var freshDraft = ExportDraft()
            freshDraft.apply(freshReceipt)
            let staleSaveSource = model.saveSource(from: draft, updating: false)!
            let staleUpdateSource = model.saveSource(from: freshDraft, updating: true)!
            let staleMutationSource = model.mutationSource(for: currentMain)!
            let staleStorageRevision = model.page!.revision
            let concurrentSave = try await Backend.call("save_export_preset", [
                "name": "\(prefix) Concurrent", "settings": draft.settings(includeDestination: false),
                "expected_revision": staleStorageRevision
            ])
            let concurrentRevision = try revision(concurrentSave)
            try check(concurrentRevision != staleStorageRevision, "external_writer_advances_captured_export_revision")
            let rejectedNew = await model.save(staleSaveSource, name: "\(prefix) Stale New", includeDestination: false)
            let rejectedUpdate = await model.save(staleUpdateSource, name: staleUpdateSource.name, includeDestination: true)
            let rejectedRename = await model.rename(staleMutationSource, name: "\(prefix) Stale Rename")
            let rejectedDelete = await model.delete(staleMutationSource)
            let rejectedStorage = await model.setStorage(true, expectedRevision: staleStorageRevision)
            try check(rejectedNew == nil && rejectedUpdate == nil && rejectedRename == nil
                && !rejectedDelete && !rejectedStorage
                && model.page?.revision == staleStorageRevision,
                "captured_save_update_rename_delete_and_storage_forms_reject_stale_revision")
            let latestPresetPage = try await Backend.call("list_export_presets", ["offset": 0, "search": prefix])
            let latestPresetRevision = try revision(latestPresetPage)
            let verifyUnchanged = try await Backend.call("get_export_preset", [
                "preset_id": saved.id, "expected_revision": latestPresetRevision
            ])
            let verifySettings = ((verifyUnchanged["preset"] as? [String: Any])?["settings"] as? [String: Any])!
            try check((verifySettings["options"] as? [String: Any])?["max_edge"] as? Int == 2048
                && (verifyUnchanged["preset"] as? [String: Any])?["name"] as? String == renamed.name,
                "failed_stale_forms_preserve_latest_preset_values")

            // More than one page proves that search and cursor requests remain bounded at 30 rows.
            let pagePrefix = "NativePage\(UUID().uuidString.prefix(8))"
            var rollingRevision = try revision(try await Backend.call("list_export_presets", ["offset": 0, "search": pagePrefix]))
            let emptySettings: [String: Any] = ["format": "tiff16", "options": ["space": "srgb"], "destination": NSNull()]
            for index in 0..<31 {
                let result = try await Backend.call("save_export_preset", [
                    "name": "\(pagePrefix) \(String(format: "%02d", index))",
                    "settings": emptySettings, "expected_revision": rollingRevision
                ])
                rollingRevision = try revision(result)
            }
            let rawPage = try await Backend.call("list_export_presets", ["offset": 0, "search": pagePrefix])
            let rawRows = rawPage["presets"] as? [[String: Any]] ?? []
            let rawKeys = Set(rawRows.first.map { Array($0.keys) } ?? [])
            try check(rawRows.count == 30 && rawPage["total"] as? Int == 31
                && rawPage["page_size"] as? Int == 30 && rawKeys == Set(["id", "name"]),
                "backend_returns_bounded_name_only_preset_page")
            await model.refresh(offset: 0, search: pagePrefix)
            try check(model.page?.items.count == 30 && model.page?.total == 31,
                "native_browser_renders_first_bounded_preset_page")
            await model.refresh(offset: 30)
            try check(model.page?.offset == 30 && model.page?.items.count == 1,
                "native_browser_reads_second_preset_page")

            // Storage scope switches affect future writes only; existing shared/local rows stay put.
            await model.refresh(offset: 0, search: prefix)
            guard let sharedPage = model.page else { throw EngineFailure(message: "Missing shared page") }
            try check(await model.setStorage(true, expectedRevision: sharedPage.revision)
                && model.page?.local == true && model.page?.total == 0,
                "switch_to_catalog_storage_keeps_shared_presets_separate")
            let localDraft = ExportDraft()
            let localSource = model.saveSource(from: localDraft, updating: false)!
            guard let localPreset = await model.save(localSource, name: "\(prefix) Local Only", includeDestination: false) else {
                throw EngineFailure(message: model.error ?? "Could not save catalog-local export preset")
            }
            guard let localPage = model.page else { throw EngineFailure(message: "Missing catalog-local page") }
            try check(localPage.local && localPage.items.contains(where: { $0.id == localPreset.id }),
                "new_preset_uses_explicit_catalog_storage")
            try check(await model.setStorage(false, expectedRevision: localPage.revision)
                && model.page?.local == false && model.page?.items.contains(where: { $0.id == localPreset.id }) == false
                && model.page?.items.contains(where: { $0.id == saved.id }) == true,
                "switch_back_exposes_unchanged_shared_presets_without_moving_local_rows")
            guard let sharedAgain = model.page else { throw EngineFailure(message: "Missing shared page after storage switch") }
            try check(await model.setStorage(true, expectedRevision: sharedAgain.revision)
                && model.page?.local == true && model.page?.items.contains(where: { $0.id == localPreset.id }) == true
                && model.page?.items.contains(where: { $0.id == saved.id }) == false,
                "catalog_local_preset_remains_in_its_original_storage")
            guard let localPageForExport = model.page else {
                throw EngineFailure(message: "Missing catalog-local page before queue snapshot")
            }
            try check(await model.setStorage(false, expectedRevision: localPageForExport.revision)
                && model.page?.local == false,
                "explicitly_return_to_shared_presets_for_captured_export_delete")

            // The only queue action is explicit Add to Queue; its job captures the submitted options.
            store.selection = [1, 2]
            store.selected = 1
            await store.load(1)
            let queuedDraft = applied
            draft = queuedDraft
            let beforeExplicitQueue = try await Backend.call("list_jobs")
            try check((beforeExplicitQueue["jobs"] as? [[String: Any]] ?? []).isEmpty,
                "preset_management_workflow_never_enqueues_jobs")
            await store.export(destination, "jpeg", queuedDraft.options)
            await store.refreshJobs()
            createdJobIDs = store.jobs.compactMap { $0["id"] as? Int }
            try check(store.jobs.count == 2 && store.jobs.allSatisfy { $0["state"] as? String == "pending" },
                "explicit_export_action_enqueues_selected_photos_while_queue_is_paused")
            try check(createdJobIDs.count == 2, "queue_returns_two_job_identities")
            draft.quality = 99
            draft.outputSharpen = 0
            for jobID in createdJobIDs {
                let job = try await Backend.call("get_job", ["job_id": jobID])
                let frozenOptions = job["options"] as? [String: Any] ?? [:]
                try check(job["format"] as? String == "jpeg"
                    && job["destination"] as? String == destination
                    && optionsEqual(frozenOptions, queuedDraft.options),
                    "queued_job_\(jobID)_keeps_all_submitted_export_options")
            }
            let finalJobs = try await Backend.call("list_jobs")
            try check((finalJobs["jobs"] as? [[String: Any]])?.count == 2
                && finalJobs["paused"] as? Bool == true,
                "preset_save_use_and_storage_never_add_jobs")
            for jobID in createdJobIDs {
                _ = try await Backend.call("queue_control", ["action": "cancel", "job_id": jobID])
            }
            await store.refreshJobs()
            try check(store.jobs.count == 2 && store.jobs.allSatisfy { $0["state"] as? String == "cancelled" },
                "native_probe_cancels_its_paused_jobs_for_clean_shutdown")
            guard let currentSavedItem = model.page?.items.first(where: { $0.id == saved.id }),
                  let deleteSource = model.mutationSource(for: currentSavedItem) else {
                throw EngineFailure(message: "Shared preset was missing before explicit deletion")
            }
            let loadedOptionsBeforeDelete = draft.options
            let loadedDestinationBeforeDelete = draft.destination
            let selectionBeforeDelete = store.selection
            let deleted = await model.delete(deleteSource)
            draft.forgetDeletedPreset(saved.id)
            let survivingJob = try await Backend.call("get_job", ["job_id": createdJobIDs[0]])
            try check(deleted && draft.loadedPreset == nil
                && optionsEqual(draft.options, loadedOptionsBeforeDelete)
                && draft.destination == loadedDestinationBeforeDelete
                && store.selection == selectionBeforeDelete
                && optionsEqual(survivingJob["options"] as? [String: Any] ?? [:], queuedDraft.options),
                "deleting_loaded_preset_preserves_draft_selection_and_queued_job_snapshot")
            guard let afterDeleteSharedPage = model.page else {
                throw EngineFailure(message: "Missing shared page after preset deletion")
            }
            try check(await model.setStorage(true, expectedRevision: afterDeleteSharedPage.revision)
                && model.page?.local == true
                && model.page?.items.contains(where: { $0.id == localPreset.id }) == true,
                "deleting_shared_preset_does_not_delete_catalog_local_preset")
            try check(try paths.enumerated().allSatisfy {
                try Data(contentsOf: URL(fileURLWithPath: $0.element)) == originalBytes[$0.offset]
            }, "preset_and_export_queue_workflows_preserve_original_photo_bytes")

            model.invalidateReads()
            settingsModel.invalidateReads()
            print(String(data: try JSONSerialization.data(withJSONObject: [
                "ok": true, "passed": checks.count, "checks": checks,
                "offscreen_snapshots": screenshots, "desktop_ui": "NOT_VERIFIED"
            ], options: [.prettyPrinted, .sortedKeys]), encoding: .utf8)!)
            exit(0)
        } catch {
            for jobID in createdJobIDs {
                _ = try? await Backend.call("queue_control", ["action": "cancel", "job_id": jobID])
            }
            print(String(data: try! JSONSerialization.data(withJSONObject: [
                "ok": false, "passed": checks.values.filter { $0 }.count, "checks": checks,
                "error": error.localizedDescription, "store_error": store.error ?? "",
                "offscreen_snapshots": screenshots, "desktop_ui": "NOT_VERIFIED"
            ], options: [.prettyPrinted, .sortedKeys]), encoding: .utf8)!)
            exit(1)
        }
    }
}
