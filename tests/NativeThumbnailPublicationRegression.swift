// Purpose: specify deduplicated thumbnail publication and stale-work rejection.
// Inputs: one generated raster plus gated cache/render replies. Outputs: renderer
// callback and Store publication assertions. No desktop frame-rate claim.
import AppKit
import Combine
import Foundation

@MainActor private final class GatedThumbnailTransport {
    struct Key: Hashable {
        let generation: Int
        let photoID: Int
    }

    private(set) var cacheCalls=0
    private(set) var thumbnailCalls=0
    private(set) var cancelledGenerations:[Int]=[]
    private var caches:[Int:CheckedContinuation<[String:Any],Error>]=[:]
    private var thumbnails:[Key:CheckedContinuation<[String:Any],Error>]=[:]

    func call(_ method:String,_ params:[String:Any]) async throws -> [String:Any] {
        switch method {
        case "cancel_preview":
            if let generation=params["generation"] as? Int { cancelledGenerations.append(generation) }
            return ["cancelled":true]
        case "cached_thumbnails":
            cacheCalls+=1
            let request=cacheCalls
            return try await withCheckedThrowingContinuation { (continuation:CheckedContinuation<[String:Any],Error>) in
                caches[request]=continuation
            }
        case "thumbnail":
            thumbnailCalls+=1
            let key=Key(generation:params["generation"] as! Int,photoID:params["photo_id"] as! Int)
            return try await withCheckedThrowingContinuation { (continuation:CheckedContinuation<[String:Any],Error>) in
                thumbnails[key]=continuation
            }
        default:
            throw EngineFailure(message:"Unexpected thumbnail command: \(method)")
        }
    }

    var pendingCacheRequests:Set<Int> { Set(caches.keys) }
    var pendingThumbnailRequests:Set<Key> { Set(thumbnails.keys) }

    func finishCache(_ request:Int,entries:[[String:Any]]) {
        guard let continuation=caches.removeValue(forKey:request) else { preconditionFailure("Missing cache gate \(request)") }
        continuation.resume(returning:["thumbnails":entries])
    }

    func failCache(_ request:Int,message:String) {
        guard let continuation=caches.removeValue(forKey:request) else { preconditionFailure("Missing cache gate \(request)") }
        continuation.resume(throwing:EngineFailure(message:message))
    }

    func finishThumbnail(_ key:Key,revision:Int,path:String) {
        guard let continuation=thumbnails.removeValue(forKey:key) else { preconditionFailure("Missing thumbnail gate \(key)") }
        continuation.resume(returning:["photo_id":key.photoID,"revision":revision,
            "thumbnail":path,"kind":"developed"])
    }

    func failThumbnail(_ key:Key,message:String) {
        guard let continuation=thumbnails.removeValue(forKey:key) else { preconditionFailure("Missing thumbnail gate \(key)") }
        continuation.resume(throwing:EngineFailure(message:message))
    }
}

private struct ThumbnailPublication {
    let images:[Int:NSImage]
    let errors:[Int:String]
}

@main struct NativeThumbnailPublicationRegression {
    @MainActor static func main() async {
        _=NSApplication.shared
        var checks:[String:Bool]=[:]
        func check(_ value:Bool,_ name:String)throws {
            checks[name]=value
            if !value { throw EngineFailure(message:name) }
        }
        func until(_ condition:()->Bool,_ name:String) async throws {
            for _ in 0..<1000 {
                if condition() { return }
                try await Task.sleep(nanoseconds:10_000_000)
            }
            throw EngineFailure(message:name)
        }
        func cacheEntry(_ id:Int,_ revision:Int,_ path:String)->[String:Any] {
            ["photo_id":id,"revision":revision,"thumbnail":path,"kind":"developed"]
        }
        func settleReleasedResponse() async throws {
            // The controlled response is released; give the MainActor task a
            // bounded turn to process it before assertions inspect its state.
            try await Task.sleep(nanoseconds:30_000_000)
        }

        do {
            guard let fixture=ProcessInfo.processInfo.environment["LUMARAW_TEST_FIXTURES"]?
                .components(separatedBy:"|").first,!fixture.isEmpty,
                FileManager.default.fileExists(atPath:fixture) else {
                throw EngineFailure(message:"LUMARAW_TEST_FIXTURES must provide a readable raster")
            }

            // Connect a real Store's @Published thumbnail fields to the
            // controlled renderer with the same callback assignments used by
            // Store.thumbnailRenderer. This keeps publication counts observable
            // without introducing a timing dependency on the packaged broker.
            let transport=GatedThumbnailTransport()
            let store=Store()
            store.thumbnailRenderer=ThumbnailRenderer(call:transport.call,changed:{[weak store] images,errors in
                store?.thumbnails=images
                store?.thumbnailErrors=errors
            })
            var storePublications=0
            let subscription=store.objectWillChange.sink { _ in storePublications+=1 }
            let first=ThumbnailTarget(id:901,revision:0)
            let second=ThumbnailTarget(id:902,revision:0)

            store.thumbnailRenderer.request([first])
            let initialPublications=storePublications
            try await until({transport.pendingCacheRequests.contains(1)},"first_cache_gate_opened")
            let beforeCacheReply=storePublications
            transport.finishCache(1,entries:[])
            try await until({transport.pendingThumbnailRequests.contains(.init(generation:1,photoID:first.id))},
                            "first_direct_thumbnail_gate_opened")
            try check(storePublications==beforeCacheReply,
                      "unchanged_cache_miss_does_not_republish_store_state")
            transport.finishThumbnail(.init(generation:1,photoID:first.id),revision:0,path:fixture)
            try await until({store.thumbnailRenderer.frames[first.id] != nil && store.thumbnailRenderer.loading.isEmpty},
                            "first_image_adopted")
            let originalImage=store.thumbnailRenderer.frames[first.id]!.image
            try check(store.thumbnails[first.id] === originalImage && storePublications>initialPublications,
                      "changed_renderer_image_reaches_store_published_fields")

            // A forced request must still consult cached_thumbnails so the
            // service revalidates source identity/stat data. The cache hit keeps
            // the same NSImage object; its publish must be deduplicated.
            let beforeForcedCache=storePublications
            store.thumbnailRenderer.request([first,second],force:true)
            try await until({transport.pendingCacheRequests.contains(2)},"forced_cache_gate_opened")
            transport.finishCache(2,entries:[cacheEntry(first.id,first.revision,fixture)])
            try await until({transport.pendingThumbnailRequests.contains(.init(generation:2,photoID:second.id))},
                            "forced_cache_page_finished")
            try check(transport.cacheCalls==2 && store.thumbnailRenderer.frames[first.id]?.image === originalImage &&
                      storePublications==beforeForcedCache,
                      "forced_cache_hit_revalidates_without_duplicate_publication")
            transport.finishThumbnail(.init(generation:2,photoID:second.id),revision:0,path:fixture)
            try await until({store.thumbnailRenderer.frames.count==2 && store.thumbnailRenderer.loading.isEmpty},
                            "second_page_image_adopted")

            // An unchanged forced request still crosses the cache gate. This is
            // the source-stat validation path even when every visible target is
            // already loaded and the resulting image identities are unchanged.
            let beforeSameTargetForce=storePublications
            let firstImage=store.thumbnailRenderer.frames[first.id]!.image
            let secondImage=store.thumbnailRenderer.frames[second.id]!.image
            store.thumbnailRenderer.request([first,second],force:true)
            try await until({transport.pendingCacheRequests.contains(3)},"same_target_forced_cache_gate_opened")
            try check(transport.cacheCalls==3 && transport.cancelledGenerations.contains(3),
                      "same_target_force_still_cancels_old_worker_and_checks_cache")
            transport.finishCache(3,entries:[cacheEntry(first.id,first.revision,fixture),
                                              cacheEntry(second.id,second.revision,fixture)])
            try await settleReleasedResponse()
            try check(store.thumbnailRenderer.loading.isEmpty &&
                      store.thumbnailRenderer.frames[first.id]?.image === firstImage &&
                      store.thumbnailRenderer.frames[second.id]?.image === secondImage &&
                      storePublications==beforeSameTargetForce,
                      "same_target_forced_cache_hit_does_not_republish_store_state")

            // Errors are observable state. A later forced cache hit must clear
            // the previous failure and deliver its recovered image to Store.
            let failed=ThumbnailTarget(id:903,revision:0)
            store.thumbnailRenderer.request([failed])
            try await until({transport.pendingCacheRequests.contains(4)},"error_case_cache_gate_opened")
            transport.finishCache(4,entries:[])
            let failedKey=GatedThumbnailTransport.Key(generation:4,photoID:failed.id)
            try await until({transport.pendingThumbnailRequests.contains(failedKey)},"error_case_thumbnail_gate_opened")
            transport.failThumbnail(failedKey,message:"controlled thumbnail failure")
            try await until({store.thumbnailErrors[failed.id] != nil && store.thumbnailRenderer.loading.isEmpty},
                            "controlled_error_published")
            let beforeRecovery=storePublications
            store.thumbnailRenderer.request([failed],force:true)
            try check(store.thumbnailErrors[failed.id]==nil && storePublications>beforeRecovery,
                      "new_generation_clears_published_thumbnail_error")
            try await until({transport.pendingCacheRequests.contains(5)},"recovery_cache_gate_opened")
            transport.finishCache(5,entries:[cacheEntry(failed.id,failed.revision,fixture)])
            try await until({store.thumbnailRenderer.frames[failed.id] != nil && store.thumbnailRenderer.loading.isEmpty},
                            "recovered_cache_image_adopted")
            try check(store.thumbnailErrors[failed.id]==nil && store.thumbnails[failed.id] != nil,
                      "recovery_callback_clears_error_and_sets_image")

            // Simulate a source-stat cache miss for the same path. Once the old
            // frame is dropped, re-decoding that path creates a new NSImage; the
            // identity change must publish even though the path is unchanged.
            let beforeReload=storePublications
            let reloadTarget=store.thumbnailRenderer.frames[failed.id]!.image
            store.thumbnailRenderer.request([failed],force:true)
            try await until({transport.pendingCacheRequests.contains(6)},"same_path_revalidation_gate_opened")
            transport.finishCache(6,entries:[])
            let reloadKey=GatedThumbnailTransport.Key(generation:6,photoID:failed.id)
            try await until({transport.pendingThumbnailRequests.contains(reloadKey)},"same_path_rerender_started")
            transport.finishThumbnail(reloadKey,revision:failed.revision,path:fixture)
            try await until({store.thumbnailRenderer.frames[failed.id]?.image !== reloadTarget &&
                             store.thumbnailRenderer.loading.isEmpty},"same_path_new_image_adopted")
            let reloaded=store.thumbnailRenderer.frames[failed.id]!
            try check(reloaded.path==fixture && reloaded.image !== reloadTarget && storePublications>beforeReload,
                      "same_path_new_nsimage_identity_is_published")

            // A failed cache validation drops the prior retained frame and
            // falls back to direct thumbnail generation instead of leaving the
            // photo blank or suppressing future work.
            let beforeCacheFailure=storePublications
            let cacheFailureTarget=failed
            store.thumbnailRenderer.request([cacheFailureTarget],force:true)
            try await until({transport.pendingCacheRequests.contains(7)},"cache_failure_gate_opened")
            try check(store.thumbnailRenderer.frames[failed.id]?.image === reloaded.image,
                      "cache_gate_retains_image_until_validation_finishes")
            transport.failCache(7,message:"controlled cache failure")
            let cacheFailureKey=GatedThumbnailTransport.Key(generation:7,photoID:failed.id)
            try await until({transport.pendingThumbnailRequests.contains(cacheFailureKey)},
                            "cache_failure_falls_back_to_direct_thumbnail")
            try check(store.thumbnailRenderer.frames.isEmpty && store.thumbnailRenderer.loading.contains(failed.id),
                      "cache_failure_clears_unverified_old_frame_before_fallback")
            transport.finishThumbnail(cacheFailureKey,revision:failed.revision,path:fixture)
            try await until({store.thumbnailRenderer.frames[failed.id] != nil && store.thumbnailRenderer.loading.isEmpty},
                            "cache_failure_direct_thumbnail_adopted")
            try check(store.thumbnailRenderer.frames[failed.id]?.image != nil && storePublications>beforeCacheFailure,
                      "cache_failure_fallback_recovers_and_publishes_image")

            let beforeClear=storePublications
            store.thumbnailRenderer.request([],force:true)
            try check(store.thumbnailRenderer.frames.isEmpty && store.thumbnailRenderer.errors.isEmpty &&
                      store.thumbnails.isEmpty && store.thumbnailErrors.isEmpty && storePublications>beforeClear,
                      "clearing_page_releases_images_and_publishes_empty_store_state")
            _=subscription

            // A late thumbnail from an old recipe generation cannot replace the
            // accepted image or invoke the changed callback after supersession.
            let delayedTransport=GatedThumbnailTransport()
            var publications:[ThumbnailPublication]=[]
            let renderer=ThumbnailRenderer(call:delayedTransport.call,changed:{images,errors in
                publications.append(ThumbnailPublication(images:images,errors:errors))
            })
            let old=ThumbnailTarget(id:904,revision:0)
            let current=ThumbnailTarget(id:904,revision:1)
            renderer.request([old])
            try await until({delayedTransport.pendingCacheRequests.contains(1)},"old_generation_cache_gate_opened")
            delayedTransport.finishCache(1,entries:[])
            let oldKey=GatedThumbnailTransport.Key(generation:1,photoID:old.id)
            try await until({delayedTransport.pendingThumbnailRequests.contains(oldKey)},"old_generation_thumbnail_gate_opened")
            renderer.request([current])
            try await until({delayedTransport.pendingCacheRequests.contains(2)},"new_generation_cache_gate_opened")
            delayedTransport.finishCache(2,entries:[])
            let currentKey=GatedThumbnailTransport.Key(generation:2,photoID:current.id)
            try await until({delayedTransport.pendingThumbnailRequests.contains(currentKey)},"new_generation_thumbnail_gate_opened")
            delayedTransport.finishThumbnail(currentKey,revision:current.revision,path:fixture)
            try await until({renderer.frames[current.id]?.target==current && renderer.loading.isEmpty},
                            "new_generation_image_adopted")
            let currentImage=renderer.frames[current.id]!.image
            let publicationCount=publications.count
            delayedTransport.finishThumbnail(oldKey,revision:old.revision,path:fixture)
            try await settleReleasedResponse()
            try check(renderer.frames[current.id]?.image === currentImage && publications.count==publicationCount,
                      "late_old_thumbnail_cannot_replace_or_republish_current_frame")
            try check(delayedTransport.cancelledGenerations.contains(1) &&
                      delayedTransport.cancelledGenerations.contains(2),
                      "superseded_requests_keep_generation_cancellation")

            // Clearing a page while its cache lookup is gated invalidates the
            // response before it can repopulate frames with stale content.
            let invalidationTransport=GatedThumbnailTransport()
            let invalidationRenderer=ThumbnailRenderer(call:invalidationTransport.call)
            let stale=ThumbnailTarget(id:905,revision:0)
            invalidationRenderer.request([stale])
            try await until({invalidationTransport.pendingCacheRequests.contains(1)},"invalidation_cache_gate_opened")
            invalidationRenderer.request([],force:true)
            invalidationTransport.finishCache(1,entries:[cacheEntry(stale.id,stale.revision,fixture)])
            try await settleReleasedResponse()
            try check(invalidationRenderer.frames.isEmpty && invalidationRenderer.errors.isEmpty &&
                      invalidationTransport.thumbnailCalls==0,
                      "page_clear_invalidates_pending_cache_response")

            let report:[String:Any]=["ok":true,"checks":checks,"desktop_ui":"NOT_VERIFIED"]
            print(String(data:try JSONSerialization.data(withJSONObject:report,options:[.prettyPrinted,.sortedKeys]),encoding:.utf8)!)
            exit(0)
        } catch {
            print(String(data:try! JSONSerialization.data(withJSONObject:["ok":false,"checks":checks,
                "error":error.localizedDescription],options:.prettyPrinted),encoding:.utf8)!)
            exit(1)
        }
    }
}
