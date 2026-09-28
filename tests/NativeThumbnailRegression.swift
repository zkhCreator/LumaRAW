// Purpose: verify developed thumbnails and external-edit refresh in native state.
// Inputs: five generated rasters and a disposable real broker. Outputs: recipe,
// metadata, cache-eviction and delayed-response assertions. No desktop UI claim.
import AppKit
import Foundation

@MainActor final class DelayedThumbnailTransport {
    var pending: [Int: CheckedContinuation<[String:Any],Error>] = [:]
    let path: String
    init(path: String) { self.path=path }
    func call(_ method: String,_ params: [String:Any]) async throws -> [String:Any] {
        if method != "thumbnail" { return ["thumbnails":[]] }
        let generation=params["generation"] as! Int
        return try await withCheckedThrowingContinuation { pending[generation]=$0 }
    }
    func finish(_ generation: Int,revision: Int) {
        pending.removeValue(forKey:generation)?.resume(returning:["photo_id":101,"revision":revision,
            "thumbnail":path,"kind":"developed"])
    }
}

@main struct NativeThumbnailRegression {
    @MainActor static func main() async {
        _ = NSApplication.shared
        let s=Store()
        var checks: [String:Bool] = [:]
        func check(_ value: Bool,_ name: String) throws {
            checks[name]=value
            if !value { throw EngineFailure(message:name) }
        }
        func until(_ condition: () -> Bool) async throws {
            for _ in 0..<1000 {
                if condition() { return }
                try await Task.sleep(nanoseconds:20_000_000)
            }
            throw EngineFailure(message:"Thumbnail state timed out: \(s.thumbnailErrors)")
        }
        do {
            let fixtures=ProcessInfo.processInfo.environment["LUMARAW_TEST_FIXTURES"]!.components(separatedBy:"|")
            await s.importPaths(fixtures)
            try await until { s.thumbnails.count == 5 && s.thumbnailRenderer.loading.isEmpty && s.photo != nil }
            try check(s.thumbnailErrors.isEmpty,"developed_thumbnails_load_for_entire_page")
            let active=s.selected!,other=s.photos.first { $0.id != active }!.id
            let first=s.thumbnailRenderer.frames[active]!
            s.set("rotation",90);s.set("exposure",0.7)
            try check(await s.flushEdits(),"recipe_edit_saved")
            try await until { s.thumbnailRenderer.frames[active]?.target.revision == 1 }
            let edited=s.thumbnailRenderer.frames[active]!
            try check(edited.path != first.path,"local_recipe_invalidates_thumbnail")
            let pixels=edited.image.representations.first!
            try check(pixels.pixelsWide == 100 && pixels.pixelsHigh == 160,"rotation_visible_in_grid_pixels")
            try check(await s.saveMetadata(targets:[s.photo!],patch:["title":"Changed title"]),"metadata_saved")
            try await until { s.thumbnailRenderer.loading.isEmpty }
            try check(s.thumbnailRenderer.frames[active]?.image === edited.image,"metadata_reuses_existing_thumbnail")
            let oldOther=s.thumbnailRenderer.frames[other]!.path
            _=try await Backend.call("edit_photo",["photo_id":other,"expected_revision":0,"patch":["exposure":1.3]])
            await s.refreshVisibleSummaries()
            try await until { s.thumbnailRenderer.frames[other]?.target.revision == 1 }
            try check(s.thumbnailRenderer.frames[other]?.path != oldOther,"external_nonactive_edit_updates_grid")
            try check(s.selected == active && s.photo?.revision == 1,"external_page_refresh_preserves_active_inspector")
            let moved=s.photos.first { $0.id == other }!.path
            let relocated=URL(fileURLWithPath:moved).deletingLastPathComponent().appendingPathComponent("relocated.png").path
            let beforeRelink=s.thumbnailRenderer.frames[other]!.path
            try FileManager.default.moveItem(atPath:moved,toPath:relocated)
            _=try await Backend.call("relink_photo",["photo_id":other,"path":relocated])
            await s.refreshVisibleSummaries()
            try await until { s.thumbnailRenderer.frames[other]?.target.sourcePath == relocated }
            try check(s.thumbnailRenderer.frames[other]?.target.revision == 1,"relink_keeps_recipe_revision")
            try check(s.thumbnailRenderer.frames[other]?.path != beforeRelink,"relink_invalidates_native_thumbnail_source")
            let evicted=s.thumbnailRenderer.frames[active]!
            try FileManager.default.removeItem(atPath:evicted.path)
            await s.refresh()
            try await until { s.thumbnailRenderer.frames[active]?.image !== evicted.image && s.thumbnails[active] != nil }
            try check(FileManager.default.fileExists(atPath:evicted.path),"evicted_cache_regenerated_on_refresh")
            s.search="unmatched-query-for-thumbnail-test";await s.refresh()
            try check(s.thumbnails.isEmpty && s.thumbnailRenderer.frames.isEmpty,"empty_page_releases_thumbnails")

            let delayed=DelayedThumbnailTransport(path:fixtures[0])
            let renderer=ThumbnailRenderer(call:delayed.call)
            renderer.request([ThumbnailTarget(id:101,revision:0)])
            try await until { delayed.pending[1] != nil }
            renderer.request([ThumbnailTarget(id:101,revision:1)])
            try await until { delayed.pending[2] != nil }
            delayed.finish(2,revision:1)
            try await until { renderer.frames[101]?.target.revision == 1 }
            delayed.finish(1,revision:0)
            try await Task.sleep(nanoseconds:50_000_000)
            try check(renderer.frames[101]?.target.revision == 1,"late_old_recipe_cannot_replace_new_thumbnail")
            renderer.request([ThumbnailTarget(id:101,revision:2)])
            try await until { delayed.pending[3] != nil }
            delayed.finish(3,revision:3)
            try await until { renderer.loading.isEmpty }
            try check(renderer.frames.isEmpty && renderer.errors[101] != nil,"unexpected_revision_never_mislabeled_as_requested")
            let report: [String:Any] = ["ok":true,"checks":checks,"desktop_ui":"NOT_VERIFIED"]
            print(String(data:try JSONSerialization.data(withJSONObject:report,options:[.prettyPrinted,.sortedKeys]),encoding:.utf8)!)
            exit(0)
        } catch {
            print(String(data:try! JSONSerialization.data(withJSONObject:["ok":false,"checks":checks,
                "error":error.localizedDescription,"store_error":s.error ?? ""],options:.prettyPrinted),encoding:.utf8)!)
            exit(1)
        }
    }
}
