// Purpose: photo-only single-key shortcuts scoped to focused viewing surfaces.
// Inputs: key events from the grid, filmstrip or canvas. Outputs: Store actions.
// Non-goals: global menu accelerators or intercepting metadata/search text input.
// Command shortcuts retain their standard native menu or focused-grid behavior.
import SwiftUI

struct PhotoKeyboardShortcuts: ViewModifier {
    @EnvironmentObject var s: Store

    func body(content: Content) -> some View {
        content.onKeyPress(.delete) {
            guard !s.actionPhotoIDs.isEmpty else { return .ignored }
            if let collection=s.activeCollection,collection.id == s.collectionID,
               ["regular","quick"].contains(collection.kind) {
                Task { await s.changeMembership(collection,action:"remove",ids:s.actionPhotoIDs) }
            } else if s.photos.filter({s.actionPhotoIDs.contains($0.id)}).allSatisfy(\.isVirtual) {
                Task { await s.prepareCopyRemoval() }
            } else { return .ignored }
            return .handled
        }.onKeyPress(characters:CharacterSet(charactersIn:"012345pxu\\gecnd/b")) { press in
            guard press.modifiers.isEmpty, s.selected != nil else { return .ignored }
            if let rating=Int(press.characters), (0...5).contains(rating) {
                s.rate(rating)
                return .handled
            }
            switch press.characters {
            case "b": Task { await s.toggleTargetMembership() }
            case "p": s.flag(1)
            case "x": s.flag(-1)
            case "u": s.flag(0)
            case "\\": if s.develop {s.compare.toggle()} else {s.showLibraryFilters=true}
            case "g": Task { await s.switchLibraryView(.grid) }
            case "e": Task { await s.switchLibraryView(.loupe) }
            case "c": Task { await s.switchLibraryView(.compare) }
            case "n": Task { await s.switchLibraryView(.survey) }
            case "d": Task { await s.startDevelop() }
            case "/": if s.isMultiReview,let id=s.selected {s.deselectReviewPhoto(id)} else {return .ignored}
            default: return .ignored
            }
            return .handled
        }
    }
}
