// Purpose: verify catalog-local Export with Previous and manual-session capture.
// Inputs: two disposable photos, an isolated catalog and packaged Backend IPC.
// Outputs: revision, selection, frozen-job, preset-baseline and offscreen layout evidence.
// Offscreen snapshots are layout evidence only; desktop interaction is NOT_VERIFIED.
import AppKit
import Combine
import Foundation
import SwiftUI

@main struct NativePreviousExportRegression {
    @MainActor static func main() async {
        _ = NSApplication.shared
        let store=Store()
        var checks:[String:Bool]=[:]
        var screenshots:[String]=[]
        var createdJobIDs:Set<Int>=[]
        var testDestinations:[String]=[]

        func check(_ value:Bool,_ name:String) throws {
            checks[name]=value
            if !value { throw EngineFailure(message:name) }
        }

        func optionsMatch(_ actual:[String:Any],_ expected:[String:Any])->Bool {
            guard Set(actual.keys)==Set(expected.keys) else{return false}
            for key in expected.keys {
                if key=="output_sharpen" {
                    guard let a=actual[key] as? NSNumber,let b=expected[key] as? NSNumber,
                          abs(a.doubleValue-b.doubleValue)<0.000001 else{return false}
                } else if key=="keyword_hierarchy" {
                    guard (actual[key] as? NSNumber)?.boolValue==(expected[key] as? NSNumber)?.boolValue else{return false}
                } else if String(describing:actual[key]!) != String(describing:expected[key]!) {return false}
            }
            return true
        }

        func jobIDs(_ rows:[[String:Any]])->[Int] {
            rows.compactMap{$0["id"] as? Int}
        }

        func rememberCurrentJobs() async throws -> [[String:Any]] {
            let response=try await Backend.call("list_jobs")
            let rows=response["jobs"] as? [[String:Any]] ?? []
            createdJobIDs.formUnion(jobIDs(rows))
            return rows
        }

        func snapshot<V:View>(_ name:String,_ view:V,_ size:NSSize,_ root:URL) async throws {
            let host=NSHostingView(rootView:view.background(Color(nsColor:.windowBackgroundColor)))
            host.frame=NSRect(origin:.zero,size:size)
            host.layoutSubtreeIfNeeded()
            try await Task.sleep(nanoseconds:100_000_000)
            host.layoutSubtreeIfNeeded()
            guard host.bounds.width>0,host.bounds.height>0,
                  let bitmap=host.bitmapImageRepForCachingDisplay(in:host.bounds) else {
                throw EngineFailure(message:"No offscreen bitmap for \(name)")
            }
            host.cacheDisplay(in:host.bounds,to:bitmap)
            guard let png=bitmap.representation(using:.png,properties:[:]) else {
                throw EngineFailure(message:"Could not encode offscreen snapshot \(name)")
            }
            try png.write(to:root.appendingPathComponent(name))
            screenshots.append(name)
        }

        func cleanup() async {
            let response=try? await Backend.call("list_jobs")
            let ids=Set(createdJobIDs).union(jobIDs(response?["jobs"] as? [[String:Any]] ?? []))
            for id in ids {
                _=try? await Backend.call("queue_control",["action":"cancel","job_id":id])
            }
            for path in testDestinations where FileManager.default.fileExists(atPath:path) {
                try? FileManager.default.removeItem(atPath:path)
            }
        }

        do {
            let paths=ProcessInfo.processInfo.environment["LUMARAW_TEST_FIXTURES"]!.components(separatedBy:"|")
            try check(paths.count==2,"runner_supplies_two_disposable_photos")
            let originalBytes=try paths.map{try Data(contentsOf:URL(fileURLWithPath:$0))}
            let root=URL(fileURLWithPath:ProcessInfo.processInfo.environment["LUMARAW_CATALOG"]!).deletingLastPathComponent()
            let prefix="Previous Export \(UUID().uuidString.prefix(8))"
            let externalDestination=root.appendingPathComponent("External Previous Export Destination \(UUID().uuidString.prefix(8))").path
            let destination=root.appendingPathComponent("Previous Export Destination \(UUID().uuidString.prefix(8))").path
            let changedDestination=root.appendingPathComponent("Previous Export Changed Destination \(UUID().uuidString.prefix(8))").path
            let finalDestination=root.appendingPathComponent("Previous Export Final Destination \(UUID().uuidString.prefix(8))").path
            testDestinations=[externalDestination,destination,changedDestination,finalDestination]

            await store.importPaths(paths)
            store.thumbnailRenderer.request([])
            store.cancelMainPreview()
            store.selection=[1,2]
            store.selected=1
            await store.load(1)
            _=try await Backend.call("queue_control",["action":"pause"])
            await store.refreshJobs()

            let initialPrevious=try await Backend.call("get_previous_export")
            let initialJobs=try await Backend.call("list_jobs")
            try check(initialPrevious["available"] as? Bool==false
                && (initialPrevious["revision"] as? Int)==0
                && ((initialPrevious["settings"] as? NSNull) != nil)
                && store.previousExportAvailable==false,
                "fresh_catalog_and_compact_poll_have_no_previous_export")
            store.error=nil
            let originalSelection=store.selection
            await store.exportWithPrevious()
            let afterUnavailable=try await Backend.call("list_jobs")
            try check(store.error?.contains("No previous export") == true
                && jobIDs(afterUnavailable["jobs"] as? [[String:Any]] ?? [])==jobIDs(initialJobs["jobs"] as? [[String:Any]] ?? [])
                && store.selection==originalSelection,
                "unavailable_previous_action_adds_no_jobs_and_preserves_selection")

            // Simulate an accepted manual export from another client. The existing jobs poll
            // must discover the compact availability token without a separate timer or full read.
            let externalDraft=ExportDraft()
            _=try await Backend.call("enqueue_exports",[
                "photo_ids":[1],"destination":externalDestination,"format":externalDraft.format,
                "options":externalDraft.options,"request_key":UUID().uuidString,"remember_previous":true
            ])
            await store.refreshJobs()
            let externalJobs=try await rememberCurrentJobs()
            let externalToken=(try await Backend.call("list_jobs"))["previous_export"] as? [String:Any] ?? [:]
            try check(externalJobs.count==1 && store.previousExportAvailable
                && externalToken["available"] as? Bool==true
                && (externalToken["revision"] as? Int)==1,
                "existing_jobs_poll_discovers_external_previous_submission")

            var manual=ExportDraft()
            manual.format="jpeg";manual.space="prophoto";manual.maxEdge=2048;manual.quality=76
            manual.outputSharpen=28.5;manual.name="{stem}-manual-{seq}";manual.priority=6
            manual.metadata="catalog";manual.keywordHierarchy=true;manual.destination=destination
            let manualOptions=manual.options
            try check(manual.shouldRememberPrevious,"manual_draft_is_a_previous_candidate")
            store.set("exposure",1.25)
            await store.export(manual.destination,manual.format,manual.options,
                rememberPrevious:manual.shouldRememberPrevious)
            var jobs=try await rememberCurrentJobs()
            let externalJobIDs=Set(jobIDs(externalJobs))
            let manualIDs=jobIDs(jobs).filter{!externalJobIDs.contains($0)}
            let acceptedA=try await Backend.call("get_previous_export")
            let acceptedASettings=acceptedA["settings"] as? [String:Any] ?? [:]
            let acceptedAOptions=acceptedASettings["options"] as? [String:Any] ?? [:]
            try check(store.error==nil && jobs.count==3 && manualIDs.count==2
                && store.previousExportAvailable
                && (acceptedA["revision"] as? Int)==2
                && acceptedA["available"] as? Bool==true
                && acceptedASettings["format"] as? String==manual.format
                && acceptedASettings["destination"] as? String==destination
                && optionsMatch(acceptedAOptions,manualOptions),
                "accepted_manual_submission_remembers_all_effective_settings")
            var photoOneJob:[String:Any]?
            for id in manualIDs {
                let job=try await Backend.call("get_job",["job_id":id])
                if job["source"] as? String==paths[0] { photoOneJob=job }
            }
            let frozenFirst=photoOneJob ?? [:]
            let firstRecipe=frozenFirst["recipe"] as? [String:Any] ?? [:]
            try check((firstRecipe["exposure"] as? NSNumber)?.doubleValue==1.25,
                "manual_submission_flushes_and_freezes_current_recipe")

            let presetModel=ExportPresetLibraryModel()
            await presetModel.refresh(offset:0,search:prefix)
            let saveSource=presetModel.saveSource(from:manual,updating:false)!
            guard let savedPreset=await presetModel.save(saveSource,name:"\(prefix) Named",includeDestination:true) else {
                throw EngineFailure(message:presetModel.error ?? "Could not save Previous regression preset")
            }
            var editedDuringSave=manual
            editedDuringSave.destination=changedDestination
            editedDuringSave.acknowledgeSavedPreset(savedPreset,source:saveSource,includeDestination:true)
            manual.acknowledgeSavedPreset(savedPreset,source:saveSource,includeDestination:true)
            try check(!manual.shouldRememberPrevious && manual.presetBaseline != nil
                && editedDuringSave.shouldRememberPrevious,
                "successful_preset_save_uses_captured_values_as_baseline")
            guard let savedItem=presetModel.page?.items.first(where:{$0.id==savedPreset.id}),
                  let savedReceipt=await presetModel.load(savedItem) else {
                throw EngineFailure(message:presetModel.error ?? "Could not read saved Previous regression preset")
            }
            var loaded=ExportDraft()
            loaded.apply(savedReceipt)
            try check(!loaded.shouldRememberPrevious && loaded.destination==destination
                && optionsMatch(loaded.options,manualOptions),
                "unchanged_loaded_preset_matches_its_previous_baseline")

            loaded.quality=68
            let updateSource=presetModel.saveSource(from:loaded,updating:true)!
            guard let updatedPreset=await presetModel.save(updateSource,name:updateSource.name,includeDestination:true) else {
                throw EngineFailure(message:presetModel.error ?? "Could not update Previous regression preset")
            }
            loaded.acknowledgeSavedPreset(updatedPreset,source:updateSource,includeDestination:true)
            try check(!loaded.shouldRememberPrevious && loaded.quality==68,
                "successful_preset_update_captures_its_saved_effective_values")

            await store.export(loaded.destination,loaded.format,loaded.options,
                rememberPrevious:loaded.shouldRememberPrevious)
            jobs=try await rememberCurrentJobs()
            let acceptedAfterUnchanged=try await Backend.call("get_previous_export")
            try check(jobs.count==5 && (acceptedAfterUnchanged["revision"] as? Int)==2
                && optionsMatch(((acceptedAfterUnchanged["settings"] as? [String:Any])?["options"] as? [String:Any]) ?? [:],manualOptions),
                "unchanged_updated_preset_export_does_not_replace_previous")

            var folderlessSourceDraft=manual
            folderlessSourceDraft.loadedPreset=nil
            folderlessSourceDraft.presetBaseline=nil
            folderlessSourceDraft.destination=""
            let folderlessSource=presetModel.saveSource(from:folderlessSourceDraft,updating:false)!
            guard let folderlessPreset=await presetModel.save(folderlessSource,
                name:"\(prefix) Folderless",includeDestination:false),
                  let folderlessItem=presetModel.page?.items.first(where:{$0.id==folderlessPreset.id}),
                  let folderlessReceipt=await presetModel.load(folderlessItem) else {
                throw EngineFailure(message:presetModel.error ?? "Could not create or load folderless preset")
            }
            var folderless=ExportDraft()
            folderless.destination=destination
            folderless.apply(folderlessReceipt)
            try check(folderless.destination.isEmpty && !folderless.shouldRememberPrevious,
                "loading_folderless_preset_clears_destination_and_establishes_baseline")
            folderless.destination=changedDestination
            try check(folderless.shouldRememberPrevious,
                "destination_only_change_from_folderless_preset_is_a_manual_session")
            await store.export(folderless.destination,folderless.format,folderless.options,
                rememberPrevious:folderless.shouldRememberPrevious)
            jobs=try await rememberCurrentJobs()
            let acceptedB=try await Backend.call("get_previous_export")
            let acceptedBSettings=acceptedB["settings"] as? [String:Any] ?? [:]
            try check(jobs.count==7 && (acceptedB["revision"] as? Int)==3
                && acceptedBSettings["destination"] as? String==changedDestination
                && optionsMatch(acceptedBSettings["options"] as? [String:Any] ?? [:],manualOptions),
                "modified_named_preset_remembers_destination_only_change")

            let baselineBeforeRename=folderless.presetBaseline
            guard let currentFolderless=presetModel.page?.items.first(where:{$0.id==folderlessPreset.id}),
                  let renameSource=presetModel.mutationSource(for:currentFolderless),
                  let renamed=await presetModel.rename(renameSource,name:"\(prefix) Renamed Folderless") else {
                throw EngineFailure(message:presetModel.error ?? "Could not rename folderless preset")
            }
            folderless.acknowledgeRename(renamed,sourceRevision:renameSource.expectedRevision)
            try check(folderless.presetBaseline==baselineBeforeRename && folderless.shouldRememberPrevious
                && folderless.destination==changedDestination,
                "rename_changes_preset_label_without_changing_effective_baseline")
            guard let renamedItem=presetModel.page?.items.first(where:{$0.id==folderlessPreset.id}),
                  let deleteSource=presetModel.mutationSource(for:renamedItem) else {
                throw EngineFailure(message:"Renamed folderless preset missing before delete")
            }
            let deleted=await presetModel.delete(deleteSource)
            folderless.forgetDeletedPreset(folderlessPreset.id)
            try check(deleted && folderless.loadedPreset==nil && folderless.presetBaseline==nil
                && folderless.shouldRememberPrevious && folderless.destination==changedDestination,
                "deleting_loaded_preset_keeps_values_but_drops_its_previous_baseline")

            let staleCapture=PreviousExportSnapshot(try await Backend.call("get_previous_export"))!
            var finalManual=manual
            finalManual.format="tiff16";finalManual.space="adobe";finalManual.maxEdge=0
            finalManual.quality=91;finalManual.outputSharpen=15.25;finalManual.name="{stem}-final-{seq}"
            finalManual.priority=2;finalManual.metadata="copyright";finalManual.keywordHierarchy=false
            finalManual.destination=finalDestination
            let finalOptions=finalManual.options
            await store.export(finalManual.destination,finalManual.format,finalOptions,rememberPrevious:true)
            jobs=try await rememberCurrentJobs()
            let advanced=PreviousExportSnapshot(try await Backend.call("get_previous_export"))!
            let jobsBeforeStale=jobIDs(jobs)
            var staleRejected=false
            do {
                _=try await Backend.call("enqueue_previous_exports",[
                    "photo_ids":[1],"expected_revision":staleCapture.revision,
                    "request_key":UUID().uuidString
                ])
            } catch { staleRejected=error.localizedDescription.localizedCaseInsensitiveContains("changed") }
            let afterStale=try await rememberCurrentJobs()
            try check(staleRejected && advanced.revision>staleCapture.revision
                && jobIDs(afterStale)==jobsBeforeStale,
                "stale_previous_revision_is_rejected_without_implicit_replay")

            store.selection=[2]
            store.selected=2
            await store.load(2)
            store.set("exposure",-0.75)
            let selectedForPrevious=store.selection
            let revisionBeforePrevious=advanced.revision
            let submission=Task { await store.exportWithPrevious() }
            var enteredAwait=false
            for _ in 0..<10_000 {
                if store.exportSubmissionBusy && (store.editing || !store.hasPendingEdits) {
                    enteredAwait=true
                    break
                }
                await Task.yield()
            }
            try check(store.exportSubmissionBusy && enteredAwait,
                "previous_action_is_suspended_with_submission_guard_held")
            store.selection=[1]
            await store.export(finalDestination,finalManual.format,finalOptions,rememberPrevious:true)
            await store.exportWithPrevious()
            await submission.value
            jobs=try await rememberCurrentJobs()
            var usedPreviousJob:[String:Any]?
            for id in jobIDs(jobs) {
                let job=try await Backend.call("get_job",["job_id":id])
                let recipe=job["recipe"] as? [String:Any] ?? [:]
                if job["source"] as? String==paths[1]
                    && (recipe["exposure"] as? NSNumber)?.doubleValue == -0.75 {
                    usedPreviousJob=job
                }
            }
            let usedPreviousJobRow=usedPreviousJob ?? [:]
            let usedPreviousRecipe=usedPreviousJobRow["recipe"] as? [String:Any] ?? [:]
            let previousAfterQueue=PreviousExportSnapshot(try await Backend.call("get_previous_export"))!
            try check(store.error==nil && selectedForPrevious==Set([2]) && store.selection==Set([1])
                && jobs.count==10 && usedPreviousJobRow["photo_id"] as? Int==2
                && usedPreviousJobRow["format"] as? String==finalManual.format
                && usedPreviousJobRow["destination"] as? String==finalDestination
                && optionsMatch(usedPreviousJobRow["options"] as? [String:Any] ?? [:],finalOptions)
                && (usedPreviousRecipe["exposure"] as? NSNumber)?.doubleValue == -0.75
                && previousAfterQueue.revision==revisionBeforePrevious
                && previousAfterQueue.settings==advanced.settings,
                "previous_command_captures_selected_live_recipe_without_mutating_previous")

            let firstJobAfterChanges=try await Backend.call("get_job",["job_id":frozenFirst["id"] as! Int])
            try check(firstJobAfterChanges["format"] as? String==frozenFirst["format"] as? String
                && firstJobAfterChanges["destination"] as? String==frozenFirst["destination"] as? String
                && optionsMatch(firstJobAfterChanges["options"] as? [String:Any] ?? [:],manualOptions)
                && ((firstJobAfterChanges["recipe"] as? [String:Any])?["exposure"] as? NSNumber)?.doubleValue==1.25,
                "later_previous_updates_do_not_rewrite_accepted_job_snapshots")
            try check(try paths.enumerated().allSatisfy {
                try Data(contentsOf:URL(fileURLWithPath:$0.element))==originalBytes[$0.offset]
            },"manual_and_previous_queue_actions_preserve_original_photo_bytes")

            try await snapshot("previous-export-sheet-offscreen.png",
                ExportSheet().environmentObject(store),NSSize(width:720,height:920),root)

            for jobID in createdJobIDs {
                _=try await Backend.call("queue_control",["action":"cancel","job_id":jobID])
            }
            await store.refreshJobs()
            try check(store.jobs.allSatisfy{$0["state"] as? String=="cancelled"},
                "regression_cancels_its_paused_jobs_for_clean_shutdown")

            // Unchanged polls and a revision-only reply must not republish workspace state.
            store.thumbnailRenderer.request([])
            store.cancelMainPreview()
            var previewsQuiet=false
            for _ in 0..<10_000 {
                if !store.loading && !store.rendering && store.thumbnailRenderer.loading.isEmpty {
                    previewsQuiet=true
                    break
                }
                await Task.yield()
            }
            try check(previewsQuiet,"preview_and_thumbnail_work_is_quiet_before_poll_observation")
            await store.refreshJobs()
            var pollPublications=0
            let pollObserver=store.objectWillChange.sink{_ in pollPublications+=1}
            await store.refreshJobs()
            var syntheticReply=try await Backend.call("list_jobs")
            var syntheticToken=syntheticReply["previous_export"] as? [String:Any] ?? [:]
            let actualRevision=(syntheticToken["revision"] as? Int) ?? 0
            syntheticToken["revision"]=actualRevision+1
            syntheticReply["previous_export"]=syntheticToken
            store.adoptJobsResponse(syntheticReply)
            let revisionOnlyWasQuiet=pollPublications==0 && store.previousExportAvailable
            await store.refreshJobs()
            let unchangedPollWasQuiet=pollPublications==0
            pollObserver.cancel()
            try check(revisionOnlyWasQuiet && unchangedPollWasQuiet,
                "unchanged_jobs_poll_and_revision_only_previous_update_are_quiet")
            await cleanup()
            presetModel.invalidateReads()
            print(String(data:try JSONSerialization.data(withJSONObject:[
                "ok":true,"passed":checks.count,"checks":checks,
                "offscreen_snapshots":screenshots,"desktop_ui":"NOT_VERIFIED"
            ],options:[.prettyPrinted,.sortedKeys]),encoding:.utf8)!)
            exit(0)
        } catch {
            await cleanup()
            print(String(data:try! JSONSerialization.data(withJSONObject:[
                "ok":false,"passed":checks.values.filter{$0}.count,"checks":checks,
                "error":error.localizedDescription,"store_error":store.error ?? "",
                "offscreen_snapshots":screenshots,"desktop_ui":"NOT_VERIFIED"
            ],options:[.prettyPrinted,.sortedKeys]),encoding:.utf8)!)
            exit(1)
        }
    }
}
