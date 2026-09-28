// Purpose: connect review selection/navigation to the bounded native catalog page.
// Inputs: explicit view, candidate, focus, zoom and pan actions. Outputs: review
// state, captured per-photo mutations and lightweight revision-aware preview work.
// No catalog or pixel processing; excluding a photo only changes the selection.
import AppKit
import Foundation

extension Store {
    var isMultiReview: Bool { workspace == "library" && !develop && (libraryView == .compare || libraryView == .survey) }
    var actionPhotoIDs: [Int] {
        (!develop && libraryView == .grid) ? selection.sorted() : selected.map { [$0] } ?? []
    }
    var reviewPhotoIDs: [Int] {
        if libraryView == .compare { return review.pair }
        return photos.filter { selection.contains($0.id) }.map(\.id)
    }

    func switchLibraryView(_ view: LibraryViewMode) async {
        reviewSwitchGeneration+=1;let token=reviewSwitchGeneration
        guard await flushEdits(), !browsing,token == reviewSwitchGeneration else { return }
        develop=false;workspace="library";libraryView=view
        canvasTool="view";compare=false;splitCompare=false;detail=false
        if view == .compare {
            review.begin(visible:photos.map(\.id),selection:selection,active:selected)
            if review.usesPagePool { selection=Set(review.pair) }
            if let id=review.selectID { activateReviewPhoto(id) }
        }
        if isMultiReview { cancelMainPreview();updateReviewRequests() }
        else { reviewRenderer.stop();if view == .loupe { render() } }
    }

    func startDevelop() async {
        reviewSwitchGeneration+=1;let token=reviewSwitchGeneration
        guard await flushEdits(),token == reviewSwitchGeneration else { return }
        reviewRenderer.stop();workspace="library";develop=true;render()
    }

    func reviewSelectionChanged() {
        guard isMultiReview else { return }
        if libraryView == .compare {
            review.reconcile(visible:photos.map(\.id),selection:selection)
            if review.usesPagePool { selection=Set(review.pair) }
        }
        updateReviewRequests()
    }

    func reviewNavigate(_ direction: Int) {
        guard isMultiReview,canChangePhoto else { return }
        if libraryView == .compare {
            review.advance(direction)
            if review.usesPagePool { selection=Set(review.pair) }
            if let id=review.candidateID { activateReviewPhoto(id) }
        } else {
            let ids=reviewPhotoIDs
            guard !ids.isEmpty else { return }
            let index=ids.firstIndex(of:selected ?? -1) ?? 0
            activateReviewPhoto(ids[min(ids.count-1,max(0,index+direction))])
        }
        updateReviewRequests()
    }

    func swapReview() {
        guard canChangePhoto else { return }
        review.swap()
        if let id=review.selectID { activateReviewPhoto(id) }
        updateReviewRequests()
    }

    func promoteReview() {
        guard canChangePhoto else { return }
        review.promote()
        if review.usesPagePool { selection=Set(review.pair) }
        if let id=review.selectID { activateReviewPhoto(id) }
        updateReviewRequests()
    }

    func deselectReviewPhoto(_ id: Int) {
        guard canChangePhoto else { return }
        selection.remove(id)
        if libraryView == .compare {
            review.remove(id)
            if review.usesPagePool { selection=Set(review.pair) }
        }
        let remaining=reviewPhotoIDs
        if selected == id || !remaining.contains(selected ?? -1) {
            if let next=remaining.first { activateReviewPhoto(next) }
            else { selected=nil;clearPhoto() }
        }
        updateReviewRequests()
    }

    func setReviewViewport(_ value: ReviewViewport, id: Int, render: Bool=true) {
        review.setViewport(value,for:id)
        if render { updateReviewRequests() }
    }

    func navigateLoupe(_ direction: Int) {
        guard let index=photos.firstIndex(where: { $0.id == selected }),!photos.isEmpty else { return }
        choose(photos[min(photos.count-1,max(0,index+direction))].id)
    }

    func setReviewPaneSize(_ size: CGSize, scale: Double) {
        let width=max(1,Int((size.width*scale).rounded()))
        let height=max(1,Int((size.height*scale).rounded()))
        guard reviewPaneWidth != width || reviewPaneHeight != height else { return }
        reviewPaneWidth=width;reviewPaneHeight=height
        updateReviewRequests()
    }

    func updateReviewRequests(force: Bool=false) {
        guard isMultiReview else { return }
        let requests=reviewPhotoIDs.compactMap { id -> ReviewRequest? in
            guard let row=photos.first(where: { $0.id == id }) else { return nil }
            let viewport=libraryView == .compare ? review.viewports[id] ?? ReviewViewport():ReviewViewport()
            return ReviewRequest(photoID:id,revision:row.revision,viewport:viewport,
                width:viewport.zoom > 0 ? max(1,min(2048,Int(Double(reviewPaneWidth)/viewport.zoom))):1,
                height:viewport.zoom > 0 ? max(1,min(1536,Int(Double(reviewPaneHeight)/viewport.zoom))):1,
                edge:libraryView == .survey ? 512:1680)
        }
        reviewRenderer.request(requests,force:force)
    }
}
