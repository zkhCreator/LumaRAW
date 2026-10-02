// Purpose: photo-only shortcuts, including documented Shift culling actions.
// Inputs: key events from focused viewing surfaces. Outputs: captured Store actions.
// Non-goals: global menu accelerators, text input, Auto Advance preferences or Caps Lock behavior.
// Command shortcuts retain their standard native menu or focused-grid behavior.
import SwiftUI

struct PhotoKeyboardShortcuts: ViewModifier {
    @EnvironmentObject var s: Store

    func body(content: Content) -> some View {
        content.onKeyPress(.escape) {
            if s.whiteBalanceTargetActive || s.whiteBalanceSampling || s.whiteBalanceArming {
                s.cancelWhiteBalanceSelector();return .handled
            }
            guard s.painterEnabled else { return .ignored }
            s.setPainting(false);return .handled
        }.onKeyPress(characters:CharacterSet(charactersIn:"kK")) { press in
            guard press.modifiers == .shift,s.keywordShortcut?.ids.isEmpty == false else { return .ignored }
            s.applyKeywordShortcut();return .handled
        }.onKeyPress(.delete) {
            let ids=s.actionPhotoIDs
            guard !ids.isEmpty else { return .ignored }
            if let collection=s.activeCollection,collection.id == s.collectionID,
               ["regular","quick"].contains(collection.kind) {
                s.beginCollectionMembership(collection,action:"remove",ids:ids)
            } else if s.photos.filter({ids.contains($0.id)}).allSatisfy(\.isVirtual) {
                Task { await s.prepareCopyRemoval() }
            } else { return .ignored }
            return .handled
        }.onKeyPress(characters:CharacterSet(charactersIn:"sS[]{}")) { press in
            guard let id=s.selected,s.canStack,s.photoStacks[id] != nil else { return .ignored }
            if press.modifiers.isEmpty,press.characters == "s" {
                Task { await s.changeStack("toggle",ids:[id]) };return .handled
            }
            if press.modifiers == .shift {
                let action: String
                switch press.characters.lowercased() {
                case "s": action="top"
                case "[","{": action="up"
                case "]","}": action="down"
                default: return .ignored
                }
                Task { await s.changeStack(action,ids:[id]) };return .handled
            }
            return .ignored
        }.onKeyPress(characters:CharacterSet(charactersIn:"rR")) { press in
            guard press.modifiers == .shift,s.selected != nil else {return .ignored}
            Task {await s.startReferenceView()};return .handled
        }.onKeyPress(characters:CharacterSet(charactersIn:"wW")) { press in
            guard press.modifiers.isEmpty,s.workspace=="library",s.develop,s.selected != nil else {return .ignored}
            if s.whiteBalanceTargetActive || s.whiteBalanceSampling || s.whiteBalanceArming {
                s.cancelWhiteBalanceSelector();return .handled
            }
            Task {await s.armWhiteBalanceSelector()};return .handled
        }.onKeyPress(characters:CharacterSet(charactersIn:"yY¥")) { press in
            s.comparisonShortcut(press.modifiers) ? .handled:.ignored
        }.onKeyPress(characters:CharacterSet(charactersIn:"0123456789pPxXuU\\gecnd/b")) { press in
            guard s.selected != nil else { return .ignored }
            let key=press.characters.lowercased()
            let shifted=press.modifiers == .shift
            guard shifted || press.modifiers.isEmpty else { return .ignored }
            if let action=CullingShortcutMapper.action(for:key,shifted:shifted) {
                if shifted || actionRequiresLibrary(action) {
                    guard s.workspace == "library",!s.develop else { return .ignored }
                }
                return s.applyCullingShortcut(
                    action.mutation,
                    advanceAfterSuccess:action.advanceAfterSuccess,
                    refreshAfterMetadataMutation:action.refreshAfterMetadataMutation
                ) ? .handled:.ignored
            }
            guard !shifted else { return .ignored }
            switch key {
            case "b": Task { await s.toggleTargetMembership() }
            case "\\": if s.develop {s.setComparisonMode(s.compare ? "after":"before")} else {s.showLibraryFilters=true}
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

    private func actionRequiresLibrary(_ action: CullingShortcutAction) -> Bool {
        if case .colorLabel(_) = action.mutation { return true }
        return false
    }
}
