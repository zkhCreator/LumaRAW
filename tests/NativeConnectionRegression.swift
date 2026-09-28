// Purpose: native incompatible-service recovery against a real tagged test broker.
// Inputs: an isolated catalog seeded with one paused export. Outputs: startup error,
// explicit activation, queue/recipe preservation and reconnection assertions.
// No rendered alert, Settings interaction or desktop accessibility claim.
import AppKit
import Foundation

@main struct NativeConnectionRegression {
    @MainActor static func main() async {
        _ = NSApplication.shared
        let s=Store()
        var checks: [String:Bool] = [:]
        func check(_ value: Bool,_ name: String) throws {
            checks[name]=value
            if !value { throw EngineFailure(message:name) }
        }
        do {
            let before=try await Backend.call("service_connection",["action":"status"])
            try check(before["compatible"] as? Bool == false,"fixture_has_different_engine")
            await s.start()
            try check(s.error?.contains("Another build") == true,"startup_explains_build_mismatch")
            try check(s.serviceUpgradeNeeded && s.photo == nil,"startup_exposes_activation_without_loading_old_state")
            await s.activateCurrentService()
            try check(s.error == nil && !s.serviceUpgradeNeeded,"activation_recovers_failed_startup")
            try check(s.photo != nil && s.total == 2,"catalog_loads_after_handoff")
            let current=try await Backend.call("service_connection",["action":"status"])
            try check(current["compatible"] as? Bool == true && current["pid"] as? Int != before["pid"] as? Int,"new_engine_owns_catalog")
            let queue=try await Backend.call("list_jobs")
            let jobs=queue["jobs"] as? [[String:Any]] ?? []
            try check(queue["paused"] as? Bool == true && jobs.count == 1 && jobs[0]["state"] as? String == "pending","paused_pending_export_preserved")
            let job=try await Backend.call("get_job",["job_id":jobs[0]["id"]!])
            let recipe=job["recipe"] as? [String:Any] ?? [:]
            try check((recipe["exposure"] as? NSNumber)?.doubleValue == 0.75,"submitted_recipe_preserved")
            await s.activateCurrentService()
            let again=try await Backend.call("service_connection",["action":"status"])
            try check(again["pid"] as? Int == current["pid"] as? Int,"matching_activation_does_not_restart_service")
            try check(!s.connectingService && s.serviceConnectionMessage.contains("Connected"),"connection_state_is_settled")
            _=try await Backend.call("queue_control",["action":"cancel"])
            print(String(data:try JSONSerialization.data(withJSONObject:["ok":true,"checks":checks,
                "desktop_ui":"NOT_VERIFIED"],options:[.prettyPrinted,.sortedKeys]),encoding:.utf8)!)
            exit(0)
        } catch {
            print(String(data:try! JSONSerialization.data(withJSONObject:["ok":false,"checks":checks,
                "error":error.localizedDescription,"store_error":s.error ?? ""],options:.prettyPrinted),encoding:.utf8)!)
            exit(1)
        }
    }
}
