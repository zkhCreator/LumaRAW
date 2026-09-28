// Purpose: bounded, revision-aware comparison previews through the shared engine.
// Inputs: at most 60 small fitted requests or two full-resolution viewports.
// Outputs: ICC-tagged NSImages and per-photo errors. Stale replies never repaint.
// No image algorithms or SQL; a separate client generation cancels only review work.
import AppKit
import Foundation
import SwiftUI

struct ReviewRequest: Equatable, Hashable {
    let photoID: Int
    let revision: Int
    let viewport: ReviewViewport
    let width: Int
    let height: Int
    let edge: Int
    var params: [String: Any] {
        var result: [String: Any] = ["photo_id":photoID,"include_before":false]
        if viewport.zoom > 0 {
            result["detail"]=["cx":viewport.cx,"cy":viewport.cy,"width":width,"height":height]
        } else { result["max_edge"]=edge }
        return result
    }
}

struct ReviewFrame {
    let request: ReviewRequest
    let image: NSImage
    let revision: Int
    let fullWidth: Int
    let fullHeight: Int
    let width: Int
    let height: Int
}

@MainActor final class ReviewRenderer: ObservableObject {
    @Published private(set) var frames: [Int: ReviewFrame] = [:]
    @Published private(set) var errors: [Int: String] = [:]
    @Published private(set) var loading: Set<Int> = []
    private(set) var generation=0
    private let client=UUID().uuidString
    private var task: Task<Void,Never>?
    private var requests: [ReviewRequest] = []
    private let call: (String, [String: Any]) async throws -> [String: Any]

    init(call: @escaping (String, [String: Any]) async throws -> [String: Any] = Backend.call) {
        self.call=call
    }

    func request(_ next: [ReviewRequest], force: Bool=false) {
        guard next != requests || force else { return }
        generation+=1;let token=generation
        task?.cancel();requests=next
        let ids=Set(next.map(\.photoID))
        frames=frames.filter { id,frame in !force && ids.contains(id) && next.contains(frame.request) }
        errors=[:];loading=Set(next.filter { frames[$0.photoID] == nil }.map(\.photoID))
        task=Task { [weak self] in
            guard let self else { return }
            // Supersede work immediately even if all requested frames are cached.
            _=try? await call("cancel_preview",["client_id":client,"generation":token])
            for request in next {
                guard !Task.isCancelled,token == generation else { return }
                if frames[request.photoID] != nil { continue }
                var params=request.params
                params["client_id"]=client;params["generation"]=token
                do {
                    let result=try await call("preview_photo",params)
                    guard !Task.isCancelled,token == generation else { return }
                    guard result["photo_id"] as? Int == request.photoID,
                          let path=result["preview"] as? String,let image=NSImage(contentsOfFile:path) else {
                        throw EngineFailure(message:"The comparison preview could not be loaded")
                    }
                    frames[request.photoID]=ReviewFrame(request:request,image:image,
                        revision:result["revision"] as? Int ?? request.revision,
                        fullWidth:result["full_width"] as? Int ?? 1,fullHeight:result["full_height"] as? Int ?? 1,
                        width:result["width"] as? Int ?? 1,height:result["height"] as? Int ?? 1)
                } catch {
                    guard !Task.isCancelled,token == generation else { return }
                    errors[request.photoID]=error.localizedDescription
                }
                loading.remove(request.photoID)
            }
        }
    }

    func stop() {
        guard !requests.isEmpty || task != nil else { return }
        generation+=1;let token=generation
        task?.cancel();task=nil;requests=[];frames=[:];errors=[:];loading=[]
        Task { _=try? await call("cancel_preview",["client_id":client,"generation":token]) }
    }
}
