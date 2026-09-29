// Purpose: main-thread presentation state and user workflows for the native shell.
// Inputs: native controls and service replies. Outputs: reversible recipe edits,
// preview paths and queue state. Revisions belong to the service; stale edits are
// rejected, never silently retried. UI state contains one bounded catalog page.
import SwiftUI
import AppKit
import UniformTypeIdentifiers

@MainActor final class Store: ObservableObject {
    @Published var photos: [Photo] = []
    @Published var photoStacks: [Int:PhotoStack] = [:]
    @Published var stackRevision=0
    @Published var stackBusy=false
    @Published var showStacks=true
    @Published var autoStackSource: AutoStackSource?
    @Published var showAutoStack=false
    @Published var selected: Int?
    @Published var selection: Set<Int> = []
    @Published var photo: Photo?
    @Published var recipe: [String: Any] = [:]
    @Published var thumbnails: [Int: NSImage] = [:]
    @Published var thumbnailErrors: [Int: String] = [:]
    lazy var thumbnailRenderer=ThumbnailRenderer(changed: { [weak self] images,errors in
        self?.thumbnails=images;self?.thumbnailErrors=errors
    })
    @Published var preview: NSImage?
    @Published var previewGeometry: PhotoPreviewGeometry?
    @Published var orientationState: PhotoOrientationState?
    @Published var orientationBusy=false
    @Published var developPresetPage: DevelopPresetPage?
    @Published var developPresetQuery: [String:Any]=[:]
    @Published var developPresetBusy=false
    @Published var showDevelopPresets=false
    @Published var developPresetEditor: DevelopPresetEditorSource?
    @Published var painterDevelopPreset: DevelopPresetSelection?
    var developPresetReadGeneration=0
    var developPresetEditorGeneration=0
    var orientationReadGeneration=0
    @Published var before: NSImage?
    @Published var histogram: [[Double]] = []
    @Published var metadata: [String: Any] = [:]
    @Published var importReview: ImportReviewModel?
    @Published var iptcFields: [MetadataField]=[]
    @Published var metadataPresetPage: MetadataPresetPage?
    @Published var metadataPresetQuery: [String:Any]=[:]
    @Published var metadataPresetBusy=false
    @Published var showMetadataPresets=false
    @Published var metadataPresetEditor: MetadataPresetEditorSource?
    @Published var painterMetadataPreset: MetadataPresetSelection?
    var metadataPresetReadGeneration=0
    var metadataPresetEditorGeneration=0
    @Published var total=0
    @Published var offset=0
    @Published var mode="all"
    @Published var selectPreviousImport=true
    @Published var importPreferenceBusy=false
    var importPreferenceGeneration=0
    var previousImportRevision = -1
    @Published var search=""
    @Published var libraryFilters: [String: Any] = [:]
    @Published var librarySort="imported"
    @Published var sortDescending=true
    @Published var collectionID: Int?
    @Published var activeCollection: LibraryCollection?
    @Published var folderID: Int?
    @Published var activeFolder: LibraryFolder?
    @Published var showFolderRelocation=false
    @Published var relocationFolder: LibraryFolder?
    @Published var showFolderSync=false
    @Published var syncFolder: LibraryFolder?
    @Published var includeSubfolders=true
    @Published var folderSearch=""
    @Published var folderFavorites=false
    @Published var folderColor="any"
    @Published var folderPages: [Int:FolderPage]=[:]
    @Published var expandedFolders: Set<Int>=[]
    var folderPageGenerations: [Int:Int]=[:]
    var folderSearchTask: Task<Void,Never>?
    var folderRevision = -1
    var photoFolderRevision = -1
    var sourceNavigationGeneration=0
    @Published var keywordSearch=""
    @Published var keywordPages: [Int:KeywordPage]=[:]
    @Published var expandedKeywords: Set<Int>=[]
    @Published var keywordBusy=false
    @Published var keywordSets: KeywordSetState?
    @Published var keywordSetBusy=false
    @Published var keywordSetDraft: [String]?
    var keywordSetDraftRevision: String?
    var keywordSetGeneration=0
    @Published var keywordShortcut: KeywordShortcut?
    @Published var shortcutEditor: KeywordShortcutEditorSource?
    @Published var painterKeywordPicker: PainterKeywordPickerModel?
    var shortcutReadGeneration=0
    @Published var painterEnabled=false
    @Published var painterKind="keywords"
    @Published var painterRating=5
    @Published var painterFlag=1
    @Published var painterLabel="red"
    @Published var painterOrientationAction="rotate_right"
    @Published var painterBusy=false
    @Published var painterTouched: Set<Int>=[]
    var painterStroke: PainterStroke?
    @Published var showKeywordEditor=false
    @Published var keywordEditorLoading=false
    var keywordEditorGeneration=0
    @Published var editingKeyword: LibraryKeyword?
    @Published var newKeywordParent: LibraryKeyword?
    var keywordEditorTargets: [Photo]=[]
    var keywordEditorRevision=0
    var keywordRevision = -1
    var photoKeywordRevision = -1
    var keywordPageGenerations: [Int:Int]=[:]
    var keywordSearchTask: Task<Void,Never>?
    @Published var collections: [LibraryCollection] = []
    @Published var collectionOffset=0
    @Published var collectionPages: [Int:CollectionPage] = [:]
    var collectionPageGenerations: [Int:Int] = [:]
    @Published var expandedCollections: Set<Int> = []
    @Published var collectionState: CollectionState?
    @Published var newCollectionKind="regular"
    @Published var newCollectionParent: Int?
    @Published var showQuickSave=false
    @Published var quickSaveSource: LibraryCollection?
    @Published var collectionTotal=0
    @Published var showCollectionEditor=false
    @Published var editingCollection: LibraryCollection?
    @Published var showLibraryFilters=false
    @Published var copyBusy=false
    @Published var showCopyRemoval=false
    @Published var copyRemovalTargets: [Photo] = []
    @Published var showMetadataEditor=false
    @Published var metadataTargets: [Photo] = []
    @Published var workspace="library"
    @Published var develop=false
    @Published var libraryView: LibraryViewMode = .grid
    @Published var review=ReviewSession()
    let reviewRenderer=ReviewRenderer()
    var reviewPaneWidth=1200
    var reviewPaneHeight=900
    var reviewSwitchGeneration=0
    @Published var showInspector=true
    @Published var compare=false
    @Published var splitCompare=false
    @Published var splitPosition=0.5
    @Published var canvasTool="view"
    @Published var detail=false
    @Published var cx=0.5
    @Published var cy=0.5
    @Published var gamut=false
    @Published var proof: [String: Any] = [:]
    @Published var busy=false
    @Published var browsing=false
    @Published var loading=false
    @Published var rendering=false
    @Published var editing=false
    @Published var error: String?
    @Published var serviceUpgradeNeeded=false
    @Published var connectingService=false
    @Published var serviceConnectionMessage=""
    @Published var message="Originals are read-only · Edits save automatically"
    @Published var jobs: [[String: Any]] = []
    @Published var paused=false
    @Published var budget=4096.0
    @Published var computeBackend="auto"
    @Published var processingSummary="No photos processed yet"
    @Published var effectiveBudget=4096
    @Published var availableMemory=0.0
    @Published var versions: [[String: Any]] = []
    @Published var defaults: [String: Any] = [:]
    @Published var pointCurvePresets: [String:[[Double]]] = [:]
    @Published var presets: [String: [String: Any]] = [:]
    @Published var showExport=false
    @Published var showVersions=false
    @Published var showRecipe=false
    @Published var showSync=false
    @Published var showCalibration=false
    private let previewClient=UUID().uuidString
    private var generation=0
    private var pageGeneration=0
    private var previewTask: Task<Void,Never>?
    private var pendingPatch: [String: Any] = [:]
    private var editTask: Task<Void,Never>?
    private var saveFailed=false
    private var copied: [String: Any]?
    private var polling: Task<Void,Never>?
    private var started=false
    private var selectionAnchor: Int?
    var canChangePhoto: Bool { !browsing && !editing && pendingPatch.isEmpty }
    var hasPendingEdits: Bool { editing || !pendingPatch.isEmpty }

    func start() async {
        guard !started else{return};started=true
        do {
            let schema=try await Backend.call("recipe_schema")
            defaults=schema["defaults"] as? [String:Any] ?? [:]
            presets=schema["presets"] as? [String:[String:Any]] ?? [:]
            await refreshMemory()
            await refreshCollections()
            await refresh()
            let args=CommandLine.arguments
            if let i=args.firstIndex(of:"--import"),args.count>i+1 { await reviewImport([args[i+1]]) }
            polling=Task { [weak self] in
                while !Task.isCancelled {
                    try? await Task.sleep(nanoseconds:2_000_000_000)
                    guard let self else { return }
                    await self.refreshJobs()
                    await self.refreshVisibleSummaries()
                    if let current=self.photo, !self.editing, self.pendingPatch.isEmpty {
                        if let row=try? await Backend.call("get_photo",["photo_id":current.id]),let updated=Photo(row) {
                            guard !self.editing,self.pendingPatch.isEmpty,self.selected==current.id,self.photo?.revision==current.revision else{continue}
                            if updated.revision != current.revision {
                                self.photo=updated;self.recipe=updated.recipe;self.message="Loaded edits from another client";self.render()
                            } else if updated.rating != current.rating || updated.flag != current.flag || updated.metadataRevision != current.metadataRevision || updated.sourceRevision != current.sourceRevision {self.photo=updated}
                        }
                    }
                }
            }
        } catch {
            started=false
            serviceUpgradeNeeded=(error as? EngineFailure)?.canActivateService ?? false
            self.error=error.localizedDescription
        }
    }

    func activateCurrentService() async {
        guard !connectingService else { return }
        connectingService=true
        defer { connectingService=false }
        do {
            _=try await Backend.call("service_connection",["action":"activate"])
            serviceUpgradeNeeded=false;serviceConnectionMessage="Connected with this version of LumaRAW"
            error=nil
            if !started { await start() }
            else { await refreshMemory();await refreshCollections();await refresh() }
        } catch {
            serviceConnectionMessage=error.localizedDescription
            serviceUpgradeNeeded=(error as? EngineFailure)?.canActivateService ?? false
            self.error=error.localizedDescription
        }
    }
    func refresh() async {
        pageGeneration += 1;let token=pageGeneration;browsing=true
        defer{if token==pageGeneration{browsing=false}}
        guard await flushEdits(),token==pageGeneration else{return}
        do {
            var params: [String: Any] = ["offset":offset,"mode":mode,"search":search,
                                       "filters":libraryFilters,"sort":librarySort,"descending":sortDescending,"stacked":showStacks]
            if let collectionID { params["collection_id"]=collectionID }
            if let folderID { params["folder_id"]=folderID;params["include_subfolders"]=includeSubfolders }
            let result=try await Backend.call("list_photos",params)
            guard token==pageGeneration else{return}
            photos=(result["photos"] as? [[String:Any]] ?? []).compactMap(Photo.init)
            adoptStacks(result)
            previousImportRevision=(result["previous_import"] as? [String:Any])?["revision"] as? Int ?? previousImportRevision
            photoFolderRevision=result["folder_revision"] as? Int ?? photoFolderRevision
            photoKeywordRevision=result["keyword_revision"] as? Int ?? photoKeywordRevision
            total=result["total"] as? Int ?? 0
            offset=result["offset"] as? Int ?? offset
            thumbnails=thumbnails.filter { id,_ in photos.contains{$0.id==id} }
            selection.formIntersection(Set(photos.map(\.id)))
            if !photos.contains(where: { $0.id == selectionAnchor }) { selectionAnchor=nil }
            if selected==nil || !photos.contains(where:{$0.id==selected}) {
                if let first=photos.first{selected=first.id;selection=[first.id];await load(first.id)}
                else{selected=nil;selection=[];clearPhoto()}
            }
            reviewSelectionChanged()
            updateThumbnails(force:true)
            await refreshCollectionState()
            await refreshOrientationState()
            if folderRevision != photoFolderRevision { await refreshFolders() }
            if keywordRevision != photoKeywordRevision { await refreshKeywords();await refreshKeywordPhoto() }
        } catch {self.error=error.localizedDescription}
    }
    func clearPhoto() {
        generation += 1;previewTask?.cancel();photo=nil;recipe=[:]
        preview=nil;previewGeometry=nil;before=nil;metadata=[:];histogram=[];rendering=false;loading=false
    }
    func choose(_ id:Int, extend:Bool=false, range:Bool=false) {
        guard !browsing,!editing,pendingPatch.isEmpty else{message="Wait for the current edit to finish saving";return}
        guard photos.contains(where:{$0.id==id}) else{return}
        defer { reviewSelectionChanged() }
        if isMultiReview,libraryView == .compare,!extend,!range {
            review.chooseCandidate(id)
            selection.insert(id)
            activateReviewPhoto(id)
            return
        }
        if range,let end=photos.firstIndex(where: { $0.id == id }),
           let start=photos.firstIndex(where: { $0.id == (selectionAnchor ?? selected ?? id) }) {
            selectionAnchor=selectionAnchor ?? selected ?? id
            let ids=Set(photos[min(start,end)...max(start,end)].map(\.id))
            selection=extend ? selection.union(ids):ids
            if selected != id || photo == nil {
                selected=id;saveFailed=false;clearPhoto();Task { await load(id) }
            }
            return
        }
        selectionAnchor=id
        if extend && selection.contains(id) {
            selection.remove(id)
            if selected==id {
                selected=selection.sorted().first
                clearPhoto()
                if let next=selected{Task{await load(next)}}
            }
            return
        }
        if extend {selection.insert(id)}else if !selection.contains(id){selection=[id]}
        guard selected != id || photo==nil else{return}
        selected=id;saveFailed=false;clearPhoto()
        Task{await load(id)}
    }
    func activateReviewPhoto(_ id: Int) {
        guard !editing,pendingPatch.isEmpty,photos.contains(where: { $0.id == id }) else { return }
        guard selected != id || photo == nil else { return }
        selected=id;saveFailed=false;clearPhoto()
        Task { await load(id) }
    }
    func cancelMainPreview() {
        generation+=1;let token=generation
        previewTask?.cancel();rendering=false
        Task { _=try? await Backend.call("cancel_preview",["client_id":previewClient,"generation":token]) }
    }
    func load(_ id:Int) async {
        guard selected==id else{return}
        clearPhoto();loading=true;let token=generation
        defer{if token==generation{loading=false}}
        do {
            let row=try await Backend.call("get_photo",["photo_id":id])
            guard selected==id,token==generation,let p=Photo(row) else{return}
            photo=p;recipe=p.recipe;metadata=p.metadata;loading=false
            if let index=photos.firstIndex(where: { $0.id == p.id }) { photos[index]=p }
            render()
        } catch {if selected==id,token==generation{self.error=error.localizedDescription}}
    }
    func render(curveDraft:(PointCurveCapture,[[Double]])?=nil,debounce:Bool=true) {
        if curveDraft == nil { updateThumbnails() }
        if isMultiReview { updateReviewRequests();return }
        guard let p=photo,p.id==selected,!loading else{return}
        if let (capture,_) = curveDraft {
            guard p.id == capture.photoID,p.revision == capture.revision,!hasPendingEdits else {return}
        }
        generation += 1;let token=generation
        previewTask?.cancel()
        if !debounce {rendering=true}
        previewTask=Task {
            if debounce {try? await Task.sleep(nanoseconds:180_000_000)}
            guard !Task.isCancelled,token==generation else{return}
            rendering=true
            var params:[String:Any]=["photo_id":p.id,"client_id":previewClient,"generation":token]
            if let (capture,points) = curveDraft {
                params["curve_patch"]=[capture.key:points];params["expected_revision"]=capture.revision
                params["include_before"]=false
            }
            if detail{params["detail"]=["cx":cx,"cy":cy,"width":1600,"height":1100]}
            var display:[String:Any]=["gamut":gamut]
            if let path=proof["path"],let sha=proof["sha256"]{display["proof_path"]=path;display["proof_sha"]=sha}
            params["display"]=display
            do {
                let r=try await Backend.call("preview_photo",params)
                guard token==generation,selected==p.id else{return}
                guard r["revision"] as? Int == p.revision else { rendering=false;return }
                if let path=r["preview"] as? String{preview=NSImage(contentsOfFile:path)}
                if let path=r["before"] as? String{before=NSImage(contentsOfFile:path)}
                histogram=r["histogram"] as? [[Double]] ?? []
                metadata=r["metadata"] as? [String:Any] ?? [:]
                previewGeometry=PhotoPreviewGeometry(r)
                message=curveDraft != nil ? "Curve preview · Release to save, Escape to cancel" : (detail ? "Full-resolution viewport · 1 image pixel = 1 screen pixel" : "Preview · Originals are read-only · Edits save automatically")
                rendering=false
            } catch {if token==generation {rendering=false;self.error=error.localizedDescription}}
        }
    }
    func set(_ key:String,_ value:Any) {
        guard !loading,!browsing,!orientationBusy,!developPresetBusy,let p=photo,p.id==selected else{return}
        saveFailed=false;recipe[key]=value;pendingPatch[key]=value
        if !editing {scheduleCommit()}
    }
    func scheduleCommit() {
        editTask?.cancel();editTask=Task {
            try? await Task.sleep(nanoseconds:350_000_000)
            guard !Task.isCancelled else{return};await commit()
        }
    }
    func commit() async {
        guard let p=photo,!editing,!pendingPatch.isEmpty else{return}
        let patch=pendingPatch;pendingPatch=[:];editing=true
        do {
            let row=try await Backend.call("edit_photo",["photo_id":p.id,"expected_revision":p.revision,"patch":patch])
            if let updated=Photo(row),selected==p.id {
                photo=updated;recipe=updated.recipe.merging(pendingPatch){_,new in new}
                if let i=photos.firstIndex(where:{$0.id==p.id}) {photos[i]=updated}
            }
            editing=false
            if pendingPatch.isEmpty {render()}else{await commit()}
        } catch {
            pendingPatch=[:];editing=false;saveFailed=true;self.error=error.localizedDescription
            await load(p.id)
        }
    }
    func flushEdits() async -> Bool {
        if !editing,pendingPatch.isEmpty{saveFailed=false;return true}
        editTask?.cancel()
        while editing {try? await Task.sleep(nanoseconds:20_000_000)}
        if !pendingPatch.isEmpty {await commit()}
        while editing {try? await Task.sleep(nanoseconds:20_000_000)}
        return !saveFailed && pendingPatch.isEmpty
    }
    func apply(_ patch:[String:Any]) {for(k,v)in patch{set(k,v)}}
    func preset(_ name:String) {
        guard let values=presets[name] else{return}
        let keys=["exposure","temperature","tint","contrast","highlights","shadows","whites","blacks","saturation","vibrance","curve_shadows","curve_midtones","curve_lights","red_hue","red_sat","orange_hue","orange_sat","green_hue","green_sat","blue_hue","blue_sat","monochrome"]
        apply(values.filter{keys.contains($0.key)})
    }
    func undo() {
        guard let p=photo,p.id==selected,!loading,!browsing,!editing,!orientationBusy,!developPresetBusy,pendingPatch.isEmpty else{return}
        editing=true
        Task{await recipeMutation("undo_photo",["photo_id":p.id,"expected_revision":p.revision],photoID:p.id)}
    }
    func recipeMutation(_ method:String,_ params:[String:Any],photoID:Int) async {
        do {
            let row=try await Backend.call(method,params)
            if let updated=Photo(row),selected==photoID {
                photo=updated;recipe=updated.recipe.merging(pendingPatch){_,new in new}
                if let i=photos.firstIndex(where:{$0.id==photoID}){photos[i]=updated}
            }
            editing=false
            if pendingPatch.isEmpty{render()}else{await commit()}
        }catch{
            pendingPatch=[:];editing=false;saveFailed=true;self.error=error.localizedDescription
            if selected==photoID{await load(photoID)}
        }
    }
    func selectAllVisible() {
        guard !browsing,!editing,pendingPatch.isEmpty,!photos.isEmpty else { return }
        selection=Set(photos.map(\.id))
        if selected == nil { selected=photos.first?.id; if let selected { Task { await load(selected) } } }
        selectionAnchor=selected
    }
    func rate(_ value:Int) {
        let ids=actionPhotoIDs
        Task { await ratePhotos(ids,patch:["rating":value]) }
    }
    func flag(_ value:Int) {
        let ids=actionPhotoIDs
        Task { await ratePhotos(ids,patch:["flag":value]) }
    }
    func ratePhotos(_ ids: [Int], patch: [String: Any]) async {
        guard !ids.isEmpty else { return }
        do {
            let result=try await Backend.call("rate_photos",patch.merging(["photo_ids":ids]) { _,new in new })
            for row in result["updated"] as? [[String: Any]] ?? [] {
                guard let id=row["photo_id"] as? Int else { continue }
                if var current=photo,current.id == id {
                    if let rating=row["rating"] as? Int { current.rating=rating }
                    if let flag=row["flag"] as? Int { current.flag=flag }
                    photo=current
                }
                if let index=photos.firstIndex(where: { $0.id == id }) {
                    if let rating=row["rating"] as? Int { photos[index].rating=rating }
                    if let flag=row["flag"] as? Int { photos[index].flag=flag }
                }
            }
            // Keep the active recipe revision for conflict detection. A new
            // library query is explicit so a pick does not unexpectedly hide
            // the photo while the user is still reviewing or editing it.
            message="Updated \(ids.count) \(ids.count == 1 ? "photo":"photos")"
        } catch { self.error=error.localizedDescription }
    }
    func mutate(_ method:String,_ params:[String:Any]) async {
        do {
            let row=try await Backend.call(method,params)
            if let p=Photo(row){
                if selected==p.id {
                    if method=="rate_photo",var current=photo {
                        // A rating reply must not adopt another client's recipe revision.
                        current.rating=p.rating;current.flag=p.flag;photo=current
                    }else{photo=p}
                }
                if let i=photos.firstIndex(where:{$0.id==p.id}){photos[i]=p}
            }
        }
        catch{self.error=error.localizedDescription}
    }
    func importPanel() {let panel=NSOpenPanel();panel.canChooseDirectories=true;panel.canChooseFiles=true;panel.allowsMultipleSelection=true;panel.prompt="Review";panel.message="Choose photographs or folders to review before importing";if panel.runModal() == .OK{Task{await reviewImport(panel.urls.map(\.path))}}}
    func importPaths(_ paths:[String]) async {
        busy=true;defer{busy=false}
        do{let r=try await Backend.call("import_photos",["paths":paths]);message="Imported \(r["imported"] ?? 0) photos";await finishImport(r["imported"] as? Int ?? 0)}catch{self.error=error.localizedDescription}
    }
    func refreshMemory() async {
        let importPreferenceRead=importPreferenceGeneration
        if let value=try? await Backend.call("settings",[:]) {
            if !importPreferenceBusy,importPreferenceRead == importPreferenceGeneration { selectPreviousImport=value["select_previous_import"] as? Bool ?? true }
            computeBackend=value["compute_backend"] as? String ?? "auto"
            if let processing=value["last_processing"] as? [String:Any],let backend=processing["backend"] as? String {
                let device=processing["device"] as? String ?? "CPU"
                let time=(processing["worker_seconds"] as? NSNumber)?.doubleValue ?? 0
                processingSummary="Last process: \(backend) · \(device) · \(String(format:"%.2f",time)) s"
            }
            budget=(value["budget_mb"] as? NSNumber)?.doubleValue ?? budget
            effectiveBudget=value["effective_budget_mb"] as? Int ?? Int(budget)
            availableMemory=(value["available_mb"] as? NSNumber)?.doubleValue ?? 0
        }
    }
    func refreshJobs() async {if let r=try? await Backend.call("list_jobs"){jobs=r["jobs"] as? [[String:Any]] ?? [];paused=r["paused"] as? Bool ?? false}}
    func queue(_ action:String,_ id:Int?=nil){Task{do{var p:[String:Any]=["action":action];if let id{p["job_id"]=id};_=try await Backend.call("queue_control",p);await refreshJobs()}catch{self.error=error.localizedDescription}}}
    func export(_ destination:String,_ format:String,_ options:[String:Any]) async {
        guard await flushEdits() else{return}
        let ids=Array(selection).sorted()
        guard !ids.isEmpty else{error="Select photos to export";return}
        do{_=try await Backend.call("enqueue_exports",["photo_ids":ids,"destination":destination,"format":format,"options":options,"request_key":UUID().uuidString]);showExport=false;workspace="exports";await refreshJobs()}catch{self.error=error.localizedDescription}
    }
    func readVersions() async {guard let p=photo else{return};if let r=try? await Backend.call("list_versions",["photo_id":p.id]){versions=r["versions"] as? [[String:Any]] ?? []}}
    func saveVersion(_ name:String) async {guard await flushEdits(),let p=photo else{return};do{_=try await Backend.call("save_version",["photo_id":p.id,"name":name]);await readVersions()}catch{self.error=error.localizedDescription}}
    func restoreVersion(_ id:Int) async {
        guard await flushEdits(),let p=photo,p.id==selected,!loading else{return}
        editing=true
        await recipeMutation("restore_version",["photo_id":p.id,"version_id":id,"expected_revision":p.revision],photoID:p.id)
    }
    func asset(_ kind:String) {
        let panel=NSOpenPanel();panel.canChooseDirectories=false;panel.allowsMultipleSelection=false
        let target=selected
        if panel.runModal() == .OK,let url=panel.url {Task{do{let r=try await Backend.call("import_asset",["path":url.path,"kind":kind]);if let a=r["asset"] as? [String:Any]{if kind=="icc"{proof=a;render()}else if selected==target{set(kind=="lut" ? "lut":"camera_profile",a)}else{message="Asset imported; selection changed, so no adjustment was applied"}}}catch{self.error=error.localizedDescription}}}
    }
    func libraryAction(_ method:String){Task{busy=true;defer{busy=false};do{_=try await Backend.call(method);await refresh();message="Library index updated"}catch{self.error=error.localizedDescription}}}
    func backup(){let panel=NSSavePanel();panel.nameFieldStringValue="LumaRAW-backup.sqlite";if panel.runModal() == .OK,let path=panel.url?.path{Task{do{_=try await Backend.call("backup_catalog",["path":path]);message="Library backup saved"}catch{self.error=error.localizedDescription}}}}
    func recipeFile(save:Bool){guard let p=photo else{return};if save{let panel=NSSavePanel();panel.nameFieldStringValue="\(p.name).lumarecipe";if panel.runModal() == .OK,let path=panel.url?.path{Task{guard await flushEdits() else{return};do{_=try await Backend.call("save_recipe",["photo_id":p.id,"path":path])}catch{self.error=error.localizedDescription}}}}else{let panel=NSOpenPanel();if panel.runModal() == .OK,let path=panel.url?.path{Task{guard await flushEdits(),let q=photo,q.id==p.id else{return};editing=true;await recipeMutation("load_recipe",["photo_id":q.id,"path":path,"expected_revision":q.revision],photoID:q.id)}}}}
    func relink(){guard let p=photo else{return};let panel=NSOpenPanel();if panel.runModal() == .OK,let path=panel.url?.path{Task{await mutate("relink_photo",["photo_id":p.id,"path":path]);await load(p.id)}}}
    func reveal(){if let p=photo{NSWorkspace.shared.activateFileViewerSelecting([URL(fileURLWithPath:p.path)])}}
    func copyEdits(){copied=recipe;message="Adjustments copied"}
    func pasteEdits(){if let copied{apply(copied)}}
    func sync(_ groups:[String]) async {
        guard await flushEdits(),let p=photo else{return}
        do{
            var targets:[[String:Any]]=[]
            for id in selection where id != p.id {let r=try await Backend.call("get_photo",["photo_id":id]);targets.append(["photo_id":id,"expected_revision":r["revision"] ?? 0])}
            _=try await Backend.call("sync_photos",["source_id":p.id,"targets":targets,"groups":groups]);showSync=false;message="Synced \(targets.count) photos";await refresh()
        }catch{self.error=error.localizedDescription}
    }
}
