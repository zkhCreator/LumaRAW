// Purpose: handle documented rating, flag and color-label culling-key variants
// and reconcile overlapping asynchronous rating/flag write replies.
// Inputs: captured action targets and a bounded Library page snapshot.
// Outputs: catalog mutations, accepted field presentation and guarded focus state.
// Non-goals: Auto Advance preferences, Caps Lock behavior and unloaded-page guessing.
import Foundation

typealias CullingCommandCall = (String, [String: Any]) async throws -> [String: Any]
typealias CullingMutationAdoption = @MainActor (Int) -> Bool
typealias CullingActionCompletion = @MainActor () -> Void

struct PhotoFieldWriteKey: Hashable {
    let photoID: Int
    let field: String
}

struct PhotoFieldWriteResolution {
    let adoptable: Set<PhotoFieldWriteKey>
    let isLatestAttempt: Bool
}

// Bounds rating/flag reply ordering to fields with active writes only.
struct PhotoFieldWriteLedger {
    private struct State {
        var pending: Set<Int> = []
        var latestStarted: Int
        var latestAcknowledged: Int? = nil
    }

    private var generation = 0
    private var states: [PhotoFieldWriteKey: State] = [:]

    mutating func begin(_ keys: Set<PhotoFieldWriteKey>) -> Int {
        generation += 1
        let token = generation
        for key in keys {
            var state = states[key] ?? State(latestStarted: token)
            state.pending.insert(token)
            state.latestStarted = token
            states[key] = state
        }
        return token
    }

    mutating func finish(
        _ token: Int,
        keys: Set<PhotoFieldWriteKey>,
        accepted: Bool
    ) -> PhotoFieldWriteResolution {
        var adoptable: Set<PhotoFieldWriteKey> = []
        var isLatestAttempt = true

        for key in keys {
            guard var state = states[key], state.pending.remove(token) != nil else {
                isLatestAttempt = false
                continue
            }

            if state.latestStarted != token {
                isLatestAttempt = false
            }
            if accepted && (state.latestAcknowledged.map { token > $0 } ?? true) {
                state.latestAcknowledged = token
                adoptable.insert(key)
            }

            if state.pending.isEmpty {
                states.removeValue(forKey: key)
            } else {
                states[key] = state
            }
        }

        return PhotoFieldWriteResolution(adoptable: adoptable, isLatestAttempt: isLatestAttempt)
    }
}

enum CullingShiftMutation {
    case rating(Int)
    case flag(Int)
    case colorLabel(String)
}

struct CullingShortcutAction {
    let mutation: CullingShiftMutation
    let advanceAfterSuccess: Bool
    let refreshAfterMetadataMutation: Bool
}

enum CullingShortcutMapper {
    static func action(for key: String, shifted: Bool) -> CullingShortcutAction? {
        let key = key.lowercased()
        if let rating = Int(key), (0...5).contains(rating) {
            return CullingShortcutAction(
                mutation: .rating(rating),
                advanceAfterSuccess: shifted,
                refreshAfterMetadataMutation: false
            )
        }

        switch key {
        case "p":
            return CullingShortcutAction(mutation: .flag(1), advanceAfterSuccess: shifted, refreshAfterMetadataMutation: false)
        case "x":
            return CullingShortcutAction(mutation: .flag(-1), advanceAfterSuccess: shifted, refreshAfterMetadataMutation: false)
        case "u":
            return CullingShortcutAction(mutation: .flag(0), advanceAfterSuccess: shifted, refreshAfterMetadataMutation: false)
        case "6":
            return CullingShortcutAction(mutation: .colorLabel("red"), advanceAfterSuccess: shifted, refreshAfterMetadataMutation: !shifted)
        case "7":
            return CullingShortcutAction(mutation: .colorLabel("yellow"), advanceAfterSuccess: shifted, refreshAfterMetadataMutation: !shifted)
        case "8":
            return CullingShortcutAction(mutation: .colorLabel("green"), advanceAfterSuccess: shifted, refreshAfterMetadataMutation: !shifted)
        case "9":
            return CullingShortcutAction(mutation: .colorLabel("blue"), advanceAfterSuccess: shifted, refreshAfterMetadataMutation: !shifted)
        default:
            return nil
        }
    }
}

@MainActor
final class CullingAdvanceContext {
    let actionPhotoIDs: [Int]
    let activePhotoID: Int
    let visiblePhotoIDs: [Int]
    let selectedPhotoID: Int?
    let selection: Set<Int>
    let selectionAnchor: Int?
    let sourceNavigationGeneration: Int
    let reviewSwitchGeneration: Int
    let reviewSwitchInFlightGeneration: Int?
    let cullingActionGeneration: Int
    let pageGeneration: Int
    let workspace: String
    let develop: Bool
    let libraryView: LibraryViewMode
    let mode: String
    let collectionID: Int?
    let folderID: Int?
    let activeCollectionID: Int?
    let activeCollectionKind: String?
    let activeCollectionRevision: Int?
    let activeCollectionRules: [String: Any]
    let aggregateSetID: Int?
    let collectionNodePhotoRefreshGeneration: Int?
    let offset: Int
    let search: String
    let filters: [String: Any]
    let librarySort: String
    let sortDescending: Bool
    let showStacks: Bool
    let includeSubfolders: Bool
    private(set) var acceptedPageOffset: Int?
    private(set) var adoptedFocus: CullingFocusSnapshot?

    struct CullingFocusSnapshot {
        let selected: Int?
        let selection: Set<Int>
        let anchor: Int?
    }

    init(store: Store, actionPhotoIDs: [Int]) {
        self.actionPhotoIDs = actionPhotoIDs
        activePhotoID = store.selected ?? -1
        visiblePhotoIDs = store.photos.map(\.id)
        selectedPhotoID = store.selected
        selection = store.selection
        selectionAnchor = store.cullingSelectionAnchor
        sourceNavigationGeneration = store.sourceNavigationGeneration
        reviewSwitchGeneration = store.reviewSwitchGeneration
        reviewSwitchInFlightGeneration = store.reviewSwitchInFlightGeneration
        cullingActionGeneration = store.cullingActionGeneration
        pageGeneration = store.cullingPageGeneration
        workspace = store.workspace
        develop = store.develop
        libraryView = store.libraryView
        mode = store.mode
        collectionID = store.collectionID
        folderID = store.folderID
        activeCollectionID = store.activeCollection?.id
        activeCollectionKind = store.activeCollection?.kind
        activeCollectionRevision = store.activeCollection?.revision
        activeCollectionRules = store.activeCollection?.rules ?? [:]
        let currentSetID = store.workspace == "library"
            && !store.develop
            && store.folderID == nil
            && store.collectionID == store.activeCollection?.id
            && store.activeCollection?.kind == "set"
            ? store.collectionID
            : nil
        aggregateSetID = currentSetID
        collectionNodePhotoRefreshGeneration = currentSetID == nil
            ? nil
            : store.collectionNodePhotoRefreshGeneration
        offset = store.offset
        search = store.search
        filters = store.libraryFilters
        librarySort = store.librarySort
        sortDescending = store.sortDescending
        showStacks = store.showStacks
        includeSubfolders = store.includeSubfolders
    }

    var canAdvance: Bool {
        workspace == "library"
            && !develop
            && reviewSwitchInFlightGeneration == nil
            && (libraryView == .grid || libraryView == .loupe)
            && actionPhotoIDs == [activePhotoID]
            && visiblePhotoIDs.contains(activePhotoID)
    }

    func matches(
        _ store: Store,
        pageGeneration expectedPageGeneration: Int
    ) -> Bool {
        let expectedSelected: Int?
        let expectedSelection: Set<Int>
        let expectedAnchor: Int?
        if let adoptedFocus {
            expectedSelected = adoptedFocus.selected
            expectedSelection = adoptedFocus.selection
            expectedAnchor = adoptedFocus.anchor
        } else {
            expectedSelected = selectedPhotoID
            expectedSelection = selection
            expectedAnchor = selectionAnchor
        }
        guard store.cullingPageGeneration == expectedPageGeneration,
              store.sourceNavigationGeneration == sourceNavigationGeneration,
              store.reviewSwitchGeneration == reviewSwitchGeneration,
              store.reviewSwitchInFlightGeneration == reviewSwitchInFlightGeneration,
              store.cullingActionGeneration == cullingActionGeneration,
              store.workspace == workspace,
              store.develop == develop,
              store.libraryView == libraryView,
              store.mode == mode,
              store.collectionID == collectionID,
              store.folderID == folderID,
              store.activeCollection?.id == activeCollectionID,
              store.activeCollection?.kind == activeCollectionKind,
              store.activeCollection?.revision == activeCollectionRevision,
              store.offset == (acceptedPageOffset ?? offset),
              store.search == search,
              NSDictionary(dictionary: store.libraryFilters).isEqual(to: filters),
              store.librarySort == librarySort,
              store.sortDescending == sortDescending,
              store.showStacks == showStacks,
              store.includeSubfolders == includeSubfolders,
              store.selected == expectedSelected,
              store.selection == expectedSelection,
              store.cullingSelectionAnchor == expectedAnchor else {
            return false
        }
        if aggregateSetID != nil,
           store.collectionNodePhotoRefreshGeneration != collectionNodePhotoRefreshGeneration {
            return false
        }
        return true
    }

    func acceptPageOffset(_ value: Int) {
        acceptedPageOffset = value
    }

    func adoptAdvanceFocus(_ store: Store, pagePhotoIDs: Set<Int>) {
        guard canAdvance,
              let currentIndex = visiblePhotoIDs.firstIndex(of: activePhotoID) else { return }
        if let next = visiblePhotoIDs.dropFirst(currentIndex + 1).first(where: pagePhotoIDs.contains) {
            store.adoptCullingFocus(next)
            recordFocus(store)
        } else if pagePhotoIDs.contains(activePhotoID) {
            var survivingSelection = selection.intersection(pagePhotoIDs)
            survivingSelection.insert(activePhotoID)
            let anchor = selectionAnchor.flatMap {
                survivingSelection.contains($0) ? $0 : nil
            } ?? activePhotoID
            store.adoptCullingBatchFocus(
                activePhotoID,
                selection: survivingSelection,
                anchor: anchor
            )
            recordFocus(store)
        } else {
            store.clearCullingFocus()
            recordFocus(store)
        }
    }

    func adoptBatchFocus(_ store: Store, pagePhotoIDs: Set<Int>) {
        let survivors = selection.intersection(pagePhotoIDs)
        guard !survivors.isEmpty else {
            store.clearCullingFocus()
            recordFocus(store)
            return
        }
        let nextSelected: Int
        if let selectedPhotoID, survivors.contains(selectedPhotoID) {
            nextSelected = selectedPhotoID
        } else {
            nextSelected = visiblePhotoIDs.first(where: survivors.contains) ?? survivors.sorted()[0]
        }
        store.adoptCullingBatchFocus(
            nextSelected,
            selection: survivors,
            anchor: selectionAnchor.flatMap { survivors.contains($0) ? $0 : nil } ?? nextSelected
        )
        recordFocus(store)
    }

    func recordFocus(_ store: Store) {
        adoptedFocus = CullingFocusSnapshot(
            selected: store.selected,
            selection: store.selection,
            anchor: store.cullingSelectionAnchor
        )
    }

    func needsPageRefresh(for mutation: CullingShiftMutation) -> Bool {
        guard workspace == "library",
              !develop,
              (libraryView == .grid || libraryView == .loupe) else { return false }

        switch mutation {
        case .rating(_) where mode == "stars": return true
        case .flag(_) where mode == "keepers" || mode == "rejects": return true
        default: break
        }

        let filterFields: Set<String>
        let sortField: String?
        switch mutation {
        case .rating(_):
            filterFields = ["rating_min", "rating_max"]
            sortField = "rating"
        case .flag(_):
            filterFields = ["flag"]
            sortField = nil
        case .colorLabel(_):
            filterFields = ["color_label"]
            sortField = "color"
        }
        if !filterFields.isDisjoint(with: Set(filters.keys)) {
            return true
        }
        if let sortField, librarySort == sortField { return true }
        if !search.isEmpty { return true }
        if activeCollectionID == collectionID,
           activeCollectionKind == "set" {
            return true
        }
        guard activeCollectionID == collectionID,
              activeCollectionKind == "smart" else { return false }
        return !filterFields.isDisjoint(with: Set(activeCollectionRules.keys))
    }
}

extension Store {
    @discardableResult
    func applyCullingShortcut(
        _ mutation: CullingShiftMutation,
        advanceAfterSuccess: Bool,
        refreshAfterMetadataMutation: Bool = false,
        call: CullingCommandCall? = nil,
        pageCall: CullingCommandCall? = nil,
        completion: CullingActionCompletion? = nil
    ) -> Bool {
        let ids = actionPhotoIDs
        guard !ids.isEmpty else { return false }

        cullingActionGeneration += 1
        let actionGeneration = cullingActionGeneration
        let context = CullingAdvanceContext(store: self, actionPhotoIDs: ids)
        let shouldAdvance = advanceAfterSuccess && context.canAdvance
        let shouldRefreshPage = (advanceAfterSuccess || refreshAfterMetadataMutation)
            && context.needsPageRefresh(for: mutation)
        let preserveGridBatch = context.libraryView == .grid && ids.count > 1
        let idSet = Set(ids)
        let capturedTargets = photos.filter { idSet.contains($0.id) }
        if case .colorLabel(_)=mutation, capturedTargets.count != ids.count { return false }
        for id in idSet {
            cullingPhotoActionGenerationByPhoto[id] = actionGeneration
        }
        let shouldAdoptMutation: CullingMutationAdoption = { [weak self] photoID in
            guard let self else { return false }
            return self.cullingActionGeneration == actionGeneration
                && self.cullingPhotoActionGenerationByPhoto[photoID] == actionGeneration
        }

        Task {
            defer {
                for id in idSet where cullingPhotoActionGenerationByPhoto[id] == actionGeneration {
                    cullingPhotoActionGenerationByPhoto.removeValue(forKey: id)
                }
                completion?()
            }
            let accepted: Bool
            switch mutation {
            case .rating(let value):
                accepted = await ratePhotos(
                    ids,
                    patch: ["rating": value],
                    call: call,
                    shouldAdopt: shouldAdoptMutation
                )
            case .flag(let value):
                accepted = await ratePhotos(
                    ids,
                    patch: ["flag": value],
                    call: call,
                    shouldAdopt: shouldAdoptMutation
                )
            case .colorLabel(let label):
                accepted = await saveMetadata(
                    targets: capturedTargets,
                    patch: ["color_label": label],
                    refreshAfter: refreshAfterMetadataMutation && !shouldRefreshPage,
                    call: call,
                    shouldAdopt: shouldAdoptMutation
                )
            }
            guard accepted,
                  actionGeneration == cullingActionGeneration,
                  context.matches(self, pageGeneration: context.pageGeneration) else { return }

            if shouldRefreshPage {
                let pendingNodeRefresh = context.aggregateSetID == nil
                    ? nil
                    : pendingCollectionNodePhotoRefreshGeneration
                let refreshed = await refreshPage(
                    expectedSourceNavigationGeneration: context.sourceNavigationGeneration,
                    expectedReviewSwitchGeneration: context.aggregateSetID == nil
                        ? nil
                        : context.reviewSwitchGeneration,
                    expectedCollectionID: context.aggregateSetID,
                    consumingCollectionNodeRefreshGeneration: pendingNodeRefresh,
                    guardingCollectionNodePhotoRefreshGeneration: context.collectionNodePhotoRefreshGeneration,
                    cullingAdvanceContext: context,
                    advanceCullingSelection: shouldAdvance,
                    preserveCullingBatchSelection: preserveGridBatch,
                    pageCall: pageCall
                )
                guard refreshed,
                      actionGeneration == cullingActionGeneration,
                      context.matches(self, pageGeneration: context.pageGeneration + 1) else { return }
                return
            }

            guard shouldAdvance else { return }
            guard let currentIndex = context.visiblePhotoIDs.firstIndex(of: context.activePhotoID) else { return }
            let currentPageIDs = Set(photos.map(\.id))
            if let next = context.visiblePhotoIDs.dropFirst(currentIndex + 1).first(where: currentPageIDs.contains) {
                choose(next)
            } else if !currentPageIDs.contains(context.activePhotoID) {
                clearCullingFocus()
            }
        }
        return true
    }
}
