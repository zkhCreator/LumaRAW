// Purpose: keep the visible library page and its edited thumbnails current.
// Inputs: bounded page summaries, local edits and external-client polling.
// Outputs: revision-keyed thumbnail requests and changed summary rows only.
// Full inspector recipes retain their separate optimistic-conflict barrier.
import Foundation

extension Store {
    func updateThumbnails(force: Bool=false) {
        thumbnailRenderer.request(photos.map { ThumbnailTarget(id:$0.id,revision:$0.revision,sourcePath:$0.path) },force:force)
    }

    func refreshVisibleSummaries() async {
        let snapshot=photos
        let ids=snapshot.map(\.id)
        guard !browsing else { return }
        if ids.isEmpty {
            if let result=try? await Backend.call("stack_state"),let revision=result["revision"] as? Int,
               !browsing,photos.isEmpty,revision != stackRevision { await refresh() }
            return
        }
        do {
            let result=try await Backend.call("photo_summaries",["photo_ids":ids])
            guard !browsing,photos.map(\.id) == ids else { return }
            if let revision=result["stack_revision"] as? Int,revision != stackRevision { await refresh();return }
            let rows=result["photos"] as? [[String:Any]] ?? []
            if rows.count != ids.count { await refresh();return }
            for row in rows {
                guard let updated=Photo(row),let index=photos.firstIndex(where: { $0.id == updated.id }) else { continue }
                // If local metadata/culling/recipe changed during this read, keep
                // it and let the next poll reconcile. Never regress a revision.
                guard photos[index].sameSummary(as:snapshot[index]),
                      updated.revision >= photos[index].revision,
                      updated.metadataRevision >= photos[index].metadataRevision else { continue }
                if !updated.sameSummary(as:photos[index]) { photos[index]=updated }
                if var current=photo,current.id == updated.id,current.sourceRevision <= updated.sourceRevision {
                    // Family structure may change without an edit revision. Keep
                    // the inspector's recipe/metadata conflict barriers intact.
                    current.sourceID=updated.sourceID;current.sourceRevision=updated.sourceRevision
                    current.masterID=updated.masterID;current.isVirtual=updated.isVirtual;photo=current
                }
            }
            updateThumbnails()
            updateReviewRequests()
            await refreshCollectionState()
        } catch { message=error.localizedDescription }
    }
}

extension Photo {
    func sameSummary(as other: Photo) -> Bool {
        id == other.id && revision == other.revision && metadataRevision == other.metadataRevision &&
        name == other.name && path == other.path && rating == other.rating && flag == other.flag &&
        title == other.title && colorLabel == other.colorLabel && copyName == other.copyName &&
        sourceID == other.sourceID && sourceRevision == other.sourceRevision &&
        masterID == other.masterID && isVirtual == other.isVirtual
    }
}
