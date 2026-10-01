// Purpose: revision-aware developed thumbnails for one bounded native page.
// Inputs: visible IDs/revisions and a shared command transport. Outputs: retained
// file-backed images or per-photo errors. No pixels, SQL, or recipe ownership.
// A separate client generation cancels obsolete page work without touching export.
import AppKit
import Foundation

struct ThumbnailTarget: Equatable, Hashable {
    let id: Int
    let revision: Int
    var sourcePath: String = ""
}

struct ThumbnailFrame {
    let target: ThumbnailTarget
    let path: String
    let image: NSImage
}

@MainActor final class ThumbnailRenderer {
    private(set) var frames: [Int: ThumbnailFrame] = [:]
    private(set) var errors: [Int: String] = [:]
    private(set) var loading: Set<Int> = []
    private var targets: [ThumbnailTarget] = []
    private var generation=0
    private let client=UUID().uuidString
    private var task: Task<Void,Never>?
    private let call: (String,[String:Any]) async throws -> [String:Any]
    private let changed: ([Int:NSImage],[Int:String]) -> Void

    init(call: @escaping (String,[String:Any]) async throws -> [String:Any] = Backend.call,
         changed: @escaping ([Int:NSImage],[Int:String]) -> Void = { _,_ in }) {
        self.call=call;self.changed=changed
    }

    func request(_ next: [ThumbnailTarget], force: Bool=false) {
        guard force || next != targets else { return }
        generation+=1;let token=generation
        task?.cancel();targets=next
        let wanted=Set(next)
        frames=frames.filter { wanted.contains($0.value.target) }
        errors=[:];loading=Set(next.filter { self.frames[$0.id] == nil }.map(\.id))
        publish()
        task=Task { [weak self] in
            guard let self else { return }
            _=try? await call("cancel_preview",["client_id":client,"generation":token])
            guard !next.isEmpty,!Task.isCancelled,token == generation else { return }
            do {
                let result=try await call("cached_thumbnails",["photo_ids":next.map(\.id),"kind":"developed"])
                guard !Task.isCancelled,token == generation else { return }
                let entries=result["thumbnails"] as? [[String:Any]] ?? []
                var cached: Set<Int> = []
                for entry in entries {
                    if await adopt(entry,wanted:wanted,token:token) { cached.insert(entry["photo_id"] as! Int) }
                    guard !Task.isCancelled,token==generation else {return}
                }
                // Even unchanged recipe revisions need fresh source-stat checks.
                // Remove a previous frame if the broker no longer recognizes it.
                frames=frames.filter { cached.contains($0.key) }
                loading=Set(next.filter { self.frames[$0.id] == nil }.map(\.id))
                publish()
            } catch {
                guard !Task.isCancelled,token == generation else { return }
                // A cache query failure must not permanently suppress direct work.
                frames=[:];loading=Set(next.map(\.id));publish()
            }
            for target in next {
                guard !Task.isCancelled,token == generation else { return }
                if frames[target.id] != nil { continue }
                do {
                    let result=try await call("thumbnail",["photo_id":target.id,"kind":"developed",
                        "client_id":client,"generation":token])
                    guard !Task.isCancelled,token == generation else { return }
                    let accepted=await adopt(result,wanted:[target],token:token)
                    guard !Task.isCancelled,token==generation else {return}
                    if !accepted {
                        errors[target.id]="Photo changed while its thumbnail was being generated; refresh the library"
                    }
                } catch {
                    guard !Task.isCancelled,token == generation else { return }
                    errors[target.id]=error.localizedDescription
                }
                loading.remove(target.id);publish()
            }
        }
    }

    private func adopt(_ row: [String:Any], wanted: Set<ThumbnailTarget>,token:Int) async -> Bool {
        guard let id=row["photo_id"] as? Int,let revision=row["revision"] as? Int,
              row["kind"] as? String == "developed",let path=row["thumbnail"] as? String else { return false }
        guard let target=wanted.first(where: { $0.id == id && $0.revision == revision &&
            ($0.sourcePath.isEmpty || row["source"] as? String == $0.sourcePath) }) else { return false }
        if let existing=frames[id],existing.target == target,existing.path == path { return true }
        let loaded=await PreviewImageLoader.load(path)
        guard !Task.isCancelled,token==generation,let image=loaded else {return false}
        frames[id]=ThumbnailFrame(target:target,path:path,image:image)
        return true
    }

    private func publish() { changed(frames.mapValues(\.image),errors) }
}
