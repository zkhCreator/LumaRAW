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
                .onOpenURL {url in Task{await store.reviewImport([url.path])}}
        }
        .defaultSize(width:1440,height:920)
        .commands {
            CommandGroup(replacing:.newItem) {
                Button("Import Photos…"){store.importPanel()}.keyboardShortcut("i")
                Button("Review Pending Import…") { Task { await store.reviewImport() } }
                Button("Export Selected Photos…"){store.showExport=true}.keyboardShortcut("e",modifiers:[.command,.shift]).disabled(store.selected==nil)
            }
            CommandGroup(replacing:.undoRedo) {
                Button("Undo Develop Adjustment"){store.undo()}.keyboardShortcut("z").disabled(!store.canUndoDevelop)
                Button("Redo Develop Adjustment"){store.redo()}.keyboardShortcut("z",modifiers:[.command,.shift]).disabled(!store.canRedoDevelop)
            }
            CommandMenu("Photo") {
                Button("Develop Presets…") { store.showDevelopPresets=true }
                Divider()
                PhotoOrientationActions().environmentObject(store)
                Divider()
                StackActions().environmentObject(store)
                Divider()
                Button("Create Virtual Copies") { Task { await store.createVirtualCopies() } }.keyboardShortcut("\"").disabled(store.actionPhotoIDs.isEmpty || store.copyBusy)
                Button("Set Copy as Master") { Task { await store.setCopyAsMaster() } }.disabled(store.photo?.isVirtual != true || store.copyBusy)
                Button("Show Master and Copies") { if let photo=store.photo { Task { await store.showPhotoFamily(photo) } } }.disabled(store.photo == nil)
                Button("Remove Virtual Copies from Catalog…") { Task { await store.prepareCopyRemoval() } }.disabled(store.actionPhotoIDs.isEmpty || store.copyBusy)
                Divider()
                Button("Add to / Remove from Target Collection") { Task { await store.toggleTargetMembership() } }.disabled(store.actionPhotoIDs.isEmpty)
                Divider()
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
                Button("Go to Folder in Library") { if let photo=store.photo { Task { await store.showPhotoFolder(photo) } } }.disabled(store.photo == nil)
                Button("Locate Missing Original…"){store.relink()}
            }
            CommandMenu("Library") {
                ForEach(LibraryViewMode.allCases,id:\.self) { view in
                    Button("\(view.title) View") { Task { await store.switchLibraryView(view) } }
                }
                Divider()
                Button("New Collection…") { store.editCollection() }.keyboardShortcut("n",modifiers:[.command,.shift])
                Button("New Collection Set…") { store.editCollection(kind:"set") }
                Button("Show Quick Collection") { if let quick=store.collectionState?.quick { Task { await store.openCollection(quick) } } }
                Button("Filter Photos…") { store.showLibraryFilters=true }
                Toggle("Show Photo Stacks",isOn:Binding(get:{store.showStacks},set:{value in store.showStacks=value;Task { await store.refresh() }}))
                Toggle("Include Photos from Subfolders",isOn:Binding(get:{store.includeSubfolders},set:{value in
                    Task { await store.changeSubfolderInclusion(value) }
                }))
                Button("Refresh Library") { Task { await store.refreshCollections(); await store.refresh() } }
            }
            CommandMenu("Metadata") {
                Button("Metadata Presets…") { store.showMetadataPresets=true }
                Divider()
                KeywordExchangeActions().environmentObject(store)
                Divider()
                Button("Set Keyword Shortcut…") { Task { await store.prepareKeywordShortcut() } }
                    .keyboardShortcut("k",modifiers:[.command,.option,.shift]).disabled(store.painterBusy)
                Button("Add Keyword Shortcut") { store.applyKeywordShortcut() }
                    .disabled(store.keywordShortcut?.ids.isEmpty != false || store.actionPhotoIDs.isEmpty || store.painterBusy)
                Toggle("Enable Painting",isOn:Binding(get:{store.painterEnabled},set:{store.setPainting($0)}))
                    .keyboardShortcut("k",modifiers:[.command,.option]).disabled(!store.painterInGrid || store.painterBusy)
                Button("Choose Painter Keywords from Sets…") { store.choosePainterKeywordSets() }
                    .disabled(!store.painterCanReceive || store.painterKind != "keywords")
                Divider()
                ForEach(1...9,id:\.self) { slot in
                    Button("Apply Keyword Set Slot \(slot)") { Task { await store.applyKeywordSlot(slot) } }
                        .keyboardShortcut(KeyEquivalent(Character(String(slot))),modifiers:.option)
                        .disabled(!store.canApplyKeywordSlot(slot))
                }
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
