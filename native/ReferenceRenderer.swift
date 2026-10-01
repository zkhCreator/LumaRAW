// Purpose: one independently cancellable, revision-bound Develop reference image.
// Inputs: captured photo identity, display options and a bounded Fit/1:1 viewport.
// Outputs: an ICC-tagged image and validated ROI or a visible retryable error.
// Uses the shared preview service; no pixel algorithms, catalog writes or Before
// processing. Active-photo renders never replace or cancel this client's work.
import AppKit
import SwiftUI

struct ReferenceRequest:Equatable {
    let context:BeforePreviewContext
    let proofPath:String
    var params:[String:Any] {
        var result:[String:Any]=["photo_id":context.photoID,"expected_revision":context.revision,
                                "include_before":false,"include_color_readouts":true,"display":["gamut":context.gamut]]
        if !proofPath.isEmpty {
            result["display"]=["gamut":context.gamut,"proof_path":proofPath,"proof_sha":context.proofSHA]
        }
        if context.detail {
            result["detail"]=["cx":context.cx,"cy":context.cy,"width":context.width,"height":context.height]
        } else {result["max_edge"]=1680}
        return result
    }
}

struct ReferenceFrame {
    let request:ReferenceRequest
    let image:NSImage
    let region:BeforeAfterFrame
    let colors:ColorReadoutFrame?
}

@MainActor final class ReferenceRenderer:ObservableObject {
    @Published private(set) var frame:ReferenceFrame?
    @Published private(set) var error:String?
    @Published private(set) var loading=false
    private(set) var generation=0
    private let client=UUID().uuidString
    private var task:Task<Void,Never>?
    private var current:ReferenceRequest?
    private let call:(String,[String:Any]) async throws -> [String:Any]

    init(call:@escaping (String,[String:Any]) async throws -> [String:Any]=Backend.call) {self.call=call}

    func request(_ request:ReferenceRequest,force:Bool=false) {
        guard force || request != current else {return}
        generation+=1;let token=generation
        task?.cancel();current=request;frame=nil;error=nil;loading=true
        task=Task { [weak self] in
            guard let self else {return}
            _=try? await call("cancel_preview",["client_id":client,"generation":token])
            guard !Task.isCancelled,token==generation else {return}
            var params=request.params;params["client_id"]=client;params["generation"]=token
            do {
                let reply=try await call("preview_photo",params)
                guard !Task.isCancelled,token==generation else {return}
                guard reply["photo_id"] as? Int == request.context.photoID,
                      reply["revision"] as? Int == request.context.revision,
                      let geometry=PhotoPreviewGeometry(reply),geometry.orientation==request.context.orientation,
                      geometry.detail==request.context.detail,
                      let region=BeforeAfterFrame(reply,context:request.context),
                      let path=reply["preview"] as? String else {
                    throw EngineFailure(message:"The reference preview changed or could not be loaded. Refresh the reference photo.")
                }
                async let loadedImage=PreviewImageLoader.load(path)
                async let loadedColors=ColorReadoutLoader.frame(reply,context:request.context)
                let (loaded,colors)=await (loadedImage,loadedColors)
                guard !Task.isCancelled,token==generation else {return}
                guard let image=loaded else {throw EngineFailure(message:"The reference preview could not be loaded. Refresh the reference photo.")}
                frame=ReferenceFrame(request:request,image:image,region:region,colors:colors)
            } catch {
                guard !Task.isCancelled,token==generation else {return}
                self.error=error.localizedDescription
            }
            loading=false
        }
    }

    func stop() {
        guard current != nil || task != nil else {return}
        generation+=1;let token=generation
        task?.cancel();task=nil;current=nil;frame=nil;error=nil;loading=false
        Task {_=try? await call("cancel_preview",["client_id":client,"generation":token])}
    }
}
