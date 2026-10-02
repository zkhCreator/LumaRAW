// Purpose: real Copy destination-folder pages, stale handling and read-only safety.
// Inputs: five runner photographs expanded into source folders, plus an isolated
// catalog and packaged Backend IPC. Outputs: page/count assertions and an offscreen
// sheet snapshot with long Unicode paths. Desktop UI interaction is NOT_VERIFIED.
import AppKit
import Foundation
import SwiftUI

@main struct NativeImportDestinationRegression {
    @MainActor static func main() async {
        _ = NSApplication.shared
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
            try await Task.sleep(nanoseconds: 100_000_000)
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

        do {
            let fixtures = ProcessInfo.processInfo.environment["LUMARAW_TEST_FIXTURES"]!
                .components(separatedBy: "|")
            try check(fixtures.count == 5, "runner_supplies_five_source_photos")
            let originalFixtureBytes = try fixtures.map { try Data(contentsOf: URL(fileURLWithPath: $0)) }
            let root = URL(fileURLWithPath: ProcessInfo.processInfo.environment["LUMARAW_CATALOG"]!)
                .deletingLastPathComponent()
            let sourceRoot = root.appendingPathComponent("旅行🌄摄影_日本語_SourceSet")
            let destination = root.appendingPathComponent("输出目的_日本語_LongPath")
            let backup = root.appendingPathComponent("备份目的_第二份")
            for folder in [sourceRoot, destination, backup] {
                try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
            }

            let unicodeSubfolder = String(repeating: "旅行摄影_日本_", count: 7)
            var sources: [String] = []
            var sourceBytes: [Data] = []
            for index in 0..<65 {
                let group = sourceRoot.appendingPathComponent("拍摄地_東京_森林_胶片_\(String(format: "%03d", index))")
                try FileManager.default.createDirectory(at: group, withIntermediateDirectories: true)
                let source = group.appendingPathComponent("原片_\(String(format: "%03d", index)).png")
                let fixtureIndex = index % fixtures.count
                try FileManager.default.copyItem(at: URL(fileURLWithPath: fixtures[fixtureIndex]), to: source)
                sources.append(source.path)
                sourceBytes.append(originalFixtureBytes[fixtureIndex])
            }

            let review = ImportReviewModel(sources: [sourceRoot.path])
            review.mode = "copy"
            review.destination = destination.path
            review.organization = "source"
            review.subfolder = unicodeSubfolder
            await review.scan()
            try check(review.plan?.ready == true && review.plan?.isCopy == true
                && review.plan?.number("selected_count") == sources.count,
                "source_grouped_copy_review_scans_all_nested_originals")
            await review.setBackup(backup.path)
            try check(review.plan?.backup?["destination"] as? String == backup.path,
                "backup_destination_is_captured_separately")

            var reviewValues = review.plan!.values
            reviewValues["processing"] = [
                "develop_name": String(repeating: "Landscape Develop Preset With A Long Display Name ", count: 5),
                "metadata_name": String(repeating: "Editorial Metadata Preset With A Long Display Name ", count: 5),
                "keyword_count": 42
            ]
            review.plan = ImportPlan(values: reviewValues)
            let longSummary = ((review.plan?.values["processing"] as? [String: Any])?["develop_name"] as? String ?? "")
                + ((review.plan?.values["processing"] as? [String: Any])?["metadata_name"] as? String ?? "")
            try check(longSummary.count > 300, "ready_copy_toolbar_uses_long_processing_preset_summary")
            try await snapshot("import-destination-ready-review.png",
                ImportReviewSheet(model: review).content, NSSize(width: 1060, height: 840), root)

            let plan = review.plan!
            let folders = ImportDestinationModel(planID: plan.id, revision: plan.revision)
            await folders.loadInitial()
            try check(folders.error == nil && folders.loaded && folders.destination == destination.path
                && folders.selectedCount == sources.count && folders.items.count == 60
                && folders.pageSize == 60 && folders.nextAfter != nil,
                "source_organization_returns_bounded_first_folder_page")
            try check(folders.items.allSatisfy { $0.relativePath.hasPrefix(unicodeSubfolder)
                && $0.path.hasPrefix(destination.path) && $0.photoCount == 1 }
                && folders.items.contains(where: { $0.relativePath.contains("拍摄地_東京") }),
                "grouped_rows_include_unicode_subfolder_relative_paths_and_counts")
            try check(folders.items.reduce(0) { $0 + $1.photoCount } == 60
                && folders.backup?.destination == backup.path
                && (folders.backup?.subfolder.hasPrefix("Imported on ") ?? false)
                && folders.backup?.photoCount == sources.count,
                "backup_count_is_separate_from_main_checked_photo_count")
            try check(folders.items.contains(where: { $0.path.count > 180 && $0.path.contains("旅行🌄") }),
                "folder_rows_retain_long_unicode_absolute_paths")

            let emptyCursor = try await Backend.call("get_import_destinations", [
                "plan_id": plan.id, "expected_revision": plan.revision, "after": ""
            ])
            try check(emptyCursor["plan_id"] as? Int == plan.id && emptyCursor["revision"] as? Int == plan.revision,
                "backend_accepts_empty_string_page_cursor")
            await folders.readPage(after: "")
            try check(folders.error == nil && folders.items.count == 60,
                "native_page_reader_preserves_empty_cursor_value")

            try await snapshot("import-destination-folders.png",
                ImportDestinationSheet(model: folders).content, NSSize(width: 920, height: 650), root)

            let firstPagePaths = folders.items.map(\.path)
            await folders.nextPage()
            try check(folders.pageNumber == 2 && folders.canGoBack && folders.items.count == 5
                && folders.nextAfter == nil,
                "next_cursor_reads_last_page_and_builds_back_stack")
            await folders.previousPage()
            try check(folders.pageNumber == 1 && folders.items.map(\.path) == firstPagePaths,
                "previous_cursor_restores_prior_page")

            let unchecked = Array(review.items.prefix(2).map(\.id))
            await review.select(false, ids: unchecked)
            let selectionRevision = review.plan!.revision
            await folders.reloadCurrentReview()
            try check(folders.revision == selectionRevision && folders.selectedCount == sources.count - 2
                && folders.items.count == 60 && folders.nextAfter != nil && folders.pageNumber == 1,
                "explicit_reload_reflects_checked_photo_changes_and_resets_cursor")
            try check(folders.backup?.photoCount == sources.count - 2,
                "backup_summary_tracks_the_same_checked_originals")

            let capturedRows = folders.items.map(\.path)
            let capturedRevision = folders.revision
            _ = try await Backend.call("set_import_options", [
                "plan_id": plan.id, "expected_revision": selectionRevision, "skip_duplicates": false
            ])
            await folders.nextPage()
            try check(folders.error?.localizedCaseInsensitiveContains("changed") == true
                && folders.revision == capturedRevision && folders.items.map(\.path) == capturedRows
                && folders.pageNumber == 1,
                "stale_page_rejection_preserves_visible_page_and_cursor")
            await folders.reloadCurrentReview()
            try check(folders.error == nil && folders.revision > capturedRevision
                && folders.pageNumber == 1 && folders.items.count == 60,
                "explicit_reload_rebases_only_after_fresh_review_read")

            await review.load()
            await review.select(false)
            await folders.reloadCurrentReview()
            let recheckIDs = Array(review.items.prefix(3).map(\.id))
            await review.select(true, ids: recheckIDs)
            await folders.reloadCurrentReview()
            try check(folders.selectedCount == recheckIDs.count && folders.items.count == recheckIDs.count
                && folders.items.reduce(0) { $0 + $1.photoCount } == recheckIDs.count
                && folders.backup?.photoCount == recheckIDs.count,
                "checking_photos_updates_main_and_backup_folder_counts_after_reload")
            await review.select(false)
            await folders.reloadCurrentReview()
            try check(folders.selectedCount == 0 && folders.items.isEmpty
                && folders.backup?.photoCount == 0 && folders.nextAfter == nil,
                "empty_selection_returns_no_main_or_backup_folders")
            try check(try FileManager.default.contentsOfDirectory(atPath: destination.path).isEmpty
                && FileManager.default.contentsOfDirectory(atPath: backup.path).isEmpty,
                "destination_preview_does_not_create_main_or_backup_folders")
            try check(try sources.enumerated().allSatisfy {
                try Data(contentsOf: URL(fileURLWithPath: $0.element)) == sourceBytes[$0.offset]
            }, "folder_preview_preserves_every_original_byte")
            folders.invalidate()
            await review.cancel()
            review.invalidate()

            let dateDestination = root.appendingPathComponent("date-grouped-output")
            try FileManager.default.createDirectory(at: dateDestination, withIntermediateDirectories: true)
            let dateReview = ImportReviewModel(sources: Array(fixtures.prefix(2)))
            dateReview.mode = "copy"
            dateReview.destination = dateDestination.path
            dateReview.organization = "date"
            await dateReview.scan()
            let datePlan = dateReview.plan!
            let dateFolders = ImportDestinationModel(planID: datePlan.id, revision: datePlan.revision)
            await dateFolders.loadInitial()
            try check(dateFolders.error == nil && dateFolders.selectedCount == 2
                && dateFolders.items.count == 1 && dateFolders.items[0].relativePath == "Unknown Date"
                && dateFolders.items[0].photoCount == 2,
                "date_organization_groups_missing_capture_dates_without_filesystem_scan")
            try check(try FileManager.default.contentsOfDirectory(atPath: dateDestination.path).isEmpty,
                "date_folder_preview_does_not_create_destination_directories")
            dateFolders.invalidate()
            await dateReview.cancel()
            dateReview.invalidate()

            let flatDestination = root.appendingPathComponent("flat-destination-output")
            try FileManager.default.createDirectory(at: flatDestination, withIntermediateDirectories: true)
            let flatReview = ImportReviewModel(sources: [fixtures[2]])
            flatReview.mode = "copy"
            flatReview.destination = flatDestination.path
            flatReview.organization = "flat"
            await flatReview.scan()
            let flatPlan = flatReview.plan!
            let flatFolders = ImportDestinationModel(planID: flatPlan.id, revision: flatPlan.revision)
            await flatFolders.loadInitial()
            try check(flatFolders.error == nil && flatFolders.items.count == 1
                && flatFolders.items[0].relativePath.isEmpty
                && flatFolders.items[0].path == flatDestination.path
                && flatFolders.items[0].photoCount == 1,
                "flat_organization_renders_empty_relative_path_as_destination_root")
            flatFolders.invalidate()
            await flatReview.cancel()
            flatReview.invalidate()

            let addReview = ImportReviewModel(sources: [fixtures[0]])
            await addReview.scan()
            guard let addPlan = addReview.plan else { throw EngineFailure(message: "Add review did not scan") }
            var rejectedAdd = false
            do {
                _ = try await Backend.call("get_import_destinations", [
                    "plan_id": addPlan.id, "expected_revision": addPlan.revision
                ])
            } catch { rejectedAdd = true }
            try check(rejectedAdd, "destination_folder_endpoint_rejects_add_reviews")
            await addReview.cancel()
            addReview.invalidate()
            try check(try fixtures.map { try Data(contentsOf: URL(fileURLWithPath: $0)) } == originalFixtureBytes,
                "runner_originals_remain_unchanged")

            let receipt: [String: Any] = [
                "ok": true,
                "passed": checks.count,
                "checks": checks,
                "offscreen_screenshots": screenshots,
                "desktop_ui": "NOT_VERIFIED"
            ]
            let data = try JSONSerialization.data(withJSONObject: receipt, options: [.prettyPrinted, .sortedKeys])
            print(String(decoding: data, as: UTF8.self))
            exit(0)
        } catch {
            let receipt: [String: Any] = ["ok": false, "checks": checks, "error": error.localizedDescription,
                "offscreen_screenshots": screenshots, "desktop_ui": "NOT_VERIFIED"]
            let data = (try? JSONSerialization.data(withJSONObject: receipt, options: [.prettyPrinted, .sortedKeys])) ?? Data()
            print(String(decoding: data, as: UTF8.self))
            exit(1)
        }
    }
}
