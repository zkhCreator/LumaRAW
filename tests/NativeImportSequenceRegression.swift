// Purpose: native catalog-counter editing and counter-dependent Copy naming.
// Inputs: generated photographs, an isolated catalog and packaged Backend IPC.
// Outputs: revision, draft, preview and apply assertions plus offscreen Settings
// and counter-editor snapshots. No desktop interaction or acceptance is implied.
import AppKit
import Foundation
import SwiftUI

private func sequenceNumber(_ value: Any?) -> Int64? {
    if let number = value as? NSNumber { return number.int64Value }
    if let value = value as? Int64 { return value }
    if let value = value as? Int { return Int64(value) }
    return nil
}

@main struct NativeImportSequenceRegression {
    @MainActor static func main() async {
        _ = NSApplication.shared
        var checks: [String: Bool] = [:]
        func check(_ value: Bool, _ name: String) throws {
            checks[name] = value
            if !value { throw EngineFailure(message: name) }
        }
        func snapshot<V: View>(_ name: String, _ view: V, _ size: NSSize) async throws {
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
            let output = URL(fileURLWithPath: ProcessInfo.processInfo.environment["LUMARAW_CATALOG"]!)
                .deletingLastPathComponent().appendingPathComponent(name)
            try png.write(to: output)
        }

        do {
            let paths = ProcessInfo.processInfo.environment["LUMARAW_TEST_FIXTURES"]!
                .components(separatedBy: "|")
            let originals = try paths.map { try Data(contentsOf: URL(fileURLWithPath: $0)) }
            let root = URL(fileURLWithPath: ProcessInfo.processInfo.environment["LUMARAW_CATALOG"]!)
                .deletingLastPathComponent()

            let initial = try await Backend.call("get_import_sequence")
            let initialRevision = initial["revision"] as? Int
            try check(initialRevision != nil
                && sequenceNumber(initial["next_import"]) == 1
                && sequenceNumber(initial["next_image"]) == 1,
                "packaged_backend_reads_initial_catalog_counters")

            let editor = ImportSequenceEditor()
            await editor.load()
            try check(editor.loaded && editor.revision == initialRevision
                && editor.nextImport == "1" && editor.nextImage == "1",
                "native_editor_loads_backend_sequence")

            editor.nextImport = "4123"
            editor.nextImage = "5678"
            try check(editor.dirty && editor.canSave, "counter_changes_form_a_valid_draft")
            editor.nextImport = "10000000000"
            try check(!editor.valid && !editor.canSave, "counter_editor_enforces_supported_range")
            editor.nextImport = "4123"

            let staleRevision = editor.revision!
            let concurrent = try await Backend.call("set_import_sequence", [
                "expected_revision": staleRevision,
                "next_import": 7001,
                "next_image": 8001
            ])
            let concurrentRevision = concurrent["revision"] as? Int
            try check(concurrentRevision != nil && concurrentRevision! > staleRevision,
                "backend_accepts_revision_checked_counter_save")
            await editor.save()
            try check(editor.error?.localizedCaseInsensitiveContains("changed") == true
                && editor.revision == staleRevision
                && editor.nextImport == "4123" && editor.nextImage == "5678"
                && editor.dirty,
                "stale_native_save_rejects_without_rebasing_or_losing_draft")

            await editor.reloadCurrentValues()
            try check(editor.revision == concurrentRevision
                && editor.nextImport == "4123" && editor.nextImage == "5678"
                && editor.currentImport == "7001" && editor.currentImage == "8001"
                && editor.reloadedDraft && editor.dirty,
                "explicit_reload_rebases_revision_and_preserves_draft")
            await editor.save()
            let saved = try await Backend.call("get_import_sequence")
            try check(editor.error == nil
                && sequenceNumber(saved["next_import"]) == 4123
                && sequenceNumber(saved["next_image"]) == 5678
                && (saved["revision"] as? Int ?? 0) > (concurrentRevision ?? 0),
                "explicitly_rebased_draft_saves_through_backend")

            let settingsStore = Store()
            try await snapshot("import-sequence-settings.png",
                SettingsView().environmentObject(settingsStore), NSSize(width: 600, height: 620))
            try await snapshot("import-sequence-counter-editor.png",
                CatalogImportSequenceSheet(), NSSize(width: 680, height: 500))

            let destination = root.appendingPathComponent("sequence-output")
            try FileManager.default.createDirectory(at: destination, withIntermediateDirectories: true)
            let review = ImportReviewModel(sources: paths)
            review.mode = "copy"
            review.destination = destination.path
            await review.scan()
            guard let capturedSequence = review.plan?.sequence,
                  let capturedRevision = capturedSequence["revision"] as? Int,
                  let capturedImport = sequenceNumber(capturedSequence["import_number"]),
                  let capturedImage = sequenceNumber(capturedSequence["image_number"]),
                  capturedSequence["frozen"] as? Bool != nil else {
                throw EngineFailure(message: "Copy review did not expose its captured sequence")
            }
            try check(review.plan?.ready == true && capturedRevision == (saved["revision"] as? Int),
                "copy_review_captures_catalog_sequence")

            review.openNaming()
            let naming = review.namingEditor!
            await naming.load()
            try check(naming.ready && naming.kinds.contains("import_number")
                && naming.kinds.contains("image_number"),
                "filename_editor_offers_import_and_image_tokens")
            var importToken = FilenameToken(kind: "import_number")
            importToken.digits = 4
            var separator = FilenameToken(kind: "literal")
            separator.text = "-"
            var secondSeparator = FilenameToken(kind: "literal")
            secondSeparator.text = "-"
            var imageToken = FilenameToken(kind: "image_number")
            imageToken.digits = 5
            naming.enabled = true
            naming.tokens = [importToken, separator, imageToken, secondSeparator, FilenameToken(kind: "filename")]

            let beforePreview = try await Backend.call("get_import_sequence")
            await naming.preview()
            let afterPreview = try await Backend.call("get_import_sequence")
            let previewSequence = naming.sequence
            try check(naming.previewCurrent && naming.previewRows.count == paths.count
                && previewSequence?["revision"] as? Int == capturedRevision
                && sequenceNumber(previewSequence?["import_number"]) == capturedImport
                && sequenceNumber(previewSequence?["image_number"]) == capturedImage
                && (beforePreview["revision"] as? Int) == (afterPreview["revision"] as? Int)
                && sequenceNumber(beforePreview["next_import"]) == sequenceNumber(afterPreview["next_import"])
                && sequenceNumber(beforePreview["next_image"]) == sequenceNumber(afterPreview["next_image"]),
                "naming_preview_uses_sequence_snapshot_without_incrementing")

            for (offset, row) in naming.previewRows.enumerated() {
                guard let source = row["source"] as? String,
                      let destinationPath = row["destination"] as? String else {
                    throw EngineFailure(message: "Counter filename preview is incomplete")
                }
                let ordinal = Int64(row["index"] as? Int ?? offset + 1)
                let imported = String(format: "%04lld", capturedImport)
                let image = String(format: "%05lld", capturedImage + ordinal - 1)
                let sourceURL = URL(fileURLWithPath: source)
                let expected = "\(imported)-\(image)-\(sourceURL.deletingPathExtension().lastPathComponent).\(sourceURL.pathExtension)"
                try check(URL(fileURLWithPath: destinationPath).lastPathComponent == expected,
                    "preview_renders_import_and_image_numbers_\(offset)")
            }
            try check(try FileManager.default.contentsOfDirectory(atPath: destination.path).isEmpty,
                "counter_preview_writes_no_copy_files")
            try check(await naming.save(), "counter_tokens_save_to_ready_copy_review")
            naming.invalidate()
            review.namingEditor = nil
            guard let savedPlanSequence = review.plan?.sequence,
                  let applyRevision = savedPlanSequence["revision"] as? Int else {
                throw EngineFailure(message: "Saved Copy review lost its sequence revision")
            }

            let changedCounters = try await Backend.call("set_import_sequence", [
                "expected_revision": applyRevision,
                "next_import": 9001,
                "next_image": 9101
            ])
            let changedRevision = changedCounters["revision"] as? Int
            try check(changedRevision != nil && changedRevision! > applyRevision,
                "concurrent_counter_change_is_revisioned")

            await review.apply()
            let refreshed = review.plan?.sequence
            let conflict = (review.error ?? "") + " " + (review.plan?.text("error") ?? "")
            try check(review.plan?.state == "ready"
                && conflict.localizedCaseInsensitiveContains("sequence")
                && refreshed?["revision"] as? Int == changedRevision
                && sequenceNumber(refreshed?["import_number"]) == 9001
                && sequenceNumber(refreshed?["image_number"]) == 9101,
                "apply_revision_conflict_returns_ready_review_with_refreshed_sequence")
            try check(try FileManager.default.contentsOfDirectory(atPath: destination.path).isEmpty,
                "sequence_conflict_precedes_copy_writes")
            let refreshedNames = Set(review.items.map { URL(fileURLWithPath: $0.destination).lastPathComponent })
            let expectedRefreshedNames = Set(paths.enumerated().map { offset, path in
                let source = URL(fileURLWithPath: path)
                let importPart = String(format: "%04d", 9001)
                let imagePart = String(format: "%05d", 9101 + offset)
                return "\(importPart)-\(imagePart)-\(source.deletingPathExtension().lastPathComponent).\(source.pathExtension)"
            })
            try check(refreshedNames == expectedRefreshedNames,
                "sequence_conflict_refreshes_counter_dependent_destinations")

            await review.apply()
            try check(review.plan?.state == "applied" && review.plan?.number("imported") == paths.count,
                "review_applies_after_counter_revision_is_explicitly_refreshed")
            let expectedNames = Set(paths.enumerated().map { offset, path in
                let source = URL(fileURLWithPath: path)
                let importPart = String(format: "%04d", 9001)
                let imagePart = String(format: "%05d", 9101 + offset)
                return "\(importPart)-\(imagePart)-\(source.deletingPathExtension().lastPathComponent).\(source.pathExtension)"
            })
            let written = Set(try FileManager.default.contentsOfDirectory(atPath: destination.path))
            try check(written == expectedNames, "published_filenames_use_reserved_import_and_image_values")
            let finalSequence = try await Backend.call("get_import_sequence")
            try check(sequenceNumber(finalSequence["next_import"]) == 9002
                && sequenceNumber(finalSequence["next_image"]) == Int64(9101 + paths.count),
                "successful_copy_reserves_each_counter_once")
            try check(try paths.map { try Data(contentsOf: URL(fileURLWithPath: $0)) } == originals,
                "counter_named_copy_preserves_all_original_bytes")

            review.invalidate()
            print(String(data: try JSONSerialization.data(withJSONObject: [
                "ok": true,
                "passed": checks.count,
                "checks": checks,
                "offscreen_snapshots": ["import-sequence-settings.png", "import-sequence-counter-editor.png"],
                "rendering": "OFFSCREEN_ONLY",
                "desktop_ui": "NOT_VERIFIED"
            ], options: [.prettyPrinted, .sortedKeys]), encoding: .utf8)!)
            exit(0)
        } catch {
            print(String(data: try! JSONSerialization.data(withJSONObject: [
                "ok": false,
                "checks": checks,
                "error": error.localizedDescription,
                "rendering": "OFFSCREEN_ONLY",
                "desktop_ui": "NOT_VERIFIED"
            ], options: [.prettyPrinted, .sortedKeys]), encoding: .utf8)!)
            exit(1)
        }
    }
}
