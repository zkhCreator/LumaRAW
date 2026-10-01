// Purpose: native durable Add/Copy state and real preview/service integration.
// Inputs: five generated photos and an isolated catalog. Outputs: checked scope,
// no-write preview, stale-plan rejection, resume, cancellation and original safety.
// This does not verify rendered sheets, desktop gestures or VoiceOver.
import AppKit
import Foundation
import SwiftUI

@main struct NativeImportRegression {
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
            let model=ImportReviewModel(sources:paths)
            var applied: [Int]=[];model.onApplied={applied.append($0)}
            await model.load(initial:true)
            try check(model.plan == nil && model.canScan && !model.canApply,"new_review_requires_scan_before_import")
            await model.scan()
            try check(model.plan?.ready == true && model.items.count == 5 && model.plan?.number("selected_count") == 5,"scan_populates_checked_bounded_review")
            let status=try await Backend.call("status")
            try check(status["photos"] as? Int == 0,"scanning_does_not_import_photos")
            let captured=model.plan!,first=model.items[0]
            let preview=try await Backend.call("preview_import_item",["plan_id":captured.id,"item_id":first.id,
                "expected_revision":captured.revision,"client_id":"native-import-check","generation":1])
            try check(preview["source"] as? String == first.path && (preview["thumbnail"] as? String).flatMap{NSImage(contentsOfFile:$0)} != nil,"preview_decodes_scanned_source_without_catalog_photo")
            let detail=try await Backend.call("preview_import_item",["plan_id":captured.id,"item_id":first.id,
                "expected_revision":captured.revision,"client_id":"native-import-check","generation":2,"detail":true])
            try check((detail["preview"] as? String).flatMap{NSImage(contentsOfFile:$0)} != nil,"loupe_receives_file_backed_preview")
            await model.select(false,ids:[first.id])
            try check(model.plan?.number("selected_count") == 4 && model.items.first?.selected == false,"single_check_changes_selection_only")
            await model.browse(kind:"selected")
            try check(model.total == 4 && !model.items.contains(where:{$0.id == first.id}),"checked_filter_excludes_unchecked_photo")
            let checkedRevision=model.plan!.revision
            await model.select(true)
            try check(model.plan?.revision == checkedRevision && model.plan?.number("selected_count") == 4,"check_all_in_checked_filter_cannot_check_hidden_items")
            await model.select(false)
            try check(model.plan?.number("selected_count") == 0 && !model.canApply,"uncheck_all_disables_import")
            await model.browse(kind:"all");await model.select(true,ids:[first.id])
            try check(model.canApply && model.plan?.number("selected_count") == 1,"checking_one_enables_import")
            let stale=model.plan!
            _=try await Backend.call("set_import_options",["plan_id":stale.id,"expected_revision":stale.revision,"skip_duplicates":false])
            await model.select(true)
            try check(model.error?.contains("changed") == true && model.plan?.revision == stale.revision,"stale_checkbox_does_not_overwrite_newer_review")
            model.error=nil;await model.load()
            try check(model.plan?.skipDuplicates == false && model.plan?.number("selected_count") == 1,"explicit_refresh_retains_checked_selection")
            await model.apply()
            try check(model.plan?.state == "applied" && applied == [1],"import_applies_once_and_delivers_receipt")
            await model.load()
            try check(applied == [1],"repeated_receipt_does_not_repeat_application_callback")
            let after=try await Backend.call("status")
            try check(after["photos"] as? Int == 1,"only_checked_photo_enters_catalog")
            await model.cancel()
            try check(model.plan?.state == "applied","cancel_cannot_undo_completed_import")
            model.invalidate()
            let second=ImportReviewModel(sources:paths)
            await second.load(initial:true);await second.scan()
            try check(second.plan?.count("existing") == 1 && second.plan?.number("selected_count") == 4,"existing_original_is_visible_but_not_eligible")
            await second.browse(kind:"existing")
            let existingRevision=second.plan!.revision
            await second.select(false)
            try check(second.plan?.revision == existingRevision && second.plan?.number("selected_count") == 4,"existing_filter_cannot_uncheck_new_photos")
            let oldRevision=second.plan!.revision
            second.invalidate()
            let resumed=ImportReviewModel()
            await resumed.load(initial:true)
            try check(resumed.plan?.revision == oldRevision && resumed.canApply,"closing_and_reopening_preserves_review")
            await resumed.cancel()
            try check(resumed.plan?.state == "cancelled" && resumed.items.isEmpty,"cancel_discards_pending_review_only")
            resumed.invalidate()
            let store=Store()
            await store.reviewImport([paths[0]])
            await store.reviewImport([paths[1],paths[0]])
            try check(store.importReview?.sources == Array(paths.prefix(2)),"successive_file_open_events_coalesce_without_duplicate_sources")
            store.importReview?.invalidate()
            let destination=URL(fileURLWithPath:ProcessInfo.processInfo.environment["LUMARAW_CATALOG"]!).deletingLastPathComponent().appendingPathComponent("copy-output")
            try FileManager.default.createDirectory(at:destination,withIntermediateDirectories:false)
            let copy=ImportReviewModel(sources:[paths[1]])
            copy.mode="copy";copy.destination=destination.path;copy.subfolder="Album"
            func snapshot(_ name:String) throws {
                let rendered=ImportReviewModel(sources:copy.sources)
                rendered.mode=copy.mode;rendered.destination=copy.destination;rendered.subfolder=copy.subfolder
                rendered.plan=copy.plan;rendered.items=copy.items;rendered.total=copy.total
                let host=NSHostingView(rootView:ImportReviewSheet(model:rendered).content.background(Color(nsColor:.windowBackgroundColor)))
                host.frame=NSRect(x:0,y:0,width:1060,height:760);host.layoutSubtreeIfNeeded()
                guard let bitmap=host.bitmapImageRepForCachingDisplay(in:host.bounds) else {throw EngineFailure(message:"Offscreen import layout unavailable")}
                host.cacheDisplay(in:host.bounds,to:bitmap)
                guard let png=bitmap.representation(using:.png,properties:[:]) else {throw EngineFailure(message:"Offscreen import PNG unavailable")}
                try png.write(to:destination.deletingLastPathComponent().appendingPathComponent(name))
            }
            try snapshot("import-copy-options.png")
            await copy.scan()
            try check(copy.plan?.isCopy == true && copy.canApply,"copy_options_create_ready_destination_review")
            let target=destination.appendingPathComponent("Album").appendingPathComponent(URL(fileURLWithPath:paths[1]).lastPathComponent)
            try check(copy.items.first?.destination == target.path && !FileManager.default.fileExists(atPath:target.path),"copy_review_shows_destination_without_writes")
            try FileManager.default.createDirectory(at:target.deletingLastPathComponent(),withIntermediateDirectories:true)
            try Data("existing destination".utf8).write(to:target)
            await copy.apply()
            try check(copy.plan?.interruptedCopy == true && !copy.canScan && copy.canResumeCopy,"collision_offers_explicit_copy_recovery_not_scan")
            try snapshot("import-copy-interrupted.png")
            try check(try Data(contentsOf:target) == Data("existing destination".utf8),"copy_collision_preserves_existing_file")
            try FileManager.default.removeItem(at:target)
            await copy.resumeCopy()
            try check(copy.plan?.state == "applied" && !copy.canResumeCopy,"explicit_copy_resume_applies_catalog")
            try check(try Data(contentsOf:target) == originals[1],"copied_destination_matches_source_bytes")
            let receipts=try await Backend.call("get_import_copies",["plan_id":copy.plan!.id])
            let rows=receipts["items"] as? [[String:Any]] ?? []
            try check(rows.count == 1 && rows[0]["state"] as? String == "published","completed_copy_keeps_readable_transfer_receipt")
            copy.invalidate()
            try check(try paths.map { try Data(contentsOf:URL(fileURLWithPath:$0)) } == originals,"all_original_bytes_preserved")
            print(String(data:try JSONSerialization.data(withJSONObject:["ok":true,"checks":checks,"desktop_ui":"NOT_VERIFIED"],options:[.prettyPrinted,.sortedKeys]),encoding:.utf8)!)
            exit(0)
        } catch {
            print(String(data:try! JSONSerialization.data(withJSONObject:["ok":false,"checks":checks,"error":error.localizedDescription],options:.prettyPrinted),encoding:.utf8)!)
            exit(1)
        }
    }
}
