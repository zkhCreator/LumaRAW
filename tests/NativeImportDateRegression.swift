// Purpose: native Copy date-folder choices, saved preset restoration and real file output.
// Inputs: five EXIF-dated runner photographs, an isolated catalog and Backend IPC.
// Outputs: captured path assertions and offscreen option snapshots. No desktop UI
// interaction or acceptance is implied; the date comes from EXIF civil time.
import AppKit
import Foundation
import SwiftUI

@main struct NativeImportDateRegression {
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
                throw EngineFailure(message: "No offscreen PNG for \(name)")
            }
            host.cacheDisplay(in: host.bounds, to: bitmap)
            guard let rendered = bitmap.representation(using: .png, properties: [:]) else {
                throw EngineFailure(message: "No rendered offscreen PNG for \(name)")
            }
            try rendered.write(to: root.appendingPathComponent(name))
            screenshots.append(name)
        }
        func expectedFolder(_ destination: URL, _ format: String) -> URL {
            switch format {
            case "year_month_day":
                return destination.appendingPathComponent("2026").appendingPathComponent("09").appendingPathComponent("28")
            case "date":
                return destination.appendingPathComponent("2026-09-28")
            default:
                return destination.appendingPathComponent("2026").appendingPathComponent("2026-09-28")
            }
        }

        do {
            let fixtures = ProcessInfo.processInfo.environment["LUMARAW_TEST_FIXTURES"]!
                .components(separatedBy: "|")
            try check(fixtures.count == 5, "runner_supplies_five_EXIF_date_fixtures")
            let originals = try fixtures.map { try Data(contentsOf: URL(fileURLWithPath: $0)) }
            let root = URL(fileURLWithPath: ProcessInfo.processInfo.environment["LUMARAW_CATALOG"]!)
                .deletingLastPathComponent()
            let formats = ["year_date", "year_month_day", "date"]

            // Older catalog presets may omit this option. Native restoration keeps
            // the established year/date layout when reading such a choice.
            let legacy = ImportReviewModel()
            let legacyChoice: [String: Any] = [
                "id": "legacy-date-preset",
                "revision": 1,
                "name": "Legacy Date Import",
                "options": [
                    "mode": "copy",
                    "organization": "date",
                    "destination": root.appendingPathComponent("legacy-date-output").path
                ] as [String: Any]
            ]
            try check(await legacy.usePreset(legacyChoice)
                && legacy.organization == "date" && legacy.dateFormat == "year_date",
                "missing_preset_date_format_restores_legacy_layout")
            legacy.invalidate()

            for format in formats {
                let sourceFolder = root.appendingPathComponent("date-sources-\(format)")
                let destination = root.appendingPathComponent("date-output-\(format)")
                try FileManager.default.createDirectory(at: sourceFolder, withIntermediateDirectories: true)
                try FileManager.default.createDirectory(at: destination, withIntermediateDirectories: true)
                var sources: [String] = []
                for (index, fixture) in fixtures.enumerated() {
                    let source = sourceFolder.appendingPathComponent("\(format)-photo-\(index).png")
                    try FileManager.default.copyItem(at: URL(fileURLWithPath: fixture), to: source)
                    sources.append(source.path)
                }

                let review = ImportReviewModel(sources: sources)
                review.mode = "copy"
                review.destination = destination.path
                review.organization = "date"
                review.dateFormat = format
                let screenshot = "import-date-format-\(format).png"
                try await snapshot(screenshot, ImportReviewSheet(model: review).content,
                    NSSize(width: 1060, height: 840), root)

                await review.scan()
                let expectedPaths = Set(sources.map {
                    expectedFolder(destination, format).appendingPathComponent(URL(fileURLWithPath: $0).lastPathComponent).path
                })
                try check(review.plan?.ready == true && review.plan?.copy["organization"] as? String == "date"
                    && review.plan?.copy["date_format"] as? String == format,
                    "scan_captures_\(format)_date_folder_option")
                try check(review.items.count == sources.count && Set(review.items.map(\.destination)) == expectedPaths,
                    "preview_uses_EXIF_civil_date_for_\(format)")
                try check(try FileManager.default.contentsOfDirectory(atPath: destination.path).isEmpty,
                    "preview_does_not_create_\(format)_date_folders")

                review.openPresets()
                let saver = review.presetEditor!
                await saver.browse()
                saver.name = "Capture Date \(format)"
                await saver.save()
                guard let saved = saver.selected,
                      let presetID = saved["id"] as? String,
                      let presetRevision = saved["revision"] as? Int else {
                    throw EngineFailure(message: "Date preset was not returned after save for \(format)")
                }
                try check((saved["options"] as? [String: Any])?["date_format"] as? String == format,
                    "preset_save_roundtrips_\(format)_date_format")
                let reread = try await Backend.call("get_import_preset", [
                    "preset_id": presetID,
                    "expected_revision": presetRevision
                ])
                try check((reread["options"] as? [String: Any])?["date_format"] as? String == format,
                    "packaged_backend_reads_\(format)_preset_option")
                saver.invalidate()
                review.presetEditor = nil
                await review.cancel()
                review.invalidate()

                let restored = ImportReviewModel(sources: sources)
                restored.openPresets()
                let picker = restored.presetEditor!
                await picker.browse()
                guard let row = picker.rows.first(where: { $0["id"] as? String == presetID }) else {
                    throw EngineFailure(message: "Saved date preset not found for \(format)")
                }
                await picker.choose(row)
                try check(await picker.use() && restored.organization == "date" && restored.dateFormat == format,
                    "native_preset_restore_selects_\(format)_date_format")
                picker.invalidate()
                restored.presetEditor = nil
                await restored.scan()
                try check(restored.plan?.ready == true && restored.plan?.copy["date_format"] as? String == format
                    && Set(restored.items.map(\.destination)) == expectedPaths,
                    "preset_scan_reuses_\(format)_captured_format")

                await restored.apply()
                try check(restored.plan?.state == "applied" && restored.plan?.number("imported") == sources.count,
                    "copy_apply_completes_\(format)_date_layout")
                for (index, path) in sources.enumerated() {
                    let copied = expectedFolder(destination, format)
                        .appendingPathComponent(URL(fileURLWithPath: path).lastPathComponent)
                    try check(FileManager.default.fileExists(atPath: copied.path),
                        "copy_creates_\(format)_date_destination_\(index)")
                    try check(try Data(contentsOf: copied) == originals[index],
                        "copy_preserves_\(format)_source_bytes_\(index)")
                    try check(try Data(contentsOf: URL(fileURLWithPath: path)) == originals[index],
                        "copy_keeps_\(format)_source_unchanged_\(index)")
                }
                restored.invalidate()
            }

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
