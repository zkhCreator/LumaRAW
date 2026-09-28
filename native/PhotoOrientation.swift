// Purpose: native catalog orientation actions and displayed-to-Develop coordinates.
// Inputs: captured visual revisions, portable orientation receipts and unit points.
// Outputs: scoped rotate/flip batches, separate batch undo and refreshed previews.
// No SQL, pixel processing or recipe rotation changes. Orientation survives Develop
// reset; source images and frozen jobs are preserved. Stale operations never retry.
import SwiftUI

enum PhotoOrientation {
    static let actions=[("Rotate Left","rotate_left"),("Rotate Right","rotate_right"),
                        ("Flip Horizontal","flip_horizontal"),("Flip Vertical","flip_vertical")]

    static func ratio(_ value: String,orientation: Int) -> String {
        let parts=value.split(separator:":")
        return orientation % 2 == 1 && parts.count == 2 ? parts.reversed().joined(separator:":"):value
    }

    static func inverse(_ point: CGPoint,orientation: Int) -> CGPoint {
        var x=point.x,y=point.y
        switch orientation % 4 {
        case 1: (x,y)=(y,1-x)
        case 2: (x,y)=(1-x,1-y)
        case 3: (x,y)=(1-y,x)
        default: break
        }
        if orientation>=4 { x=1-x }
        return CGPoint(x:x,y:y)
    }

    static func forward(_ point: CGPoint,orientation: Int) -> CGPoint {
        var x=orientation>=4 ? 1-point.x:point.x,y=point.y
        switch orientation % 4 {
        case 1: (x,y)=(1-y,x)
        case 2: (x,y)=(1-x,1-y)
        case 3: (x,y)=(y,1-x)
        default: break
        }
        return CGPoint(x:x,y:y)
    }

    static func box(_ bounds: [Double],orientation: Int,inverse: Bool=false) -> [Double] {
        let points=[CGPoint(x:bounds[0],y:bounds[1]),CGPoint(x:bounds[2],y:bounds[3])].map {
            inverse ? Self.inverse($0,orientation:orientation):forward($0,orientation:orientation)
        }
        return [min(points[0].x,points[1].x),min(points[0].y,points[1].y),
                max(points[0].x,points[1].x),max(points[0].y,points[1].y)]
    }
}

struct PhotoPreviewGeometry {
    let photoID: Int
    let revision: Int
    let orientation: Int
    let cropBox: [Double]
    let detail: Bool
    init?(_ result: [String:Any]) {
        guard let id=result["photo_id"] as? Int,let revision=result["revision"] as? Int,
              let geometry=result["geometry"] as? [String:Any],let orientation=geometry["orientation"] as? Int,
              let box=geometry["crop_box"] as? [Double],box.count == 4 else { return nil }
        photoID=id;self.revision=revision;self.orientation=orientation;cropBox=box
        detail=result["detail"] as? Bool ?? false
    }
}

struct PhotoOrientationState {
    let revision: Int
    let actionID: Int?
    init?(_ result: [String:Any]) {
        guard let revision=result["revision"] as? Int else { return nil }
        self.revision=revision
        actionID=(result["latest"] as? [String:Any])?["id"] as? Int
    }
}

extension Store {
    var canOrientPhotos: Bool {
        !orientationBusy && !painterBusy && !hasPendingEdits && !browsing && !loading && !actionPhotoIDs.isEmpty
    }

    func refreshOrientationState() async {
        guard !orientationBusy else { return }
        orientationReadGeneration+=1
        let token=orientationReadGeneration
        do {
            let result=try await Backend.call("orientation_state")
            guard token == orientationReadGeneration,!orientationBusy else { return }
            orientationState=PhotoOrientationState(result)
        } catch { if token == orientationReadGeneration { self.error=error.localizedDescription } }
    }

    @discardableResult func orientSelection(_ action: String) -> Task<Void,Never>? {
        guard canOrientPhotos else { return nil }
        let ids=actionPhotoIDs
        let targets=photos.filter { ids.contains($0.id) }
        guard targets.count == ids.count else { return nil }
        return submitOrientation(targets:targets,action:action)
    }

    @discardableResult func submitOrientation(targets: [Photo],action: String) -> Task<Void,Never>? {
        guard !orientationBusy,!painterBusy,!hasPendingEdits,!targets.isEmpty else { return nil }
        let params: [String:Any]=["action":action,"targets":targets.map { ["photo_id":$0.id,"expected_revision":$0.revision] }]
        return orientationCommand("orient_photos",params:params)
    }

    @discardableResult func undoOrientation() -> Task<Void,Never>? {
        guard !orientationBusy,!painterBusy,!hasPendingEdits,
              let state=orientationState,let id=state.actionID else { return nil }
        return orientationCommand("undo_orientation",params:["action_id":id,"expected_revision":state.revision])
    }

    private func orientationCommand(_ method: String,params: [String:Any]) -> Task<Void,Never> {
        cancelPainterStroke()
        orientationBusy=true
        orientationReadGeneration+=1
        cancelMainPreview()
        return Task {
            defer { orientationBusy=false }
            do {
                let result=try await Backend.call(method,params)
                orientationState=PhotoOrientationState(result)
                let changed=result["updated"] as? [Int] ?? []
                await refresh()
                if let active=selected,changed.contains(active) { await load(active) }
                else { render() }
                message="\(method == "undo_orientation" ? "Restored":"Changed") orientation for \(changed.count) photos"
            } catch { self.error=error.localizedDescription }
        }
    }
}

struct PhotoOrientationActions: View {
    @EnvironmentObject var s: Store
    var body: some View {
        Button("Rotate Left") { s.orientSelection("rotate_left") }.keyboardShortcut("[",modifiers:.command).disabled(!s.canOrientPhotos)
        Button("Rotate Right") { s.orientSelection("rotate_right") }.keyboardShortcut("]",modifiers:.command).disabled(!s.canOrientPhotos)
        Button("Flip Horizontal") { s.orientSelection("flip_horizontal") }.disabled(!s.canOrientPhotos)
        Button("Flip Vertical") { s.orientSelection("flip_vertical") }.disabled(!s.canOrientPhotos)
        Button("Undo Last Rotation or Flip") { s.undoOrientation() }
            .disabled(s.orientationState?.actionID == nil || s.orientationBusy || s.painterBusy || s.hasPendingEdits)
    }
}
