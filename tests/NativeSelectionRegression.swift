// Purpose: native range selection and batch culling against the real service.
// Inputs: five disposable image paths and an empty catalog from run_native.py.
// Outputs: bounded-page selection and persisted rating/flag assertions.
// Non-goals: mouse/keyboard event injection or cross-page selection acceptance.
import AppKit
import Foundation

@main struct NativeSelectionRegression {
    @MainActor static func main() async {
        _ = NSApplication.shared
        let s=Store()
        var checks:[String:Bool]=[:]
        func check(_ value:Bool,_ name:String)throws {
            checks[name]=value
            if !value { throw EngineFailure(message:name) }
        }
        func loaded() async throws {
            for _ in 0..<200 {
                if s.photo?.id == s.selected && s.photo != nil && !s.loading { return }
                try await Task.sleep(nanoseconds:20_000_000)
            }
            throw EngineFailure(message:"Photo did not load")
        }
        do {
            let fixtures=ProcessInfo.processInfo.environment["LUMARAW_TEST_FIXTURES"]!.components(separatedBy:"|")
            await s.importPaths(fixtures);try await loaded()
            let ids=s.photos.map(\.id)
            try check(ids.count == 5,"five_photo_page")
            s.choose(ids[0]);try await loaded()
            s.choose(ids[4],range:true);try await loaded()
            try check(s.selection == Set(ids),"shift_selects_contiguous_range")
            s.choose(ids[2],range:true);try await loaded()
            try check(s.selection == Set(ids[0...2]),"shift_keeps_original_anchor")
            s.choose(ids[1],extend:true);try await loaded()
            try check(s.selection == Set([ids[0],ids[2]]),"command_toggles_one_member")
            s.selectAllVisible()
            try check(s.selection == Set(ids),"select_all_visible_page")
            let active=s.photo!,revision=active.revision
            _=try await Backend.call("edit_photo",["photo_id":active.id,"expected_revision":revision,"patch":["exposure":0.6]])
            await s.ratePhotos(s.selection.sorted(),patch:["rating":4,"flag":1])
            try check(s.photo?.revision == revision,"batch_rating_preserves_recipe_revision")
            for id in ids {
                let row=try await Backend.call("get_photo",["photo_id":id])
                try check(row["rating"] as? Int == 4 && row["flag"] as? Int == 1,"batch_culling_photo_\(id)")
            }
            s.develop=true
            let target=s.selected!
            s.rate(5)
            for _ in 0..<200 {
                let row=try await Backend.call("get_photo",["photo_id":target])
                if row["rating"] as? Int == 5 { break }
                try await Task.sleep(nanoseconds:20_000_000)
            }
            let rows=try await Backend.call("list_photos")
            let rated=(rows["photos"] as? [[String:Any]] ?? []).filter { $0["rating"] as? Int == 5 }
            try check(rated.count == 1 && rated[0]["id"] as? Int == target,"develop_rates_only_active_photo")
            let report:[String:Any]=["ok":true,"checks":checks,"desktop_ui":"NOT_VERIFIED"]
            print(String(data:try JSONSerialization.data(withJSONObject:report,options:[.prettyPrinted,.sortedKeys]),encoding:.utf8)!)
            exit(0)
        } catch {
            print(String(data:try! JSONSerialization.data(withJSONObject:["ok":false,"checks":checks,"error":error.localizedDescription,"store_error":s.error ?? ""],options:.prettyPrinted),encoding:.utf8)!)
            exit(1)
        }
    }
}
