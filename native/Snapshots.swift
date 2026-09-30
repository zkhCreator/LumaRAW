// Purpose: captured snapshot management and bounded alphabetical presentation.
// Inputs: selected photo, summary pages and explicit named actions. Outputs:
// revision-bound service commands and ordinary Develop restores/Before copies.
// Catalog owns shared-family identity, recipes, ordering and conflict checks.
// Native forms never adopt newer photo/snapshot revisions automatically.
import SwiftUI

struct SnapshotEntry:Identifiable {
    let id:Int,name:String,revision:Int,created:Double,updated:Double
    init?(_ row:[String:Any]) {
        guard let id=row["id"] as? Int,let name=row["name"] as? String,
              let revision=row["revision"] as? Int,
              let created=(row["created"] as? NSNumber)?.doubleValue,
              let updated=(row["updated"] as? NSNumber)?.doubleValue else {return nil}
        self.id=id;self.name=name;self.revision=revision;self.created=created;self.updated=updated
    }
}

struct SnapshotPage {
    let photoID:Int,sourceID:Int,revision:Int,entries:[SnapshotEntry],nextAfter:Int?
    var photoRevision:Int
    init?(_ reply:[String:Any]) {
        guard let photo=reply["photo_id"] as? Int,let source=reply["source_id"] as? Int,
              let revision=reply["snapshots_revision"] as? Int,
              let photoRevision=reply["photo_revision"] as? Int,
              let rows=reply["versions"] as? [[String:Any]],rows.count<=60 else {return nil}
        let entries=rows.compactMap(SnapshotEntry.init)
        guard entries.count==rows.count else {return nil}
        photoID=photo;sourceID=source;self.revision=revision;self.entries=entries
        self.photoRevision=photoRevision;nextAfter=reply["next_after"] as? Int
    }
}

struct SnapshotDraft:Identifiable {
    let id=UUID()
    let photoID:Int,sourceID:Int,photoRevision:Int
    let version:SnapshotEntry?,stepID:Int?
    let name:String
    init(photo:Photo,version:SnapshotEntry?=nil,stepID:Int?=nil) {
        photoID=photo.id;sourceID=photo.sourceID;photoRevision=photo.revision
        self.version=version;self.stepID=stepID
        name=version?.name ?? Date().formatted(date:.abbreviated,time:.standard)
    }
    init(page:SnapshotPage,version:SnapshotEntry) {
        photoID=page.photoID;sourceID=page.sourceID;photoRevision=page.photoRevision
        self.version=version;stepID=nil;name=version.name
    }
}

extension Store {
    var snapshotReady:Bool {
        guard let p=photo,p.id==selected else {return false}
        return !loading && !browsing && !hasPendingEdits && !orientationBusy &&
            !developPresetBusy && !historyBusy && !snapshotBusy
    }
    func snapshotCaptureValid(_ capture:SnapshotDraft)->Bool {
        snapshotReady && photo?.id==capture.photoID && photo?.sourceID==capture.sourceID &&
            photo?.revision==capture.photoRevision
    }
    func prepareSnapshot(step:Int?=nil,history:DevelopHistoryPage?=nil) {
        guard snapshotReady,let p=photo else {return}
        if let history {
            guard history.photoID==p.id,history.revision==p.revision else {
                snapshotError="The photo changed. Refresh before creating this snapshot.";return
            }
        }
        snapshotError=nil;snapshotDraft=SnapshotDraft(photo:p,stepID:step)
    }
    func prepareSnapshotRename(_ entry:SnapshotEntry,page:SnapshotPage) {
        let capture=SnapshotDraft(page:page,version:entry)
        guard snapshotCaptureValid(capture) else {
            snapshotError="The photo changed. Refresh before renaming this snapshot.";return
        }
        snapshotError=nil;snapshotDraft=capture
    }
    func readVersions(after:Int?=nil,onlyChanged:Bool=false) async {
        guard let p=photo,p.id==selected,!loading,!snapshotBusy else {return}
        if onlyChanged && snapshotLoading {return}
        var params:[String:Any]=["photo_id":p.id]
        if let after {
            guard let page=snapshotPage,page.photoID==p.id else {return}
            params["after_id"]=after;params["expected_snapshots_revision"]=page.revision
        } else if onlyChanged,let page=snapshotPage,page.photoID==p.id {
            params["known_revision"]=page.revision
        }
        snapshotRequest+=1;let request=snapshotRequest
        snapshotLoading=true
        defer {if request==snapshotRequest {snapshotLoading=false}}
        do {
            let reply=try await Backend.call("list_versions",params)
            guard request==snapshotRequest,photo?.id==p.id,selected==p.id,photo?.revision==p.revision else {return}
            if reply["unchanged"] as? Bool == true {
                guard var page=snapshotPage,page.sourceID==p.sourceID,
                      page.revision==reply["snapshots_revision"] as? Int else {return}
                page.photoRevision=p.revision;snapshotPage=page
            } else {
                guard let page=SnapshotPage(reply),page.sourceID==p.sourceID else {
                    throw EngineFailure(message:"Invalid snapshot page")
                }
                snapshotPage=page;snapshotAfter=after
            }
            // Background polling must not erase a captured mutation conflict.
            if !onlyChanged {snapshotError=nil}
        } catch {
            if request==snapshotRequest,selected==p.id {snapshotError=error.localizedDescription}
        }
    }
    func refreshSnapshotsIfVisible() {
        guard showVersions || snapshotExpanded,let p=photo,!snapshotBusy,!snapshotLoading else {return}
        Task {
            guard photo?.id==p.id,photo?.revision==p.revision,!snapshotLoading else {return}
            await readVersions(onlyChanged:true)
        }
    }
    func refreshSnapshotPhoto() async {
        guard snapshotReady,let id=selected else {return}
        await load(id);await readVersions()
    }
    @discardableResult func applySnapshotDraft(_ draft:SnapshotDraft,name:String) async ->Bool {
        guard snapshotCaptureValid(draft) else {
            snapshotError="The photo changed. Close this form and refresh before trying again.";return false
        }
        snapshotBusy=true;snapshotError=nil
        var params:[String:Any]=["photo_id":draft.photoID,"name":name]
        let method:String
        if let entry=draft.version {
            method="rename_version";params["version_id"]=entry.id;params["expected_version_revision"]=entry.revision
        } else {
            method="save_version";params["expected_revision"]=draft.photoRevision
            if let step=draft.stepID {params["step_id"]=step}
        }
        do {
            _=try await Backend.call(method,params)
            snapshotBusy=false
            if selected==draft.photoID {await readVersions()}
            return true
        } catch {
            snapshotBusy=false;snapshotError=error.localizedDescription;return false
        }
    }
    @discardableResult func performSnapshot(_ action:String,captured:SnapshotDraft) async ->Bool {
        guard snapshotCaptureValid(captured),let entry=captured.version else {
            snapshotError="The photo changed. Refresh before applying this snapshot action.";return false
        }
        guard ["restore_version","update_version","delete_version","before_after"].contains(action) else {return false}
        var params:[String:Any]=["photo_id":captured.photoID,"version_id":entry.id,"expected_version_revision":entry.revision]
        if action != "delete_version" {params["expected_revision"]=captured.photoRevision}
        if action=="before_after" {params["action"]="snapshot_to_before"}
        snapshotBusy=true;snapshotError=nil
        let success:Bool
        if action=="restore_version" || action=="before_after" {
            editing=true
            success=await recipeMutation(action,params,photoID:captured.photoID)
            if !success {snapshotError=error}
        } else {
            do {_=try await Backend.call(action,params);success=true}
            catch {snapshotError=error.localizedDescription;success=false}
        }
        snapshotBusy=false
        if success,selected==captured.photoID {await readVersions()}
        return success
    }
    // Retained for native callers that save after their own pending adjustments.
    func saveVersion(_ name:String) async {
        guard let id=selected,await flushEdits(),let p=photo,p.id==id else {return}
        _=await applySnapshotDraft(SnapshotDraft(photo:p),name:name)
    }
}
