// Purpose: bounded temporary previews shared by curves, mixer and Color Grading.
// Inputs: revision-bound, field-scoped drafts supplied by native editors.
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
        enqueue(store:store) {
            guard let draft=current() else {return}
            store.render(curveDraft:draft,debounce:false)
        }
    }
    func requestMixer(store:Store,current:@escaping () -> MixerPreviewDraft?) {
        enqueue(store:store) {
            guard let draft=current() else {return}
            store.render(mixerDraft:draft,debounce:false)
        }
    }
    func requestGrading(store:Store,current:@escaping () -> GradingPreviewDraft?) {
        enqueue(store:store) {
            guard let draft=current() else {return}
            store.render(gradingDraft:draft,debounce:false)
        }
    }
    private func enqueue(store:Store,action:@escaping () -> Void) {
        guard task == nil else {return}
        generation+=1;let token=generation
        task=Task { @MainActor in
            defer {if token == generation {task=nil}}
            try? await Task.sleep(nanoseconds:180_000_000)
            while store.rendering && !Task.isCancelled {
                try? await Task.sleep(nanoseconds:40_000_000)
            }
            guard !Task.isCancelled,token == generation else {return}
            action()
        }
    }
    func cancel() {generation+=1;task?.cancel();task=nil}
}
