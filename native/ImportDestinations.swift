// Purpose: read-only, revision-bound Copy destination-folder pages on Mac.
// Inputs: a ready Copy review ID and its captured revision; reloads explicitly read
// the latest review before requesting a new first page. Outputs: bounded folder
// paths and eligible original-photo counts for main and optional backup copies.
// Navigation is cursor-based, empty cursors are valid, and failed reads retain the
// visible page. No filesystem enumeration, folder creation, selection changes or polling.
import Foundation
import SwiftUI

struct ImportDestinationFolder: Identifiable {
    let relativePath: String
    let path: String
    let photoCount: Int
    var id: String { path }

    init?(_ value: [String: Any]) {
        guard let relativePath = value["relative_path"] as? String,
              let path = value["path"] as? String,
              let photoCount = Self.integer(value["photo_count"]) else { return nil }
        self.relativePath = relativePath
        self.path = path
        self.photoCount = photoCount
    }

    private static func integer(_ value: Any?) -> Int? {
        if let number = value as? NSNumber { return number.intValue }
        return value as? Int
    }
}

struct ImportBackupDestinationSummary {
    let destination: String
    let subfolder: String
    let photoCount: Int

    init?(_ value: [String: Any]) {
        guard let destination = value["destination"] as? String,
              let subfolder = value["subfolder"] as? String,
              let count = value["photo_count"] as? NSNumber else { return nil }
        self.destination = destination
        self.subfolder = subfolder
        photoCount = count.intValue
    }
}

@MainActor final class ImportDestinationModel: ObservableObject, Identifiable {
    let id = UUID()
    let planID: Int
    @Published private(set) var revision: Int
    @Published private(set) var destination = ""
    @Published private(set) var selectedCount = 0
    @Published private(set) var items: [ImportDestinationFolder] = []
    @Published private(set) var nextAfter: String?
    @Published private(set) var pageSize = 60
    @Published private(set) var backup: ImportBackupDestinationSummary?
    @Published private(set) var loading = false
    @Published private(set) var loaded = false
    @Published var error: String?

    private var currentAfter: String?
    private var previousCursors: [String?] = []
    private var closed = false

    init(planID: Int, revision: Int) {
        self.planID = planID
        self.revision = revision
    }

    var canGoBack: Bool { !previousCursors.isEmpty }
    var pageNumber: Int { previousCursors.count + 1 }

    func loadInitial() async {
        guard !loaded else { return }
        await requestPage(after: nil, action: .initial, revision: revision)
    }

    func nextPage() async {
        guard let cursor = nextAfter else { return }
        await requestPage(after: cursor, action: .next, revision: revision)
    }

    func previousPage() async {
        guard !previousCursors.isEmpty else { return }
        await requestPage(after: previousCursors[previousCursors.count - 1], action: .previous, revision: revision)
    }

    func reloadCurrentReview() async {
        guard !closed, !loading else { return }
        loading = true
        error = nil
        defer { loading = false }
        do {
            let result = try await Backend.call("get_import", ["plan_id": planID])
            guard let values = result["plan"] as? [String: Any],
                  (values["id"] as? Int) == planID,
                  (values["mode"] as? String) == "copy",
                  (values["state"] as? String) == "ready",
                  let freshRevision = values["revision"] as? Int else {
                throw EngineFailure(message: "Destination folders are available only for a ready Copy review")
            }
            let page = try await fetchPage(after: nil, revision: freshRevision)
            guard !closed else { return }
            install(page)
            revision = freshRevision
            currentAfter = nil
            previousCursors = []
            loaded = true
        } catch {
            show(error)
        }
    }

    // Kept internal so regression coverage can exercise an empty-string cursor.
    func readPage(after cursor: String?) async {
        await requestPage(after: cursor, action: .initial, revision: revision)
    }

    private enum Navigation { case initial, next, previous }

    private struct Page {
        let destination: String
        let selectedCount: Int
        let items: [ImportDestinationFolder]
        let nextAfter: String?
        let pageSize: Int
        let backup: ImportBackupDestinationSummary?
    }

    private func requestPage(after cursor: String?, action: Navigation, revision requestedRevision: Int) async {
        guard !closed, !loading else { return }
        loading = true
        error = nil
        defer { loading = false }
        do {
            let page = try await fetchPage(after: cursor, revision: requestedRevision)
            guard !closed else { return }
            install(page)
            switch action {
            case .initial:
                currentAfter = cursor
                previousCursors = []
                loaded = true
            case .next:
                previousCursors.append(currentAfter)
                currentAfter = cursor
            case .previous:
                if !previousCursors.isEmpty { previousCursors.removeLast() }
                currentAfter = cursor
            }
        } catch {
            show(error)
        }
    }

    private func fetchPage(after cursor: String?, revision requestedRevision: Int) async throws -> Page {
        var params: [String: Any] = ["plan_id": planID, "expected_revision": requestedRevision]
        if let cursor { params["after"] = cursor }
        let value = try await Backend.call("get_import_destinations", params)
        guard (value["plan_id"] as? Int) == planID,
              (value["revision"] as? Int) == requestedRevision,
              let destination = value["destination"] as? String,
              let selectedCount = value["selected_count"] as? Int,
              let rawItems = value["items"] as? [[String: Any]],
              let pageSize = value["page_size"] as? Int,
              let cursorValue = value["next_after"] else {
            throw EngineFailure(message: "The destination-folder response was incomplete")
        }
        let nextAfter: String?
        if cursorValue is NSNull { nextAfter = nil }
        else if let cursor = cursorValue as? String { nextAfter = cursor }
        else { throw EngineFailure(message: "The destination-folder cursor was invalid") }
        let rows = rawItems.compactMap(ImportDestinationFolder.init)
        guard rows.count == rawItems.count else {
            throw EngineFailure(message: "A destination-folder row was incomplete")
        }
        var backup: ImportBackupDestinationSummary?
        if let rawBackup = value["backup"] as? [String: Any] {
            guard let parsed = ImportBackupDestinationSummary(rawBackup) else {
                throw EngineFailure(message: "The backup destination summary was incomplete")
            }
            backup = parsed
        }
        return Page(destination: destination, selectedCount: selectedCount, items: rows,
            nextAfter: nextAfter, pageSize: pageSize, backup: backup)
    }

    private func install(_ page: Page) {
        destination = page.destination
        selectedCount = page.selectedCount
        items = page.items
        nextAfter = page.nextAfter
        pageSize = page.pageSize
        backup = page.backup
    }

    private func show(_ error: Error) {
        let message = error.localizedDescription
        let lowered = message.lowercased()
        if lowered.contains("changed") || lowered.contains("stale") {
            self.error = "This import review changed. Reload to see destinations for its latest selection. \(message)"
        } else {
            self.error = message
        }
    }

    func invalidate() { closed = true }
}

struct ImportDestinationSheet: View {
    @ObservedObject var model: ImportDestinationModel
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        content.task { await model.loadInitial() }
            .onDisappear { model.invalidate() }
            .interactiveDismissDisabled(model.loading)
    }

    var content: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack {
                VStack(alignment: .leading, spacing: 4) {
                    Text("Destination Folders").font(.title2)
                    Text("Only checked photos eligible for Copy are included. This preview does not create folders.")
                        .font(.caption).foregroundStyle(.secondary)
                }
                Spacer()
                if model.loading { ProgressView().controlSize(.small) }
            }

            Text("Copy destination: \(model.destination)")
                .font(.caption).lineLimit(2).textSelection(.enabled)
            Text("\(model.selectedCount) checked photos included")
                .font(.subheadline.weight(.semibold))

            ScrollView {
                LazyVStack(alignment: .leading, spacing: 8) {
                    if model.items.isEmpty {
                        Text("No checked photos are eligible for Copy under the current duplicate policy.")
                            .foregroundStyle(.secondary).frame(maxWidth: .infinity, alignment: .leading).padding(12)
                    }
                    ForEach(model.items) { item in
                        VStack(alignment: .leading, spacing: 4) {
                            HStack(alignment: .firstTextBaseline) {
                                Text(item.relativePath.isEmpty ? "Destination root" : item.relativePath)
                                    .font(.body.weight(.medium)).textSelection(.enabled)
                                    .fixedSize(horizontal: false, vertical: true)
                                Spacer(minLength: 12)
                                Text("\(item.photoCount) photos").font(.caption).foregroundStyle(.secondary)
                            }
                            Text(item.path).font(.caption).foregroundStyle(.secondary)
                                .textSelection(.enabled).fixedSize(horizontal: false, vertical: true)
                        }
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(10)
                        .background(Color.secondary.opacity(0.07), in: RoundedRectangle(cornerRadius: 7))
                    }
                }
            }
            .frame(minHeight: 220)

            if let backup = model.backup {
                GroupBox("Second Copy") {
                    VStack(alignment: .leading, spacing: 4) {
                        Text("Root: \(backup.destination)").font(.caption).textSelection(.enabled)
                            .fixedSize(horizontal: false, vertical: true)
                        Text("Subfolder: \(backup.subfolder.isEmpty ? "None" : backup.subfolder)")
                            .font(.caption).textSelection(.enabled)
                        Text("\(backup.photoCount) checked photos included").font(.caption.weight(.medium))
                    }.frame(maxWidth: .infinity, alignment: .leading)
                }
            } else {
                Text("No second-copy destination is configured.").font(.caption).foregroundStyle(.secondary)
            }

            if let error = model.error {
                Text(error).font(.caption).foregroundStyle(.red).textSelection(.enabled)
            }
            HStack {
                Button("Previous") { Task { await model.previousPage() } }
                    .disabled(!model.canGoBack || model.loading)
                Text("Page \(model.pageNumber) · \(model.items.count) folders")
                    .font(.caption).foregroundStyle(.secondary)
                Button("Next") { Task { await model.nextPage() } }
                    .disabled(model.nextAfter == nil || model.loading)
                Spacer()
                Button("Reload") { Task { await model.reloadCurrentReview() } }.disabled(model.loading)
                Button("Done") { dismiss() }.keyboardShortcut(.cancelAction)
            }
        }
        .padding(22)
        .frame(width: 920, height: 650)
    }
}
