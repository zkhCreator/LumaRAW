// Purpose: native macOS lifecycle, standard menus and settings scene.
// Inputs: menu actions / file-open events. Outputs: Store workflows.
// Domain processing stays in the platform-neutral engine.
import SwiftUI
import AppKit

@main struct LumaRAWApp: App {
    @StateObject private var store=Store()
    var body: some Scene {
        WindowGroup("LumaRAW") {
            ContentView().environmentObject(store)
                .frame(minWidth:1000,minHeight:660)
                .task {await store.start()}
                .onOpenURL {url in Task{await store.importPaths([url.path])}}
        }
        .defaultSize(width:1440,height:920)
        .commands {
            CommandGroup(replacing:.newItem) {
                Button("Import Photos…"){store.importPanel()}.keyboardShortcut("i")
                Button("Export Selected Photos…"){store.showExport=true}.keyboardShortcut("e",modifiers:[.command,.shift]).disabled(store.selected==nil)
            }
            CommandGroup(replacing:.undoRedo) {
                Button("Undo Last Adjustment"){store.undo()}.keyboardShortcut("z").disabled(store.photo==nil || store.editing)
            }
            CommandMenu("Photo") {
                Button("Edit Selected Metadata…"){Task{await store.prepareMetadataEditor()}}.disabled(store.selection.isEmpty)
                Menu("Set Color Label") {
                    ForEach(LibraryLabels.names,id:\.self) { label in
                        Button(label.capitalized) { store.labelSelection(label) }
                    }
                }.disabled(store.selection.isEmpty)
                Divider()
                Button("Copy Adjustments"){store.copyEdits()}.keyboardShortcut("c",modifiers:[.command,.shift])
                Button("Paste Adjustments"){store.pasteEdits()}.keyboardShortcut("v",modifiers:[.command,.shift])
                Button("Sync Selected Photos…"){store.showSync=true}.disabled(store.selection.count<2)
                Divider()
                ForEach(0..<6){value in Button(value==0 ? "Clear Rating":"\(value) \(value == 1 ? "Star" : "Stars")"){store.rate(value)}}
                Button("Flag as Pick"){store.flag(1)}
                Button("Flag as Rejected"){store.flag(-1)}
                Button("Clear Flag"){store.flag(0)}
                Divider()
                Button("Show in Finder"){store.reveal()}
                Button("Locate Missing Original…"){store.relink()}
            }
            CommandMenu("Library") {
                Button("New Collection…") { store.editCollection() }.keyboardShortcut("n",modifiers:[.command,.shift])
                Button("Filter Photos…") { store.showLibraryFilters=true }
                Button("Refresh Library") { Task { await store.refreshCollections(); await store.refresh() } }
            }
            CommandGroup(after:.toolbar) {
                Button("Show Adjustment Inspector"){store.showInspector.toggle()}.keyboardShortcut("i",modifiers:[.command,.option])
                Button("Before / After"){store.compare.toggle()}
                Button("Full Resolution 1:1"){store.detail.toggle();store.render()}.keyboardShortcut("1",modifiers:[.command])
            }
        }
        Settings { SettingsView().environmentObject(store).frame(width:600,height:620) }
    }
}
