// Purpose: exercise native selection and revision races against the actual broker.
// Inputs: disposable catalog and two fixture paths. Output: JSON assertions.
// Boundaries: in-process state tests, not desktop gestures or VoiceOver evidence.
import AppKit
import Foundation

@main struct NativeStateRegression {
    @MainActor static func main() async {
        _ = NSApplication.shared
        let s=Store()
        var checks:[String:Bool]=[:]
        func check(_ value:Bool,_ name:String)throws {checks[name]=value;if !value{throw EngineFailure(message:name)}}
        func waitForLoad() async throws {
            for _ in 0..<200 {if s.photo?.id==s.selected && s.photo != nil && !s.loading{return};try await Task.sleep(nanoseconds:20_000_000)}
            throw EngineFailure(message:"Load timed out")
        }
        do {
            let paths=ProcessInfo.processInfo.environment["LUMARAW_TEST_FIXTURES"]!.components(separatedBy:"|")
            await s.importPaths(paths)
            try check(s.photos.count==2,"import_two_photos")
            let a=s.photos[0].id,b=s.photos[1].id
            s.choose(a);try await waitForLoad()
            let original=try await Backend.call("get_photo",["photo_id":a])
            s.choose(b)
            try check(s.photo==nil && s.recipe.isEmpty,"selection_clears_old_inspector_synchronously")
            s.set("exposure",4.0)
            try await waitForLoad()
            try check((s.recipe["exposure"] as? NSNumber)?.doubleValue==0,"loading_rejects_parameter_edits")
            let after=try await Backend.call("get_photo",["photo_id":a])
            try check(original["revision"] as? Int == after["revision"] as? Int,"switch_preserves_previous_photo")
            s.choose(b,extend:true)
            try check(s.selected==nil && s.selection.isEmpty && s.photo==nil,"deselect_last_clears_active_photo")
            await s.export(Backend.catalog+"/exports","jpeg",[:])
            let queue=try await Backend.call("list_jobs")
            try check((queue["jobs"] as? [[String:Any]])?.isEmpty==true,"empty_selection_cannot_export")
            s.error=nil;s.choose(a);try await waitForLoad()
            s.set("exposure",0.4);s.search="no-such-photo-unique";await s.refresh()
            try check(s.photos.isEmpty && s.selected==nil && s.photo==nil && s.selection.isEmpty,"filter_clears_invisible_selection")
            let saved=try await Backend.call("get_photo",["photo_id":a])
            try check(((saved["recipe"] as? [String:Any])?["exposure"] as? NSNumber)?.doubleValue==0.4,"filter_flushes_pending_edit")
            s.search="";await s.refresh();s.choose(a);try await waitForLoad()
            let oldRevision=s.photo!.revision
            _=try await Backend.call("edit_photo",["photo_id":a,"expected_revision":oldRevision,"patch":["exposure":1.1]])
            await s.mutate("rate_photo",["photo_id":a,"rating":4])
            try check(s.photo?.revision==oldRevision && s.photo?.rating==4,"rating_does_not_adopt_external_recipe_revision")
            s.set("exposure",0.7)
            let flushed=await s.flushEdits()
            try check(!flushed && s.error != nil,"stale_edit_reports_conflict")
            let external=try await Backend.call("get_photo",["photo_id":a])
            try check(((external["recipe"] as? [String:Any])?["exposure"] as? NSNumber)?.doubleValue==1.1,"conflict_preserves_external_edit")
            s.error=nil;s.set("exposure",0.8)
            try check(await s.flushEdits(),"save_after_conflict")
            s.undo();s.choose(b)
            try check(s.selected==a && s.editing,"undo_blocks_selection_until_reply")
            for _ in 0..<200 {if !s.editing{break};try await Task.sleep(nanoseconds:20_000_000)}
            try check((s.recipe["exposure"] as? NSNumber)?.doubleValue==1.1,"undo_applies_to_correct_photo")
            s.choose(b);try await waitForLoad()
            try check((s.recipe["exposure"] as? NSNumber)?.doubleValue==0,"other_photo_untouched")
            let report:[String:Any]=["ok":true,"checks":checks,"desktop_ui":"NOT_VERIFIED","voiceover":"NOT_VERIFIED"]
            let data=try JSONSerialization.data(withJSONObject:report,options:[.prettyPrinted,.sortedKeys]);print(String(data:data,encoding:.utf8)!);exit(0)
        }catch {
            let report:[String:Any]=["ok":false,"checks":checks,"error":error.localizedDescription]
            let data=try! JSONSerialization.data(withJSONObject:report,options:[.prettyPrinted,.sortedKeys]);print(String(data:data,encoding:.utf8)!);exit(1)
        }
    }
}
