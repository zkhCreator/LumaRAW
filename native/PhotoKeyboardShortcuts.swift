// Purpose: photo-only single-key shortcuts scoped to focused viewing surfaces.
// Inputs: key events from the grid, filmstrip or canvas. Outputs: Store actions.
// Non-goals: global menu accelerators or intercepting metadata/search text input.
// Command shortcuts retain their standard native menu or focused-grid behavior.
import SwiftUI

struct PhotoKeyboardShortcuts: ViewModifier {
    @EnvironmentObject var s: Store

    func body(content: Content) -> some View {
        content.onKeyPress(characters:CharacterSet(charactersIn:"012345pxu\\")) { press in
            guard press.modifiers.isEmpty, s.selected != nil else { return .ignored }
            if let rating=Int(press.characters), (0...5).contains(rating) {
                s.rate(rating)
                return .handled
            }
            switch press.characters {
            case "p": s.flag(1)
            case "x": s.flag(-1)
            case "u": s.flag(0)
            case "\\": s.compare.toggle()
            default: return .ignored
            }
            return .handled
        }
    }
}
