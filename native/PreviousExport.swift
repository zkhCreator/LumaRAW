// Purpose: validate the catalog-local Previous export receipt used by native commands.
// Inputs: compact availability signals or a full settings read from the service.
// Outputs: typed, revision-bound state for one explicit queue action.
// This adapter performs no retries, queue writes, preset lookup or filesystem access.
import Foundation

struct PreviousExportSnapshot {
    let available: Bool
    let revision: Int
    let settings: ExportEffectiveSettings?

    init?(_ result: [String: Any]) {
        guard let available=result["available"] as? Bool,
              let revision=(result["revision"] as? NSNumber)?.intValue ?? result["revision"] as? Int,
              revision >= 0 else { return nil }
        self.available=available
        self.revision=revision
        if available {
            guard let raw=result["settings"] as? [String: Any],
                  let format=raw["format"] as? String,
                  let options=raw["options"] as? [String: Any],
                  let destination=raw["destination"] as? String,
                  let settings=ExportEffectiveSettings(format:format,options:options,destination:destination) else {
                return nil
            }
            self.settings=settings
        } else {
            self.settings=nil
        }
    }
}
