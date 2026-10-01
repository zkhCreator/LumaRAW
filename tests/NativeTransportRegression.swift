// Purpose: persistent native relay ordering, failure isolation and UI suspension.
// Inputs: an isolated real engine plus a disposable adversarial stdio fixture.
// Outputs: correlation/no-replay assertions and warm request/main-actor timings.
// No personal catalog, real desktop input or end-to-end UI smoothness claim.
import AppKit
import Foundation

@main struct NativeTransportRegression {
    @MainActor static func main() async {
        _=NSApplication.shared
        var checks:[String:Bool]=[:],times:[Double]=[]
        func check(_ value:Bool,_ name:String)throws {checks[name]=value;if !value {throw EngineFailure(message:name)}}
        do {
            let env=ProcessInfo.processInfo.environment
            let work=env["LUMARAW_TEST_WORK"]!,fixture=env["LUMARAW_TEST_RELAY"]!
            let peer=NativeCommandTransport(executable:fixture,catalog:work+"/relay-fixture")
            let first=try await peer.call("ping",["value":"first"]),pid=first["pid"] as? Int
            try check(pid != nil,"relay_starts")
            for index in 0..<12 {
                let result=try await peer.call("ping",["value":index])
                try check(result["pid"] as? Int==pid && result["value"] as? Int==index,"reuses_one_process_\(index)")
            }
            async let slow=peer.call("slow",["value":"slow"])
            try await Task.sleep(nanoseconds:20_000_000)
            let start=Date(),fast=try await peer.call("ping",["value":"fast"])
            try check(fast["value"] as? String=="fast" && Date().timeIntervalSince(start)<0.25,"fast_reply_overtakes_slow_request")
            let slowReply=try await slow
            try check(slowReply["value"] as? String=="slow","out_of_order_reply_keeps_identity")
            let unicode="照片 é / ' & $",split=try await peer.call("split",["value":unicode])
            try check(split["value"] as? String==unicode,"split_utf8_lines_preserve_content")
            do {_=try await peer.call("failure",[:]);try check(false,"typed_engine_failure")}
            catch let error as EngineFailure {try check(error.canActivateService && error.message=="Engine busy","typed_engine_failure")}
            do {_=try await peer.call("ping",["value":String(repeating:"x",count:1024*1024)]);try check(false,"oversize_request_rejected")}
            catch {try check(error.localizedDescription.contains("not sent"),"oversize_request_rejected")}
            let healthy=try await peer.call("ping",[:])
            try check(healthy["pid"] as? Int==pid,"local_validation_preserves_healthy_relay")
            do {_=try await peer.call("lost_mutation",[:]);try check(false,"lost_mutation_reports_unknown_outcome")}
            catch {try check(error.localizedDescription.contains("may have completed"),"lost_mutation_reports_unknown_outcome")}
            let marker=try String(contentsOfFile:work+"/relay-fixture/mutation-count",encoding:.utf8)
            try check(marker=="committed\n","lost_mutation_is_never_replayed")
            let replacement=try await peer.call("ping",[:])
            try check(replacement["pid"] as? Int != pid,"new_call_can_launch_replacement")
            for method in ["malformed","unknown","oversize"] {
                do {_=try await peer.call(method,[:]);try check(false,"reject_\(method)")}
                catch {try check(error.localizedDescription.contains("may have completed"),"reject_\(method)")}
                _=try await peer.call("ping",[:])
            }
            _=try await Backend.call("queue_control",["action":"pause"])
            for _ in 0..<30 {
                let time=Date();_=try await Backend.call("status");times.append(Date().timeIntervalSince(time)*1000)
            }
            async let status=Backend.call("status")
            async let schema=Backend.call("recipe_schema")
            let (a,b)=try await (status,schema)
            try check(a["catalog"] != nil && b["defaults"] != nil,"real_broker_concurrent_replies")
            let sorted=times.sorted()
            let report:[String:Any]=["ok":true,"checks":checks,"warm_status_samples":times,
                "warm_status_median_ms":sorted[sorted.count/2],"warm_status_p95_ms":sorted[Int(Double(sorted.count-1)*0.95)],
                "desktop_ui":"NOT_VERIFIED","voiceover":"NOT_VERIFIED"]
            let data=try JSONSerialization.data(withJSONObject:report,options:[.prettyPrinted,.sortedKeys]);print(String(data:data,encoding:.utf8)!);exit(0)
        } catch {
            let data=try! JSONSerialization.data(withJSONObject:["ok":false,"checks":checks,"error":error.localizedDescription],options:[.prettyPrinted,.sortedKeys])
            print(String(data:data,encoding:.utf8)!);exit(1)
        }
    }
}
