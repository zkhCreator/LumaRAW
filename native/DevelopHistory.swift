// Purpose: bounded Develop history presentation and revision-bound navigation.
// Inputs: service summaries and explicit user actions. Outputs: timeline requests
// and recipe mutations through Store. Engine owns state ordering/branching; this
// shell never stores historical recipes or implements a global application undo.
import SwiftUI

struct DevelopHistoryStep:Identifiable {
    let id:Int,label:String,created:Double,current:Bool
    init?(_ row:[String:Any]) {
        guard let id=row["id"] as? Int,let label=row["label"] as? String,
              let created=row["created"] as? Double,let current=row["current"] as? Bool else {return nil}
        self.id=id;self.label=label;self.created=created;self.current=current
    }
}
struct DevelopHistoryPage {
    let photoID:Int,revision:Int,cursor:Int,currentLabel:String
    let canUndo:Bool,canRedo:Bool,steps:[DevelopHistoryStep],nextBefore:Int?
    init?(_ row:[String:Any]) {
        guard let photoID=row["photo_id"] as? Int,let revision=row["revision"] as? Int,
              let cursor=row["cursor"] as? Int,let label=row["current_label"] as? String,
              let undo=row["can_undo"] as? Bool,let redo=row["can_redo"] as? Bool,
              let steps=row["steps"] as? [[String:Any]],steps.count<=60 else {return nil}
        let parsed=steps.compactMap(DevelopHistoryStep.init)
        guard parsed.count==steps.count else {return nil}
        self.photoID=photoID;self.revision=revision;self.cursor=cursor;currentLabel=label
        canUndo=undo;canRedo=redo;self.steps=parsed;nextBefore=row["next_before"] as? Int
    }
}

extension Store {
    var historyReady:Bool {
        guard let p=photo,let page=historyPage else {return false}
        return p.id==selected && page.photoID==p.id && page.revision==p.revision &&
            !loading && !browsing && !hasPendingEdits && !orientationBusy && !developPresetBusy && !historyBusy
    }
    var canUndoDevelop:Bool { historyReady && historyPage?.canUndo == true }
    var canRedoDevelop:Bool { historyReady && historyPage?.canRedo == true }

    func readHistory(before:Int?=nil) async {
        guard let p=photo,p.id==selected else {return}
        historyRequest+=1;let request=historyRequest
        historyReadPhotoID=p.id;historyReadRevision=p.revision
        historyLoading=true
        defer {if request==historyRequest {historyLoading=false}}
        do {
            var params:[String:Any]=["photo_id":p.id,"expected_revision":p.revision]
            if let before {params["before_id"]=before}
            let result=try await Backend.call("list_history",params)
            guard request==historyRequest,selected==p.id,photo?.revision==p.revision else {return}
            guard let page=DevelopHistoryPage(result) else {throw EngineFailure(message:"Invalid history response")}
            historyPage=page;historyBefore=before;historyError=nil
        } catch {
            guard request==historyRequest,selected==p.id,photo?.revision==p.revision else {return}
            historyPage=nil;historyError=error.localizedDescription
        }
    }
    func refreshHistoryIfNeeded() {
        guard let p=photo else {return}
        if historyPage?.photoID != p.id || historyPage?.revision != p.revision {
            Task {
                guard photo?.id==p.id,photo?.revision==p.revision else {return}
                guard historyPage?.photoID != p.id || historyPage?.revision != p.revision else {return}
                // A queued automatic refresh must not supersede an explicit
                // read/page request already loading this exact photo revision.
                guard !historyLoading || historyReadPhotoID != p.id || historyReadRevision != p.revision else {return}
                await readHistory()
            }
        }
    }
    func redo() { moveDevelopHistory("redo_photo") }
    func moveDevelopHistory(_ method:String,step:Int?=nil,name:String?=nil,captured:DevelopHistoryPage?=nil) {
        guard let p=photo,p.id==selected,!loading,!browsing,!hasPendingEdits,
              !orientationBusy,!developPresetBusy,!historyBusy else {return}
        if let captured {
            guard captured.photoID==p.id,captured.revision==p.revision else {
                error="History changed; refresh before applying this action";return
            }
        }
        var params:[String:Any]=["photo_id":p.id,"expected_revision":p.revision]
        if let step {params["step_id"]=step}
        if let name {params["name"]=name}
        historyBusy=true;editing=true
        cancelCurveTarget(restore:false);cancelMixerTarget(restore:false)
        Task {
            await recipeMutation(method,params,photoID:p.id)
            historyBusy=false
            if selected==p.id {await readHistory()}
        }
    }
}

struct DevelopHistoryPanel:View {
    @EnvironmentObject var s:Store
    @State private var expanded=false
    @State private var renameStep:DevelopHistoryStep?
    @State private var captured:DevelopHistoryPage?
    @State private var name=""
    @State private var clear=false
    var body:some View {
        DisclosureGroup("History",isExpanded:$expanded) {
            VStack(alignment:.leading,spacing:8) {
                HStack {
                    Button("Undo"){s.undo()}.disabled(!s.canUndoDevelop)
                    Button("Redo"){s.redo()}.disabled(!s.canRedoDevelop)
                    Spacer()
                    Button {captured=s.historyPage;clear=true} label:{Image(systemName:"trash")}
                        .help("Clear History").accessibilityLabel("Clear History").disabled(!s.historyReady)
                }
                if let page=s.historyPage {
                    Text("Current: \(page.currentLabel)").font(.caption).foregroundStyle(.secondary)
                    ScrollView {
                        LazyVStack(alignment:.leading,spacing:3) {
                            ForEach(page.steps) {step in
                                Button {s.moveDevelopHistory("select_history",step:step.id,captured:page)} label:{
                                    HStack(alignment:.top) {
                                        Image(systemName:step.current ? "checkmark.circle.fill":"circle").frame(width:16)
                                        VStack(alignment:.leading,spacing:2) {
                                            Text(step.label).lineLimit(2)
                                            Text(Date(timeIntervalSince1970:step.created),format:.dateTime.month().day().hour().minute().second()).font(.caption2).foregroundStyle(.secondary)
                                        }
                                        Spacer(minLength:0)
                                    }.padding(5).frame(maxWidth:.infinity,alignment:.leading)
                                        .background(step.current ? Color.accentColor.opacity(0.14):Color.clear).clipShape(RoundedRectangle(cornerRadius:4))
                                }.buttonStyle(.plain).disabled(!s.historyReady)
                                    .accessibilityLabel("\(step.label)\(step.current ? ", current state":"")")
                                    .contextMenu {
                                        Button("Rename…"){captured=page;renameStep=step;name=step.label}
                                            .disabled(!s.historyReady)
                                    }
                            }
                        }
                    }.frame(height:min(240,CGFloat(page.steps.count)*48))
                    HStack {
                        if s.historyBefore != nil {Button("Latest"){Task {await s.readHistory()}}}
                        Spacer()
                        if let next=page.nextBefore {Button("Older Steps"){Task {await s.readHistory(before:next)}}}
                    }.disabled(s.historyLoading || !s.historyReady)
                }
                if s.historyLoading {ProgressView().controlSize(.small)}
                if let error=s.historyError {
                    Text(error).font(.caption).foregroundStyle(.red)
                    Button("Refresh Photo"){if let id=s.selected {Task {await s.load(id)}}}.disabled(s.hasPendingEdits || s.historyBusy)
                }
            }.padding(.top,10)
        }
        .alert("Rename History Step",isPresented:Binding(get:{renameStep != nil},set:{if !$0 {renameStep=nil}}),presenting:renameStep) {step in
            TextField("Name",text:$name)
            Button("Save") {
                if let captured {s.moveDevelopHistory("rename_history",step:step.id,name:name,captured:captured)}
                renameStep=nil
            }
            Button("Cancel",role:.cancel){renameStep=nil}
        }
        .confirmationDialog("Clear this photo’s history?",isPresented:$clear,titleVisibility:.visible) {
            Button("Clear History",role:.destructive){if let captured {s.moveDevelopHistory("clear_history",captured:captured)}}
            Button("Cancel",role:.cancel){}
        } message: {Text("Current adjustments and snapshots stay unchanged. Earlier states and redo steps will be removed. This cannot be undone.")}
    }
}
