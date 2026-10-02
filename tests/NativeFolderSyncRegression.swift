// Purpose: verify native folder-sync preview, suspected-duplicate review,
// selection, metadata and removal. Inputs: isolated generated images/sidecars
// and real broker IPC. Outputs: state assertions and offscreen layout evidence.
// Screenshots are not rendered desktop, file-picker, keyboard or VoiceOver acceptance.
import AppKit
import Foundation
import SwiftUI

@main struct NativeFolderSyncRegression {
    @MainActor static func main() async {
        _ = NSApplication.shared
        let s=Store()
        var checks: [String:Bool]=[:]
        var screenshots: [String]=[]
        func check(_ value: Bool,_ name: String) throws {
            checks[name]=value
            if !value { throw EngineFailure(message:name) }
        }
        func revision() async throws -> Int { (try await Backend.call("library_state"))["folder_revision"] as! Int }
        func settleLibraryImages() async throws {
            // Applying a plan refreshes the library and can start a preview.
            // Wait for that real work before testing another apply; a busy-image
            // refusal is an independent product safeguard, not a retry signal.
            for _ in 0..<500 {
                try await Task.sleep(nanoseconds:20_000_000)
                if !s.loading && !s.browsing && !s.rendering && s.thumbnailRenderer.loading.isEmpty { return }
            }
            throw EngineFailure(message:"Library previews did not settle before folder synchronization")
        }
        func catalogContains(_ path: String) async throws -> Bool {
            let result=try await Backend.call("list_photos",["offset":0,"mode":"all"])
            let rows=result["photos"] as? [[String:Any]] ?? []
            return rows.contains(where:{($0["path"] as? String)==path})
        }
        func snapshot<V: View>(_ name: String,_ view: V,_ size: NSSize,_ root: URL) async throws {
            let host=NSHostingView(rootView:view.background(Color(nsColor:.windowBackgroundColor)))
            host.frame=NSRect(origin:.zero,size:size);host.layoutSubtreeIfNeeded()
            try await Task.sleep(nanoseconds:150_000_000);host.layoutSubtreeIfNeeded()
            guard host.bounds.width>0,host.bounds.height>0,
                  let bitmap=host.bitmapImageRepForCachingDisplay(in:host.bounds) else {
                throw EngineFailure(message:"Could not create offscreen folder-sync snapshot \(name)")
            }
            host.cacheDisplay(in:host.bounds,to:bitmap)
            guard let png=bitmap.representation(using:.png,properties:[:]) else {
                throw EngineFailure(message:"Could not encode offscreen folder-sync snapshot \(name)")
            }
            try png.write(to:root.appendingPathComponent(name));screenshots.append(name)
        }
        do {
            let clockItem=FolderSyncItem(["id":1,"path":"clock.jpg","state":"updated",
                "clock":["taken":0,"taken_us":Int64(123456),"taken_submicro":"789","capture_clock":"camera"]])!
            try check(clockItem.value("taken")=="1970-01-01 00:00:00.123456789 (camera clock)","metadata_preview_preserves_camera_clock_and_fraction")
            let legacyModel=FolderSyncModel(folder:nil)
            legacyModel.includeDuplicates=true
            legacyModel.receive(["plan":["id":700,"revision":1,"state":"ready","duplicate_detection":0,
                "counts":["duplicate":1],"selected_counts":["duplicate":1]],
                "items":[["id":701,"path":"legacy.jpg","state":"duplicate","selected":1]]])
            let legacyItem=legacyModel.items.first!
            try check(!legacyModel.includeDuplicates && !legacyModel.plan!.supportsDuplicateReview
                      && !legacyItem.selectable(in:legacyModel.plan),"legacy_plan_does_not_expose_duplicate_import")
            let paths=ProcessInfo.processInfo.environment["LUMARAW_TEST_FIXTURES"]!.components(separatedBy:"|")
            guard let duplicatePath=ProcessInfo.processInfo.environment["LUMARAW_TEST_DUPLICATE_INCOMING"] else {
                throw EngineFailure(message:"Missing same-name, same-byte capture-time duplicate fixture")
            }
            await s.setImportNavigation(false)
            await s.importPaths(paths)
            s.thumbnailRenderer.request([]);s.cancelMainPreview()
            let root=LibraryFolder(try await Backend.call("get_folder",["photo_id":1]))!
            _=try await Backend.call("create_virtual_copies",["targets":[["photo_id":2,"expected_revision":0,"expected_metadata_revision":0]]])
            try FileManager.default.removeItem(atPath:paths[1])
            let new=URL(fileURLWithPath:root.path).appendingPathComponent("new.png")
            let excluded=URL(fileURLWithPath:root.path).appendingPathComponent("excluded.png")
            try FileManager.default.copyItem(atPath:paths[0],toPath:new.path)
            try FileManager.default.copyItem(atPath:paths[0],toPath:excluded.path)
            let caption=String(repeating:"🌊",count:5000)
            let keywords=(0..<45).map { "<rdf:li>Keyword \($0)</rdf:li>" }.joined()
            let xmp="""
            <x:xmpmeta xmlns:x="adobe:ns:meta/"><rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
            <rdf:Description xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:xmp="http://ns.adobe.com/xap/1.0/" xmp:Rating="4">
            <dc:title>External title</dc:title><dc:description>\(caption)</dc:description>
            <dc:subject><rdf:Bag>\(keywords)</rdf:Bag></dc:subject></rdf:Description></rdf:RDF></x:xmpmeta>
            """
            try xmp.write(to:URL(fileURLWithPath:paths[0]).deletingPathExtension().appendingPathExtension("xmp"),atomically:true,encoding:.utf8)
            let model=FolderSyncModel(folder:root)
            await model.reload();await model.prepare(revision:try await revision())
            try check(model.canScan && !model.canApply,"prepared_plan_requires_scan")
            await model.scan()
            try check(model.canApply && model.plan?.count("new")==2 && model.plan?.count("missing")==1,"scan_reports_new_and_missing_originals")
            try check(model.plan?.count("updated")==1 && model.plan?.number("file_count")==6,"scan_covers_root_and_descendants")
            try check(model.plan?.supportsDuplicateReview==true && model.plan?.count("duplicate")==1
                      && model.plan?.count("duplicate",selected:true)==1,"scan_reviews_capture_time_duplicate_without_reclassifying_legacy_plans")
            try check(!model.includeDuplicates,"duplicate_import_toggle_defaults_off")
            model.kind="duplicate";await model.reload()
            guard let duplicateItem=model.items.first(where:{$0.path==duplicatePath}) else {
                throw EngineFailure(message:"The matched duplicate was not on its review page")
            }
            try check(duplicateItem.state=="duplicate" && duplicateItem.selectable(in:model.plan)
                      && duplicateItem.selected && duplicateItem.duplicateOfPath==paths[4],"duplicate_row_exposes_review_selection_and_match_path")
            await model.select(false,kind:"duplicate",item:duplicateItem)
            try check(model.plan?.count("duplicate",selected:true)==0,"duplicate_can_be_unchecked_in_its_filter")
            if let duplicateItem=model.items.first(where:{$0.path==duplicatePath}) {
                await model.select(true,kind:"duplicate",item:duplicateItem)
            }
            model.includeDuplicates=false
            try check(model.plan?.count("duplicate",selected:true)==1,"turning_off_duplicate_import_keeps_manual_check")
            let screenshotRoot=URL(fileURLWithPath:ProcessInfo.processInfo.environment["LUMARAW_CATALOG"]!).deletingLastPathComponent()
            try FileManager.default.createDirectory(at:screenshotRoot,withIntermediateDirectories:true)
            try await snapshot("folder-sync-suspected-duplicates.png",
                               FolderSyncSheet(folder:root,model:model).environmentObject(s),
                               NSSize(width:740,height:840),screenshotRoot)
            let unchanged=try await Backend.call("get_photo",["photo_id":1])
            try check(unchanged["title"] as? String == "","preview_does_not_write_metadata")
            model.kind="new";await model.reload()
            let exclude=model.items.first(where:{$0.path==excluded.path})!
            await model.select(false,kind:"new",item:exclude)
            try check(model.plan?.count("new",selected:true)==1 && model.items.count==2,"explicit_import_selection_is_persisted")
            model.kind="updated";await model.reload()
            let scanned=model.items.first!
            try check(scanned.metadataDeferred && scanned.patch.isEmpty,"long_metadata_is_deferred_in_summary")
            let detail=FolderSyncMetadataModel(planID:model.plan!.id,itemID:scanned.id,revision:model.plan!.revision)
            await detail.load()
            try check(detail.item?.value("title")=="External title" && detail.item?.value("caption")==caption,"complete_metadata_values_are_read_on_demand")
            try check(detail.total==45 && (detail.item?.patch["keyword_paths"] as? [[String]])?.count==20,"metadata_keywords_are_paged")
            await detail.load(offset:40)
            try check(detail.offset==40 && (detail.item?.patch["keyword_paths"] as? [[String]])?.count==5,"last_metadata_page_is_complete")
            detail.receive(["plan_id":detail.planID,"revision":detail.revision,"item":["id":99999,"path":"wrong","state":"updated"]])
            try check(detail.item?.id==scanned.id,"wrong_metadata_item_is_rejected")
            detail.receive(["plan_id":detail.planID+1,"revision":detail.revision,"item":["id":scanned.id,"path":"wrong","state":"updated"]])
            detail.receive(["plan_id":detail.planID,"revision":detail.revision+1,"item":["id":scanned.id,"path":"wrong","state":"updated"]])
            try check(detail.item?.path==scanned.path,"different_plan_and_revision_are_rejected")
            await model.select(true,kind:"updated",item:scanned)
            await detail.load()
            try check(detail.error?.contains("changed")==true,"changed_plan_requires_fresh_review")
            s.folderID=root.id;s.activeFolder=root;s.selected=nil;s.photo=nil
            await model.apply(using:s)
            try check(model.plan?.state=="applied" && model.error==nil,"native_apply_completes")
            try check(model.plan?.number("imported")==1 && model.plan?.number("removed")==0,"default_apply_imports_without_removal")
            let updated=try await Backend.call("get_photo",["photo_id":1])
            try check(updated["title"] as? String == "External title" && updated["rating"] as? Int == 4,"external_metadata_adopted")
            try check(updated["caption"] as? String == caption && (updated["keywords"] as? [String])?.count==45,"full_scanned_metadata_survives_application")
            try check(s.folderID==root.id && s.activeFolder?.totalCount==5,"active_folder_count_refreshed")
            let missing=try await Backend.call("get_photo",["photo_id":2])
            try check(missing["missing"] as? Int == 1,"unremoved_original_marked_missing")
            let duplicateAfterDefault=try await catalogContains(duplicatePath)
            try check(!duplicateAfterDefault,"default_apply_skips_checked_suspected_duplicate")

            try await settleLibraryImages()
            let gated=FolderSyncModel(folder:root)
            await gated.reload();await gated.prepare(revision:try await revision());await gated.scan()
            gated.includeDuplicates=true;gated.importNew=false
            try check(gated.plan?.count("duplicate",selected:true)==1,"duplicate_check_survives_new_photo_gate")
            await gated.apply(using:s)
            try check(gated.plan?.state=="applied" && gated.plan?.number("imported")==0,
                      "import_new_off_suppresses_new_and_suspected_duplicates")
            try check(gated.includeDuplicates && gated.plan?.count("duplicate",selected:true)==1,
                      "apply_does_not_clear_duplicate_selection_or_switch")

            try await settleLibraryImages()
            let stale=FolderSyncModel(folder:root)
            await stale.reload();await stale.prepare(revision:try await revision());await stale.scan()
            stale.includeDuplicates=true
            let stalePlan=stale.plan!
            _=try await Backend.call("select_folder_sync_items",["plan_id":stalePlan.id,
                "expected_revision":stalePlan.revision,"selected":false,"kind":"duplicate"])
            await stale.apply(using:s)
            try check(stale.plan?.state=="ready" && stale.error != nil && stale.includeDuplicates,
                      "stale_duplicate_apply_preserves_switch_and_requires_review")
            try check(stale.plan?.count("duplicate",selected:true)==0,
                      "stale_apply_reads_back_external_selection_without_replaying")
            let duplicateAfterStale=try await catalogContains(duplicatePath)
            try check(!duplicateAfterStale,"stale_duplicate_apply_does_not_import_candidate")
            await stale.cancel(using:s)
            try check(stale.plan?.state=="cancelled","stale_plan_is_explicitly_cancelled_before_fresh_review")

            try await settleLibraryImages()
            let include=FolderSyncModel(folder:root)
            await include.reload();await include.prepare(revision:try await revision());await include.scan()
            await include.select(false,kind:"new")
            include.kind="duplicate";await include.reload();include.includeDuplicates=true
            try check(include.plan?.count("duplicate",selected:true)==1 && include.plan?.count("new",selected:true)==0,
                      "duplicate_apply_captures_independent_checked_items")
            await include.apply(using:s)
            try check(include.plan?.state=="applied" && include.plan?.number("imported")==1,
                      "explicit_duplicate_option_imports_only_checked_candidate")
            let duplicateAfterOptIn=try await catalogContains(duplicatePath)
            try check(duplicateAfterOptIn,"explicit_duplicate_import_keeps_original_path")

            try await settleLibraryImages()
            s.thumbnailRenderer.request([]);s.cancelMainPreview()
            let removal=FolderSyncModel(folder:root)
            await removal.reload();await removal.prepare(revision:try await revision());await removal.scan()
            removal.importNew=false;removal.removeMissing=true
            await removal.apply(using:s)
            try check(removal.plan?.state=="applied" && removal.plan?.number("removed")==2,"explicit_removal_includes_missing_family_variants")
            try check(FileManager.default.fileExists(atPath:excluded.path),"unselected_original_remains_on_disk")
            s.thumbnailRenderer.request([]);s.cancelMainPreview()
            let staged=FolderSyncModel(folder:root)
            await staged.reload();await staged.prepare(revision:try await revision())
            let restored=FolderSyncModel(folder:nil);await restored.reload()
            try check(restored.canScan && restored.plan?.id==staged.plan?.id,"fresh_model_restores_saved_plan")
            await restored.cancel(using:s)
            try check(restored.plan?.state=="cancelled" && !restored.canApply,"cancel_discards_unapplied_plan")
            restored.receive(["plan":["id":restored.plan!.id,"revision":0,"state":"ready"]])
            try check(restored.plan?.state=="cancelled","late_reply_cannot_regress_terminal_state")
            print(String(data:try JSONSerialization.data(withJSONObject:["ok":true,"checks":checks,
                "offscreen_snapshots":screenshots,"desktop_ui":"NOT_VERIFIED"],options:[.prettyPrinted,.sortedKeys]),encoding:.utf8)!)
            exit(0)
        } catch {
            print(String(data:try! JSONSerialization.data(withJSONObject:["ok":false,"checks":checks,
                "offscreen_snapshots":screenshots,"error":error.localizedDescription,
                "store_error":s.error ?? ""],options:.prettyPrinted),encoding:.utf8)!)
            exit(1)
        }
    }
}
