// Purpose: compare/survey workflow and stale-preview evidence for the native shell.
// Inputs: five generated images and a disposable real broker catalog.
// Outputs: role/navigation, viewport, mutation-scope and retained-frame assertions.
// A controlled late-reply transport supplements real renders for a deterministic
// cancellation race. This does not verify desktop clicks or physical display scale.
import AppKit
import Foundation

@MainActor final class DelayedReviewTransport {
    var pending: [Int: CheckedContinuation<[String:Any], Error>] = [:]
    let path: String
    init(path: String) { self.path=path }
    func call(_ method: String, _ params: [String:Any]) async throws -> [String:Any] {
        if method != "preview_photo" { return [:] }
        let id=params["photo_id"] as! Int
        return try await withCheckedThrowingContinuation { pending[id]=$0 }
    }
    func finish(_ id: Int) {
        pending.removeValue(forKey:id)?.resume(returning:["photo_id":id,"revision":0,"preview":path,
            "width":160,"height":100,"full_width":160,"full_height":100])
    }
}

@main struct NativeReviewRegression {
    @MainActor static func main() async {
        _ = NSApplication.shared
        let s=Store()
        var checks:[String:Bool]=[:]
        func check(_ value:Bool,_ name:String)throws {
            checks[name]=value
            if !value { throw EngineFailure(message:name) }
        }
        func until(_ condition: () -> Bool) async throws {
            for _ in 0..<600 {
                if condition() { return }
                try await Task.sleep(nanoseconds:25_000_000)
            }
            throw EngineFailure(message:"Review state timed out: \(s.reviewRenderer.errors)")
        }
        func rendered(_ ids: [Int]) async throws {
            try await until { Set(s.reviewRenderer.frames.keys) == Set(ids) && s.reviewRenderer.loading.isEmpty }
        }
        do {
            let fixtures=ProcessInfo.processInfo.environment["LUMARAW_TEST_FIXTURES"]!.components(separatedBy:"|")
            await s.importPaths(fixtures)
            try await until { s.photo != nil && !s.loading }
            let ids=s.photos.map(\.id)
            s.selection=Set(ids.prefix(3));s.choose(ids[0])
            await s.switchLibraryView(.compare)
            try check(s.review.selectID == ids[0] && s.review.candidateID == ids[1],"compare_starts_with_active_and_next_selected")
            try await rendered([ids[0],ids[1]])
            let retained=s.reviewRenderer.frames[ids[0]]!.image
            s.choose(ids[2]);try await rendered([ids[0],ids[2]])
            try check(s.review.selectID == ids[0],"candidate_navigation_keeps_select")
            try check(s.reviewRenderer.frames[ids[0]]!.image === retained,"unchanged_select_reuses_rendered_frame")
            try check(s.actionPhotoIDs == [ids[2]] && s.selection.count == 3,"compare_actions_target_only_active")
            s.swapReview()
            try check(s.review.selectID == ids[2] && s.review.candidateID == ids[0],"swap_exchanges_roles")
            s.setReviewViewport(ReviewViewport(zoom:1,cx:0.3,cy:0.4),id:ids[2])
            try check(s.review.viewports[ids[2]] == s.review.viewports[ids[0]],"linked_zoom_and_pan")
            try await rendered([ids[2],ids[0]])
            try check(s.reviewRenderer.frames.values.allSatisfy { $0.request.viewport.zoom == 1 },"compare_requests_full_resolution_views")
            s.review.linked=false
            s.setReviewViewport(ReviewViewport(zoom:2,cx:0.7,cy:0.8),id:ids[0])
            try check(s.review.viewports[ids[2]]?.zoom == 1 && s.review.viewports[ids[0]]?.zoom == 2,"unlinked_zoom_is_independent")
            s.review.synchronize(from:ids[0]);s.updateReviewRequests()
            try check(s.review.viewports[ids[2]] == s.review.viewports[ids[0]],"sync_matches_viewports")
            s.promoteReview()
            try check(s.review.selectID == ids[0] && s.review.candidateID == ids[1],"promote_advances_candidate")
            s.selection=Set(ids)
            await s.switchLibraryView(.survey)
            try await rendered(ids)
            try check(s.reviewRenderer.frames.values.allSatisfy { $0.request.edge == 512 && $0.request.viewport.zoom == 0 },"survey_uses_bounded_fitted_previews")
            s.activateReviewPhoto(ids[3])
            try await until { s.photo?.id == ids[3] }
            try check(s.selection == Set(ids) && s.actionPhotoIDs == [ids[3]],"survey_focus_preserves_other_selected_photos")
            s.flag(1)
            for _ in 0..<100 {
                if s.photos.first(where: { $0.id == ids[3] })?.flag == 1 { break }
                try await Task.sleep(nanoseconds:20_000_000)
            }
            let summaries=try await Backend.call("photo_summaries",["photo_ids":ids])
            let picked=(summaries["photos"] as? [[String:Any]] ?? []).filter { $0["flag"] as? Int == 1 }
            try check(picked.count == 1 && picked.first?["id"] as? Int == ids[3],"survey_flags_only_active_photo")
            s.deselectReviewPhoto(ids[3]);try await rendered(ids.filter { $0 != ids[3] })
            let library=try await Backend.call("list_photos")
            try check(library["total"] as? Int == 5 && !s.selection.contains(ids[3]),"survey_deselect_preserves_catalog")
            let remaining=s.selection
            s.choose(ids[0])
            try check(s.selection == remaining,"click_selected_photo_keeps_multiple_selection")
            s.develop=true;s.canvasTool="crop";s.compare=true;s.splitCompare=true;s.detail=true
            await s.switchLibraryView(.loupe)
            try check(!s.develop && s.canvasTool == "view" && !s.compare && !s.splitCompare && !s.detail,
                      "loupe_leaves_develop_drawing_and_baseline_modes")
            await s.switchLibraryView(.grid)
            try check(s.reviewRenderer.frames.isEmpty && s.reviewRenderer.loading.isEmpty,"exit_releases_review_frames")

            // A transport that ignores Task cancellation reproduces the real
            // Process adapter's late reply, without relying on timing luck.
            let delayed=DelayedReviewTransport(path:fixtures[0])
            let renderer=ReviewRenderer(call:delayed.call)
            let first=ReviewRequest(photoID:101,revision:0,viewport:ReviewViewport(),width:1,height:1,edge:512)
            let next=ReviewRequest(photoID:102,revision:0,viewport:ReviewViewport(),width:1,height:1,edge:512)
            renderer.request([first]);try await until { delayed.pending[101] != nil }
            renderer.request([next]);try await until { delayed.pending[102] != nil }
            delayed.finish(102);try await until { renderer.frames[102] != nil }
            delayed.finish(101)
            try await Task.sleep(nanoseconds:50_000_000)
            try check(Set(renderer.frames.keys) == [102],"late_preview_cannot_replace_new_selection")
            renderer.stop()

            var session=ReviewSession()
            session.begin(visible:ids,selection:[ids[0]],active:ids[0])
            let removed=session.candidateID!
            session.remove(removed);session.reconcile(visible:ids,selection:Set(session.pair))
            try check(!session.pool.contains(removed),"removed_candidate_stays_excluded")
            session.chooseCandidate(removed)
            try check(session.candidateID == removed && !session.excluded.contains(removed),"explicit_candidate_selection_can_restore_excluded_photo")

            let report:[String:Any]=["ok":true,"checks":checks,"desktop_ui":"NOT_VERIFIED"]
            print(String(data:try JSONSerialization.data(withJSONObject:report,options:[.prettyPrinted,.sortedKeys]),encoding:.utf8)!)
            exit(0)
        } catch {
            s.reviewRenderer.stop()
            print(String(data:try! JSONSerialization.data(withJSONObject:["ok":false,"checks":checks,"error":error.localizedDescription,"store_error":s.error ?? ""],options:.prettyPrinted),encoding:.utf8)!)
            exit(1)
        }
    }
}
