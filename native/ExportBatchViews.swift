// Purpose: native multi-preset batch export setup and durable batch receipts.
// Inputs: bounded preset/history pages and an explicit captured Store selection.
// Outputs: one revision-bound batch request and user-invoked receipt actions.
// Preset options stay read-only here; this view does not render or write photos.
import AppKit
import SwiftUI

@MainActor struct ExportBatchSheet: View {
    @EnvironmentObject private var store: Store
    @Environment(\.dismiss) private var dismiss
    @StateObject private var picker: ExportBatchPresetPickerModel
    @StateObject private var history = ExportBatchHistoryModel()
    @State private var drafts: [ExportBatchPresetDraft] = []
    @State private var configuring = false
    @State private var parentMode = false
    @State private var parentDestination = ""
    @State private var submitting = false
    @State private var showingReceipt = false
    @State private var showHistory = false
    @State private var submissionUncertain = false
    @State private var localError: String?
    @State private var receiptPollingTask: Task<Void, Never>?
    @State private var isVisible = false
    @State private var visibilityGeneration = 0

    init(picker: ExportBatchPresetPickerModel? = nil) {
        _picker = StateObject(wrappedValue: picker ?? ExportBatchPresetPickerModel())
    }

    var body: some View {
        Group {
            if showingReceipt {
                ExportBatchReceiptView(model: history, onClose: { dismiss() })
            } else if configuring {
                configuration
            } else {
                presetPicker
            }
        }
        .padding(22)
        .frame(width: 850, height: 700)
        .onAppear {
            isVisible=true;visibilityGeneration+=1
            if picker.page == nil { Task { await picker.refresh(offset: 0, search: picker.searchText) } }
        }
        .onDisappear {
            isVisible=false;visibilityGeneration+=1
            receiptPollingTask?.cancel();receiptPollingTask=nil
            picker.invalidateReads();history.invalidateReads()
        }
        .sheet(isPresented: $showHistory) { ExportBatchHistorySheet().environmentObject(store) }
    }

    private var presetPicker: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack {
                VStack(alignment: .leading, spacing: 4) {
                    Text("Batch Export").font(.title2.weight(.semibold))
                    Text("Queue the selected photos once for each chosen preset. Preset options remain fixed for this batch.")
                        .font(.callout).foregroundStyle(.secondary)
                }
                Spacer()
                Button("Cancel") { dismiss() }.keyboardShortcut(.cancelAction)
            }
            Text("Selected photos: \(store.selection.count) · Batch limit: 1,000 photo and preset jobs")
                .font(.caption).foregroundStyle(.secondary)
            HStack {
                TextField("Search export presets", text: $picker.searchText)
                    .onSubmit { Task { await picker.refresh(offset: 0, search: picker.searchText) } }
                    .disabled(picker.loading || picker.loadingSettings || picker.stale)
                Button("Search") { Task { await picker.refresh(offset: 0, search: picker.searchText) } }
                    .disabled(picker.loading || picker.loadingSettings || picker.stale)
                if picker.stale {
                    Button("Reload & Clear Selection") { Task { await picker.reloadAndClearSelection() } }
                } else {
                    Button("Reload") { Task { await picker.refresh() } }
                        .disabled(picker.loading || picker.loadingSettings)
                }
            }
            if let error = picker.error { Text(error).font(.caption).foregroundStyle(.red) }
            if let page = picker.page {
                ScrollView {
                    LazyVStack(alignment: .leading, spacing: 3) {
                        ForEach(page.items) { item in
                            Toggle(isOn: Binding(
                                get: { picker.selectedIDs.contains(item.id) },
                                set: { _ = picker.setSelected(item.id, $0) }
                            )) {
                                Text(item.name).lineLimit(1)
                            }
                            .toggleStyle(.checkbox)
                            .disabled(picker.loading || picker.loadingSettings || picker.stale)
                        }
                    }
                }
                HStack {
                    Button("Previous") { Task { await picker.refresh(offset: max(0, page.offset - 30)) } }
                        .disabled(page.offset == 0 || picker.loading || picker.loadingSettings || picker.stale)
                    Text("\(page.total == 0 ? 0 : page.offset + 1)–\(min(page.offset + page.items.count, page.total)) of \(page.total)")
                        .font(.caption).foregroundStyle(.secondary)
                    Button("Next") { Task { await picker.refresh(offset: page.offset + 30) } }
                        .disabled(page.offset + 30 >= page.total || picker.loading || picker.loadingSettings || picker.stale)
                    Spacer()
                    Text("\(picker.selectedOrder.count) of 30 presets selected")
                        .font(.caption).foregroundStyle(.secondary)
                    if picker.loading || picker.loadingSettings { ProgressView().controlSize(.small) }
                }
            } else if picker.loading {
                ProgressView("Loading export presets…").frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                ContentUnavailableView("No Export Presets", systemImage: "square.and.arrow.up",
                    description: Text("Save export presets before creating a batch."))
            }
            HStack {
                Spacer()
                Button("Continue") { Task { await capturePresets() } }
                    .buttonStyle(.borderedProminent)
                    .disabled(!picker.canContinue || store.selection.isEmpty || store.selection.count > 1000)
            }
        }
    }

    private var configuration: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                VStack(alignment: .leading, spacing: 4) {
                    Text("Review Batch Destinations").font(.title2.weight(.semibold))
                    Text("\(store.selection.count) selected photos × \(drafts.count) presets = \(store.selection.count * drafts.count) jobs")
                        .font(.callout).foregroundStyle(.secondary)
                }
                Spacer()
                Button("Back") { configuring = false; localError = nil }
                    .disabled(submitting || store.exportSubmissionBusy || submissionUncertain)
                Button("Cancel") { dismiss() }.keyboardShortcut(.cancelAction)
                    .disabled(submitting || store.exportSubmissionBusy)
            }
            Toggle("Use one parent folder with a subfolder for each preset", isOn: $parentMode)
                .disabled(submitting || store.exportSubmissionBusy)
            if parentMode {
                HStack {
                    Text(parentDestination.isEmpty ? "Choose a parent folder" : parentDestination)
                        .font(.caption).foregroundStyle(parentDestination.isEmpty ? .secondary : .primary)
                        .lineLimit(2).textSelection(.enabled)
                    Spacer()
                    Button("Choose Parent…") { parentDestination = chooseFolder() ?? parentDestination }
                        .disabled(submitting || store.exportSubmissionBusy)
                }
            }
            if store.selection.count * drafts.count > 1000 {
                Label("Reduce the photo or preset count to stay within 1,000 jobs.", systemImage: "exclamationmark.triangle")
                    .font(.caption).foregroundStyle(.orange)
            }
            if hasDuplicateSubfolders {
                Label("Each preset needs a different subfolder name.", systemImage: "exclamationmark.triangle")
                    .font(.caption).foregroundStyle(.orange)
            }
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 10) {
                    ForEach($drafts) { $draft in
                        presetDestinationEditor(draft: $draft)
                    }
                }
            }
            if let localError { Text(localError).font(.caption).foregroundStyle(.red).textSelection(.enabled) }
            if submissionUncertain {
                Button("Check Batch History…") { showHistory = true }
                    .disabled(submitting || store.exportSubmissionBusy)
            }
            HStack {
                Text("The batch captures current edits when accepted. Choosing presets never starts an export.")
                    .font(.caption).foregroundStyle(.secondary)
                Spacer()
                Button(submitting ? "Submitting…" : "Queue Batch") { submit() }
                    .buttonStyle(.borderedProminent)
                    .disabled(!canSubmit || submitting || store.exportSubmissionBusy || submissionUncertain)
            }
        }
    }

    private func presetDestinationEditor(draft: Binding<ExportBatchPresetDraft>) -> some View {
        let value = draft.wrappedValue
        return GroupBox {
            VStack(alignment: .leading, spacing: 8) {
                HStack {
                    Text(value.snapshot.name).font(.headline).lineLimit(1)
                    Spacer()
                    Text(value.snapshot.settings.format == "jpeg" ? "JPEG" : "16-bit TIFF")
                        .font(.caption).foregroundStyle(.secondary)
                }
                settingsSummary(value.snapshot.settings)
                if parentMode {
                    TextField("Subfolder", text: draft.subfolder)
                        .disabled(submitting || store.exportSubmissionBusy)
                    Text("Stored preset folders are replaced by the chosen parent and this subfolder.")
                        .font(.caption).foregroundStyle(.secondary)
                } else {
                    HStack {
                        Text(value.resolvedDestination ?? "This preset has no saved export folder")
                            .font(.caption).foregroundStyle(value.resolvedDestination == nil ? .orange : .secondary)
                            .lineLimit(2).textSelection(.enabled)
                        Spacer()
                        if !value.destinationOverride.isEmpty {
                            Button("Use Saved Folder") { draft.destinationOverride.wrappedValue = "" }
                                .disabled(submitting || store.exportSubmissionBusy)
                        }
                        Button(value.destinationOverride.isEmpty ? "Override…" : "Choose…") {
                            if let path = chooseFolder() { draft.destinationOverride.wrappedValue = path }
                        }.disabled(submitting || store.exportSubmissionBusy)
                    }
                }
                TextField("Filename suffix", text: draft.filenameSuffix)
                    .disabled(submitting || store.exportSubmissionBusy)
                Text("Used only when an output filename collides; otherwise the original name is kept.")
                    .font(.caption2).foregroundStyle(.secondary)
                if let issue = value.validationMessage(parentMode: parentMode) {
                    Label(issue, systemImage: "exclamationmark.triangle")
                        .font(.caption2).foregroundStyle(.red)
                }
            }
        }
    }

    private func settingsSummary(_ settings: ExportEffectiveSettings) -> some View {
        let edge = settings.maxEdge == 0 ? "Full size" : "Max edge \(settings.maxEdge) px"
        let space = ["srgb": "sRGB", "p3": "Display P3", "adobe": "Adobe RGB", "prophoto": "ProPhoto RGB"][settings.space] ?? settings.space
        return VStack(alignment: .leading, spacing: 3) {
            Text("\(space) · \(edge) · Quality \(settings.quality) · Sharpen \(settings.outputSharpen, specifier: "%.1f") · Priority \(settings.priority) · Metadata \(settings.metadata)")
            Text("Filename template: \(settings.filenameTemplate)")
            Text("Write keywords as Lightroom hierarchy: \(settings.keywordHierarchy ? "On" : "Off")")
        }.font(.caption).foregroundStyle(.secondary).textSelection(.enabled)
    }

    private var canSubmit: Bool {
        guard !drafts.isEmpty, store.selection.count > 0, store.selection.count * drafts.count <= 1000,
              drafts.allSatisfy({ $0.submissionEntry(parentMode: parentMode) != nil }),
              !hasDuplicateSubfolders else { return false }
        return !parentMode || !parentDestination.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }

    private var hasDuplicateSubfolders: Bool {
        guard parentMode else { return false }
        let keys = drafts.map { $0.subfolder.precomposedStringWithCanonicalMapping.folding(
            options: [.caseInsensitive], locale: Locale(identifier: "en_US_POSIX")) }
        return Set(keys).count != keys.count
    }

    private func capturePresets() async {
        guard let captured = await picker.captureSelectedSettings() else { return }
        drafts = captured.map(ExportBatchPresetDraft.init(snapshot:))
        configuring = true
    }

    private func submit() {
        guard canSubmit, let revision = picker.capturedRevision else { return }
        let capturedDrafts = drafts
        let capturedParent = parentMode ? parentDestination : nil
        let submission = ExportBatchPresetSubmission(expectedRevision: revision,
            entries: capturedDrafts, parentDestination: capturedParent)
        let visibleToken=visibilityGeneration
        submitting = true
        localError = nil
        Task {
            let result = await store.exportBatch(submission)
            switch result {
            case .accepted(let batchID):
                guard isVisible,visibilityGeneration==visibleToken else { submitting=false;return }
                await history.open(batchID)
                guard isVisible,visibilityGeneration==visibleToken else { submitting=false;return }
                showingReceipt = true
                startReceiptPolling(visibleToken:visibleToken)
            case .rejected(let message):
                localError = message
                if message.localizedCaseInsensitiveContains("changed") {
                    picker.markStale("The export preset library changed. Reload and reselect presets before continuing. \(message)")
                    configuring = false
                }
            case .uncertain(let message):
                localError = message
                submissionUncertain = true
            }
            submitting = false
        }
    }

    private func chooseFolder() -> String? {
        let panel = NSOpenPanel()
        panel.canChooseDirectories = true
        panel.canChooseFiles = false
        panel.canCreateDirectories = true
        panel.allowsMultipleSelection = false
        return panel.runModal() == .OK ? panel.url?.path : nil
    }

    private func startReceiptPolling(visibleToken:Int) {
        guard isVisible,visibilityGeneration==visibleToken else { return }
        guard receiptPollingTask == nil else { return }
        receiptPollingTask=Task {
            while !Task.isCancelled {
                try? await Task.sleep(nanoseconds:2_000_000_000)
                guard !Task.isCancelled,isVisible,visibilityGeneration==visibleToken,showingReceipt else { return }
                await history.loadDetail(showActivity:false)
            }
        }
    }
}

@MainActor struct ExportBatchHistorySheet: View {
    @Environment(\.dismiss) private var dismiss
    @StateObject private var model: ExportBatchHistoryModel
    let pollsWhileVisible: Bool
    @State private var pollingTask: Task<Void, Never>?
    @State private var isVisible = false
    @State private var visibilityGeneration = 0

    init(model: ExportBatchHistoryModel? = nil, pollsWhileVisible: Bool = true) {
        self.pollsWhileVisible=pollsWhileVisible
        _model = StateObject(wrappedValue: model ?? ExportBatchHistoryModel())
    }

    var body: some View {
        Group {
            if model.selectedBatchID != nil {
                ExportBatchReceiptView(model: model, onBack: { model.showList() }, onClose: { dismiss() })
            } else {
                batchList
            }
        }
        .padding(22)
        .frame(width: 820, height: 660)
        .onAppear {
            isVisible=true;visibilityGeneration+=1
            let visibleToken=visibilityGeneration
            Task {
                if model.page == nil { await model.refresh(offset: 0) }
                guard pollsWhileVisible,isVisible,visibilityGeneration==visibleToken else { return }
                startVisiblePolling(visibleToken:visibleToken)
            }
        }
        .onDisappear {
            isVisible=false;visibilityGeneration+=1
            pollingTask?.cancel();pollingTask=nil
            model.invalidateReads()
        }
    }

    private var batchList: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack {
                Text("Export Batches").font(.title2.weight(.semibold))
                Spacer()
                Button("Reload") { Task { await model.refresh() } }.disabled(model.listLoading)
                Button("Close") { dismiss() }.keyboardShortcut(.cancelAction)
            }
            Text("Batch history refreshes while this view is open. Jobs keep their captured preset settings.")
                .font(.caption).foregroundStyle(.secondary)
            if let error = model.error { Text(error).font(.caption).foregroundStyle(.red) }
            if let page = model.page, !page.batches.isEmpty {
                List(page.batches) { batch in
                    Button { Task { await model.open(batch.id) } } label: {
                        HStack(spacing: 14) {
                            Image(systemName: "square.stack.3d.up").foregroundStyle(.tint)
                            VStack(alignment: .leading, spacing: 4) {
                                Text("\(batch.presetCount) presets · \(batch.photoCount) photos").font(.headline)
                                Text("\(batch.destinationMode == "parent" ? "Shared parent folder" : "Individual preset folders") · \(batch.createdLabel)")
                                    .font(.caption).foregroundStyle(.secondary)
                                Text(countSummary(batch.counts)).font(.caption).foregroundStyle(.secondary)
                            }
                            Spacer()
                            Text("\(batch.queued) jobs").font(.callout)
                            Image(systemName: "chevron.right").font(.caption).foregroundStyle(.tertiary)
                        }
                        .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                    .disabled(model.listLoading || model.detailLoading)
                }
                .listStyle(.inset)
                HStack {
                    Button("Previous") { Task { await model.refresh(offset: max(0, page.offset - page.pageSize)) } }
                        .disabled(page.offset == 0 || model.listLoading)
                    Text("\(page.total == 0 ? 0 : page.offset + 1)–\(min(page.offset + page.batches.count, page.total)) of \(page.total)")
                        .font(.caption).foregroundStyle(.secondary)
                    Button("Next") { Task { await model.refresh(offset: page.offset + page.pageSize) } }
                        .disabled(page.offset + page.pageSize >= page.total || model.listLoading)
                    Spacer()
                    if model.listLoading { ProgressView().controlSize(.small) }
                }
            } else if model.listLoading {
                ProgressView("Loading batches…").frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                ContentUnavailableView("No Export Batches", systemImage: "square.stack.3d.up",
                    description: Text("Accepted multi-preset exports will appear here."))
            }
        }
    }

    private func startVisiblePolling(visibleToken:Int) {
        guard isVisible,visibilityGeneration==visibleToken else { return }
        guard pollingTask == nil else { return }
        pollingTask=Task {
            while !Task.isCancelled {
                try? await Task.sleep(nanoseconds:2_000_000_000)
                guard !Task.isCancelled,isVisible,visibilityGeneration==visibleToken else { return }
                await model.refreshVisibleQuietly()
            }
        }
    }
}

@MainActor struct ExportBatchReceiptView: View {
    @EnvironmentObject private var store: Store
    @ObservedObject var model: ExportBatchHistoryModel
    var onBack: (() -> Void)? = nil
    var onClose: () -> Void
    @State private var errorMessage: String?

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                if let onBack { Button("Batches", action: onBack) }
                VStack(alignment: .leading, spacing: 3) {
                    Text("Batch Receipt").font(.title2.weight(.semibold))
                    if let batch = model.receipt?.batch {
                        Text("\(batch.presetCount) presets · \(batch.photoCount) photos · \(batch.queued) jobs")
                            .font(.caption).foregroundStyle(.secondary)
                    }
                }
                Spacer()
                Button("Reload") { Task { await model.loadDetail(offset: model.receipt?.offset ?? 0) } }
                    .disabled(model.detailLoading || model.actionBusy)
                Button("Done", action: onClose).keyboardShortcut(.cancelAction)
            }
            if let message = model.error ?? errorMessage { Text(message).font(.caption).foregroundStyle(.red).textSelection(.enabled) }
            if let receipt = model.receipt {
                HStack(alignment: .top, spacing: 18) {
                    VStack(alignment: .leading, spacing: 5) {
                        Text("Batch status").font(.headline)
                        Text(countSummary(receipt.counts)).font(.caption).foregroundStyle(.secondary)
                        Text(receipt.batch.destinationMode == "parent" ? "Parent: \(receipt.parentDestination ?? "")" : "Each preset uses its captured destination")
                            .font(.caption).foregroundStyle(.secondary).textSelection(.enabled)
                    }
                    Spacer()
                    Menu("Batch Actions") {
                        Button("Cancel Pending or Running Jobs") { Task { await perform("cancel", receipt.batch.id) } }
                            .disabled((receipt.counts["pending"] ?? 0) + (receipt.counts["running"] ?? 0) == 0)
                        Button("Retry Failed or Interrupted") { Task { await perform("retry", receipt.batch.id) } }
                            .disabled((receipt.counts["failed"] ?? 0) + (receipt.counts["interrupted"] ?? 0) == 0)
                        Button("Retry Cancelled Jobs") { Task { await perform("retry_cancelled", receipt.batch.id) } }
                            .disabled((receipt.counts["cancelled"] ?? 0) == 0)
                    }.disabled(model.actionBusy || model.detailLoading)
                }
                ScrollView(.horizontal) {
                    HStack(alignment: .top, spacing: 10) {
                        ForEach(Array(receipt.presets.enumerated()), id: \.offset) { _, preset in
                            capturedPresetCard(preset)
                        }
                    }
                }.frame(height: 220)
                List(Array(receipt.jobs.enumerated()), id: \.offset) { _, job in
                    HStack(spacing: 10) {
                        Image(systemName: job["state"] as? String == "done" ? "checkmark.circle.fill" : "photo")
                            .foregroundStyle(job["state"] as? String == "done" ? .green : .secondary)
                        VStack(alignment: .leading, spacing: 3) {
                            Text(job["preset_name"] as? String ?? "Export job").font(.headline).lineLimit(1)
                            Text("\(URL(fileURLWithPath: job["source"] as? String ?? "").lastPathComponent) → \(URL(fileURLWithPath: job["destination"] as? String ?? "").lastPathComponent)")
                                .font(.caption).foregroundStyle(.secondary).lineLimit(1)
                            if let suffix = job["collision_suffix"] as? String, !suffix.isEmpty {
                                Text("Filename suffix: \(suffix)").font(.caption2).foregroundStyle(.secondary)
                            }
                        }
                        Spacer()
                        Text(job["state"] as? String ?? "unknown").font(.caption)
                    }.padding(.vertical, 3)
                }.listStyle(.inset)
                HStack {
                    Button("Previous jobs") { Task { await model.loadDetail(offset: max(0, receipt.offset - receipt.pageSize)) } }
                        .disabled(receipt.offset == 0 || model.detailLoading)
                    Text("\(receipt.total == 0 ? 0 : receipt.offset + 1)–\(min(receipt.offset + receipt.jobs.count, receipt.total)) of \(receipt.total) jobs")
                        .font(.caption).foregroundStyle(.secondary)
                    Button("Next jobs") { Task { await model.loadDetail(offset: receipt.offset + receipt.pageSize) } }
                        .disabled(receipt.offset + receipt.pageSize >= receipt.total || model.detailLoading)
                    Spacer()
                    if model.detailLoading || model.actionBusy { ProgressView().controlSize(.small) }
                }
            } else if model.detailLoading {
                ProgressView("Loading batch receipt…").frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                ContentUnavailableView("Batch Receipt Unavailable", systemImage: "exclamationmark.circle",
                    description: Text("Reload this batch to read its captured presets and jobs."))
            }
        }
    }

    private func capturedPresetCard(_ raw: [String: Any]) -> some View {
        let name = raw["name"] as? String ?? "Preset"
        let destination = raw["destination"] as? String ?? ""
        let subfolder = raw["subfolder"] as? String
        let suffix = raw["filename_suffix"] as? String ?? ""
        return GroupBox(name) {
            VStack(alignment: .leading, spacing: 3) {
                Text(raw["format"] as? String == "jpeg" ? "JPEG" : "16-bit TIFF").font(.caption)
                if let options = raw["options"] as? [String: Any],
                   let format = raw["format"] as? String,
                   let settings = ExportEffectiveSettings(format: format, options: options, destination: destination) {
                    capturedSettings(settings)
                }
                if let subfolder { Text("Subfolder: \(subfolder)").font(.caption2) }
                Text("Collision suffix: \(suffix)").font(.caption2)
                Text(destination).font(.caption2).lineLimit(2).textSelection(.enabled)
            }.frame(width: 210, alignment: .leading)
        }
    }

    private func capturedSettings(_ settings: ExportEffectiveSettings) -> some View {
        let edge = settings.maxEdge == 0 ? "Full size" : "Max edge \(settings.maxEdge) px"
        let space = ["srgb": "sRGB", "p3": "Display P3", "adobe": "Adobe RGB", "prophoto": "ProPhoto RGB"][settings.space] ?? settings.space
        return VStack(alignment: .leading, spacing: 2) {
            Text("\(space) · \(edge) · Quality \(settings.quality)")
            Text("Sharpen \(settings.outputSharpen, specifier: "%.1f") · Priority \(settings.priority) · Metadata \(settings.metadata)")
            Text("Template: \(settings.filenameTemplate)")
            Text("Keyword hierarchy: \(settings.keywordHierarchy ? "On" : "Off")")
        }.font(.caption2).foregroundStyle(.secondary).textSelection(.enabled)
    }

    private func perform(_ action: String, _ batchID: String) async {
        errorMessage = nil
        if await model.perform(action, on: batchID) { await store.refreshJobs() }
        else { errorMessage = model.error ?? "The batch action could not be confirmed." }
    }
}

private func countSummary(_ counts: [String: Int]) -> String {
    let order = ["pending", "running", "done", "failed", "interrupted", "cancelled"]
    let parts = order.compactMap { state -> String? in
        guard let value = counts[state], value > 0 else { return nil }
        return "\(state.capitalized): \(value)"
    }
    return parts.isEmpty ? "No jobs" : parts.joined(separator: " · ")
}
