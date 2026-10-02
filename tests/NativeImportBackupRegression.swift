// Purpose: explicit second-copy choices and progress through real native IPC.
// Inputs: disposable photographs, main/backup folders and an isolated catalog.
// Outputs: conflict/recovery assertions and offscreen layout. No desktop input,
// removable-media, physical-drive redundancy or VoiceOver acceptance is claimed.
import AppKit
import Foundation
import SwiftUI

@main struct NativeImportBackupRegression {
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
            let main=root.appendingPathComponent("main-output"),backup=root.appendingPathComponent("backup-output")
            for url in [main,backup] { try FileManager.default.createDirectory(at:url,withIntermediateDirectories:true) }
            let review=ImportReviewModel(sources:paths);review.mode="copy";review.destination=main.path
            review.makeSecondCopy=true
            await review.scan()
            try check(review.plan == nil && review.error?.contains("second-copy destination") == true,"enabled_backup_requires_explicit_destination")
            review.secondCopyDestination=backup.path
            func snapshot(_ name:String) throws {
                let view=ImportReviewModel(sources:review.sources)
                view.mode=review.mode;view.destination=review.destination;view.makeSecondCopy=review.makeSecondCopy
                view.secondCopyDestination=review.secondCopyDestination;view.plan=review.plan;view.items=review.items;view.total=review.total
                let host=NSHostingView(rootView:ImportReviewSheet(model:view).content.background(Color(nsColor:.windowBackgroundColor)))
                host.frame=NSRect(x:0,y:0,width:1060,height:800);host.layoutSubtreeIfNeeded()
                guard let bitmap=host.bitmapImageRepForCachingDisplay(in:host.bounds) else {throw EngineFailure(message:"No offscreen bitmap")}
                host.cacheDisplay(in:host.bounds,to:bitmap)
                try bitmap.representation(using:.png,properties:[:])!.write(to:root.appendingPathComponent(name))
            }
            try snapshot("import-backup-options.png")
            await review.scan()
            try check(review.plan?.backup?["destination"] as? String == backup.path && review.canApply,"prepare_captures_backup_without_writes")
            try check(try FileManager.default.contentsOfDirectory(atPath:backup.path).isEmpty,"scan_does_not_create_backup_files")
            await review.setBackup(nil)
            try check(review.plan?.backup == nil && review.items.allSatisfy{$0.secondDestination.isEmpty},"ready_review_can_disable_backup")
            let captured=review.plan!
            _=try await Backend.call("set_import_options",["plan_id":captured.id,"expected_revision":captured.revision,"skip_duplicates":false])
            await review.setBackup(backup.path)
            try check(review.error?.contains("changed") == true && review.plan?.revision == captured.revision,"stale_backup_change_rejected_without_rebase")
            await review.load();await review.setBackup(backup.path)
            try check(review.plan?.backup != nil,"explicit_refresh_allows_new_backup_choice")
            await review.select(false,ids:[review.items[0].id])
            try check(review.items[0].secondDestination.isEmpty && !review.items[1].secondDestination.isEmpty,"backup_previews_follow_checked_subset")
            review.openNaming();let naming=review.namingEditor!;await naming.load()
            naming.chooseBuiltin(naming.builtins[2]);naming.customText="Selected"
            try check(await naming.save(),"primary_rename_captured_with_backup_enabled")
            naming.invalidate();review.namingEditor=nil
            let first=review.items[1],backupFile=URL(fileURLWithPath:first.secondDestination)
            try check(first.destination.hasSuffix("Selected-0001.png") && backupFile.lastPathComponent == first.name,"backup_keeps_source_name_when_primary_is_renamed")
            try snapshot("import-backup-ready.png")
            try FileManager.default.createDirectory(at:backupFile.deletingLastPathComponent(),withIntermediateDirectories:true)
            try Data("existing backup".utf8).write(to:backupFile)
            await review.apply()
            try check(review.plan?.interruptedCopy == true && review.canResumeCopy,"backup_collision_requires_explicit_resume")
            try check(try FileManager.default.contentsOfDirectory(atPath:main.path).isEmpty,"backup_collision_prevents_all_main_writes")
            try check(try Data(contentsOf:backupFile) == Data("existing backup".utf8),"existing_backup_is_preserved")
            try snapshot("import-backup-interrupted.png")
            try FileManager.default.removeItem(at:backupFile)
            await review.resumeCopy()
            try check(review.plan?.state == "applied" && review.plan?.number("imported") == 4,"resume_catalogs_only_checked_main_photos")
            try check(review.plan?.copy["copied"] as? Int == 8 && review.plan?.backup?["copied"] as? Int == 4,"progress_counts_both_roles_once")
            try check(review.plan?.primaryCopied == 4 && review.plan?.primaryTransferCount == 4,"main_progress_excludes_second_copy_transfers")
            let receipts=try await Backend.call("get_import_copies",["plan_id":review.plan!.id])
            let rows=receipts["items"] as! [[String:Any]]
            try check(rows.count == 8 && rows.filter{$0["role"] as? String == "second"}.count == 4,"receipts_distinguish_main_and_second_copies")
            let photos=try await Backend.call("list_photos",["stacked":false])
            try check(photos["total"] as? Int == 4 && (photos["photos"] as! [[String:Any]]).allSatisfy{($0["path"] as! String).hasPrefix(main.path+"/")},"backup_files_never_become_catalog_photos")
            for row in rows {
                let source=paths.firstIndex(of:row["source"] as! String)!
                try check(try Data(contentsOf:URL(fileURLWithPath:row["target"] as! String)) == originals[source],"exact_\(row["role"]!)_bytes_\(source)")
            }
            try check(try paths.map { try Data(contentsOf:URL(fileURLWithPath:$0)) } == originals,"original_bytes_unchanged")
            review.invalidate()
            print(String(data:try JSONSerialization.data(withJSONObject:["ok":true,"checks":checks,"desktop_ui":"NOT_VERIFIED"],options:[.prettyPrinted,.sortedKeys]),encoding:.utf8)!)
            exit(0)
        } catch {
            print(String(data:try! JSONSerialization.data(withJSONObject:["ok":false,"checks":checks,"error":error.localizedDescription],options:.prettyPrinted),encoding:.utf8)!)
            exit(1)
        }
    }
}
