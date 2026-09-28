// Purpose: native Painter controls and an identity-safe keyword shortcut editor.
// Inputs: toolbar choices, captured shortcut state and local selected IDs/text.
// Outputs: explicit Store actions; typing never applies metadata to photos.
// Existing keywords remain IDs, so editing never splits legacy literal labels.
import SwiftUI

struct PainterToolbar: View {
    @EnvironmentObject var s: Store
    var body: some View {
        if s.painterInGrid {
            VStack(alignment:.leading,spacing:6) {
                HStack(spacing:10) {
                    Toggle(isOn:Binding(get:{s.painterEnabled},set:{s.setPainting($0)})) {
                        Label("Painter",systemImage:"paintbrush.pointed")
                    }.toggleStyle(.button).help("Enable Painting · Command-Option-K")
                    if s.painterEnabled {
                        Picker("Paint",selection:$s.painterKind) {
                            Text("Keywords").tag("keywords");Text("Rating").tag("rating")
                            Text("Flag").tag("flag");Text("Color Label").tag("label")
                            Text("Target Collection").tag("target_collection")
                            Text("Rotation").tag("orientation")
                            Text("Develop Preset").tag("develop_preset")
                        }.frame(width:205).onChange(of:s.painterKind) { _,value in
                            s.cancelPainterStroke()
                            if value == "target_collection" { Task { await s.refreshCollectionState() } }
                        }
                    }
                    Spacer(minLength:0)
                    if s.painterBusy || s.orientationBusy || s.developPresetBusy { ProgressView().controlSize(.small) }
                }
                if s.painterEnabled {
                    HStack(spacing:10) {
                        if s.painterKind == "keywords" {
                            Button("Set Keywords… (\(s.keywordShortcut?.ids.count ?? 0))") { Task { await s.prepareKeywordShortcut() } }
                            Button("Choose from Sets…") { s.choosePainterKeywordSets() }.help("Shift while the Painter has focus")
                            Text("Option removes these keywords").font(.caption).foregroundStyle(.secondary)
                        } else if s.painterKind == "rating" {
                            Picker("Rating",selection:$s.painterRating) { Text("None").tag(0);ForEach(1...5,id:\.self) { Text("\($0) stars").tag($0) } }.frame(width:135)
                        } else if s.painterKind == "flag" {
                            Picker("Flag",selection:$s.painterFlag) { Text("Pick").tag(1);Text("Unflagged").tag(0);Text("Rejected").tag(-1) }.frame(width:135)
                        } else if s.painterKind == "develop_preset" {
                            Text(s.painterPresetName).lineLimit(1)
                            Button("Choose Preset…") { s.cancelPainterStroke();s.showDevelopPresets=true }
                        } else if s.painterKind == "orientation" {
                            Picker("Rotation",selection:$s.painterOrientationAction) {
                                ForEach(PhotoOrientation.actions,id:\.1) { title,action in Text(title).tag(action) }
                            }.frame(width:230)
                        } else if s.painterKind == "target_collection" {
                            Text("Target: \(s.painterTargetName)").lineLimit(1)
                            Text("Option removes from this collection").font(.caption).foregroundStyle(.secondary)
                            Button("Refresh Target") { Task { await s.refreshCollectionState() } }
                        } else {
                            Picker("Label",selection:$s.painterLabel) { ForEach(LibraryLabels.names,id:\.self) { Text($0.capitalized).tag($0) } }.frame(width:135)
                        }
                        Spacer(minLength:0)
                    }
                    Text("Click or drag thumbnails · Esc to finish").font(.caption).foregroundStyle(.secondary)
                }
            }.controlSize(.small).padding(.horizontal,20).padding(.vertical,6).disabled(s.painterBusy || s.orientationBusy || s.developPresetBusy)
        }
    }
}

struct KeywordShortcutEditor: View {
    @EnvironmentObject var s: Store
    @Environment(\.dismiss) private var dismiss
    let source: KeywordShortcutEditorSource
    @State private var ids: [Int]
    @State private var additions=""
    @State private var choosing=false
    init(source: KeywordShortcutEditorSource) {
        self.source=source;_ids=State(initialValue:source.shortcut.ids)
    }
    var body: some View {
        VStack(alignment:.leading,spacing:16) {
            Text("Set Keyword Shortcut").font(.title2)
            Text("Use this shortcut with Add Keyword Shortcut, Shift-K, or the Painter. Setting it does not tag photos.").foregroundStyle(.secondary)
            HStack {
                Text("\(ids.count) existing keywords")
                Button("Choose Existing Keywords…") { choosing=true }
                Button("Clear") { ids=[] }.disabled(ids.isEmpty)
            }
            TextField("Add keywords, separated by commas",text:$additions,axis:.vertical).lineLimit(3...6).textFieldStyle(.roundedBorder)
            Text("Use Parent | Child for a hierarchy. Existing choices retain their identities, including names with literal separators.").font(.caption).foregroundStyle(.secondary)
            HStack {
                Button("Cancel") { dismiss() }.keyboardShortcut(.cancelAction)
                Spacer()
                Button("Set") {
                    let extra=metadataKeywordReplacement(additions,original:[],targetCount:1) ?? []
                    Task { if await s.saveKeywordShortcut(ids:ids,additions:extra,revision:source.shortcut.revision) { dismiss() } }
                }.keyboardShortcut(.defaultAction)
            }.disabled(s.painterBusy)
        }.padding(24).frame(width:660)
            .sheet(isPresented:$choosing) {
                KeywordSelectionSheet(ids:ids,explanation:"These identities become the shortcut when you click Set.") { ids=$0 }
            }
    }
}

struct PhotoKeywordShortcutActions: View {
    @EnvironmentObject var s: Store
    let photoID: Int
    var body: some View {
        if let shortcut=s.keywordShortcut,!shortcut.ids.isEmpty {
            Button("Add Keyword Shortcut (\(shortcut.ids.count))") {
                s.applyKeywordShortcut(ids:s.actionPhotoIDs.contains(photoID) ? s.actionPhotoIDs:[photoID])
            }.disabled(s.painterBusy || s.keywordBusy)
        }
    }
}
