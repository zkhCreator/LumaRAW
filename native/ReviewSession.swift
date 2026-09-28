// Purpose: value-state rules for Library Loupe, Compare and Survey workflows.
// Inputs: a bounded visible page, selection and explicit navigation/zoom actions.
// Outputs: ordered review IDs and normalized viewport requests for the renderer.
// Non-goals: pixels, catalog mutation, file access or platform event handling.
import Foundation

enum LibraryViewMode: String, CaseIterable {
    case grid, loupe, compare, survey
    var title: String { rawValue.capitalized }
    var symbol: String {
        switch self {
        case .grid: return "square.grid.2x2"
        case .loupe: return "rectangle"
        case .compare: return "rectangle.split.2x1"
        case .survey: return "rectangle.split.3x3"
        }
    }
}

struct ReviewViewport: Equatable, Hashable {
    // Zero means Fit. Other values are physical screen pixels per image pixel.
    var zoom: Double = 0
    var cx: Double = 0.5
    var cy: Double = 0.5

    mutating func move(x: Double, y: Double) {
        cx=min(1,max(0,x));cy=min(1,max(0,y))
    }
}

struct ReviewSession: Equatable {
    var pool: [Int] = []
    var selectID: Int?
    var candidateID: Int?
    var usesPagePool=false
    var excluded: Set<Int> = []
    var linked=true
    var viewports: [Int: ReviewViewport] = [:]

    var pair: [Int] { [selectID,candidateID].compactMap { $0 } }

    mutating func begin(visible: [Int], selection: Set<Int>, active: Int?) {
        let picked=visible.filter { selection.contains($0) }
        usesPagePool=picked.count < 2
        pool=usesPagePool ? visible:picked
        selectID=active.flatMap { pool.contains($0) ? $0:nil } ?? pool.first
        let start=pool.firstIndex(of:selectID ?? -1) ?? 0
        candidateID=pool.indices.dropFirst(start+1).map { pool[$0] }.first ?? pool.first { $0 != selectID }
        viewports=[:];linked=true;excluded=[]
    }

    mutating func reconcile(visible: [Int], selection: Set<Int>) {
        pool=usesPagePool ? visible.filter { !excluded.contains($0) }:visible.filter { selection.contains($0) }
        if !pool.contains(selectID ?? -1) { selectID=pool.first }
        if !pool.contains(candidateID ?? -1) || candidateID == selectID {
            candidateID=pool.first { $0 != selectID }
        }
        viewports=viewports.filter { pool.contains($0.key) }
    }

    mutating func chooseCandidate(_ id: Int) {
        guard id != selectID else { return }
        excluded.remove(id)
        if !pool.contains(id) { pool.append(id) }
        candidateID=id
        if linked,let selectID { viewports[id]=viewports[selectID] ?? ReviewViewport() }
    }

    mutating func advance(_ direction: Int) {
        let candidates=pool.filter { $0 != selectID }
        guard !candidates.isEmpty else { candidateID=nil;return }
        let index=candidates.firstIndex(of:candidateID ?? -1) ?? 0
        // Clamp at either end; repeated navigation must not unexpectedly wrap.
        chooseCandidate(candidates[min(candidates.count-1,max(0,index+direction))])
    }

    mutating func swap() {
        guard candidateID != nil else { return }
        let old=selectID;selectID=candidateID;candidateID=old
    }

    mutating func promote() {
        guard let candidateID else { return }
        selectID=candidateID
        let index=pool.firstIndex(of:candidateID) ?? 0
        self.candidateID=pool.dropFirst(index+1).first ?? pool.first { $0 != candidateID }
        if linked,let next=self.candidateID { viewports[next]=viewports[candidateID] ?? ReviewViewport() }
    }

    mutating func remove(_ id: Int) {
        pool.removeAll { $0 == id };viewports.removeValue(forKey:id);excluded.insert(id)
        if selectID == id { selectID=candidateID == id ? nil:candidateID }
        if selectID == nil { selectID=pool.first }
        if candidateID == id || candidateID == selectID { candidateID=pool.first { $0 != selectID } }
    }

    mutating func setViewport(_ value: ReviewViewport, for id: Int) {
        if linked {
            for photoID in pair { viewports[photoID]=value }
        } else { viewports[id]=value }
    }

    mutating func synchronize(from id: Int) {
        let value=viewports[id] ?? ReviewViewport()
        for photoID in pair { viewports[photoID]=value }
    }
}
