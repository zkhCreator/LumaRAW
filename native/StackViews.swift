// Purpose: source-scoped stack commands and visible cover/count controls.
// Inputs: Store page metadata. Outputs: explicit stack actions only.
// Hidden photos are not selected by clicking a collapsed stack's badge.
import SwiftUI

struct StackActions: View {
    @EnvironmentObject var s: Store
    var photoID: Int? = nil
    var ids: [Int] {
        if let photoID,!s.actionPhotoIDs.contains(photoID) { return [photoID] }
        return s.actionPhotoIDs
    }
    var active: Int? { photoID ?? s.selected }
    var stack: PhotoStack? { active.flatMap { s.photoStacks[$0] } }
    var body: some View {
        Menu("Stacking") {
            Button("Group into Stack") { Task { await s.changeStack("group",ids:ids) } }
                .keyboardShortcut("g",modifiers:.command)
                .disabled(ids.count < 2)
            Button("Unstack") { Task { await s.changeStack("unstack",ids:ids) } }
                .keyboardShortcut("g",modifiers:[.command,.shift])
                .disabled(!ids.contains { s.photoStacks[$0] != nil })
            Divider()
            Button(stack?.collapsed == true ? "Expand Stack":"Collapse Stack") {
                if let active { Task { await s.changeStack("toggle",ids:[active]) } }
            }.disabled(stack == nil)
            Button("Remove from Stack") { Task { await s.changeStack("remove",ids:ids) } }
                .disabled(!ids.contains { s.photoStacks[$0] != nil })
            Button("Split Stack") { Task { await s.changeStack("split",ids:ids) } }
                .disabled(stack == nil || stack?.collapsed == true || ids == [stack?.top ?? -1])
            Divider()
            Button("Move to Top of Stack") { if let active { Task { await s.changeStack("top",ids:[active]) } } }
                .disabled(stack == nil || stack?.top == active)
            Button("Move Up in Stack") { if let active { Task { await s.changeStack("up",ids:[active]) } } }.disabled(stack == nil)
            Button("Move Down in Stack") { if let active { Task { await s.changeStack("down",ids:[active]) } } }.disabled(stack == nil)
            Divider()
            Button("Expand All Stacks") { Task { await s.setStackVisibility(collapsed:false) } }
            Button("Collapse All Stacks") { Task { await s.setStackVisibility(collapsed:true) } }
            Divider()
            Button("Auto-Stack by Capture Time…") { s.prepareAutoStack() }
        }.disabled(!s.canStack)
    }
}

struct StackBadge: View {
    @EnvironmentObject var s: Store
    let photoID: Int
    var body: some View {
        if let stack=s.photoStacks[photoID] {
            Button { Task { await s.changeStack("toggle",ids:[photoID]) } } label: {
                HStack(spacing:3) {
                    Image(systemName:stack.collapsed ? "square.stack.fill":"square.stack")
                    Text("\(stack.count)").monospacedDigit()
                }.font(.caption2).padding(4).foregroundStyle(.white)
                    .background(.black.opacity(0.75),in:RoundedRectangle(cornerRadius:3))
            }.buttonStyle(.plain).disabled(!s.canStack)
                .help("\(stack.collapsed ? "Expand":"Collapse") stack of \(stack.count) photos")
                .accessibilityLabel("\(stack.collapsed ? "Expand":"Collapse") stack of \(stack.count) photos\(stack.top == photoID ? ", top photo":"")")
        }
    }
}
