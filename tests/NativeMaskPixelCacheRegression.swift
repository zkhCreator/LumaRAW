// Purpose: label-only mask edits reuse pixels with freshly captured native frames.
// Inputs: generated originals and the real engine through the shared native relay.
// Outputs: cache receipts, saved history and revision-bound readout/WB frame evidence.
// No desktop input, latency benchmark, pixel processing or mutation replay.
import AppKit
import Foundation

@main struct NativeMaskPixelCacheRegression {
    @MainActor static func main() async {
        _=NSApplication.shared
        let s=Store();var checks:[String:Bool]=[:]
        func check(_ value:Bool,_ name:String) throws {
            checks[name]=value;if !value {throw EngineFailure(message:name)}
        }
        func ready(_ revision:Int) async throws {
            for _ in 0..<800 {
                if !s.loading && !s.rendering && s.whiteBalancePreviewIdentity?.context.revision==revision &&
                    s.colorReadoutFrame?.region.context.revision==revision {return}
                try await Task.sleep(nanoseconds:20_000_000)
            }
            throw EngineFailure(message:"Current mask frame did not settle: \(s.error ?? "no error")")
        }
        func receipt(_ revision:Int) async throws -> [String:Any] {
            try await Backend.call("preview_photo",["photo_id":1,"expected_revision":revision,
                "include_before":false,"include_color_readouts":true,"display":["gamut":false]])
        }
        do {
            let paths=ProcessInfo.processInfo.environment["LUMARAW_TEST_FIXTURES"]!.components(separatedBy:"|")
            let original=try Data(contentsOf:URL(fileURLWithPath:paths[0]))
            await s.importPaths(paths);s.selected=1;s.selection=[1];s.develop=true;await s.load(1)
            s.set("masks",[["kind":"radial","name":"Skin 肤色","exposure":0.6]])
            try check(await s.flushEdits(),"initial_mask_saves")
            let firstRevision=s.photo!.revision
            try await ready(firstRevision)
            let oldIdentity=s.whiteBalancePreviewIdentity!,oldMap=s.colorReadoutFrame!.after.path
            let oldSample=s.colorReadoutFrame!.after.sample(CGPoint(x:0.5,y:0.5))
            let first=try await receipt(firstRevision)
            guard let target=await s.prepareLocalMaskTarget(0) else {throw EngineFailure(message:"Missing target")}
            let outcome=await s.performLocalMaskAction("rename",target:target,name:"Portrait 🐈")
            if case .accepted=outcome {} else {throw EngineFailure(message:s.error ?? "Rename failed")}
            let revision=s.photo!.revision
            try check(revision==firstRevision+1,"rename_has_its_own_saved_revision")
            try check(s.whiteBalancePreviewIdentity==nil && s.colorReadoutFrame==nil,"old_sampling_context_invalidated_before_cache_reply")
            try await ready(revision)
            let current=s.whiteBalancePreviewIdentity!,hit=try await receipt(revision)
            try check(current.context.revision==revision && current.sourceFingerprint==oldIdentity.sourceFingerprint,
                "reused_pixels_have_new_revision_and_same_source_identity")
            try check(s.colorReadoutFrame?.after.path==oldMap && s.colorReadoutFrame?.after.sample(CGPoint(x:0.5,y:0.5))==oldSample,
                "color_readouts_reuse_same_map_and_values")
            try check(hit["preview_cache_hit"] as? Bool==true && hit["worker_spawned"] as? Bool==false &&
                hit["preview"] as? String==first["preview"] as? String,"rename_avoids_worker_and_reuses_preview")
            let processing=hit["processing"] as? [String:Any]
            try check(processing?["backend"] as? String=="cache" &&
                (processing?["worker_seconds"] as? NSNumber)?.doubleValue==0,"cache_receipt_reports_no_new_pixel_work")
            do {
                _=try await receipt(firstRevision)
                try check(false,"old_revision_must_fail")
            } catch {try check(error.localizedDescription.contains("Edit conflict"),"cached_old_revision_still_fails_visibly")}
            let photo=Photo(try await Backend.call("get_photo",["photo_id":1]))!
            try check((photo.recipe["masks"] as? [[String:Any]])?[0]["name"] as? String=="Portrait 🐈",
                "catalog_preserves_renamed_label")
            try check(try Data(contentsOf:URL(fileURLWithPath:paths[0]))==original,"original_bytes_unchanged")
            print(String(data:try JSONSerialization.data(withJSONObject:["ok":true,"checks":checks,
                "desktop_ui":"NOT_VERIFIED","voiceover":"NOT_VERIFIED"],options:[.prettyPrinted,.sortedKeys]),encoding:.utf8)!)
            exit(0)
        } catch {
            print(String(data:try! JSONSerialization.data(withJSONObject:["ok":false,"checks":checks,
                "error":error.localizedDescription,"store_error":s.error ?? ""],options:.prettyPrinted),encoding:.utf8)!)
            exit(1)
        }
    }
}
