// Purpose: saved import workflows through native models and real engine IPC.
// Inputs: disposable sources, destinations and catalog-local preset snapshots.
// Outputs: lifecycle, stale-draft, rescan, original safety and offscreen evidence.
// No desktop event, native file-panel or VoiceOver acceptance is implied.
import AppKit
import Foundation
import SwiftUI

@main struct NativeImportPresetRegression {
    @MainActor static func main() async {
        _=NSApplication.shared
        var checks:[String:Bool]=[:]
        func check(_ value:Bool,_ name:String) throws {
            checks[name]=value;if !value {throw EngineFailure(message:name)}
        }
        do {
            let paths=ProcessInfo.processInfo.environment["LUMARAW_TEST_FIXTURES"]!.components(separatedBy:"|")
            let originals=try paths.map {try Data(contentsOf:URL(fileURLWithPath:$0))}
            let root=URL(fileURLWithPath:ProcessInfo.processInfo.environment["LUMARAW_CATALOG"]!).deletingLastPathComponent()
            let destination=root.appendingPathComponent("preset-output"),backup=root.appendingPathComponent("preset-backup")
            for url in [destination,backup] {try FileManager.default.createDirectory(at:url,withIntermediateDirectories:true)}
            let review=ImportReviewModel(sources:paths)
            review.mode="copy";review.destination=destination.path;review.makeSecondCopy=true;review.secondCopyDestination=backup.path
            await review.scan();try check(review.plan?.ready == true,"initial_copy_review_ready")
            review.openNaming();let naming=review.namingEditor!;await naming.load()
            naming.chooseBuiltin(naming.builtins[2]);naming.customText="Trip"
            try check(await naming.save(),"naming_saved_before_preset")
            naming.invalidate();review.namingEditor=nil
            review.openProcessing();let processing=review.processingEditor!;await processing.load()
            processing.keywordsText="Travel, Coast";await processing.saveKeywords()
            try check(processing.error == nil,"processing_saved_before_preset")
            processing.invalidate();review.processingEditor=nil
            review.openPresets();let editor=review.presetEditor!;await editor.browse()
            try check(editor.total == 0 && editor.ready,"empty_library_bounded")
            editor.name="Travel Import";await editor.save()
            try check(editor.total == 1 && editor.selected?["name"] as? String == "Travel Import","save_current_configuration")
            let saved=editor.selected!,key=saved["id"] as! String,oldRevision=saved["revision"] as! Int
            try check((saved["processing"] as? [String:Any])?["keyword_count"] as? Int == 2,"preset_summary_keeps_keywords")
            func snapshot<V:View>(_ name:String,_ view:V,_ size:NSSize) throws {
                let host=NSHostingView(rootView:view.background(Color(nsColor:.windowBackgroundColor)))
                host.frame=NSRect(origin:.zero,size:size);host.layoutSubtreeIfNeeded()
                guard let bitmap=host.bitmapImageRepForCachingDisplay(in:host.bounds) else {throw EngineFailure(message:"No offscreen bitmap")}
                host.cacheDisplay(in:host.bounds,to:bitmap)
                try bitmap.representation(using:.png,properties:[:])!.write(to:root.appendingPathComponent(name))
            }
            try snapshot("import-preset-library.png",ImportPresetSheet(model:editor).content,NSSize(width:800,height:510))
            _=try await Backend.call("import_preset_action",["action":"rename","name":"Outside Change","preset_id":key,"expected_revision":oldRevision])
            await editor.browse(offset:0)
            editor.name="Stale Draft";await editor.action("rename")
            try check(editor.error?.contains("changed") == true && editor.name == "Stale Draft","pagination_does_not_rebase_selected_draft")
            await editor.browse(reset:true);await editor.choose(editor.rows[0]);editor.name="Travel Import";await editor.action("rename")
            try check(editor.selected?["name"] as? String == "Travel Import","explicit_reload_and_rename")
            await editor.save(update:true)
            try check(editor.total == 1 && editor.error == nil,"update_keeps_preset_identity")
            editor.invalidate();review.presetEditor=nil
            await review.select(false,ids:[review.items[0].id])
            let previous=review.plan!
            review.openPresets();let use=review.presetEditor!;await use.browse();await use.choose(use.rows[0])
            try check(await use.use(),"explicit_use_and_rescan")
            try check(!use.busy,"preset_sheet_releases_before_long_scan")
            let deadline=Date().addingTimeInterval(15)
            while review.plan?.ready != true,Date()<deadline {
                try await Task.sleep(nanoseconds:20_000_000)
            }
            try check(review.plan?.ready == true,"parent_scan_finishes_after_preset_sheet_release")
            try check(review.plan?.id != previous.id && review.plan?.number("selected_count") == paths.count,"rescan_resets_checked_scope")
            try check(review.plan?.text("preset_name") == "Travel Import" && review.items[0].destination.hasSuffix("Trip-0001.png"),"rescan_restores_naming_and_provenance")
            try check(review.plan?.backup != nil && review.plan?.primaryCopied == 0,"fresh_backup_identity_without_writes")
            let copy=ImportReviewModel(sources:paths);copy.plan=review.plan;copy.items=review.items;copy.total=review.total
            try snapshot("import-preset-review.png",ImportReviewSheet(model:copy).content,NSSize(width:1060,height:840))
            use.invalidate();review.presetEditor=nil
            await review.cancel()
            let fresh=ImportReviewModel(sources:[paths[0]])
            fresh.openPresets();let picker=fresh.presetEditor!;await picker.browse();await picker.choose(picker.rows[0])
            try check(await picker.use(),"choose_preset_before_scan")
            try check(fresh.sources == [paths[0]] && fresh.mode == "copy" && fresh.makeSecondCopy,"preset_preserves_new_source_selection")
            fresh.subfolder="New Shoot";fresh.makeSecondCopy=false
            await fresh.scan()
            try check(fresh.plan?.ready == true && fresh.plan?.backup == nil,"explicit_option_overrides_preserved")
            try check(fresh.items[0].destination.contains("New Shoot/Trip-0001.png"),"destination_override_and_captured_naming_combined")
            await picker.action("delete")
            try check(picker.total == 0,"delete_configuration_only")
            picker.invalidate();fresh.presetEditor=nil
            await fresh.apply()
            try check(fresh.plan?.state == "applied" && fresh.plan?.number("imported") == 1,"deleted_preset_does_not_retarget_review")
            let photo=try await Backend.call("get_photo",["photo_id":1])
            try check(Set(photo["keywords"] as? [String] ?? []) == Set(["Travel","Coast"]),"captured_keywords_apply")
            try check(try paths.enumerated().allSatisfy {try Data(contentsOf:URL(fileURLWithPath:$0.element)) == originals[$0.offset]},"original_bytes_unchanged")
            review.invalidate();fresh.invalidate()
            print(String(decoding:try JSONSerialization.data(withJSONObject:["passed":checks.count,"checks":checks],options:[.prettyPrinted,.sortedKeys]),as:UTF8.self))
            exit(0)
        } catch {
            print(String(decoding:(try? JSONSerialization.data(withJSONObject:["error":error.localizedDescription,"checks":checks],options:[.prettyPrinted,.sortedKeys])) ?? Data(),as:UTF8.self));exit(1)
        }
    }
}
