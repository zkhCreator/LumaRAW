// Purpose: navigate to the persisted last-import source after a local import.
// Inputs: a completed import count and the catalog's navigation preference.
// Outputs: refreshed pages and acknowledged preference state. External-client
// imports refresh an already viewed source without stealing current navigation.
// No catalog SQL, file operations, replay of imports or inferred batch membership.
import Foundation

extension Store {
    func finishImport(_ count: Int) async {
        guard count > 0 else { await refresh();return }
        let navigation=sourceNavigationGeneration
        let preferenceRead=importPreferenceGeneration
        do {
            let settings=try await Backend.call("settings")
            guard navigation == sourceNavigationGeneration,!importPreferenceBusy,
                  preferenceRead == importPreferenceGeneration else { await refresh();return }
            selectPreviousImport=settings["select_previous_import"] as? Bool ?? true
            if selectPreviousImport {
                guard await flushEdits() else { return }
                develop=false;libraryView = .grid
                await openLibraryMode("previous_import",clearFilters:true)
            } else { await refresh() }
        } catch { self.error=error.localizedDescription;await refresh() }
    }

    func setImportNavigation(_ value: Bool) async {
        guard !importPreferenceBusy else { return }
        importPreferenceGeneration+=1
        importPreferenceBusy=true;defer { importPreferenceBusy=false }
        do {
            let result=try await Backend.call("settings",["select_previous_import":value])
            selectPreviousImport=result["select_previous_import"] as? Bool ?? selectPreviousImport
        } catch { self.error=error.localizedDescription }
    }

    func importSourceChanged(_ result: [String:Any]) -> Bool {
        guard mode == "previous_import",let state=result["previous_import"] as? [String:Any],
              let revision=state["revision"] as? Int else { return false }
        return revision != previousImportRevision
    }
}
