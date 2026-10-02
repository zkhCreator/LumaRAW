// Purpose: verify culling-key mappings, guarded focus advance and overlapping write receipts.
// Inputs: five generated originals, real catalog mutations and local reply gates.
// Outputs: mapping, bounded-page, stale-focus and accepted-versus-failed-write receipts.
// This exercises native Store/backend state only; desktop keyboard dispatch is not verified.
import AppKit
import Foundation

private actor CullingReplyGate {
    private var entered = false
    private var released = false
    private var continuation: CheckedContinuation<Void, Never>?

    func holdAfterReply() async {
        entered = true
        guard !released else { return }
        await withCheckedContinuation { continuation = $0 }
    }

    func isEntered() -> Bool { entered }

    func release() {
        released = true
        continuation?.resume()
        continuation = nil
    }
}

@MainActor private final class CullingCompletionLatch {
    private(set) var completed = false

    func signal() {
        completed = true
    }

    func wait() async throws {
        for _ in 0..<500 {
            if completed { return }
            try await Task.sleep(nanoseconds: 20_000_000)
        }
        throw EngineFailure(message: "Older culling mutation did not finish after its reply was released")
    }
}

@main struct NativeCullingShiftRegression {
    @MainActor static func main() async {
        _ = NSApplication.shared
        let s = Store()
        var checks: [String: Bool] = [:]

        func check(_ value: Bool, _ name: String) throws {
            checks[name] = value
            if !value { throw EngineFailure(message: name) }
        }

        func waitUntil(_ name: String, _ predicate: () -> Bool) async throws {
            for _ in 0..<500 {
                if predicate() { return }
                try await Task.sleep(nanoseconds: 20_000_000)
            }
            throw EngineFailure(message: "Timed out: \(name); selected=\(s.selected.map(String.init) ?? "nil"), " +
                "photo=\(s.photo.map { String($0.id) } ?? "nil"), offset=\(s.offset), total=\(s.total), " +
                "visible=\(s.photos.map(\.id)), error=\(s.error ?? "no error")")
        }

        func waitForPage(total: Int, ids: Set<Int>? = nil, offset: Int? = nil,
                         afterPageGeneration: Int? = nil, name: String) async throws {
            try await waitUntil(name) {
                s.total == total && (offset.map { s.offset == $0 } ?? true) &&
                    (ids.map { Set(s.photos.map(\.id)) == $0 } ?? true) &&
                    (afterPageGeneration.map { s.cullingPageGeneration > $0 } ?? true) &&
                    !s.browsing && !s.loading
            }
        }

        func waitForFocus(_ id: Int, name: String) async throws {
            try await waitUntil(name) {
                s.selected == id && s.photo?.id == id && !s.loading && !s.browsing
            }
        }

        func waitForMutation(_ id: Int, rating: Int? = nil, flag: Int? = nil,
                             label: String? = nil, name: String) async throws {
            try await waitUntil(name) {
                guard let row = s.photos.first(where: { $0.id == id }),
                      s.message.hasPrefix("Updated "), s.error == nil, !s.browsing else { return false }
                if let rating, row.rating != rating { return false }
                if let flag, row.flag != flag { return false }
                if let label, row.colorLabel != label { return false }
                return true
            }
        }

        func waitForGate(_ gate: CullingReplyGate) async throws {
            for _ in 0..<500 {
                if await gate.isEntered() { return }
                try await Task.sleep(nanoseconds: 20_000_000)
            }
            await gate.release()
            throw EngineFailure(message: "Mutation or page read did not reach its reply gate")
        }

        func readPhoto(_ id: Int) async throws -> Photo {
            guard let photo = Photo(try await Backend.call("get_photo", ["photo_id": id])) else {
                throw EngineFailure(message: "Photo \(id) disappeared")
            }
            return photo
        }

        func sameMutation(_ actual: CullingShiftMutation, _ expected: CullingShiftMutation) -> Bool {
            switch (actual, expected) {
            case let (.rating(a), .rating(b)): return a == b
            case let (.flag(a), .flag(b)): return a == b
            case let (.colorLabel(a), .colorLabel(b)): return a == b
            default: return false
            }
        }

        func verifyMappedAction(_ key: String, shifted: Bool, mutation: CullingShiftMutation,
                                advances: Bool, refreshesMetadata: Bool, name: String) throws {
            guard let action = CullingShortcutMapper.action(for: key, shifted: shifted) else {
                throw EngineFailure(message: "Missing culling mapping for \(key)")
            }
            try check(sameMutation(action.mutation, mutation) &&
                      action.advanceAfterSuccess == advances &&
                      action.refreshAfterMetadataMutation == refreshesMetadata, name)
        }

        func focus(_ id: Int, selection: Set<Int>? = nil, view: LibraryViewMode = .grid) async throws {
            guard s.photos.contains(where: { $0.id == id }) else {
                throw EngineFailure(message: "Cannot focus photo \(id) outside the loaded page")
            }
            s.workspace = "library"
            s.develop = false
            s.libraryView = view
            s.selected = id
            s.selection = selection ?? [id]
            s.clearPhoto()
            s.choose(id)
            try await waitForFocus(id, name: "photo_\(id)_becomes_active")
        }

        func apply(_ mutation: CullingShiftMutation, advance: Bool = false,
                   refreshMetadata: Bool = false, call: CullingCommandCall? = nil,
                   pageCall: CullingCommandCall? = nil,
                   completion: (@MainActor () -> Void)? = nil, name: String) throws {
            s.message = ""
            s.error = nil
            try check(s.applyCullingShortcut(mutation, advanceAfterSuccess: advance,
                refreshAfterMetadataMutation: refreshMetadata, call: call, pageCall: pageCall,
                completion: completion), name)
        }

        func seedRatings(_ ids: [Int], _ values: [Int]) async throws {
            guard ids.count == values.count else { throw EngineFailure(message: "Rating seed mismatch") }
            for (id, value) in zip(ids, values) {
                _ = try await Backend.call("rate_photos", ["photo_ids": [id], "rating": value])
            }
        }

        func seedFlags(_ ids: [Int], value: Int) async throws {
            _ = try await Backend.call("rate_photos", ["photo_ids": ids, "flag": value])
        }

        func rateAll(_ ids: [Int], value: Int) async throws {
            for start in stride(from: 0, to: ids.count, by: 60) {
                let end = min(start + 60, ids.count)
                _ = try await Backend.call("rate_photos", ["photo_ids": Array(ids[start..<end]), "rating": value])
            }
        }

        func enterAll() async throws {
            s.librarySort = "imported"
            s.sortDescending = true
            await s.openLibraryMode("all", clearFilters: true)
            try await waitUntil("all_mode_refreshes") { !s.browsing && s.mode == "all" && s.collectionID == nil }
        }

        do {
            let keyMappings: [(String, CullingShiftMutation)] = [
                ("p", .flag(1)), ("x", .flag(-1)), ("u", .flag(0)),
                ("6", .colorLabel("red")), ("7", .colorLabel("yellow")),
                ("8", .colorLabel("green")), ("9", .colorLabel("blue")),
            ]
            for value in 0...5 {
                let key = String(value)
                try verifyMappedAction(key, shifted: true, mutation: .rating(value), advances: true,
                                       refreshesMetadata: false, name: "shift_\(value)_maps_to_rating_and_advance")
                try verifyMappedAction(key, shifted: false, mutation: .rating(value), advances: false,
                                       refreshesMetadata: false, name: "unshifted_\(value)_maps_without_advance")
            }
            for (key, mutation) in keyMappings {
                try verifyMappedAction(key, shifted: true, mutation: mutation, advances: true,
                                       refreshesMetadata: false, name: "shift_\(key)_maps_to_culling_action")
                try verifyMappedAction(key.uppercased(), shifted: false, mutation: mutation, advances: false,
                                       refreshesMetadata: { if case .colorLabel = mutation { return true }; return false }(),
                                       name: "unshifted_\(key)_maps_without_advance")
            }
            let unsupportedShifted = CullingShortcutMapper.action(for: "a", shifted: true)
            let unsupportedUnshifted = CullingShortcutMapper.action(for: "b", shifted: false)
            try check((unsupportedShifted.map { _ in false } ?? true) &&
                      (unsupportedUnshifted.map { _ in false } ?? true),
                      "unsupported_culling_keys_are_not_mapped")

            guard let fixtureValue = ProcessInfo.processInfo.environment["LUMARAW_TEST_FIXTURES"] else {
                throw EngineFailure(message: "Missing generated photo fixtures")
            }
            let paths = fixtureValue.components(separatedBy: "|")
            guard paths.count == 5 else {
                throw EngineFailure(message: "This regression requires five generated photo fixtures")
            }
            let originalBytes = try paths.map { try Data(contentsOf: URL(fileURLWithPath: $0)) }
            await s.importPaths(paths)
            let listing = try await Backend.call("list_photos", ["stacked": false])
            let ids = (listing["photos"] as? [[String: Any]] ?? []).compactMap { $0["id"] as? Int }
            try check(ids.count == 5, "five_generated_photos_imported")
            try await enterAll()
            try await waitForPage(total: 5, ids: Set(ids), offset: 0, name: "initial_five_photo_page_loaded")

            // Exercise the same mutation calls the key mapper produces.
            let first = s.photos[0].id
            try await focus(first)
            let unshiftedRating = CullingShortcutMapper.action(for: "3", shifted: false)!
            try apply(unshiftedRating.mutation, advance: unshiftedRating.advanceAfterSuccess,
                      refreshMetadata: unshiftedRating.refreshAfterMetadataMutation, name: "rating_shortcut_is_admitted")
            try await waitForMutation(first, rating: 3, name: "rating_shortcut_updates_catalog_and_native_page")
            let unshiftedPick = CullingShortcutMapper.action(for: "p", shifted: false)!
            try apply(unshiftedPick.mutation, advance: unshiftedPick.advanceAfterSuccess,
                      refreshMetadata: unshiftedPick.refreshAfterMetadataMutation, name: "pick_shortcut_is_admitted")
            try await waitForMutation(first, flag: 1, name: "pick_shortcut_updates_active_photo")
            let unshiftedReject = CullingShortcutMapper.action(for: "x", shifted: false)!
            try apply(unshiftedReject.mutation, advance: unshiftedReject.advanceAfterSuccess,
                      refreshMetadata: unshiftedReject.refreshAfterMetadataMutation, name: "reject_shortcut_is_admitted")
            try await waitForMutation(first, flag: -1, name: "reject_shortcut_updates_active_photo")
            let unshiftedClear = CullingShortcutMapper.action(for: "u", shifted: false)!
            try apply(unshiftedClear.mutation, advance: unshiftedClear.advanceAfterSuccess,
                      refreshMetadata: unshiftedClear.refreshAfterMetadataMutation, name: "clear_flag_shortcut_is_admitted")
            try await waitForMutation(first, flag: 0, name: "clear_flag_shortcut_updates_active_photo")
            for key in ["6", "7", "8", "9"] {
                let action = CullingShortcutMapper.action(for: key, shifted: false)!
                let expected: String
                switch action.mutation {
                case .colorLabel(let label): expected = label
                default: throw EngineFailure(message: "Unshifted label key did not map to a label")
                }
                try apply(action.mutation, advance: action.advanceAfterSuccess,
                          refreshMetadata: action.refreshAfterMetadataMutation,
                          name: "label_key_\(key)_is_admitted")
                try await waitForMutation(first, label: expected,
                                          name: "label_key_\(key)_updates_active_photo")
            }
            let actualKeyTarget = try await readPhoto(first)
            try check(actualKeyTarget.rating == 3 && actualKeyTarget.flag == 0 &&
                      actualKeyTarget.colorLabel == "blue",
                      "mapped_catalog_actions_persist_expected_values")

            // Grid batches requery when a changed rating participates in the active filter/sort,
            // while retaining active focus and every captured row that remains visible.
            try await enterAll()
            try await seedRatings(ids, [1, 2, 3, 4, 5])
            s.librarySort = "rating"
            s.sortDescending = true
            s.libraryFilters = ["rating_min": 3]
            await s.refresh()
            try await waitForPage(total: 3, offset: 0, name: "filtered_rating_batch_page_loaded")
            let batchIDs = Array(s.photos.prefix(2).map(\.id))
            guard let batchActive = batchIDs.first else { throw EngineFailure(message: "Missing batch photos") }
            let batchPageIDs = Set(s.photos.map(\.id))
            try await focus(batchActive, selection: Set(batchIDs))
            let batchPageGeneration = s.cullingPageGeneration
            try apply(.rating(4), advance: true, name: "grid_batch_shortcut_is_admitted")
            try await waitForPage(total: 3, ids: batchPageIDs, offset: 0,
                                  afterPageGeneration: batchPageGeneration,
                                  name: "grid_batch_requeries_filtered_sorted_page")
            try await waitUntil("both_grid_batch_ratings_saved") {
                batchIDs.allSatisfy { id in s.photos.first(where: { $0.id == id })?.rating == 4 } &&
                    s.message == "Updated 2 photos" && s.selected == batchActive && s.selection == Set(batchIDs)
            }
            let firstBatchRow = try await readPhoto(batchIDs[0])
            let secondBatchRow = try await readPhoto(batchIDs[1])
            try check(firstBatchRow.rating == 4 && secondBatchRow.rating == 4 && s.selected == batchActive &&
                      s.selection == Set(batchIDs) && Set(s.photos.map(\.id)) == batchPageIDs,
                      "filtered_grid_batch_refresh_keeps_visible_selection_and_active_focus")

            // One-photo Grid and Loupe actions advance to the next still-loaded row; they never wrap.
            try await enterAll()
            let gridOrder = s.photos.map(\.id)
            guard gridOrder.count >= 3 else { throw EngineFailure(message: "Need three loaded photos") }
            try await focus(gridOrder[0])
            try apply(.rating(2), advance: true, name: "single_grid_culling_action_is_admitted")
            try await waitForFocus(gridOrder[1], name: "grid_single_action_advances_once")
            try check(s.selected == gridOrder[1], "grid_advances_to_next_loaded_photo")

            let loupeOrder = s.photos.map(\.id)
            let loupeActive = loupeOrder[0]
            let loupeOther = loupeOrder[1]
            let otherRatingBefore = try await readPhoto(loupeOther).rating
            try await focus(loupeActive, selection: Set([loupeActive, loupeOther]), view: .loupe)
            try apply(.rating(5), advance: true, name: "loupe_active_action_is_admitted")
            try await waitForFocus(loupeOrder[1], name: "loupe_active_action_advances_once")
            let loupeActiveAfter = try await readPhoto(loupeActive)
            let loupeOtherAfter = try await readPhoto(loupeOther)
            try check(loupeActiveAfter.rating == 5 && loupeOtherAfter.rating == otherRatingBefore,
                      "loupe_uses_active_photo_not_grid_selection")

            try await enterAll()
            let noWrapOrder = s.photos.map(\.id)
            guard let last = noWrapOrder.last else { throw EngineFailure(message: "Missing last row") }
            try await focus(last)
            try apply(.flag(1), advance: true, name: "last_grid_action_is_admitted")
            try await waitForMutation(last, flag: 1, name: "last_grid_action_finishes")
            try check(s.selected == last, "advance_does_not_wrap_past_last_loaded_photo")

            // Compare and Survey keep active-photo scope and never use Shift culling to advance.
            try await enterAll()
            let reviewIDs = Array(s.photos.prefix(3).map(\.id))
            guard reviewIDs.count == 3 else { throw EngineFailure(message: "Need review fixture rows") }
            let compareActive = reviewIDs[0]
            try await focus(compareActive, selection: Set(reviewIDs.prefix(2)))
            await s.switchLibraryView(.compare)
            try await waitUntil("compare_view_started") { s.libraryView == .compare && s.selected == compareActive && !s.browsing }
            let compareOtherBefore = try await readPhoto(reviewIDs[1]).flag
            try apply(.flag(-1), advance: true, name: "compare_shift_action_is_admitted")
            try await waitForMutation(compareActive, flag: -1, name: "compare_active_flag_saved")
            let compareOtherAfter = try await readPhoto(reviewIDs[1]).flag
            try check(s.libraryView == .compare && s.selected == compareActive &&
                      compareOtherAfter == compareOtherBefore,
                      "compare_mutates_active_photo_without_advancing_or_batching")
            await s.switchLibraryView(.survey)
            try await waitUntil("survey_view_started") { s.libraryView == .survey && !s.browsing }
            let surveyActive = s.selected ?? reviewIDs[0]
            let surveyOther = reviewIDs.first(where: { $0 != surveyActive })!
            let surveyOtherBefore = try await readPhoto(surveyOther).colorLabel
            try apply(.colorLabel("yellow"), advance: true, refreshMetadata: true,
                      name: "survey_shift_action_is_admitted")
            try await waitForMutation(surveyActive, label: "yellow", name: "survey_active_label_saved")
            let surveyOtherAfter = try await readPhoto(surveyOther)
            try check(s.libraryView == .survey && s.selected == surveyActive &&
                      surveyOtherAfter.colorLabel == surveyOtherBefore,
                      "survey_mutates_active_photo_without_advancing_or_batching")

            // Failed writes never advance or alter the catalog value.
            try await enterAll()
            let failureOrder = s.photos.map(\.id)
            let failureActive = failureOrder[0]
            let failureNext = failureOrder[1]
            try await focus(failureActive)
            let ratingBeforeFailure = try await readPhoto(failureActive).rating
            try apply(.rating(1), advance: true, call: { method, _ in
                throw EngineFailure(message: "controlled culling mutation failure for \(method)")
            }, name: "failed_mutation_action_is_admitted_once")
            try await waitUntil("failed_mutation_reports_error") { s.error?.contains("controlled culling mutation failure") == true }
            let failedPhotoAfter = try await readPhoto(failureActive)
            try check(s.selected == failureActive && s.selected != failureNext &&
                      failedPhotoAfter.rating == ratingBeforeFailure,
                      "failed_mutation_preserves_focus_and_catalog")

            // A later failed same-field attempt has no catalog write, so it must not
            // permanently suppress an older backend-acknowledged rating reply.
            try await enterAll()
            let failedNewerOrder = s.photos.map(\.id)
            let failedNewerPhoto = failedNewerOrder[0]
            try await focus(failedNewerPhoto)
            let ratingBaselineAccepted = await s.ratePhotos([failedNewerPhoto], patch: ["rating": 0])
            try check(ratingBaselineAccepted &&
                      s.photos.first(where: { $0.id == failedNewerPhoto })?.rating == 0 &&
                      s.photo?.id == failedNewerPhoto && s.photo?.rating == 0,
                      "rating_failure_case_starts_from_a_distinct_catalog_value")
            let oldRatingGate = CullingReplyGate()
            let oldRatingCompletion = CullingCompletionLatch()
            try apply(.rating(2), advance: true, call: { method, params in
                let reply = try await Backend.call(method, params)
                if method == "rate_photos" { await oldRatingGate.holdAfterReply() }
                return reply
            }, completion: { oldRatingCompletion.signal() },
               name: "older_rating_ack_is_held_after_catalog_commit")
            try await waitForGate(oldRatingGate)
            let newerRatingFailure = "controlled newer rating failure"
            let failedRatingCompletion = CullingCompletionLatch()
            try apply(.rating(4), call: { _, _ in
                throw EngineFailure(message: newerRatingFailure)
            }, completion: { failedRatingCompletion.signal() },
               name: "newer_rating_failure_is_admitted")
            try await failedRatingCompletion.wait()
            let ratingAfterNewerFailure = try await readPhoto(failedNewerPhoto)
            try check(ratingAfterNewerFailure.rating == 2 &&
                      s.error?.contains(newerRatingFailure) == true && s.selected == failedNewerPhoto,
                      "newer_rating_failure_is_reported_without_catalog_write")
            await oldRatingGate.release()
            try await oldRatingCompletion.wait()
            let recoveredRatingCatalog = try await readPhoto(failedNewerPhoto)
            try check(recoveredRatingCatalog.rating == 2 &&
                      s.photos.first(where: { $0.id == failedNewerPhoto })?.rating == 2 &&
                      s.photo?.id == failedNewerPhoto && s.photo?.rating == 2 &&
                      s.selected == failedNewerPhoto && s.selection == [failedNewerPhoto] &&
                      s.error?.contains(newerRatingFailure) == true && !s.loading && !s.browsing,
                      "older_accepted_rating_is_adopted_after_newer_failure_without_clearing_error")

            // If the newer failure is still pending when the old acknowledgment arrives,
            // adopt the committed old value; the later failure must retain its own error.
            let pendingFailurePhoto = failedNewerPhoto
            let pendingOldRatingGate = CullingReplyGate()
            let pendingOldRatingCompletion = CullingCompletionLatch()
            try apply(.rating(3), advance: true, call: { method, params in
                let reply = try await Backend.call(method, params)
                if method == "rate_photos" { await pendingOldRatingGate.holdAfterReply() }
                return reply
            }, completion: { pendingOldRatingCompletion.signal() },
               name: "old_rating_reply_waits_for_failure_order_case")
            try await waitForGate(pendingOldRatingGate)
            let pendingFailureGate = CullingReplyGate()
            let pendingFailureCompletion = CullingCompletionLatch()
            try apply(.rating(4), call: { _, _ in
                await pendingFailureGate.holdAfterReply()
                throw EngineFailure(message: "controlled delayed rating failure")
            }, completion: { pendingFailureCompletion.signal() },
               name: "newer_rating_failure_is_held_before_return")
            try await waitForGate(pendingFailureGate)
            await pendingOldRatingGate.release()
            try await pendingOldRatingCompletion.wait()
            try check(s.photos.first(where: { $0.id == pendingFailurePhoto })?.rating == 3 &&
                      s.photo?.id == pendingFailurePhoto && s.photo?.rating == 3 && s.error == nil &&
                      s.selected == pendingFailurePhoto,
                      "old_rating_ack_is_adopted_while_newer_failure_is_still_pending")
            await pendingFailureGate.release()
            try await pendingFailureCompletion.wait()
            let delayedFailureCatalog = try await readPhoto(pendingFailurePhoto)
            try check(delayedFailureCatalog.rating == 3 &&
                      s.photos.first(where: { $0.id == pendingFailurePhoto })?.rating == 3 &&
                      s.photo?.rating == 3 && s.selected == pendingFailurePhoto &&
                      s.error?.contains("controlled delayed rating failure") == true &&
                      !s.loading && !s.browsing,
                      "later_rating_failure_preserves_old_acknowledged_value_and_reports_error")

            // A failed middle attempt cannot let an even older reply replace a third
            // accepted same-field mutation that completes before that old reply returns.
            let thirdWritePhoto = failedNewerPhoto
            let lateOldGate = CullingReplyGate()
            let lateOldCompletion = CullingCompletionLatch()
            try apply(.rating(2), advance: true, call: { method, params in
                let reply = try await Backend.call(method, params)
                if method == "rate_photos" { await lateOldGate.holdAfterReply() }
                return reply
            }, completion: { lateOldCompletion.signal() },
               name: "old_rating_reply_is_delayed_across_failed_middle_attempt")
            try await waitForGate(lateOldGate)
            let middleFailureCompletion = CullingCompletionLatch()
            try apply(.rating(4), call: { _, _ in
                throw EngineFailure(message: "controlled middle rating failure")
            }, completion: { middleFailureCompletion.signal() },
               name: "middle_rating_attempt_fails_without_writing")
            try await middleFailureCompletion.wait()
            try check(s.error?.contains("controlled middle rating failure") == true,
                      "middle_failed_rating_is_visible_before_third_success")
            let newestRatingGate = CullingReplyGate()
            let newestRatingCompletion = CullingCompletionLatch()
            try apply(.rating(5), call: { method, params in
                let reply = try await Backend.call(method, params)
                if method == "rate_photos" { await newestRatingGate.holdAfterReply() }
                return reply
            }, completion: { newestRatingCompletion.signal() },
               name: "third_rating_write_is_accepted_and_held")
            try await waitForGate(newestRatingGate)
            await newestRatingGate.release()
            try await newestRatingCompletion.wait()
            let thirdSuccessMessage = s.message
            try check(s.photos.first(where: { $0.id == thirdWritePhoto })?.rating == 5,
                      "third_rating_success_is_adopted_before_old_reply")
            await lateOldGate.release()
            try await lateOldCompletion.wait()
            let thirdSuccessCatalog = try await readPhoto(thirdWritePhoto)
            try check(thirdSuccessCatalog.rating == 5 &&
                      s.photos.first(where: { $0.id == thirdWritePhoto })?.rating == 5 &&
                      s.photo?.id == thirdWritePhoto && s.photo?.rating == 5 &&
                      s.selected == thirdWritePhoto && s.selection == [thirdWritePhoto] &&
                      s.message == thirdSuccessMessage && !s.loading && !s.browsing,
                      "late_old_rating_reply_cannot_overwrite_third_accepted_success")

            // Metadata color labels use the same acknowledgment-order rules as ratings.
            let metadataFailurePhoto = failedNewerPhoto
            let metadataBaselineTarget = s.photos.first(where: { $0.id == metadataFailurePhoto })!
            let colorBaselineAccepted = await s.saveMetadata(
                targets: [metadataBaselineTarget], patch: ["color_label": "none"], refreshAfter: false
            )
            try check(colorBaselineAccepted &&
                      s.photos.first(where: { $0.id == metadataFailurePhoto })?.colorLabel == "none" &&
                      s.photo?.id == metadataFailurePhoto && s.photo?.colorLabel == "none",
                      "color_failure_case_starts_from_none")
            let oldColorGate = CullingReplyGate()
            let oldColorCompletion = CullingCompletionLatch()
            try apply(.colorLabel("red"), advance: true, call: { method, params in
                let reply = try await Backend.call(method, params)
                if method == "edit_metadata" { await oldColorGate.holdAfterReply() }
                return reply
            }, completion: { oldColorCompletion.signal() },
               name: "older_color_label_ack_is_held_after_catalog_commit")
            try await waitForGate(oldColorGate)
            let colorFailureText = "controlled newer color failure"
            let failedColorCompletion = CullingCompletionLatch()
            try apply(.colorLabel("blue"), call: { _, _ in
                throw EngineFailure(message: colorFailureText)
            }, completion: { failedColorCompletion.signal() },
               name: "newer_color_label_failure_is_admitted")
            try await failedColorCompletion.wait()
            let colorAfterNewerFailure = try await readPhoto(metadataFailurePhoto)
            try check(colorAfterNewerFailure.colorLabel == "red" &&
                      s.error?.contains(colorFailureText) == true,
                      "newer_color_failure_does_not_write_over_older_catalog_ack")
            await oldColorGate.release()
            try await oldColorCompletion.wait()
            let recoveredColorCatalog = try await readPhoto(metadataFailurePhoto)
            try check(recoveredColorCatalog.colorLabel == "red" &&
                      s.photos.first(where: { $0.id == metadataFailurePhoto })?.colorLabel == "red" &&
                      s.photo?.id == metadataFailurePhoto && s.photo?.colorLabel == "red" &&
                      s.error?.contains(colorFailureText) == true && !s.loading && !s.browsing,
                      "older_accepted_color_is_adopted_after_newer_failure_without_clearing_error")

            let pendingColorPhoto = metadataFailurePhoto
            let pendingOldColorGate = CullingReplyGate()
            let pendingOldColorCompletion = CullingCompletionLatch()
            try apply(.colorLabel("green"), advance: true, call: { method, params in
                let reply = try await Backend.call(method, params)
                if method == "edit_metadata" { await pendingOldColorGate.holdAfterReply() }
                return reply
            }, completion: { pendingOldColorCompletion.signal() },
               name: "old_color_label_reply_waits_for_failure_order_case")
            try await waitForGate(pendingOldColorGate)
            let pendingColorFailureGate = CullingReplyGate()
            let pendingColorFailureCompletion = CullingCompletionLatch()
            try apply(.colorLabel("purple"), call: { _, _ in
                await pendingColorFailureGate.holdAfterReply()
                throw EngineFailure(message: "controlled delayed color failure")
            }, completion: { pendingColorFailureCompletion.signal() },
               name: "newer_color_failure_is_held_before_return")
            try await waitForGate(pendingColorFailureGate)
            await pendingOldColorGate.release()
            try await pendingOldColorCompletion.wait()
            try check(s.photos.first(where: { $0.id == pendingColorPhoto })?.colorLabel == "green" &&
                      s.photo?.id == pendingColorPhoto && s.photo?.colorLabel == "green" && s.error == nil,
                      "old_color_label_ack_is_adopted_while_newer_failure_is_still_pending")
            await pendingColorFailureGate.release()
            try await pendingColorFailureCompletion.wait()
            let delayedColorFailureCatalog = try await readPhoto(pendingColorPhoto)
            try check(delayedColorFailureCatalog.colorLabel == "green" &&
                      s.photos.first(where: { $0.id == pendingColorPhoto })?.colorLabel == "green" &&
                      s.photo?.colorLabel == "green" &&
                      s.error?.contains("controlled delayed color failure") == true &&
                      !s.loading && !s.browsing,
                      "later_color_failure_preserves_old_acknowledged_value_and_reports_error")

            // A delayed successful write cannot advance after a newer selection or view transition.
            try await enterAll()
            let selectionOrder = s.photos.map(\.id)
            let selectionActive = selectionOrder[0]
            let selectionChangedTo = selectionOrder[2]
            try await focus(selectionActive)
            let selectionGate = CullingReplyGate()
            try apply(.rating(4), advance: true, call: { method, params in
                let reply = try await Backend.call(method, params)
                if method == "rate_photos" { await selectionGate.holdAfterReply() }
                return reply
            }, name: "selection_race_action_is_admitted")
            try await waitForGate(selectionGate)
            try await focus(selectionChangedTo)
            await selectionGate.release()
            try await waitUntil("delayed_reply_keeps_new_selection") {
                s.selected == selectionChangedTo && s.photo?.id == selectionChangedTo &&
                    s.photos.first(where: { $0.id == selectionActive })?.rating == 4 &&
                    s.message == "Updated 1 photo" && !s.loading
            }
            try check(s.selected == selectionChangedTo, "mutation_reply_cannot_retarget_a_new_selection")

            try await enterAll()
            let viewOrder = s.photos.map(\.id)
            let viewActive = viewOrder[0]
            try await focus(viewActive)
            let viewGate = CullingReplyGate()
            try apply(.flag(1), advance: true, call: { method, params in
                let reply = try await Backend.call(method, params)
                if method == "rate_photos" { await viewGate.holdAfterReply() }
                return reply
            }, name: "view_race_action_is_admitted")
            try await waitForGate(viewGate)
            await s.switchLibraryView(.compare)
            let selectedInCompare = s.selected
            await viewGate.release()
            try await waitUntil("delayed_reply_keeps_review_view") {
                s.libraryView == .compare && s.selected == selectedInCompare && !s.loading && !s.browsing &&
                    s.message == "Updated 1 photo"
            }
            try check(s.libraryView == .compare && s.selected == selectedInCompare,
                      "mutation_reply_cannot_advance_after_view_change")

            // Starting a newer culling action invalidates an older delayed focus request.
            try await enterAll()
            let actionOrder = s.photos.map(\.id)
            let firstActionPhoto = actionOrder[0]
            let secondActionPhoto = actionOrder[1]
            let expectedAfterSecond = actionOrder[2]
            try await focus(firstActionPhoto)
            let firstActionGate = CullingReplyGate()
            try apply(.rating(2), advance: true, call: { method, params in
                let reply = try await Backend.call(method, params)
                if method == "rate_photos" { await firstActionGate.holdAfterReply() }
                return reply
            }, name: "older_culling_action_is_admitted")
            try await waitForGate(firstActionGate)
            try await focus(secondActionPhoto)
            try apply(.flag(1), advance: true, name: "newer_culling_action_is_admitted")
            try await waitForFocus(expectedAfterSecond, name: "newer_action_advances_to_its_successor")
            await firstActionGate.release()
            try await waitUntil("older_action_cannot_advance_again") {
                s.selected == expectedAfterSecond && s.photo?.id == expectedAfterSecond &&
                    s.photos.first(where: { $0.id == firstActionPhoto })?.rating == 2 &&
                    s.photos.first(where: { $0.id == secondActionPhoto })?.flag == 1 && !s.loading && !s.browsing
            }
            try check(s.selected == expectedAfterSecond,
                      "newer_action_generation_rejects_older_focus_advance")

            // A newer edit to the same photo and field must win over an accepted older
            // reply that was held after its real backend mutation completed.
            try await enterAll()
            let samePhoto = s.photos[0].id
            try await focus(samePhoto)
            let samePhotoGate = CullingReplyGate()
            let samePhotoCompletion = CullingCompletionLatch()
            try apply(.rating(2), advance: true, call: { method, params in
                let reply = try await Backend.call(method, params)
                if method == "rate_photos" { await samePhotoGate.holdAfterReply() }
                return reply
            }, completion: { samePhotoCompletion.signal() },
               name: "older_same_photo_rating_reply_is_admitted")
            try await waitForGate(samePhotoGate)
            try apply(.rating(5), advance: false, name: "newer_same_photo_rating_is_admitted")
            try await waitUntil("newer_same_photo_rating_is_visible") {
                s.selected == samePhoto && s.photo?.id == samePhoto && s.photo?.rating == 5 &&
                    s.photos.first(where: { $0.id == samePhoto })?.rating == 5 &&
                    s.message == "Updated 1 photo" && !s.loading && !s.browsing
            }
            let newerSamePhotoCatalog = try await readPhoto(samePhoto)
            try check(newerSamePhotoCatalog.rating == 5,
                      "newer_same_photo_rating_is_committed_before_old_reply_resumes")
            await samePhotoGate.release()
            try await samePhotoCompletion.wait()
            let finalSamePhotoCatalog = try await readPhoto(samePhoto)
            try check(finalSamePhotoCatalog.rating == 5 &&
                      s.photos.first(where: { $0.id == samePhoto })?.rating == 5 &&
                      s.photo?.id == samePhoto && s.photo?.rating == 5 && s.selected == samePhoto &&
                      s.selection == [samePhoto] && !s.loading && !s.browsing,
                      "stale_same_photo_reply_cannot_overwrite_newer_catalog_or_native_rating")

            // A newer flag write must not discard an older accepted rating on that same photo.
            try await enterAll()
            let crossFieldPhoto = s.photos[0].id
            try await focus(crossFieldPhoto)
            let crossFieldGate = CullingReplyGate()
            let crossFieldCompletion = CullingCompletionLatch()
            try apply(.rating(2), advance: true, call: { method, params in
                let reply = try await Backend.call(method, params)
                if method == "rate_photos" { await crossFieldGate.holdAfterReply() }
                return reply
            }, completion: { crossFieldCompletion.signal() },
               name: "older_rating_before_newer_flag_is_admitted")
            try await waitForGate(crossFieldGate)
            try apply(.flag(1), advance: false, name: "newer_same_photo_flag_is_admitted")
            try await waitUntil("newer_flag_state_is_visible") {
                s.selected == crossFieldPhoto && s.photo?.id == crossFieldPhoto && s.photo?.flag == 1 &&
                    s.photos.first(where: { $0.id == crossFieldPhoto })?.flag == 1 &&
                    s.message == "Updated 1 photo" && !s.loading && !s.browsing
            }
            let newerFlagCatalog = try await readPhoto(crossFieldPhoto)
            try check(newerFlagCatalog.rating == 2 && newerFlagCatalog.flag == 1,
                      "cross_field_catalog_mutations_are_both_committed")
            let newerFlagMessage = "Newer flag action remains the visible status"
            s.message = newerFlagMessage
            await crossFieldGate.release()
            try await crossFieldCompletion.wait()
            let finalCrossFieldCatalog = try await readPhoto(crossFieldPhoto)
            let finalCrossFieldRow = s.photos.first(where: { $0.id == crossFieldPhoto })
            try check(finalCrossFieldCatalog.rating == 2 && finalCrossFieldCatalog.flag == 1 &&
                      finalCrossFieldRow?.rating == 2 && finalCrossFieldRow?.flag == 1 &&
                      s.photo?.id == crossFieldPhoto && s.photo?.rating == 2 && s.photo?.flag == 1 &&
                      s.selected == crossFieldPhoto && s.selection == [crossFieldPhoto] &&
                      s.message == newerFlagMessage && !s.loading && !s.browsing,
                      "older_rating_reply_adopts_unrelated_field_without_overwriting_newer_flag_status")

            // For a captured two-photo rating batch, a newer rating of only A supersedes A's
            // old value while the accepted old reply still contributes B's independent value.
            try await enterAll()
            let overlapTargets = Array(s.photos.prefix(2).map(\.id))
            guard overlapTargets.count == 2 else { throw EngineFailure(message: "Need two batch rows") }
            let overlapA = overlapTargets[0]
            let overlapB = overlapTargets[1]
            try await focus(overlapA, selection: Set(overlapTargets))
            let overlapGate = CullingReplyGate()
            let overlapCompletion = CullingCompletionLatch()
            try apply(.rating(2), advance: true, call: { method, params in
                let reply = try await Backend.call(method, params)
                if method == "rate_photos" { await overlapGate.holdAfterReply() }
                return reply
            }, completion: { overlapCompletion.signal() },
               name: "older_overlapping_grid_batch_is_admitted")
            try await waitForGate(overlapGate)
            try await focus(overlapA)
            try apply(.rating(5), advance: false, name: "newer_single_rating_overlaps_one_batch_target")
            try await waitUntil("newer_overlapping_target_rating_is_visible") {
                s.selected == overlapA && s.photo?.id == overlapA && s.photo?.rating == 5 &&
                    s.photos.first(where: { $0.id == overlapA })?.rating == 5 &&
                    s.message == "Updated 1 photo" && !s.loading && !s.browsing
            }
            let newerOverlapMessage = "Newer rating of the active batch target"
            s.message = newerOverlapMessage
            await overlapGate.release()
            try await overlapCompletion.wait()
            let finalOverlapA = try await readPhoto(overlapA)
            let finalOverlapB = try await readPhoto(overlapB)
            let finalOverlapARow = s.photos.first(where: { $0.id == overlapA })
            let finalOverlapBRow = s.photos.first(where: { $0.id == overlapB })
            try check(finalOverlapA.rating == 5 && finalOverlapB.rating == 2 &&
                      finalOverlapARow?.rating == 5 && finalOverlapBRow?.rating == 2 &&
                      s.photo?.id == overlapA && s.photo?.rating == 5 && s.selected == overlapA &&
                      s.selection == [overlapA] && s.message == newerOverlapMessage &&
                      !s.loading && !s.browsing,
                      "partially_overlapping_batch_keeps_newer_A_and_adopts_old_B_without_retargeting")

            // A context-bound page response is rejected if the user opens another source mid-query.
            try await enterAll()
            try await seedRatings(ids, Array(repeating: 3, count: ids.count))
            await s.openLibraryMode("stars", clearFilters: true)
            try await waitForPage(total: 5, ids: Set(ids), offset: 0, name: "stars_source_loaded")
            let pageRaceOrder = s.photos.map(\.id)
            let pageRaceActive = pageRaceOrder[0]
            let alternate = try await Self.createCollection("Culling alternate source", photoIDs: [pageRaceOrder.last!])
            try await focus(pageRaceActive)
            let pageGate = CullingReplyGate()
            try apply(.rating(2), advance: true, pageCall: { method, params in
                let reply = try await Backend.call(method, params)
                if method == "list_photos" { await pageGate.holdAfterReply() }
                return reply
            }, name: "filtered_page_race_action_is_admitted")
            try await waitForGate(pageGate)
            await s.openCollection(alternate)
            let alternateID = pageRaceOrder.last!
            try await waitForPage(total: 1, ids: [alternateID], offset: 0, name: "new_collection_source_loaded")
            try await waitForFocus(alternateID, name: "new_collection_photo_is_active")
            await pageGate.release()
            try await waitUntil("old_page_reply_does_not_replace_new_source") {
                s.collectionID == alternate.id && s.selected == alternateID &&
                    Set(s.photos.map(\.id)) == [alternateID] && !s.browsing && !s.loading
            }
            try check(s.collectionID == alternate.id && s.selected == alternateID &&
                      Set(s.photos.map(\.id)) == [alternateID],
                      "late_filtered_page_cannot_replace_newer_source")

            // Filter and sort changes requery the loaded page, then advance in the captured old order.
            try await enterAll()
            try await seedRatings(ids, [1, 2, 3, 4, 5])
            s.librarySort = "imported"
            s.sortDescending = true
            s.libraryFilters = ["rating_min": 3]
            await s.refresh()
            try await waitUntil("rating_filter_loaded") { s.total == 3 && !s.browsing }
            let filteredOrder = s.photos.map(\.id)
            let filteredActive = filteredOrder[0]
            let filteredNext = filteredOrder[1]
            try await focus(filteredActive)
            try apply(.rating(0), advance: true, name: "rating_filter_action_is_admitted")
            try await waitForPage(total: 2, ids: Set(filteredOrder.dropFirst()), offset: 0,
                                  name: "rating_filter_page_reloads_after_removal")
            try await waitForFocus(filteredNext, name: "rating_filter_advances_to_next_old_order_survivor")
            try check(s.selected == filteredNext, "filter_requery_uses_captured_successor_not_fallback")

            try await enterAll()
            s.libraryFilters = [:]
            s.librarySort = "rating"
            s.sortDescending = false
            await s.refresh()
            try await waitUntil("rating_sort_loaded") { s.total == 5 && !s.browsing }
            let sortedBefore = s.photos.map(\.id)
            let sortedActive = sortedBefore[0]
            let sortedSuccessor = sortedBefore[1]
            try await focus(sortedActive)
            try apply(.rating(5), advance: true, name: "rating_sort_action_is_admitted")
            try await waitForFocus(sortedSuccessor, name: "sort_requery_advances_in_captured_order")
            try check(s.selected == sortedSuccessor && s.photos.map(\.id) != sortedBefore,
                      "sort_reorder_does_not_change_captured_successor")

            // Verify mode-driven culling for Stars, Keepers and Rejects, each using the next surviving row.
            try await enterAll()
            try await seedRatings(ids, Array(repeating: 3, count: ids.count))
            await s.openLibraryMode("stars", clearFilters: true)
            try await waitForPage(total: 5, ids: Set(ids), offset: 0, name: "all_starred_rows_loaded")
            let starsOrder = s.photos.map(\.id)
            let starActive = starsOrder[1]
            let starNext = starsOrder[2]
            try await focus(starActive)
            try apply(.rating(2), advance: true, name: "stars_mode_culling_action_is_admitted")
            try await waitForPage(total: 4, ids: Set(starsOrder.filter { $0 != starActive }), offset: 0,
                                  name: "stars_mode_refresh_removes_unstarred_photo")
            try await waitForFocus(starNext, name: "stars_mode_uses_next_surviving_loaded_id")
            try check(s.selected == starNext, "stars_mode_culling_advances_without_fallback")

            try await seedFlags(ids, value: 1)
            await s.openLibraryMode("keepers", clearFilters: true)
            try await waitForPage(total: 5, ids: Set(ids), offset: 0, name: "keepers_rows_loaded")
            let keepersOrder = s.photos.map(\.id)
            let keeperActive = keepersOrder[1]
            let keeperNext = keepersOrder[2]
            try await focus(keeperActive)
            try apply(.flag(-1), advance: true, name: "keepers_mode_culling_action_is_admitted")
            try await waitForPage(total: 4, ids: Set(keepersOrder.filter { $0 != keeperActive }), offset: 0,
                                  name: "keepers_mode_refresh_removes_rejected_photo")
            try await waitForFocus(keeperNext, name: "keepers_mode_uses_next_surviving_loaded_id")

            try await seedFlags(ids, value: -1)
            await s.openLibraryMode("rejects", clearFilters: true)
            try await waitForPage(total: 5, ids: Set(ids), offset: 0, name: "rejects_rows_loaded")
            let rejectsOrder = s.photos.map(\.id)
            let rejectActive = rejectsOrder[1]
            let rejectNext = rejectsOrder[2]
            try await focus(rejectActive)
            try apply(.flag(0), advance: true, name: "rejects_mode_culling_action_is_admitted")
            try await waitForPage(total: 4, ids: Set(rejectsOrder.filter { $0 != rejectActive }), offset: 0,
                                  name: "rejects_mode_refresh_removes_cleared_flag")
            try await waitForFocus(rejectNext, name: "rejects_mode_uses_next_surviving_loaded_id")
            try check(s.selected == rejectNext, "keepers_and_rejects_culling_use_captured_successors")

            // A failed aggregate-set refresh leaves its node invalidation pending. A later
            // culling refresh that removes the set's final filtered photo must clear focus
            // and consume that exact pending invalidation only after the page pipeline succeeds.
            try await rateAll(ids, value: 0)
            let setPhoto = ids[1]
            _ = try await Backend.call("rate_photos", ["photo_ids": [setPhoto], "rating": 3])
            let aggregateSet = try await Self.createCollection("Culling pending aggregate", kind: "set")
            let moveTarget = try await Self.createCollection("Culling pending destination", kind: "set")
            let regularChild = try await Self.createCollection("Culling pending regular", parentID: aggregateSet.id,
                                                                  photoIDs: [ids[0]])
            _ = try await Self.createCollection("Culling pending smart", kind: "smart", parentID: aggregateSet.id,
                                                rules: ["rating_min": 3])
            s.expandedCollections.insert(aggregateSet.id)
            await s.refreshCollections()
            guard let visibleAggregate = s.collections.first(where: { $0.id == aggregateSet.id }),
                  let visibleMoveTarget = s.collections.first(where: { $0.id == moveTarget.id }),
                  let visibleRegular = s.collectionPages[aggregateSet.id]?.items.first(where: { $0.id == regularChild.id }) else {
                throw EngineFailure(message: "Pending aggregate set nodes did not load")
            }
            await s.openCollection(visibleAggregate)
            s.mode = "all"
            s.libraryFilters = ["rating_min": 3]
            s.search = ""
            s.offset = 0
            await s.refresh()
            try await waitForPage(total: 1, ids: [setPhoto], offset: 0,
                                  name: "set_filter_shows_only_the_live_smart_member")
            try await focus(setPhoto)
            let moveRefreshFailure = "controlled aggregate-set photo refresh failure"
            guard let moveTask = s.beginCollectionNodeDrop(
                s.collectionNodeDrag(visibleRegular),
                to: visibleMoveTarget,
                pageCall: { method, params in
                    if method == "list_photos" { throw EngineFailure(message: moveRefreshFailure) }
                    return try await Backend.call(method, params)
                }
            ) else {
                throw EngineFailure(message: "Could not admit the regular-child move into a set")
            }
            await moveTask.value
            let movedChild = try await Backend.call("get_collection", ["collection_id": regularChild.id])
            let pendingToken = s.pendingCollectionNodePhotoRefreshGeneration
            try check(movedChild["parent_id"] as? Int == moveTarget.id &&
                      (pendingToken.map { $0 == s.collectionNodePhotoRefreshGeneration } ?? false) &&
                      s.collectionID == aggregateSet.id && s.total == 1 && s.photos.map(\.id) == [setPhoto] &&
                      s.selected == setPhoto && s.error?.contains(moveRefreshFailure) == true,
                      "failed_node_page_refresh_keeps_aggregate_source_and_pending_token")
            let aggregateBeforeCull = try await Backend.call("list_photos", [
                "collection_id": aggregateSet.id, "filters": ["rating_min": 3], "stacked": false,
            ])
            try check(aggregateBeforeCull["total"] as? Int == 1 &&
                      Set((aggregateBeforeCull["photos"] as? [[String: Any]] ?? [])
                        .compactMap { $0["id"] as? Int }) == [setPhoto],
                      "moved_regular_child_is_absent_but_live_smart_member_remains")
            s.error = nil
            let pendingCullPageGeneration = s.cullingPageGeneration
            try apply(.rating(0), advance: true, name: "aggregate_set_last_photo_culling_is_admitted")
            try await waitUntil("successful_empty_set_refresh_consumes_pending_token") {
                s.cullingPageGeneration > pendingCullPageGeneration && s.total == 0 && s.offset == 0 &&
                    s.photos.isEmpty && s.selected == nil && s.selection.isEmpty && s.photo == nil &&
                    s.pendingCollectionNodePhotoRefreshGeneration == nil && !s.browsing && !s.loading
            }
            let removedSetPhoto = try await readPhoto(setPhoto)
            let aggregateAfterCull = try await Backend.call("list_photos", [
                "collection_id": aggregateSet.id, "filters": ["rating_min": 3], "stacked": false,
            ])
            try check(removedSetPhoto.rating == 0 && aggregateAfterCull["total"] as? Int == 0 &&
                      s.total == 0 && s.photos.isEmpty && s.selected == nil && s.selection.isEmpty &&
                      s.pendingCollectionNodePhotoRefreshGeneration == nil,
                      "no_successor_cull_clears_focus_and_consumes_only_successfully_refreshed_set_token")

            // Grow the catalog only with virtual-copy rows (no extra disk originals) to cover
            // batch selection reconciliation and final-page clamping.
            try await enterAll()
            try await seedRatings(ids, Array(repeating: 3, count: ids.count))
            let master = try await readPhoto(ids[0])
            var virtualIDs: [Int] = []
            for _ in 0..<56 {
                let result = try await Backend.call("create_virtual_copies", ["targets": [master.copyTarget()]])
                guard result["created"] as? Int == 1,
                      let createdID = (result["photos"] as? [[String: Any]])?.first?["id"] as? Int else {
                    throw EngineFailure(message: "Could not create bounded virtual-copy fixture row")
                }
                virtualIDs.append(createdID)
            }
            let expandedIDs = ids + virtualIDs
            try check(expandedIDs.count == 61, "virtual_rows_expand_catalog_without_more_originals")

            // A captured Grid batch that removes every selected row from Stars must refresh
            // the source and clear focus instead of falling back to an unrelated first row.
            s.showStacks = false
            s.librarySort = "imported"
            s.sortDescending = true
            await s.openLibraryMode("stars", clearFilters: true)
            try await waitForPage(total: 61, offset: 0, name: "sixty_one_starred_catalog_rows_loaded")
            try check(s.photos.count == 60, "large_culling_fixture_stays_bounded_to_sixty_rows")

            let removedBatch = [ids[1], ids[2]]
            try check(Set(s.photos.map(\.id)).isSuperset(of: removedBatch),
                      "batch_targets_are_captured_from_the_loaded_stars_page")
            try await focus(removedBatch[0], selection: Set(removedBatch))
            let removedBatchPageGeneration = s.cullingPageGeneration
            try apply(.rating(2), advance: true, name: "stars_grid_batch_action_is_admitted")
            let removedPageIDs = Set(expandedIDs).subtracting(removedBatch)
            try await waitForPage(total: 59, ids: removedPageIDs, offset: 0,
                                  afterPageGeneration: removedBatchPageGeneration,
                                  name: "stars_grid_batch_requeries_after_all_selected_rows_leave")
            let removedBatchFirst = try await readPhoto(removedBatch[0])
            let removedBatchSecond = try await readPhoto(removedBatch[1])
            let untouchedStar = try await readPhoto(ids[0])
            try check(removedBatchFirst.rating == 2 && removedBatchSecond.rating == 2 &&
                      untouchedStar.rating == 3 && s.selected == nil && s.selection.isEmpty &&
                      s.photos.count == 59 && Set(s.photos.map(\.id)) == removedPageIDs,
                      "all_removed_batch_clears_focus_without_selecting_an_unrelated_photo")

            // Rating sort moves two captured rows to the last rank. The former active photo
            // falls off the bounded page while the other selected row survives; reconciliation
            // keeps that surviving selected ID instead of selecting page.first.
            try await rateAll(expandedIDs, value: 3)
            s.showStacks = false
            s.librarySort = "rating"
            s.sortDescending = true
            await s.openLibraryMode("all", clearFilters: true)
            try await waitForPage(total: 61, offset: 0, name: "rating_sorted_sixty_one_rows_loaded")
            // Descending rating ties use descending IDs. Put the smaller ID last
            // so it is the active row that leaves the sixty-row page.
            let activeToCull = min(ids[1], ids[2])
            let survivingBatchID = max(ids[1], ids[2])
            try check(Set(s.photos.map(\.id)).isSuperset(of: [activeToCull, survivingBatchID]),
                      "rating_batch_targets_are_on_the_captured_page")
            try await focus(activeToCull, selection: [activeToCull, survivingBatchID])
            let sortedBatchPageGeneration = s.cullingPageGeneration
            try apply(.rating(0), advance: true, name: "rating_sorted_grid_batch_action_is_admitted")
            let clampedBatchPageIDs = Set(expandedIDs).subtracting([activeToCull])
            try await waitForPage(total: 61, ids: clampedBatchPageIDs, offset: 0,
                                  afterPageGeneration: sortedBatchPageGeneration,
                                  name: "rating_sorted_batch_refreshes_after_page_membership_changes")
            try await waitForFocus(survivingBatchID,
                                   name: "batch_reconciliation_loads_first_captured_surviving_selected_photo")
            let culledActive = try await readPhoto(activeToCull)
            let survivingSelected = try await readPhoto(survivingBatchID)
            let directSortedPage = try await Backend.call("list_photos", [
                "offset": 0, "mode": "all", "sort": "rating", "descending": true, "stacked": false,
            ])
            let directSortedIDs = Set((directSortedPage["photos"] as? [[String: Any]] ?? [])
                .compactMap { $0["id"] as? Int })
            try check(culledActive.rating == 0 && survivingSelected.rating == 0 &&
                      directSortedIDs == clampedBatchPageIDs && Set(s.photos.map(\.id)) == directSortedIDs &&
                      s.selected == survivingBatchID && s.selection == [survivingBatchID] &&
                      s.photo?.id == survivingBatchID,
                      "batch_refresh_keeps_first_captured_surviving_selection_after_active_leaves_page")

            // Restore a bounded all-star page, then remove the only row on its final page.
            try await rateAll(expandedIDs, value: 3)
            s.showStacks = false
            s.librarySort = "imported"
            s.sortDescending = true
            await s.openLibraryMode("stars", clearFilters: true)
            s.offset = 0
            await s.refresh()
            try await waitForPage(total: 61, offset: 0, name: "restored_sixty_one_starred_catalog_rows_loaded")
            try check(s.photos.count == 60, "restored_page_remains_bounded_to_sixty_rows")
            s.offset = 60
            await s.refresh()
            try await waitForPage(total: 61, offset: 60, name: "last_culling_page_loads_one_row")
            guard let lastPagePhoto = s.photos.first?.id else { throw EngineFailure(message: "Missing deep-page photo") }
            try check(s.photos.count == 1 && s.selected == lastPagePhoto,
                      "deep_page_focus_is_the_only_loaded_photo")
            try await focus(lastPagePhoto)
            try apply(.rating(2), advance: true, name: "deep_page_culling_action_is_admitted")
            try await waitUntil("last_star_removed_and_page_clamped_to_zero") {
                s.total == 60 && s.offset == 0 && s.photos.count == 60 && !s.browsing &&
                    s.selected == nil && s.selection.isEmpty
            }
            try check(s.total == 60 && s.offset == 0 && s.photos.count == 60 &&
                      !s.photos.contains(where: { $0.id == lastPagePhoto }) &&
                      s.selected == nil && s.selection.isEmpty,
                      "page_clamp_clears_absent_active_selection_without_stale_offset")

            try check(try paths.map { try Data(contentsOf: URL(fileURLWithPath: $0)) } == originalBytes,
                      "culling_workflows_preserve_original_bytes")
            print(String(data: try JSONSerialization.data(withJSONObject: [
                "ok": true, "checks": checks,
                "desktop_keyboard_dispatch": "NOT_VERIFIED",
                "virtual_copy_rows_are_catalog_only": true,
                "original_file_bytes_verified": true,
            ], options: [.prettyPrinted, .sortedKeys]), encoding: .utf8)!)
            exit(0)
        } catch {
            print(String(data: try! JSONSerialization.data(withJSONObject: [
                "ok": false, "checks": checks, "error": error.localizedDescription,
                "store_error": s.error ?? "",
                "desktop_keyboard_dispatch": "NOT_VERIFIED",
            ], options: [.prettyPrinted, .sortedKeys]), encoding: .utf8)!)
            exit(1)
        }
    }

    @MainActor private static func createCollection(_ name: String, kind: String = "regular", parentID: Int? = nil,
                                                    rules: [String: Any] = [:], photoIDs: [Int] = []) async throws -> LibraryCollection {
        var params: [String: Any] = [
            "name": name, "kind": kind, "rules": rules, "match": "all",
            "parent_id": parentID as Any? ?? NSNull(),
        ]
        if !photoIDs.isEmpty { params["photo_ids"] = photoIDs }
        let result = try await Backend.call("save_collection", params)
        guard let collection = LibraryCollection(result) else {
            throw EngineFailure(message: "Could not create collection \(name)")
        }
        return collection
    }
}
