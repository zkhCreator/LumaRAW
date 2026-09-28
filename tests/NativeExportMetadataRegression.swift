// Purpose: verify keyword export flags, metadata preview and native queue snapshots.
// Inputs: generated photos and the actual broker. Outputs: isolated assertions.
// No rendered desktop/VoiceOver acceptance or original metadata writes are implied.
import AppKit
import Foundation

@main struct NativeExportMetadataRegression {
    @MainActor static func main() async {
        _ = NSApplication.shared
        let s=Store()
        var checks: [String:Bool]=[:]
        func check(_ value: Bool,_ name: String) throws {
            checks[name]=value
            if !value { throw EngineFailure(message:name) }
        }
        do {
            let paths=ProcessInfo.processInfo.environment["LUMARAW_TEST_FIXTURES"]!.components(separatedBy:"|")
            await s.importPaths(paths)
            s.thumbnailRenderer.request([]);s.cancelMainPreview()
            _=try await Backend.call("queue_control",["action":"pause"])
            let created=await s.saveKeyword(name:"Private group",synonyms:["Internal"],parentID:nil,original:nil,
                revision:s.keywordRevision,includeExport:false,exportContaining:true,exportSynonyms:false)
            try check(created,"native_editor_saves_export_policies")
            let root=s.keywordPages[0]!.items.first!
            try check(!root.includeExport && root.exportContaining && !root.exportSynonyms,"keyword_policy_readback")
            let childSaved=await s.saveKeyword(name:"Coast",synonyms:["Shore"],parentID:root.id,original:nil,
                revision:s.keywordRevision,includeExport:true,exportContaining:true,exportSynonyms:true)
            try check(childSaved,"nested_exportable_keyword_created")
            s.selection=[1];s.selected=1;await s.load(1)
            s.expandedKeywords.insert(root.id);await s.loadKeywordPage(parent:root.id)
            await s.changeKeyword(s.keywordPages[root.id]!.items.first!,action:"add")
            let model=ExportMetadataModel(photoID:1)
            await model.load()
            try check(model.error == nil && model.items == ["Coast","Shore"],"preview_resolves_synonyms_and_omits_private_parent")
            model.kind="hierarchy";await model.load()
            try check(model.items == ["Coast"],"hierarchy_never_leaks_excluded_name")
            let before=model.items
            model.receive(["photo_id":2,"items":["Wrong photo"],"keyword_revision":9999,"metadata_revision":9999])
            try check(model.items == before,"preview_rejects_wrong_photo_reply")
            let restricted=ExportMetadataModel(photoID:1,metadata:"copyright",hierarchy:true)
            await restricted.load()
            try check(restricted.items.isEmpty && restricted.fields.keys.sorted() == ["copyright"],"copyright_preview_omits_other_catalog_fields")
            let hiddenHierarchy=ExportMetadataModel(photoID:1,hierarchy:false)
            hiddenHierarchy.kind="hierarchy";await hiddenHierarchy.load()
            try check(hiddenHierarchy.items.isEmpty,"hierarchy_export_option_is_independent")
            s.thumbnailRenderer.request([]);s.cancelMainPreview()
            let destination=URL(fileURLWithPath:Backend.catalog).appendingPathComponent("exports").path
            await s.export(destination,"jpeg",["metadata":"catalog","keyword_hierarchy":true])
            try check(s.jobs.count == 1 && s.error == nil,"native_export_submits_metadata_options")
            let job=s.jobs[0],jobID=job["id"] as! Int
            let frozen=job["export_metadata"] as! [String:Any]
            try check(frozen["keyword_count"] as? Int == 2 && frozen["hierarchy_count"] as? Int == 1,"queue_receipt_reports_frozen_keyword_counts")
            let child=s.keywordPages[root.id]!.items.first!
            let changed=await s.saveKeyword(name:"Coast",synonyms:["Shore"],parentID:root.id,original:child,
                revision:child.revision,includeExport:false,exportContaining:false,exportSynonyms:false)
            try check(changed,"export_policy_can_change_after_submission")
            await model.load()
            try check(model.items.isEmpty,"preview_refresh_uses_new_policy")
            model.receive(["photo_id":1,"keyword_revision":0,"metadata_revision":0,"items":["Stale"]])
            try check(model.items.isEmpty,"preview_rejects_older_metadata_revisions")
            let receipt=try await Backend.call("get_job",["job_id":jobID])
            let current=receipt["export_metadata"] as! [String:Any]
            try check(current["sha256"] as? String == frozen["sha256"] as? String && current["keyword_count"] as? Int == 2,
                "queued_metadata_snapshot_does_not_follow_later_tag_edits")
            _=try await Backend.call("queue_control",["action":"resume"])
            let deadline=Date().addingTimeInterval(30)
            var finished: [String:Any]=[:]
            while Date()<deadline {
                finished=try await Backend.call("get_job",["job_id":jobID])
                if ["done","failed","interrupted","cancelled"].contains(finished["state"] as? String ?? "") { break }
                try await Task.sleep(nanoseconds:100_000_000)
            }
            try check(finished["state"] as? String == "done","native_metadata_export_finishes")
            let bytes=try Data(contentsOf:URL(fileURLWithPath:finished["output"] as! String))
            try check(bytes.range(of:Data("Shore".utf8)) != nil && bytes.range(of:Data("Private group".utf8)) == nil,
                "jpeg_contains_frozen_synonym_without_excluded_parent")
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

