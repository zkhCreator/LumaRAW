// Purpose: native filename drafts, conflict safety and real Copy integration.
// Inputs: generated originals, an isolated broker and destination. Outputs: state
// assertions and offscreen editor layout. No desktop/VoiceOver acceptance claim.
import AppKit
import Foundation
import SwiftUI

@main struct NativeImportNamingRegression {
    @MainActor static func main() async {
        _=NSApplication.shared
        var checks: [String:Bool]=[:]
        func check(_ value: Bool,_ name: String) throws {
            checks[name]=value
            if !value { throw EngineFailure(message:name) }
        }
        do {
            let paths=ProcessInfo.processInfo.environment["LUMARAW_TEST_FIXTURES"]!.components(separatedBy:"|")
            let originals=try paths.map { try Data(contentsOf:URL(fileURLWithPath:$0)) }
            let root=URL(fileURLWithPath:ProcessInfo.processInfo.environment["LUMARAW_CATALOG"]!).deletingLastPathComponent()
            let destination=root.appendingPathComponent("naming-output")
            try FileManager.default.createDirectory(at:destination,withIntermediateDirectories:true)
            let review=ImportReviewModel(sources:paths);review.mode="copy";review.destination=destination.path
            await review.scan();review.openNaming();let editor=review.namingEditor!
            await editor.load()
            try check(editor.ready && !editor.enabled && !editor.dirty && editor.builtins.count == 9,"copy_loads_disabled_naming_and_builtin_templates")
            editor.chooseBuiltin(editor.builtins[2]);editor.customText="Coast";editor.start="21"
            try check(editor.dirty && editor.enabled && editor.templateID == nil,"builtin_choice_is_an_unsaved_draft")
            await editor.preview()
            try check(editor.previewCurrent && editor.previewRows.count == paths.count && (editor.previewRows.first?["destination"] as? String)?.hasSuffix("Coast-0021.png") == true,"engine_previews_draft_with_sequence")
            try check(try FileManager.default.contentsOfDirectory(atPath:destination.path).isEmpty,"preview_writes_no_destination_files")
            editor.customText="Harbor"
            try check(!editor.previewCurrent,"edited_draft_marks_previous_preview_stale")
            editor.templateName="Sequence";await editor.saveTemplate(asNew:true)
            let templateID=editor.templateID!,capturedLibrary=editor.templateRevision
            try check(editor.templates.count == 1 && editor.dirty,"template_save_does_not_apply_import_settings")
            _=try await Backend.call("save_filename_template",["template_id":templateID,"name":"External",
                "template":[["kind":"filename"]],"expected_revision":capturedLibrary])
            await editor.browse(offset:0);await editor.saveTemplate(asNew:false)
            try check(editor.error?.contains("changed") == true && editor.templateRevision == capturedLibrary && editor.customText == "Harbor","library_refresh_never_rebases_loaded_template_draft")
            await editor.chooseSaved(editor.templates[0]);editor.chooseBuiltin(editor.builtins[2]);editor.templateName="Import Sequence"
            await editor.saveTemplate(asNew:true)
            try check(editor.templateID != templateID,"save_as_new_preserves_existing_template_identity")
            await editor.preview()
            let host=NSHostingView(rootView:ImportNamingSheet(model:editor).content.background(Color(nsColor:.windowBackgroundColor)))
            host.frame=NSRect(x:0,y:0,width:960,height:810);host.layoutSubtreeIfNeeded()
            guard let bitmap=host.bitmapImageRepForCachingDisplay(in:host.bounds) else { throw EngineFailure(message:"No offscreen bitmap") }
            host.cacheDisplay(in:host.bounds,to:bitmap)
            try bitmap.representation(using:.png,properties:[:])!.write(to:root.appendingPathComponent("import-naming-editor.png"))
            try check(await editor.save(),"save_captures_naming_settings")
            try check(!editor.dirty && review.plan?.revision == editor.revision && review.items.first?.destination.hasSuffix("Harbor-0021.png") == true,"acknowledged_save_refreshes_parent_destination_names")
            editor.customText="Unsent"
            let captured=review.plan!
            _=try await Backend.call("set_import_options",["plan_id":captured.id,"expected_revision":captured.revision,"skip_duplicates":false])
            try check(!(await editor.save()) && editor.error?.contains("changed") == true && editor.customText == "Unsent","stale_plan_preserves_draft_and_rejects_overwrite")
            editor.invalidate();review.namingEditor=nil;await review.load();review.openNaming()
            let reopened=review.namingEditor!;await reopened.load()
            try check(reopened.customText == "Harbor" && reopened.start == "21","reopen_restores_saved_not_rejected_draft")
            await reopened.chooseSaved(reopened.templates.first{$0["id"] as? String != templateID}!)
            await reopened.deleteTemplate()
            try check(reopened.templateID == nil && reopened.customText == "Harbor","delete_template_keeps_captured_import_choice")
            reopened.invalidate();review.namingEditor=nil;await review.apply()
            try check(review.plan?.state == "applied" && review.plan?.number("imported") == paths.count,"copy_applies_saved_naming")
            let photos=try await Backend.call("list_photos",["stacked":false,"descending":false])
            for (i,row) in (photos["photos"] as! [[String:Any]]).enumerated() {
                let photo=try await Backend.call("get_photo",["photo_id":row["id"]!])
                try check(photo["name"] as? String == String(format:"Harbor-%04d.png",21+i),"catalog_uses_destination_name_\(i)")
                try check(photo["original_name"] as? String == URL(fileURLWithPath:paths[i]).lastPathComponent,"catalog_retains_original_name_\(i)")
                try check(try Data(contentsOf:URL(fileURLWithPath:photo["path"] as! String)) == originals[i],"copied_bytes_match_original_\(i)")
            }
            try check(try paths.map { try Data(contentsOf:URL(fileURLWithPath:$0)) } == originals,"originals_unchanged")
            review.invalidate()
            print(String(data:try JSONSerialization.data(withJSONObject:["ok":true,"checks":checks,"desktop_ui":"NOT_VERIFIED"],options:[.prettyPrinted,.sortedKeys]),encoding:.utf8)!)
            exit(0)
        } catch {
            print(String(data:try! JSONSerialization.data(withJSONObject:["ok":false,"checks":checks,"error":error.localizedDescription],options:.prettyPrinted),encoding:.utf8)!)
            exit(1)
        }
    }
}
