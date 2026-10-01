// Purpose: detect redundant Store invalidation and main-thread image IO regressions.
// Inputs: generated local originals and a disposable live broker. Outputs: unchanged
// poll publication counts, real update propagation and background-decode evidence.
// State/actor timing does not establish rendered desktop frame rate or interaction.
import AppKit
import Combine
import Foundation

@main struct NativeResponsivenessRegression {
    @MainActor static func main() async {
        _=NSApplication.shared
        let s=Store();var checks:[String:Bool]=[:]
        func check(_ value:Bool,_ name:String)throws {checks[name]=value;if !value {throw EngineFailure(message:name)}}
        func waitReady() async throws {
            for _ in 0..<600 {
                if s.photo != nil,!s.loading,!s.rendering,s.thumbnailRenderer.frames.count==s.photos.count {return}
                try await Task.sleep(nanoseconds:20_000_000)
            }
            throw EngineFailure(message:"Photo preparation timed out")
        }
        do {
            let paths=ProcessInfo.processInfo.environment["LUMARAW_TEST_FIXTURES"]!.components(separatedBy:"|")
            let originals=try paths.map {try Data(contentsOf:URL(fileURLWithPath:$0))}
            await s.importPaths(paths);try await waitReady()
            await s.refreshJobs();await s.refreshVisibleSummaries()
            var publications=0
            let subscription=s.objectWillChange.sink {publications+=1}
            for _ in 0..<10 {await s.refreshJobs();await s.refreshVisibleSummaries()}
            let unchanged=publications
            try check(unchanged==0,"unchanged_background_polls_publish_no_store_updates")
            let id=s.selected!
            _=try await Backend.call("rate_photo",["photo_id":id,"rating":4])
            await s.refreshVisibleSummaries()
            try check(s.photos.first(where:{$0.id==id})?.rating==4 && publications>unchanged,"external_changes_still_publish")
            await s.startReferenceView();await s.setReferencePhoto(id)
            for _ in 0..<300 {if s.referenceRenderer.frame != nil && !s.rendering {break};try await Task.sleep(nanoseconds:20_000_000)}
            await s.refreshReferencePhoto()
            let before=publications
            for _ in 0..<5 {await s.refreshReferencePhoto()}
            try check(publications==before,"unchanged_reference_polls_publish_no_store_updates")
            await s.readVersions()
            let snapshotBefore=publications
            for _ in 0..<5 {await s.readVersions(onlyChanged:true)}
            try check(publications==snapshotBefore && !s.snapshotPolling && !s.snapshotLoading,"unchanged_snapshot_polls_publish_no_store_updates")
            _=try await Backend.call("save_version",["photo_id":id,"name":"External snapshot"])
            await s.readVersions(onlyChanged:true)
            try check(s.snapshotPage?.entries.first?.name=="External snapshot" && publications>snapshotBefore,"external_snapshot_changes_still_publish")
            let recipe=(try await Backend.call("get_photo",["photo_id":id]))["recipe"] as? [String:Any]
            var beats=0
            let heartbeat=Task { @MainActor in
                while !Task.isCancelled {beats+=1;try? await Task.sleep(nanoseconds:1_000_000)}
            }
            let start=Date()
            for path in paths {
                guard let image=await PreviewImageLoader.load(path),let rep=image.representations.first else {throw EngineFailure(message:"Image load failed")}
                try check(rep.pixelsWide==2400 && rep.pixelsHigh==1800,"decoded_dimensions_\(URL(fileURLWithPath:path).lastPathComponent)")
            }
            let elapsed=Date().timeIntervalSince(start)*1000
            heartbeat.cancel()
            try check(beats>0,"main_actor_runs_during_background_decode")
            try check(await PreviewImageLoader.load(nil)==nil,"missing_image_path_is_rejected")
            let broken=Backend.catalog+"/invalid-image";try Data("invalid".utf8).write(to:URL(fileURLWithPath:broken))
            try check(await PreviewImageLoader.load(broken)==nil,"malformed_image_is_rejected")
            let preview=try await Backend.call("preview_photo",["photo_id":id,"include_before":false])
            guard let image=await PreviewImageLoader.load(preview["preview"] as? String) else {throw EngineFailure(message:"Tagged preview unavailable")}
            var proposed=CGRect(origin:.zero,size:image.size)
            let cg=image.cgImage(forProposedRect:&proposed,context:nil,hints:nil)
            try check(cg?.colorSpace != nil && cg?.width==preview["width"] as? Int,"prepared_preview_keeps_dimensions_and_color_space")
            let afterRecipe=(try await Backend.call("get_photo",["photo_id":id]))["recipe"] as? [String:Any]
            try check(NSDictionary(dictionary:recipe ?? [:]).isEqual(to:afterRecipe ?? [:]),"responsiveness_workflows_preserve_recipe")
            try check(try paths.enumerated().allSatisfy {try Data(contentsOf:URL(fileURLWithPath:$0.element))==originals[$0.offset]},"responsiveness_workflows_preserve_originals")
            subscription.cancel()
            let report:[String:Any]=["ok":true,"checks":checks,"unchanged_poll_publications":unchanged,
                "decode_elapsed_ms":elapsed,"main_actor_heartbeats":beats,"desktop_ui":"NOT_VERIFIED","voiceover":"NOT_VERIFIED"]
            let data=try JSONSerialization.data(withJSONObject:report,options:[.prettyPrinted,.sortedKeys]);print(String(data:data,encoding:.utf8)!);exit(0)
        } catch {
            let data=try! JSONSerialization.data(withJSONObject:["ok":false,"checks":checks,"error":error.localizedDescription,"store_error":s.error ?? ""],options:[.prettyPrinted,.sortedKeys]);print(String(data:data,encoding:.utf8)!);exit(1)
        }
    }
}
