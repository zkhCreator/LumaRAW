// Purpose: measure warm, same-visible-page thumbnail refresh work after ordinary
// catalog actions. Inputs are generated fixtures and an explicitly disposable
// catalog. Outputs are IPC/callback/publication counts, image identity checks,
// and separately timed operation/cache calls. The settle barrier is not latency.
// No desktop frame-rate claim, original writes, force-validation bypass, or
// test-side callback de-duplication. Run with run_thumbnail_probe.py, not the
// regression runner: this reports measurements without latency thresholds.
import AppKit
import Combine
import Darwin
import Foundation

private struct ThumbnailProbeEvent {
    let method: String
    let elapsedMilliseconds: Double
    let workerSpawned: Bool?
    let returnedThumbnails: Int?
    let failed: Bool
}

private struct ThumbnailProbeSnapshot {
    let events: [ThumbnailProbeEvent]
    let changedCallbacks: Int
    let lastImageIdentities: [Int: ObjectIdentifier]
    let lastErrors: [Int: String]
    let pendingCalls: Int

    func count(_ method: String) -> Int {
        events.reduce(0) { $0 + ($1.method == method ? 1 : 0) }
    }
}

private final class ThumbnailProbeRecorder: @unchecked Sendable {
    private let lock = NSLock()
    private var events: [ThumbnailProbeEvent] = []
    private var changedCallbacks = 0
    private var lastImageIdentities: [Int: ObjectIdentifier] = [:]
    private var lastErrors: [Int: String] = [:]
    private var pendingCalls = 0

    func callStarted() {
        lock.lock(); defer { lock.unlock() }
        pendingCalls += 1
    }

    func callFinished(method: String, elapsedMilliseconds: Double,
                      result: [String: Any]?, failed: Bool) {
        lock.lock(); defer { lock.unlock() }
        pendingCalls = max(0, pendingCalls - 1)
        events.append(ThumbnailProbeEvent(method: method,
            elapsedMilliseconds: elapsedMilliseconds,
            workerSpawned: result?["worker_spawned"] as? Bool,
            returnedThumbnails: (result?["thumbnails"] as? [[String: Any]])?.count,
            failed: failed))
    }

    func published(images: [Int: NSImage], errors: [Int: String]) {
        lock.lock(); defer { lock.unlock() }
        changedCallbacks += 1
        lastImageIdentities = images.mapValues { ObjectIdentifier($0) }
        lastErrors = errors
    }

    func snapshot() -> ThumbnailProbeSnapshot {
        lock.lock(); defer { lock.unlock() }
        return ThumbnailProbeSnapshot(events: events, changedCallbacks: changedCallbacks,
            lastImageIdentities: lastImageIdentities, lastErrors: lastErrors,
            pendingCalls: pendingCalls)
    }
}

private final class ThumbnailProbeCounter: @unchecked Sendable {
    private let lock = NSLock()
    private var value = 0
    func increment() { lock.lock(); value += 1; lock.unlock() }
    func read() -> Int { lock.lock(); defer { lock.unlock() }; return value }
}

@main struct NativeThumbnailRefreshProbe {
    @MainActor static func main() async {
        _ = NSApplication.shared
        let recorder = ThumbnailProbeRecorder()
        let store = Store()
        let objectWillChange = ThumbnailProbeCounter()
        var subscription: AnyCancellable?

        do {
            guard ProcessInfo.processInfo.environment["LUMARAW_PROBE_DISPOSABLE_CATALOG"] == "1",
                  ProcessInfo.processInfo.environment["LUMARAW_CATALOG"] != nil else {
                throw EngineFailure(message: "Set an explicitly disposable LUMARAW_CATALOG and LUMARAW_PROBE_DISPOSABLE_CATALOG=1")
            }
            guard let fixtureValue = ProcessInfo.processInfo.environment["LUMARAW_TEST_FIXTURES"] else {
                throw EngineFailure(message: "Set LUMARAW_TEST_FIXTURES to generated local images")
            }
            let paths = fixtureValue.components(separatedBy: "|").filter { !$0.isEmpty }
            guard !paths.isEmpty, paths.count <= 60 else {
                throw EngineFailure(message: "Provide 1–60 generated images for one bounded visible page")
            }
            let originalBytes = try paths.map { try Data(contentsOf: URL(fileURLWithPath: $0)) }
            let fixtureInfo = zip(paths, originalBytes).map { pair -> [String: Any] in
                let (path, data) = pair
                let dimensions: Any = pngDimensions(data).map { $0 as Any } ?? NSNull()
                return ["file": URL(fileURLWithPath: path).lastPathComponent,
                 "format": URL(fileURLWithPath: path).pathExtension.lowercased(),
                 "dimensions": dimensions]
            }

            // This wrapper delegates every command unchanged. In particular it
            // does not de-duplicate changed callbacks or suppress force requests.
            store.thumbnailRenderer = ThumbnailRenderer(call: { method, params in
                let start = ProcessInfo.processInfo.systemUptime
                recorder.callStarted()
                do {
                    let result = try await Backend.call(method, params)
                    recorder.callFinished(method: method,
                        elapsedMilliseconds: (ProcessInfo.processInfo.systemUptime - start) * 1000,
                        result: result, failed: false)
                    return result
                } catch {
                    recorder.callFinished(method: method,
                        elapsedMilliseconds: (ProcessInfo.processInfo.systemUptime - start) * 1000,
                        result: nil, failed: true)
                    throw error
                }
            }, changed: { [weak store] images, errors in
                recorder.published(images: images, errors: errors)
                // Preserve the real Store callback's two @Published assignments
                // so this measures their actual ObservableObject emissions.
                store?.thumbnails = images
                store?.thumbnailErrors = errors
            })
            subscription = store.objectWillChange.sink { _ in objectWillChange.increment() }

            // Store.start() is deliberately not called. importPaths/finishImport
            // navigate and refresh but do not create Store's periodic 2 s poll.
            await store.importPaths(paths)
            let warmCacheCalls = recorder.snapshot().count("cached_thumbnails")
            await store.refresh()
            _ = try await waitForStablePage(store, recorder: recorder,
                requiringCacheCalls: warmCacheCalls + 1, timeoutSeconds: 90)
            guard !store.photos.isEmpty else { throw EngineFailure(message: "No imported photos became visible") }
            let postWarmupPeakRSS = processMaximumRSSBytes()

            // Prepare the target before timing. The action interval below covers
            // membership mutation/refresh only, not collection construction.
            let collectionReply = try await Backend.call("save_collection", [
                "name": "Thumbnail refresh probe",
                "kind": "regular",
                "rules": [:],
                "match": "all",
                "parent_id": NSNull()
            ])
            guard let collection = LibraryCollection(collectionReply) else {
                throw EngineFailure(message: "Could not create disposable regular collection")
            }

            var measurements: [[String: Any]] = []
            let first = store.photos[0]
            measurements.append(try await measure("collection_membership_add", store: store,
                recorder: recorder, objectWillChange: objectWillChange) {
                    let oldError = store.error
                    await store.changeMembership(collection, action: "add", ids: [first.id])
                    return store.error == oldError
                })

            guard let current = store.photos.first(where: { $0.id == first.id }) else {
                throw EngineFailure(message: "The measured photo left the visible page")
            }
            measurements.append(try await measure("metadata_title_edit", store: store,
                recorder: recorder, objectWillChange: objectWillChange) {
                    await store.saveMetadata(targets: [current],
                        patch: ["title": "Thumbnail refresh probe"])
                })

            let finalBytes = try paths.map { try Data(contentsOf: URL(fileURLWithPath: $0)) }
            guard finalBytes == originalBytes else {
                throw EngineFailure(message: "A generated source image changed during catalog-only workflows")
            }
            subscription?.cancel()
            let report: [String: Any] = [
                "ok": true,
                "scope": "warm same-page refresh after collection add and metadata edit",
                "host": Self.hostInfo(),
                "fixture_images": fixtureInfo,
                "process_max_rss_bytes_after_warmup": postWarmupPeakRSS as Any? ?? NSNull(),
                "process_max_rss_bytes_at_end": processMaximumRSSBytes() as Any? ?? NSNull(),
                "rss_note": "process-lifetime high-water marks; not per-operation memory deltas",
                "store_start_called": false,
                "visible_photo_count": store.photos.count,
                "measurements": measurements,
                "generated_original_bytes_unchanged": true,
                "desktop_frame_rate": "NOT_MEASURED",
                "desktop_interaction": "NOT_VERIFIED",
                "barrier_note": "synchronization_only_ms is excluded from operation/cache latency"
            ]
            let data = try JSONSerialization.data(withJSONObject: report,
                options: [.prettyPrinted, .sortedKeys])
            print(String(data: data, encoding: .utf8)!)
            exit(0)
        } catch {
            subscription?.cancel()
            let report: [String: Any] = ["ok": false, "error": error.localizedDescription,
                "store_error": store.error ?? ""]
            let data = try! JSONSerialization.data(withJSONObject: report,
                options: [.prettyPrinted, .sortedKeys])
            print(String(data: data, encoding: .utf8)!)
            exit(1)
        }
    }

    @MainActor private static func measure(
        _ name: String,
        store: Store,
        recorder: ThumbnailProbeRecorder,
        objectWillChange: ThumbnailProbeCounter,
        action: () async throws -> Bool
    ) async throws -> [String: Any] {
        let before = recorder.snapshot()
        let beforeChangeCount = objectWillChange.read()
        let beforeIDs = store.photos.map(\.id)
        let beforeImages = store.thumbnailRenderer.frames.mapValues { ObjectIdentifier($0.image) }
        let operationStart = ProcessInfo.processInfo.systemUptime
        guard try await action() else { throw EngineFailure(message: "Workflow failed: \(name)") }
        let operationMilliseconds = (ProcessInfo.processInfo.systemUptime - operationStart) * 1000
        let synchronizationMilliseconds = try await waitForStablePage(store, recorder: recorder,
        requiringCacheCalls: before.count("cached_thumbnails") + 1)
        let after = recorder.snapshot()
        let events = Array(after.events.dropFirst(before.events.count))
        let counts = Dictionary(grouping: events, by: \.method).mapValues(\.count)
        let cacheEvents = events.filter { $0.method == "cached_thumbnails" }
        let directThumbnailEvents = events.filter { $0.method == "thumbnail" }
        let afterImages = store.thumbnailRenderer.frames.mapValues { ObjectIdentifier($0.image) }
        let samePage = beforeIDs == store.photos.map(\.id)
        let sameImageObjects = samePage && beforeImages.keys.sorted() == afterImages.keys.sorted() &&
            beforeImages.allSatisfy { afterImages[$0.key] == $0.value }
        let cachedWorkerFlags: [Any] = cacheEvents.map { $0.workerSpawned.map { $0 as Any } ?? NSNull() }
        let directWorkerFlags: [Any] = directThumbnailEvents.map { $0.workerSpawned.map { $0 as Any } ?? NSNull() }

        return [
            "operation": name,
            "operation_elapsed_ms": operationMilliseconds,
            "cached_thumbnails_elapsed_ms": cacheEvents.map(\.elapsedMilliseconds),
            "synchronization_only_ms": synchronizationMilliseconds,
            "thumbnail_ipc_counts": ["cancel_preview": counts["cancel_preview"] ?? 0,
                "cached_thumbnails": counts["cached_thumbnails"] ?? 0,
                "thumbnail": counts["thumbnail"] ?? 0],
            "cached_worker_spawned": cachedWorkerFlags,
            "direct_thumbnail_worker_spawned": directWorkerFlags,
            "renderer_changed_callback_delta": after.changedCallbacks - before.changedCallbacks,
            "store_object_will_change_delta": objectWillChange.read() - beforeChangeCount,
            "same_visible_page": samePage,
            "same_nsimage_objects": sameImageObjects,
            "renderer_errors": after.lastErrors,
            "all_renderer_calls_succeeded": events.allSatisfy { !$0.failed }
        ]
    }

    @MainActor private static func waitForStablePage(
        _ store: Store,
        recorder: ThumbnailProbeRecorder,
        requiringCacheCalls minimumCacheCalls: Int,
        timeoutSeconds: Double = 15
    ) async throws -> Double {
        let start = ProcessInfo.processInfo.systemUptime
        var previousSignature = ""
        var stableSince = ProcessInfo.processInfo.systemUptime
        while ProcessInfo.processInfo.systemUptime - start < timeoutSeconds {
            let snapshot = recorder.snapshot()
            let visible = Set(store.photos.map(\.id))
            let frameIDs = Set(store.thumbnailRenderer.frames.keys)
            let identities = store.thumbnailRenderer.frames.keys.sorted().map {
                "\($0):\(ObjectIdentifier(store.thumbnailRenderer.frames[$0]!.image).hashValue)"
            }.joined(separator: ",")
            let ready = !visible.isEmpty && visible.isSubset(of: frameIDs) &&
                store.thumbnailRenderer.loading.isEmpty && store.thumbnailErrors.isEmpty &&
                !store.loading && !store.rendering && store.photo != nil &&
                snapshot.count("cached_thumbnails") >= minimumCacheCalls && snapshot.pendingCalls == 0
            let signature = "\(snapshot.events.count)|\(snapshot.changedCallbacks)|\(identities)|\(snapshot.lastErrors)"
            if ready {
                if signature != previousSignature {
                    previousSignature = signature
                    stableSince = ProcessInfo.processInfo.systemUptime
                } else if ProcessInfo.processInfo.systemUptime - stableSince >= 0.10 {
                    return (ProcessInfo.processInfo.systemUptime - start) * 1000
                }
            } else {
                previousSignature = ""
                stableSince = ProcessInfo.processInfo.systemUptime
            }
            try await Task.sleep(nanoseconds: 10_000_000)
        }
        throw EngineFailure(message: "Thumbnail IPC/renderer did not reach a stable warm page")
    }

    private static func pngDimensions(_ data: Data) -> [String: Int]? {
        let bytes = Array(data.prefix(24))
        guard bytes.count == 24,
              Array(bytes[0..<8]) == [137, 80, 78, 71, 13, 10, 26, 10] else { return nil }
        func value(_ start: Int) -> Int {
            (Int(bytes[start]) << 24) | (Int(bytes[start + 1]) << 16) |
                (Int(bytes[start + 2]) << 8) | Int(bytes[start + 3])
        }
        return ["width": value(16), "height": value(20)]
    }

    private static func processMaximumRSSBytes() -> UInt64? {
        var usage = rusage()
        guard getrusage(RUSAGE_SELF, &usage) == 0 else { return nil }
        return UInt64(usage.ru_maxrss)
    }

    private static func hostInfo() -> [String: Any] {
        var machine = "unknown"
        var size = 0
        if sysctlbyname("hw.machine", nil, &size, nil, 0) == 0, size > 0 {
            var buffer = [CChar](repeating: 0, count: size)
            if sysctlbyname("hw.machine", &buffer, &size, nil, 0) == 0 {
                machine = buffer.withUnsafeBufferPointer { pointer in
                    guard let base = pointer.baseAddress else { return "unknown" }
                    return String(cString: base)
                }
            }
        }
        return ["macos": ProcessInfo.processInfo.operatingSystemVersionString,
            "machine": machine,
            "processor_count": ProcessInfo.processInfo.processorCount,
            "active_processor_count": ProcessInfo.processInfo.activeProcessorCount]
    }
}
