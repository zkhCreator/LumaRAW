// Purpose: native editor for the catalog's monotonic import and image counters.
// Inputs: revisioned sequence reads and explicit user drafts. Outputs: one
// revision-checked service command. It never computes names, writes SQL or touches
// files; stale saves preserve drafts until the user explicitly reloads a revision.
import Foundation
import SwiftUI

private let importSequenceMinimum: Int64 = 1
private let importSequenceMaximum: Int64 = 9_999_999_999

@MainActor final class ImportSequenceEditor: ObservableObject {
    @Published private(set) var revision: Int?
    @Published var nextImport = "1"
    @Published var nextImage = "1"
    @Published var busy = false
    @Published var loaded = false
    @Published var error: String?
    @Published private(set) var reloadedDraft = false
    @Published private(set) var currentImport = "1"
    @Published private(set) var currentImage = "1"
    private var savedDraft = ""

    var draftKey: String { "\(nextImport)|\(nextImage)" }
    var dirty: Bool { loaded && draftKey != savedDraft }
    private var parsedImport: Int64? { Int64(nextImport) }
    private var parsedImage: Int64? { Int64(nextImage) }
    var valid: Bool {
        guard let parsedImport, let parsedImage else { return false }
        return (importSequenceMinimum...importSequenceMaximum).contains(parsedImport)
            && (importSequenceMinimum...importSequenceMaximum).contains(parsedImage)
    }
    var canSave: Bool { loaded && !busy && dirty && valid }

    func load() async {
        await read(preservingDraft: false)
    }

    func reloadCurrentValues() async {
        guard !busy else { return }
        await read(preservingDraft: dirty)
    }

    private func read(preservingDraft: Bool) async {
        guard !busy else { return }
        let draftImport = nextImport
        let draftImage = nextImage
        busy = true
        error = nil
        reloadedDraft = false
        defer { busy = false }
        do {
            let value = try await Backend.call("get_import_sequence")
            guard let nextRevision = value["revision"] as? Int,
                  let imported = Self.integer(value["next_import"]),
                  let image = Self.integer(value["next_image"]) else {
                throw EngineFailure(message: "The catalog returned an invalid import sequence.")
            }
            revision = nextRevision
            loaded = true
            savedDraft = "\(imported)|\(image)"
            currentImport = String(imported)
            currentImage = String(image)
            if preservingDraft {
                nextImport = draftImport
                nextImage = draftImage
                reloadedDraft = true
            } else {
                nextImport = String(imported)
                nextImage = String(image)
            }
        } catch {
            self.error = error.localizedDescription
        }
    }

    func save() async {
        guard canSave, let revision, let imported = parsedImport, let image = parsedImage else { return }
        busy = true
        error = nil
        reloadedDraft = false
        defer { busy = false }
        do {
            let value = try await Backend.call("set_import_sequence", [
                "expected_revision": revision,
                "next_import": imported,
                "next_image": image
            ])
            guard let savedRevision = value["revision"] as? Int,
                  let savedImport = Self.integer(value["next_import"]),
                  let savedImage = Self.integer(value["next_image"]) else {
                throw EngineFailure(message: "The catalog returned an invalid import sequence.")
            }
            self.revision = savedRevision
            nextImport = String(savedImport)
            nextImage = String(savedImage)
            savedDraft = "\(savedImport)|\(savedImage)"
            currentImport = nextImport
            currentImage = nextImage
        } catch {
            self.error = "\(error.localizedDescription) Your draft is preserved. Reload to review the latest catalog values before saving again."
        }
    }

    private static func integer(_ value: Any?) -> Int64? {
        if let number = value as? NSNumber { return number.int64Value }
        if let value = value as? Int64 { return value }
        if let value = value as? Int { return Int64(value) }
        return nil
    }
}

struct CatalogImportSequenceSheet: View {
    @StateObject private var model = ImportSequenceEditor()
    @Environment(\.dismiss) private var dismiss
    @State private var showDiscard = false

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text("Catalog Import Sequence").font(.title2.weight(.semibold))
            Text("Set the next Import # and Image # used by future naming previews and imports. These settings never rename files already in the catalog.")
                .foregroundStyle(.secondary)
            Form {
                TextField("Next Import #", text: $model.nextImport)
                    .textFieldStyle(.roundedBorder)
                    .disabled(!model.loaded || model.busy)
                TextField("Next Image #", text: $model.nextImage)
                    .textFieldStyle(.roundedBorder)
                    .disabled(!model.loaded || model.busy)
            }
            Text("Import # advances once per import, and Image # once per new photo. Copy checks all destinations before reserving numbers. Cancelling or interrupting a Copy after that point may leave gaps. Changing these starts can reuse earlier numbers, but existing files are never overwritten.")
                .font(.caption).foregroundStyle(.secondary)
            if !model.valid && model.loaded {
                Text("Enter whole numbers from 1 to 9,999,999,999.").font(.caption).foregroundStyle(.orange)
            }
            if model.reloadedDraft {
                Text("The catalog currently uses Import # \(model.currentImport) and Image # \(model.currentImage). Your draft is preserved; Save will replace those values with your draft.")
                    .font(.caption).foregroundStyle(.orange)
            }
            if let error = model.error {
                Text(error).font(.caption).foregroundStyle(.red).textSelection(.enabled)
            }
            HStack {
                Spacer()
                if model.busy { ProgressView().controlSize(.small) }
                Button("Reload") { Task { await model.reloadCurrentValues() } }
                    .disabled(model.busy)
                Button("Cancel") {
                    if model.dirty { showDiscard = true } else { dismiss() }
                }.keyboardShortcut(.cancelAction).disabled(model.busy)
                Button("Save") { Task { await model.save() } }
                    .buttonStyle(.borderedProminent).keyboardShortcut(.defaultAction).disabled(!model.canSave)
            }
        }
        .padding(24)
        .frame(width: 620)
        .task { await model.load() }
        .interactiveDismissDisabled(model.busy || model.dirty)
        .confirmationDialog("Discard unsaved catalog counter changes?", isPresented: $showDiscard) {
            Button("Discard Changes", role: .destructive) { dismiss() }
        }
    }
}

struct ImportSequenceReadout: View {
    let sequence: [String: Any]?

    private var nextImport: String? { Self.counter(sequence?["import_number"]) }
    private var nextImage: String? { Self.counter(sequence?["image_number"]) }
    private var frozen: Bool { sequence?["frozen"] as? Bool ?? false }

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            if let nextImport, let nextImage {
                Text("\(frozen ? "Captured" : "Current") Import # \(nextImport) · Image # \(nextImage)")
                    .font(.callout.weight(.medium))
            } else {
                Text("Import and image counter values are not available yet.")
                    .font(.caption).foregroundStyle(.secondary)
            }
            Text("Previewing names does not use these numbers. Copy reserves them after checking all destinations; a later interruption or cancellation can leave gaps.")
                .font(.caption).foregroundStyle(.secondary)
        }
    }

    private static func counter(_ value: Any?) -> String? {
        guard let value else { return nil }
        if let number = value as? NSNumber { return number.stringValue }
        if let value = value as? Int64 { return String(value) }
        if let value = value as? Int { return String(value) }
        return nil
    }
}
