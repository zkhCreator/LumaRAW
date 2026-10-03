// Purpose: actual RAW selector workflow through native state and a packaged engine.
// Inputs: an explicitly supplied read-only RAW fixture and a fresh catalog.
// Outputs: fit/detail coordinate binding, a paired edit, undo and source-hash checks.
// No desktop pointer/keyboard/VoiceOver or camera-accuracy evidence is implied.
import AppKit
import CryptoKit
import Foundation
import SwiftUI

@main struct NativeRawWhiteBalanceRegression {
    @MainActor static func main() async {
        _=NSApplication.shared
        let store=Store()
        var checks:[String:Bool]=[:]
        var diagnostics:[String:Any]=[:]
        func check(_ value:Bool,_ name:String)throws {
            checks[name]=value
            if !value {throw EngineFailure(message:name)}
        }
        func wait(_ predicate:()->Bool) async throws {
            for _ in 0..<1200 {
                if predicate() {return}
                try await Task.sleep(nanoseconds:20_000_000)
            }
            throw EngineFailure(message:"RAW white-balance state did not settle: \(store.error ?? "no error")")
        }
        func ready(_ id:Int) async throws {
            try await wait {store.photo?.id==id && !store.loading && !store.rendering && store.whiteBalancePreviewIdentity != nil}
        }
        func photo(_ id:Int) async throws ->Photo {
            guard let row=Photo(try await Backend.call("get_photo",["photo_id":id])) else {
                throw EngineFailure(message:"RAW photo was not returned")
            }
            return row
        }
        do {
            guard let fixture=ProcessInfo.processInfo.environment["LUMARAW_TEST_RAW_FIXTURE"] else {
                throw EngineFailure(message:"An explicit read-only RAW fixture is required")
            }
            let path=URL(fileURLWithPath:fixture)
            let hashBefore=SHA256.hash(data:try Data(contentsOf:path))
            _=try await Backend.call("queue_control",["action":"pause"])
            _=try await Backend.call("settings",["compute_backend":"cpu"])
            await store.importPaths([path.path])
            await store.startDevelop()
            guard let id=store.selected else {throw EngineFailure(message:"RAW import did not select its photo")}
            try await ready(id)
            let original=try await photo(id)
            let history=try await Backend.call("list_history",["photo_id":id,"expected_revision":original.revision])
            let initialSteps=(history["steps"] as? [[String:Any]])?.count ?? 0
            try check(store.whiteBalancePreviewIdentity?.sourceFingerprint.count==24,"raw_preview_captures_source_identity")

            // A real detail preview must retain full-output dimensions. Expand
            // its center before sending the source-linear sensor sample.
            store.detail=true
            store.cx=0.5;store.cy=0.5
            store.render(debounce:false)
            try await ready(id)
            await store.armWhiteBalanceSelector()
            try await wait {store.whiteBalanceTargetActive && store.whiteBalanceArmPreview != nil}
            let display=WhiteBalanceDisplayGeometry(available:CGSize(width:640,height:480),
                imageRect:CGRect(x:0,y:0,width:640,height:480),displayScale:1,role:"active",after:true)
            store.whiteBalanceDisplayDidChange(display)
            guard let identity=store.whiteBalanceArmPreview,
                  let fullPoint=WhiteBalancePointMapping.fullPoint(CGPoint(x:0.5,y:0.5),preview:identity) else {
                throw EngineFailure(message:"RAW detail frame has no sample identity")
            }
            try check(identity.context.detail && identity.roiWidth<identity.fullWidth && identity.roiHeight<identity.fullHeight,
                      "raw_detail_frame_uses_full_output_and_bounded_roi")
            var calls:[(String,[String:Any])]=[]
            var sampleReply:[String:Any]=[:]
            let call:WhiteBalanceCommandCall={method,params in
                calls.append((method,params))
                let reply=try await Backend.call(method,params)
                if method=="sample_white_balance" {sampleReply=reply}
                return reply
            }
            let applied=await store.sampleWhiteBalance(localPoint:CGPoint(x:0.5,y:0.5),
                previewIdentity:identity,display:display,call:call)
            diagnostics=["sample":sampleReply,"calls":calls.map{$0.0},"error":store.error ?? ""]
            try check(applied,"raw_detail_click_completes_one_paired_edit")
            try check(calls.map{$0.0}==["sample_white_balance","edit_photo"],"raw_click_sends_one_sample_and_one_edit")
            try check(sampleReply["solver"] as? String=="libraw_greybox","raw_click_uses_verified_sensor_solver")
            let point=calls.first?.1["point"] as? [String:Double] ?? [:]
            try check(point["x"]==Double(fullPoint.x) && point["y"]==Double(fullPoint.y),
                      "raw_detail_click_expands_to_captured_full_output_point")
            let patch=calls.last?.1["patch"] as? [String:Any] ?? [:]
            try check(Set(patch.keys)==Set(["temperature","tint"]) &&
                calls.last?.1["expected_source_fingerprint"] as? String==identity.sourceFingerprint,
                "raw_axes_share_one_source_bound_edit")
            try await ready(id)
            let saved=try await photo(id)
            let savedHistory=try await Backend.call("list_history",["photo_id":id,"expected_revision":saved.revision])
            try check(saved.revision==original.revision+1 &&
                ((savedHistory["steps"] as? [[String:Any]])?.count ?? 0)==initialSteps+1,
                "raw_paired_edit_is_one_revision_and_history_step")
            _=try await Backend.call("undo_photo",["photo_id":id,"expected_revision":saved.revision])
            await store.load(id)
            try await ready(id)
            let undone=try await photo(id)
            try check(NSDictionary(dictionary:undone.recipe).isEqual(to:original.recipe),"raw_undo_restores_original_recipe")
            try check(SHA256.hash(data:try Data(contentsOf:path))==hashBefore,"raw_original_bytes_remain_unchanged")
            print(String(data:try JSONSerialization.data(withJSONObject:["ok":true,"checks":checks,
                "diagnostics":diagnostics,"desktop_ui":"NOT_VERIFIED","keyboard_pointer_voiceover":"NOT_VERIFIED"],
                options:[.prettyPrinted,.sortedKeys]),encoding:.utf8)!)
            exit(0)
        } catch {
            print(String(data:try! JSONSerialization.data(withJSONObject:["ok":false,"checks":checks,
                "diagnostics":diagnostics,"error":error.localizedDescription,"store_error":store.error ?? "",
                "desktop_ui":"NOT_VERIFIED"],options:.prettyPrinted),encoding:.utf8)!)
            exit(1)
        }
    }
}
