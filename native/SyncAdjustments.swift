// Purpose: captured native Sync review over the engine's recipe group contract.
// Inputs: active source, bounded selected targets, recipe schema and explicit groups.
// Outputs: one revision-bound batch command and visible conflict/uncertain errors.
// Reviews never rebase while open. No SQL, pixels or automatic mutation replay.
// The engine owns group membership; the shell owns ordering/default checkbox choices.
// Only a new explicit review may adopt changed source settings before capturing targets.
import Foundation

struct SyncAdjustmentsSchema {
    let groups:[String:[String]]
    let names:[String]
    let initiallySelected:Set<String>
    init?(_ result:[String:Any]) {
        guard let groups=result["groups"] as? [String:[String]],
              let defaults=result["defaults"] as? [String:Any],
              !groups.isEmpty,groups.count<=128,
              groups.allSatisfy({name,fields in
                  !name.isEmpty && name.count<=120 && !fields.isEmpty && fields.count<=128 &&
                  Set(fields).count==fields.count && fields.allSatisfy {defaults[$0] != nil}
              }) else {return nil}
        self.groups=groups
        let order=["White Balance","Light","Color","Presence","Black & White Mix",
                   "Tone Curve","Detail","Lens","Composition","Local Masks","Camera Profile","LUT"]
        names=order.filter {groups[$0] != nil} + groups.keys.filter {!order.contains($0)}.sorted()
        initiallySelected=Set(order.prefix(7)).intersection(groups.keys)
    }
}

struct SyncAdjustmentsDraft {
    let source:Photo
    let targets:[Photo]
    let schema:SyncAdjustmentsSchema
    var photoIDs:Set<Int> {Set(targets.map(\.id)).union([source.id])}
}

extension Store {
    func syncContextMatches(_ draft:SyncAdjustmentsDraft) -> Bool {
        selected==draft.source.id && photo?.id==draft.source.id &&
        photo?.revision==draft.source.revision && selection==draft.photoIDs &&
        !hasPendingEdits && !loading && !browsing && !orientationBusy &&
        !developPresetBusy && !painterBusy
    }

    func prepareSyncAdjustments() async -> SyncAdjustmentsDraft? {
        guard !syncBusy,let sourceID=selected,photo?.id==sourceID,
              selection.contains(sourceID),(2...61).contains(selection.count),
              !loading,!browsing,!orientationBusy,!developPresetBusy,!painterBusy else {
            error="Select an active source and up to 60 other photos before syncing";return nil
        }
        let capturedSelection=selection
        guard await flushEdits(),selected==sourceID,selection==capturedSelection,
              var source=photo,source.id==sourceID,!hasPendingEdits else {
            error="The source or selection changed while preparing Sync. Review again.";return nil
        }
        func matches() -> Bool {
            selected==sourceID && photo?.id==sourceID && photo?.revision==source.revision &&
            selection==capturedSelection && !hasPendingEdits && !loading && !browsing
        }
        do {
            let sourceRow=try await Backend.call("get_photo",["photo_id":sourceID])
            guard matches(),!syncBusy else {
                throw EngineFailure(message:"The source or selection changed while preparing Sync. Review again.")
            }
            guard let updated=Photo(sourceRow),updated.id==sourceID,
                  let revision=sourceRow["revision"] as? Int,revision==updated.revision,revision>=0 else {
                throw EngineFailure(message:"The Sync source could not be read")
            }
            let sourceChanged=updated.revision != source.revision ||
                updated.sourceRevision != source.sourceRevision || updated.orientation != source.orientation
            photo=updated;recipe=updated.recipe;metadata=updated.metadata
            if let index=photos.firstIndex(where: {$0.id==sourceID}) {photos[index]=updated}
            source=updated
            if sourceChanged {render()}
            let result=try await Backend.call("recipe_schema")
            guard let schema=SyncAdjustmentsSchema(result) else {
                throw EngineFailure(message:"Sync parameter groups could not be read")
            }
            guard matches(),!syncBusy else {
                throw EngineFailure(message:"The source or selection changed while preparing Sync. Review again.")
            }
            var targets:[Photo]=[]
            for id in capturedSelection.sorted() where id != sourceID {
                let row=try await Backend.call("get_photo",["photo_id":id])
                guard let target=Photo(row),target.id==id,
                      let revision=row["revision"] as? Int,revision==target.revision,revision>=0 else {
                    throw EngineFailure(message:"A selected Sync target could not be read")
                }
                guard matches(),!syncBusy else {
                    throw EngineFailure(message:"The source or selection changed while preparing Sync. Review again.")
                }
                targets.append(target)
            }
            let draft=SyncAdjustmentsDraft(source:source,targets:targets,schema:schema)
            guard syncContextMatches(draft) else {
                throw EngineFailure(message:"The source or selection changed while preparing Sync. Review again.")
            }
            return draft
        } catch {self.error=error.localizedDescription;return nil}
    }

    @discardableResult func sync(_ groups:[String],draft supplied:SyncAdjustmentsDraft?=nil) async -> Bool {
        guard !syncBusy else {return false}
        let reviewed:SyncAdjustmentsDraft?
        if let supplied {reviewed=supplied} else {reviewed=await prepareSyncAdjustments()}
        guard let draft=reviewed else {return false}
        guard !syncBusy,syncContextMatches(draft) else {
            error="The source, edits or selection changed after Sync review. Review again.";return false
        }
        guard !groups.isEmpty,Set(groups).count==groups.count,
              Set(groups).isSubset(of:Set(draft.schema.names)) else {
            error="Choose supported parameter groups before syncing";return false
        }
        syncBusy=true
        defer {syncBusy=false}
        do {
            let result=try await Backend.call("sync_photos",[
                "source_id":draft.source.id,"expected_source_revision":draft.source.revision,
                "targets":draft.targets.map {["photo_id":$0.id,"expected_revision":$0.revision]},
                "groups":groups
            ])
            guard result["synced"] as? Int==draft.targets.count else {
                throw EngineFailure(message:"Sync could not be confirmed. Review target photos before trying again.")
            }
            error=nil
            if syncContextMatches(draft) {showSync=false}
            message="Synced \(draft.targets.count) photos"
            await refresh()
            return true
        } catch {self.error=error.localizedDescription;return false}
    }
}
