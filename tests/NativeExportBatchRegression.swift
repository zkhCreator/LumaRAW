// Purpose: verify revision-bound multi-preset export capture and native batch receipts.
// Inputs: five disposable photographs, an isolated catalog/preset store and packaged Backend IPC.
// Outputs: bounded paging, conflict, destination, queue-snapshot and receipt-poll evidence.
// Offscreen snapshots are layout evidence only; desktop interaction is NOT_VERIFIED.
import AppKit
import Combine
import Foundation
import SwiftUI

private actor BatchActionGate {
    private var started = false
    private var startWaiters: [CheckedContinuation<Void, Never>] = []
    private var releaseContinuation: CheckedContinuation<Void, Never>?

    func pause() async {
        started = true
        let waiters = startWaiters
        startWaiters = []
        waiters.forEach { $0.resume() }
        await withCheckedContinuation { releaseContinuation = $0 }
    }

    func waitUntilStarted() async {
        if started { return }
        await withCheckedContinuation { startWaiters.append($0) }
    }

    func release() {
        releaseContinuation?.resume()
        releaseContinuation = nil
    }
}

@main struct NativeExportBatchRegression {
    @MainActor static func main() async {
        _ = NSApplication.shared
        let store = Store()
        var checks: [String: Bool] = [:]
        var screenshots: [String] = []
        var batchIDs: [String] = []
        var testDestinations: [String] = []

        func check(_ value: Bool, _ name: String) throws {
            checks[name] = value
            if !value { throw EngineFailure(message: name) }
        }

        func revision(_ result: [String: Any]) throws -> String {
            guard let value = result["revision"] as? String, value.count == 64 else {
                throw EngineFailure(message: "Missing opaque export preset revision")
            }
            return value
        }

        func optionsMatch(_ actual: [String: Any], _ expected: [String: Any]) -> Bool {
            guard Set(actual.keys) == Set(expected.keys) else { return false }
            for (key, value) in expected {
                if key == "output_sharpen" {
                    guard let a = actual[key] as? NSNumber, let b = value as? NSNumber,
                          abs(a.doubleValue - b.doubleValue) < 0.000001 else { return false }
                } else if key == "keyword_hierarchy" {
                    guard (actual[key] as? NSNumber)?.boolValue == (value as? NSNumber)?.boolValue else { return false }
                } else if String(describing: actual[key]!) != String(describing: value) {
                    return false
                }
            }
            return true
        }

        func snapshot<V: View>(_ name: String, _ view: V, _ size: NSSize, _ root: URL) async throws {
            let host = NSHostingView(rootView: view.background(Color(nsColor: .windowBackgroundColor)))
            host.frame = NSRect(origin: .zero, size: size)
            host.layoutSubtreeIfNeeded()
            try await Task.sleep(nanoseconds: 120_000_000)
            host.layoutSubtreeIfNeeded()
            guard host.bounds.width > 0, host.bounds.height > 0,
                  let bitmap = host.bitmapImageRepForCachingDisplay(in: host.bounds) else {
                throw EngineFailure(message: "No offscreen bitmap for \(name)")
            }
            host.cacheDisplay(in: host.bounds, to: bitmap)
            guard let png = bitmap.representation(using: .png, properties: [:]) else {
                throw EngineFailure(message: "Could not encode offscreen snapshot \(name)")
            }
            try png.write(to: root.appendingPathComponent(name))
            screenshots.append(name)
        }

        func savePreset(index: Int, name: String, expectedRevision: String,
                        destination: String?) async throws -> (id: String, revision: String, options: [String: Any], format: String) {
            var draft = ExportDraft()
            draft.format = index.isMultiple(of: 2) ? "tiff16" : "jpeg"
            draft.space = ["srgb", "p3", "adobe", "prophoto"][index % 4]
            draft.maxEdge = [0, 1200, 2400, 3600][index % 4]
            draft.quality = 88 + index % 13
            draft.outputSharpen = Double(index % 11) * 2.5
            draft.name = "batch-\(index)-{stem}-{seq}"
            draft.priority = index % 10
            draft.metadata = ["none", "copyright", "catalog"][index % 3]
            draft.keywordHierarchy = index.isMultiple(of: 2)
            let options = draft.options
            let settings: [String: Any] = [
                "format": draft.format,
                "options": options,
                "destination": destination as Any? ?? NSNull()
            ]
            let response = try await Backend.call("save_export_preset", [
                "name": name, "settings": settings, "expected_revision": expectedRevision
            ])
            guard let id = response["preset_id"] as? String else {
                throw EngineFailure(message: "Saved preset response omitted its ID")
            }
            return (id, try revision(response), options, draft.format)
        }

        func acceptedBatch(_ result: ExportBatchSubmissionResult) -> String? {
            if case .accepted(let id) = result { return id }
            return nil
        }

        func cancelAllBatches() async {
            for id in batchIDs {
                _ = try? await Backend.call("queue_control", ["action": "cancel", "batch_id": id])
            }
        }

        func cleanup() async {
            await cancelAllBatches()
            for path in testDestinations where FileManager.default.fileExists(atPath: path) {
                try? FileManager.default.removeItem(atPath: path)
            }
        }

        do {
            let paths = ProcessInfo.processInfo.environment["LUMARAW_TEST_FIXTURES"]!.components(separatedBy: "|")
            try check(paths.count == 5, "runner_supplies_five_disposable_photos")
            let originalBytes = try paths.map { try Data(contentsOf: URL(fileURLWithPath: $0)) }
            let root = URL(fileURLWithPath: ProcessInfo.processInfo.environment["LUMARAW_CATALOG"]!).deletingLastPathComponent()
            let prefix = "Native Batch \(UUID().uuidString.prefix(8))"
            let presetDestinations = (0..<31).map { root.appendingPathComponent("\(prefix) Folder \($0)").path }
            let overrideDestination = root.appendingPathComponent("\(prefix) Explicit Override").path
            let parentDestination = root.appendingPathComponent("\(prefix) Shared Parent").path
            let listDestination = root.appendingPathComponent("\(prefix) List Page").path
            testDestinations = presetDestinations + [overrideDestination, parentDestination, listDestination]

            await store.importPaths(paths)
            store.thumbnailRenderer.request([])
            store.cancelMainPreview()
            guard store.photos.count == 5 else { throw EngineFailure(message: "Five fixture photos were not imported") }
            let photoIDs = store.photos.map(\.id).sorted()
            store.selection = Set(photoIDs)
            store.selected = photoIDs.first
            if let first = photoIDs.first { await store.load(first) }
            _ = try await Backend.call("queue_control", ["action": "pause"])
            await store.refreshJobs()

            let initialPrevious = try await Backend.call("get_previous_export")
            try check(initialPrevious["available"] as? Bool == false,
                "isolated_catalog_starts_without_previous_export")

            var rollingRevision = try revision(try await Backend.call("list_export_presets", ["offset": 0, "search": prefix]))
            var presetIDs: [String] = []
            var expectedOptions: [String: [String: Any]] = [:]
            var expectedFormats: [String: String] = [:]
            var expectedNames: [String: String] = [:]
            for index in 0..<31 {
                let name = "\(prefix) \(String(format: "%02d", index))"
                let saved = try await savePreset(index: index, name: name, expectedRevision: rollingRevision,
                    destination: index == 0 ? nil : presetDestinations[index])
                presetIDs.append(saved.id)
                expectedOptions[saved.id] = saved.options
                expectedFormats[saved.id] = saved.format
                expectedNames[saved.id] = name
                rollingRevision = saved.revision
            }

            let picker = ExportBatchPresetPickerModel()
            await picker.refresh(offset: 0, search: prefix)
            try check(picker.page?.items.count == 30 && picker.page?.total == 31,
                "native_preset_picker_reads_bounded_30_item_pages")
            for item in picker.page?.items.prefix(12) ?? [] {
                try check(picker.setSelected(item.id, true), "first_page_selection_\(item.id)")
            }
            for item in picker.page?.items.dropFirst(12) ?? [] { _ = picker.setSelected(item.id, true) }
            await picker.refresh(offset: 30)
            if let last = picker.page?.items.first(where: { $0.id == presetIDs[30] }) {
                try check(!picker.setSelected(last.id, true) && picker.selectedOrder.count == 30,
                    "preset_selection_is_capped_at_30_across_pages")
            } else {
                throw EngineFailure(message: "Preset 31 was absent from the second page")
            }
            picker.clearSelection()
            await picker.refresh(offset: 0)
            for item in picker.page?.items.prefix(12) ?? [] { _ = picker.setSelected(item.id, true) }
            await picker.refresh(offset: 30)
            if let last = picker.page?.items.first(where: { $0.id == presetIDs[30] }) {
                try check(picker.setSelected(last.id, true), "second_page_selection_is_retained")
            } else {
                throw EngineFailure(message: "Preset 31 was absent from the second page")
            }
            let selectedIDs = picker.selectedOrder
            let capturedRevision = picker.capturedRevision!
            guard let capturedBeforeChange = await picker.captureSelectedSettings() else {
                throw EngineFailure(message: picker.error ?? "Could not capture selected preset settings")
            }
            try check(selectedIDs.count == 13 && capturedBeforeChange.count == 13
                && Set(capturedBeforeChange.map(\.id)) == Set(selectedIDs),
                "cross_page_preset_selection_captures_exactly_once_under_one_revision")
            try check(capturedBeforeChange.allSatisfy {
                optionsMatch($0.settings.options, expectedOptions[$0.id] ?? [:])
                    && $0.settings.format == expectedFormats[$0.id]
            }, "captured_presets_retain_all_eight_options_and_format")

            var staleDrafts = capturedBeforeChange.map(ExportBatchPresetDraft.init(snapshot:))
            guard let emptyDestination = staleDrafts.firstIndex(where: { $0.snapshot.settings.destination == nil }) else {
                throw EngineFailure(message: "No folder-free test preset was captured")
            }
            try check(staleDrafts[emptyDestination].submissionEntry(parentMode: false) == nil,
                "folder_free_preset_requires_an_explicit_destination")
            staleDrafts[emptyDestination].destinationOverride = overrideDestination
            staleDrafts[emptyDestination].filenameSuffix = "BatchSuffix café 🚀"
            let staleSubmission = ExportBatchPresetSubmission(expectedRevision: capturedRevision,
                entries: staleDrafts, parentDestination: nil)
            let firstEntry = staleDrafts[emptyDestination].submissionEntry(parentMode: false)!
            try check(firstEntry["destination"] as? String == overrideDestination
                && firstEntry["filename_suffix"] as? String == "BatchSuffix café 🚀",
                "individual_folder_override_and_unicode_suffix_are_preserved_verbatim")

            let external = try await savePreset(index: 6, name: "\(prefix) External Change",
                expectedRevision: capturedRevision, destination: nil)
            rollingRevision = external.revision
            await picker.refresh(offset: 0, search: prefix)
            try check(picker.stale && picker.selectedOrder == selectedIDs,
                "external_preset_revision_change_marks_captured_selection_stale")
            store.selection = Set(photoIDs)
            let beforeStaleJobs = try await Backend.call("list_jobs")
            let staleResult = await store.exportBatch(staleSubmission)
            let afterStaleJobs = try await Backend.call("list_jobs")
            try check(acceptedBatch(staleResult) == nil
                && (afterStaleJobs["jobs"] as? [[String: Any]] ?? []).count
                    == (beforeStaleJobs["jobs"] as? [[String: Any]] ?? []).count,
                "stale_revision_fails_visible_without_queueing_or_replaying")

            await picker.reloadAndClearSelection()
            try check(!picker.stale && picker.selectedOrder.isEmpty && picker.capturedRevision == rollingRevision,
                "explicit_reload_clears_selection_and_captures_new_library_revision")
            for item in picker.page?.items.prefix(12) ?? [] { _ = picker.setSelected(item.id, true) }
            await picker.refresh(offset: 30)
            if let last = picker.page?.items.first(where: { $0.id == presetIDs[30] }) {
                _ = picker.setSelected(last.id, true)
            }
            guard let snapshots = await picker.captureSelectedSettings() else {
                throw EngineFailure(message: picker.error ?? "Could not recapture presets after reload")
            }
            try check(snapshots.count == 13 && picker.capturedRevision == rollingRevision,
                "reselection_uses_the_explicitly_reloaded_revision")
            await picker.refresh(offset: 0)
            try await snapshot("export-batch-preset-picker.png",
                ExportBatchSheet(picker: picker).environmentObject(store), NSSize(width: 900, height: 760), root)

            var individualDrafts = snapshots.map(ExportBatchPresetDraft.init(snapshot:))
            guard let individualFolderFree = individualDrafts.firstIndex(where: { $0.snapshot.settings.destination == nil }) else {
                throw EngineFailure(message: "Folder-free preset disappeared after reload")
            }
            individualDrafts[individualFolderFree].destinationOverride = overrideDestination
            individualDrafts[individualFolderFree].filenameSuffix = "BatchSuffix café 🚀"
            let individualSubmission = ExportBatchPresetSubmission(expectedRevision: rollingRevision,
                entries: individualDrafts, parentDestination: nil)
            let beforePrevious = try await Backend.call("get_previous_export")

            store.selection = Set(photoIDs)
            if let first = photoIDs.first { store.selected = first;store.set("exposure", 0.375) }
            let batchTask = Task { await store.exportBatch(individualSubmission) }
            for _ in 0..<10000 where !store.exportSubmissionBusy { await Task.yield() }
            try check(store.exportSubmissionBusy, "batch_submission_uses_shared_export_busy_guard")
            let selectedAtSubmission = photoIDs
            store.selection = Set(photoIDs.suffix(2))
            let duplicateBatch = await store.exportBatch(individualSubmission)
            await store.export(overrideDestination, "jpeg", ExportDraft().options)
            await store.exportWithPrevious()
            let individualResult = await batchTask.value
            guard let individualBatchID = acceptedBatch(individualResult) else {
                throw EngineFailure(message: "Batch receipt was not accepted: \(individualResult)")
            }
            batchIDs.append(individualBatchID)
            try check({ if case .rejected = duplicateBatch { return true }; return false }(),
                "concurrent_batch_submit_is_rejected_by_shared_guard")
            let individualDetail = try await Backend.call("get_export_batch", ["batch_id": individualBatchID, "offset": 0])
            let individualPresetRows = individualDetail["presets"] as? [[String: Any]] ?? []
            let individualJobs = individualDetail["jobs"] as? [[String: Any]] ?? []
            try check(individualDetail["batch"] as? [String: Any] != nil
                && (individualDetail["batch"] as? [String: Any])?["batch_id"] as? String == individualBatchID
                && individualDetail["total"] as? Int == 65
                && individualJobs.count == 60 && individualDetail["page_size"] as? Int == 60,
                "accepted_individual_batch_returns_uuid_receipt_and_bounded_60_job_page")
            try check(Set(individualJobs.compactMap { $0["photo_id"] as? Int }) == Set(selectedAtSubmission)
                && individualJobs.allSatisfy { $0["batch_id"] as? String == individualBatchID },
                "selection_changes_during_submission_do_not_change_captured_photo_ids")
            let expectedEntryByID = Dictionary(uniqueKeysWithValues: individualDrafts.map { ($0.snapshot.id, $0) })
            try check(individualPresetRows.count == 13 && individualPresetRows.allSatisfy { row in
                guard let id = row["preset_id"] as? String, let draft = expectedEntryByID[id],
                      let options = row["options"] as? [String: Any] else { return false }
                let expectedDestination = draft.resolvedDestination
                return optionsMatch(options, draft.snapshot.settings.options)
                    && row["format"] as? String == draft.snapshot.settings.format
                    && row["filename_suffix"] as? String == draft.filenameSuffix
                    && row["destination"] as? String == expectedDestination
                    && row["subfolder"] is NSNull
            }, "individual_batch_freezes_each_preset_options_destination_and_exact_suffix")
            let secondJobPage = try await Backend.call("get_export_batch", ["batch_id": individualBatchID, "offset": 60])
            let secondJobs = secondJobPage["jobs"] as? [[String: Any]] ?? []
            try check(secondJobPage["offset"] as? Int == 60 && secondJobs.count == 5,
                "batch_receipt_pages_the_final_five_jobs")
            let representative = individualJobs.first(where: { ($0["photo_id"] as? Int) == photoIDs.first })!
            let representativeID = representative["id"] as! Int
            let frozenJob = try await Backend.call("get_job", ["job_id": representativeID])
            let selectedPresetName = representative["preset_name"] as? String ?? ""
            let selectedPreset = individualPresetRows.first { $0["name"] as? String == selectedPresetName }!
            try check(frozenJob["batch_id"] as? String == individualBatchID
                && frozenJob["format"] as? String == selectedPreset["format"] as? String
                && frozenJob["destination"] as? String == selectedPreset["destination"] as? String
                && optionsMatch(frozenJob["options"] as? [String: Any] ?? [:], selectedPreset["options"] as? [String: Any] ?? [:])
                && ((frozenJob["recipe"] as? [String: Any])?["exposure"] as? NSNumber)?.doubleValue == 0.375,
                "queued_job_keeps_frozen_preset_values_and_flushed_live_recipe")

            var parentDrafts = snapshots.map(ExportBatchPresetDraft.init(snapshot:))
            parentDrafts[0].destinationOverride = overrideDestination
            parentDrafts[0].filenameSuffix = "ParentSuffix café 🚀"
            let parentSubmission = ExportBatchPresetSubmission(expectedRevision: rollingRevision,
                entries: parentDrafts, parentDestination: parentDestination)
            let parentPayload = parentSubmission.payloadPresets!
            try check(parentPayload.allSatisfy { $0["destination"] == nil && $0["subfolder"] is String }
                && Set(parentPayload.compactMap { $0["subfolder"] as? String }).count == 13,
                "parent_folder_mode_replaces_individual_paths_with_unique_reviewable_subfolders")
            store.selection = Set(photoIDs)
            guard let parentBatchID = acceptedBatch(await store.exportBatch(parentSubmission)) else {
                throw EngineFailure(message: "Parent-folder batch was not accepted")
            }
            batchIDs.append(parentBatchID)
            let parentDetail = try await Backend.call("get_export_batch", ["batch_id": parentBatchID, "offset": 0])
            let parentSummary = parentDetail["batch"] as? [String: Any] ?? [:]
            let parentRows = parentDetail["presets"] as? [[String: Any]] ?? []
            try check(parentSummary["destination_mode"] as? String == "parent"
                && parentSummary["parent_destination"] as? String == parentDestination
                && parentRows.count == 13 && parentRows.allSatisfy { row in
                    guard let child = row["destination"] as? String,let component = row["subfolder"] as? String else { return false }
                    return child == URL(fileURLWithPath: parentDestination).appendingPathComponent(component).path
                        && child.hasPrefix(parentDestination + "/")
                }, "parent_folder_receipt_keeps_shared_parent_and_resolved_per_preset_folders")

            let afterPrevious = try await Backend.call("get_previous_export")
            try check(beforePrevious["available"] as? Bool == false
                && afterPrevious["available"] as? Bool == false
                && (beforePrevious["revision"] as? Int) == (afterPrevious["revision"] as? Int)
                && beforePrevious["settings"] is NSNull && afterPrevious["settings"] is NSNull,
                "batch_submissions_do_not_change_catalog_previous_export")

            // Add enough small receipts to prove both 30-row batch history pages.
            for index in 0..<29 {
                let result = try await Backend.call("enqueue_export_batch", [
                    "photo_ids": [photoIDs[0]],
                    "presets": [["preset_id": presetIDs[1], "destination": listDestination,
                                 "filename_suffix": "Page \(index)"]],
                    "expected_revision": rollingRevision,
                    "request_key": UUID().uuidString
                ])
                guard let id = result["batch_id"] as? String else { throw EngineFailure(message: "History fixture batch omitted its UUID") }
                batchIDs.append(id)
            }

            let history = ExportBatchHistoryModel()
            try check(await history.refresh(offset: 0) && history.page?.batches.count == 30
                && history.page?.total == 31 && history.page?.pageSize == 30,
                "batch_history_reads_30_summaries_with_numeric_created_dates_and_state_counts")
            try check(history.page?.batches.allSatisfy { $0.created.isFinite && !$0.revision.isEmpty && !$0.counts.isEmpty } == true,
                "batch_list_rows_parse_timestamp_revision_and_dynamic_counts")
            try check(await history.refresh(offset: 30) && history.page?.offset == 30 && history.page?.batches.count == 1,
                "batch_history_pages_past_first_30_receipts")
            await history.refresh(offset: 0)
            try await snapshot("export-batch-history.png",
                ExportBatchHistorySheet(model: history, pollsWhileVisible: false).environmentObject(store),
                NSSize(width: 860, height: 700), root)
            await history.open(parentBatchID)
            try check(history.receipt?.total == 65 && history.receipt?.jobs.count == 60
                && history.receipt?.counts["pending"] == 65,
                "batch_history_opens_full_receipt_with_captured_job_counts")
            await history.loadDetail(offset: 60)
            try check(history.receipt?.offset == 60 && history.receipt?.jobs.count == 5,
                "native_receipt_model_reads_second_60_job_page")
            await history.loadDetail(offset: 0)
            try await snapshot("export-batch-receipt.png",
                ExportBatchReceiptView(model: history, onClose: {}).environmentObject(store), NSSize(width: 900, height: 760), root)

            var pollPublications = 0
            let pollObserver = history.objectWillChange.sink { _ in pollPublications += 1 }
            await history.refreshVisibleQuietly()
            let unchangedPollWasQuiet = pollPublications == 0
            _ = try await Backend.call("queue_control", ["action": "cancel", "batch_id": parentBatchID])
            await history.refreshVisibleQuietly()
            let externalChangeAppeared = history.receipt?.counts["cancelled"] == 65 && pollPublications > 0
            let changedPollPublications = pollPublications
            await history.refreshVisibleQuietly()
            let repeatedPollWasQuiet = pollPublications == changedPollPublications
            pollObserver.cancel()
            try check(unchangedPollWasQuiet && externalChangeAppeared && repeatedPollWasQuiet,
                "visible_receipt_refresh_shows_external_queue_changes_and_quietly_discards_unchanged_pages")

            _ = try await Backend.call("queue_control", ["action": "retry_cancelled", "batch_id": parentBatchID])
            await history.refreshVisibleQuietly()
            let actionWorked = await history.perform("cancel", on: parentBatchID)
            try check(actionWorked && history.receipt?.counts["cancelled"] == 65,
                "batch_scoped_cancel_action_refreshes_visible_receipt")

            // A failed receipt read after a durable action must remain visible and must not be hidden by a list read.
            var failNextDetail = false
            var listReads = 0
            let failureModel = ExportBatchHistoryModel(command: { method, params in
                if method == "list_export_batches" { listReads += 1 }
                if method == "get_export_batch" && failNextDetail {
                    failNextDetail = false
                    throw EngineFailure(message: "Simulated receipt refresh failure")
                }
                return try await Backend.call(method, params)
            })
            await failureModel.refresh(offset: 0)
            let smallBatchID = batchIDs[2]
            await failureModel.open(smallBatchID)
            let listReadsBeforeAction = listReads
            failNextDetail = true
            let actionWithFailedRead = await failureModel.perform("cancel", on: smallBatchID)
            try check(!actionWithFailedRead && failureModel.error?.contains("Simulated receipt refresh failure") == true
                && listReads == listReadsBeforeAction,
                "failed_post_action_receipt_read_keeps_error_and_skips_a_successful_list_clear")

            // A delayed mutation receipt that outlives the visible sheet may complete, but starts no follow-up reads.
            let gate = BatchActionGate()
            var sessionReads = 0
            let sessionModel = ExportBatchHistoryModel(command: { method, params in
                if method == "list_export_batches" || method == "get_export_batch" { sessionReads += 1 }
                if method == "queue_control" { await gate.pause() }
                return try await Backend.call(method, params)
            })
            await sessionModel.refresh(offset: 0)
            let sessionBatchID = batchIDs[3]
            await sessionModel.open(sessionBatchID)
            let receiptReadsBeforeAction = sessionReads
            let sessionAction = Task { await sessionModel.perform("cancel", on: sessionBatchID) }
            await gate.waitUntilStarted()
            sessionModel.invalidateReads()
            await gate.release()
            let sessionActionAccepted = await sessionAction.value
            try check(sessionActionAccepted && sessionReads == receiptReadsBeforeAction
                && sessionModel.receipt != nil && !sessionModel.detailLoading && !sessionModel.listLoading,
                "closed_receipt_session_suppresses_late_post_mutation_reads_without_retry")

            let finalJobs = try await Backend.call("list_jobs")
            try check((finalJobs["paused"] as? Bool) == true,
                "queue_remains_paused_while_batch_snapshots_are_inspected")
            try check(try paths.enumerated().allSatisfy {
                try Data(contentsOf: URL(fileURLWithPath: $0.element)) == originalBytes[$0.offset]
            }, "batch_setup_submission_and_receipt_preserve_original_photo_bytes")

            history.invalidateReads();failureModel.invalidateReads();sessionModel.invalidateReads();picker.invalidateReads()
            await cleanup()
            print(String(data: try JSONSerialization.data(withJSONObject: [
                "ok": true, "passed": checks.count, "checks": checks,
                "offscreen_snapshots": screenshots, "desktop_ui": "NOT_VERIFIED"
            ], options: [.prettyPrinted, .sortedKeys]), encoding: .utf8)!)
            exit(0)
        } catch {
            await cleanup()
            print(String(data: try! JSONSerialization.data(withJSONObject: [
                "ok": false, "passed": checks.values.filter { $0 }.count, "checks": checks,
                "error": error.localizedDescription, "store_error": store.error ?? "",
                "offscreen_snapshots": screenshots, "desktop_ui": "NOT_VERIFIED"
            ], options: [.prettyPrinted, .sortedKeys]), encoding: .utf8)!)
            exit(1)
        }
    }
}
