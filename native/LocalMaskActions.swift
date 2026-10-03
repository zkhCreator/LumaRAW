// Purpose: captured native management of existing non-AI local masks.
// Inputs: displayed mask/index, photo revision and explicit domain action/name.
// Outputs: shared mask_action commands, guarded recipe adoption and visible recovery.
// No mask algorithms, SQL, inferred selections or automatic mutation replay.
// Revisions bind indices; a changed photo or mask requires another explicit review.
import Foundation
import SwiftUI

enum LocalMaskPresentation {
    static func name(_ row:[String:Any],index:Int) -> String {
        let name=row["name"] as? String ?? ""
        return name.isEmpty ? "Mask \(index+1)":name
    }
}

struct LocalMaskTarget {
    let photoID:Int
    let revision:Int
    let index:Int
    let mask:[String:Any]
}

struct LocalMaskRenameSheet:View {
    @EnvironmentObject var s:Store
    @Environment(\.dismiss) var dismiss
    let source:LocalMaskRenameSource
    @State private var name:String
    @State private var issue:String?
    init(source:LocalMaskRenameSource) {
        self.source=source;_name=State(initialValue:source.name)
    }
    var body:some View {
        VStack(alignment:.leading,spacing:16) {
            Text("Rename Mask").font(.title2.weight(.semibold))
            TextField("Mask Name",text:$name).textFieldStyle(.roundedBorder)
            Text("Up to 80 characters. An empty name uses the default mask label.")
                .font(.caption).foregroundStyle(.secondary)
            if !s.localMaskContextMatches(source.target) {
                Text("The photo or mask changed. Close this form and review the mask again.")
                    .font(.callout).foregroundStyle(.red)
            }
            if let issue {Text(issue).font(.callout).foregroundStyle(.red)}
            if let recovery=s.activeMaskRecovery {
                Button("Reload Photo") {Task {await s.reloadAfterMaskFailure(recovery)}}
                    .disabled(s.maskActionBusy)
            }
            HStack {
                Spacer()
                Button("Cancel") {dismiss()}.keyboardShortcut(.cancelAction).disabled(s.maskActionBusy)
                Button(s.maskActionBusy ? "Saving…":"Save") {
                    Task {
                        switch await s.performLocalMaskAction("rename",target:source.target,name:name) {
                        case .accepted: dismiss()
                        case .rejected: issue=s.error
                        }
                    }
                }.buttonStyle(.borderedProminent).keyboardShortcut(.defaultAction)
                    .disabled(s.maskActionBusy || s.activeMaskRecovery != nil ||
                              !s.localMaskContextMatches(source.target) || name.unicodeScalars.count>80)
            }
        }.padding(24).frame(width:440)
    }
}

struct LocalMaskRenameSource:Identifiable {
    let id=UUID()
    let target:LocalMaskTarget
    var name:String {target.mask["name"] as? String ?? ""}
}

struct LocalMaskRecovery:Identifiable {
    let id=UUID()
    let photoID:Int
    let message:String
}

enum LocalMaskActionResult {
    case accepted(index:Int?)
    case rejected
}

typealias LocalMaskCommandCall=(_ method:String,_ params:[String:Any]) async throws -> [String:Any]

extension Store {
    var localMaskRows:[[String:Any]] {recipe["masks"] as? [[String:Any]] ?? []}
    var activeMaskRecovery:LocalMaskRecovery? {
        maskActionRecovery.flatMap {$0.photoID==selected ? $0:nil}
    }
    func localMaskContextMatches(_ target:LocalMaskTarget) -> Bool {
        guard selected==target.photoID,photo?.id==target.photoID,photo?.revision==target.revision,
              !hasPendingEdits,!loading,!browsing,!orientationBusy,!syncBusy,
              !developPresetBusy,!historyBusy,!snapshotBusy,
              localMaskRows.indices.contains(target.index) else {return false}
        return NSDictionary(dictionary:target.mask).isEqual(to:localMaskRows[target.index])
    }
    func prepareLocalMaskTarget(_ index:Int) async -> LocalMaskTarget? {
        guard !maskActionBusy,activeMaskRecovery==nil,let current=photo,current.id==selected,
              !loading,!browsing,!orientationBusy,!syncBusy,!developPresetBusy,!historyBusy,!snapshotBusy,
              localMaskRows.indices.contains(index) else {
            error=activeMaskRecovery?.message ?? "The selected mask is no longer available. Review the photo again.";return nil
        }
        let mask=localMaskRows[index]
        guard await flushEdits(),selected==current.id,let saved=photo,saved.id==current.id,
              localMaskRows.indices.contains(index),
              NSDictionary(dictionary:mask).isEqual(to:localMaskRows[index]) else {
            error="The photo or mask changed while preparing this action. Review again.";return nil
        }
        let target=LocalMaskTarget(photoID:saved.id,revision:saved.revision,index:index,mask:mask)
        guard localMaskContextMatches(target) else {
            error="The photo or mask changed while preparing this action. Review again.";return nil
        }
        return target
    }
    @discardableResult func performLocalMaskAction(_ action:String,target:LocalMaskTarget,
        name:String?=nil,call:LocalMaskCommandCall?=nil) async -> LocalMaskActionResult {
        guard !maskActionBusy,activeMaskRecovery==nil,localMaskContextMatches(target) else {
            error=activeMaskRecovery?.message ?? "The photo or mask changed after review. Review again.";return .rejected
        }
        maskActionBusy=true;editing=true
        defer {maskActionBusy=false;editing=false}
        if whiteBalanceTargetActive || whiteBalanceSampling || whiteBalanceArming || whiteBalanceAwaitingFrame {
            cancelWhiteBalanceSelector()
        }
        var params:[String:Any]=["photo_id":target.photoID,"expected_revision":target.revision,
            "mask_index":target.index,"action":action]
        if let name {params["name"]=name}
        do {
            let result=try await (call ?? Backend.call)("mask_action",params)
            guard let updated=Photo(result),updated.id==target.photoID,
                  let revision=result["revision"] as? Int,revision>=target.revision,
                  let index=result["mask_index"] as? Int,
                  let masks=updated.recipe["masks"] as? [[String:Any]],
                  (masks.isEmpty ? index==0:masks.indices.contains(index)) else {
                throw EngineFailure(message:"The mask change receipt was incomplete")
            }
            error=nil
            guard selected==target.photoID,photo?.id==target.photoID,photo?.revision==target.revision else {
                message="Mask updated on the previously selected photo";return .accepted(index:nil)
            }
            photo=updated;recipe=updated.recipe
            if let i=photos.firstIndex(where:{$0.id==updated.id}) {photos[i]=updated}
            render()
            return .accepted(index:index)
        } catch {
            let message="The mask change could not be confirmed. Reload the photo and review its masks before trying again. " + error.localizedDescription
            maskActionRecovery=LocalMaskRecovery(photoID:target.photoID,message:message)
            self.error=message
            return .rejected
        }
    }
    func reloadAfterMaskFailure(_ recovery:LocalMaskRecovery) async {
        guard maskActionRecovery?.id==recovery.id,selected==recovery.photoID,!maskActionBusy,!hasPendingEdits else {return}
        await load(recovery.photoID)
        if selected==recovery.photoID,photo?.id==recovery.photoID,!loading {
            maskActionRecovery=nil;error=nil
        }
    }
}
