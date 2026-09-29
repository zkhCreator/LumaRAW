// Purpose: bounded temporary previews shared by point and parametric curve controls.
// Inputs: revision-bound, curve-only drafts supplied by native editors.
// Outputs: one in-flight Store render and one coalesced latest draft. No persistence
// or pixel algorithms; committing/cancelling a gesture remains the editor's job.
import SwiftUI

struct CurvePreviewDraft {
    let photoID:Int
    let revision:Int
    let patch:[String:Any]
}

extension PointCurveCapture {
    func preview(_ points:[[Double]]) -> CurvePreviewDraft {
        CurvePreviewDraft(photoID:photoID,revision:revision,patch:[key:points])
    }
}

@MainActor final class CurvePreviewScheduler:ObservableObject {
    private var task:Task<Void,Never>?
    private var generation=0
    func request(store:Store,current:@escaping () -> CurvePreviewDraft?) {
        guard task == nil else {return}
        generation+=1;let token=generation
        task=Task { @MainActor in
            defer {if token == generation {task=nil}}
            try? await Task.sleep(nanoseconds:180_000_000)
            while store.rendering && !Task.isCancelled {
                try? await Task.sleep(nanoseconds:40_000_000)
            }
            guard !Task.isCancelled,token == generation,let draft=current() else {return}
            store.render(curveDraft:draft,debounce:false)
        }
    }
    func cancel() {generation+=1;task?.cancel();task=nil}
}
