// Purpose: native nested/Quick/target collection integration against a real broker.
// Inputs: disposable photographs/catalog. Outputs: persistent hierarchy, aggregate
// views, captured-target conflicts, save/clear and safe subtree removal assertions.
// State evidence only; rendered disclosure controls/keyboard routing need desktop QA.
import AppKit
import Foundation

@main struct NativeCollectionRegression {
    @MainActor static func main() async {
        _ = NSApplication.shared
        let s=Store()
        var checks: [String:Bool] = [:]
        func check(_ value: Bool,_ name: String) throws {
            checks[name]=value;if !value { throw EngineFailure(message:name) }
        }
        func until(_ condition: () -> Bool) async throws {
            for _ in 0..<300 {
                if condition() { return };try await Task.sleep(nanoseconds:20_000_000)
            }
            throw EngineFailure(message:"Collection state timed out")
        }
        do {
            let fixtures=ProcessInfo.processInfo.environment["LUMARAW_TEST_FIXTURES"]!.components(separatedBy:"|")
            await s.importPaths(fixtures);await s.refreshCollections()
            try await until { s.photo != nil && !s.loading }
            let ids=s.photos.map(\.id)
            try check(s.collectionState?.target.kind == "quick","quick_is_initial_target")
            s.selection=Set(ids.prefix(2))
            await s.toggleTargetMembership()
            try check(s.collectionState?.members == Set(ids.prefix(2)),"grid_target_adds_selected_photos")
            let quick=s.collectionState!.quick
            try check(await s.saveQuickCollection(quick,name:"Saved choices",clear:true),"quick_saved_atomically")
            try check(s.total == 2 && s.collectionState?.quick.revision == quick.revision+1,"quick_save_opens_permanent_collection_and_clears_quick")
            let saved=s.activeCollection!
            await s.setTargetCollection(saved)
            try check(s.collectionState?.target.id == saved.id,"regular_target_selected")
            let stale=s.collectionState!
            _=try await Backend.call("set_target_collection",["expected_revision":stale.revision,"collection_id":NSNull()])
            await s.toggleTargetMembership(ids:[ids[2]])
            try check(s.error?.contains("Target collection conflict") == true,"target_changed_elsewhere_rejects_captured_action")
            s.error=nil;await s.refreshCollections()
            try check(s.collectionState?.target.kind == "quick","target_change_read_back")
            try check(await s.saveCollection(name:"Trip",kind:"set",rules:[:],match:"all",original:nil),"create_set")
            let root=s.activeCollection!
            try check(await s.saveCollection(name:"Day",kind:"set",rules:[:],match:"all",original:nil,parentID:root.id),"create_nested_set")
            let child=s.activeCollection!
            s.collectionID=nil;s.offset=0;await s.refresh();s.selection=Set(ids.prefix(2))
            try check(await s.saveCollection(name:"Album",kind:"regular",rules:[:],match:"all",original:nil,parentID:child.id,includePhotos:true),"create_nested_album_with_selection")
            let album=s.activeCollection!
            s.expandCollection(root.id);s.expandCollection(child.id)
            try await until { s.collectionPages[root.id] != nil && s.collectionPages[child.id] != nil }
            try check(s.collectionPages[root.id]?.items.first?.id == child.id && s.collectionPages[child.id]?.items.first?.id == album.id,"lazy_nested_pages_loaded")
            let freshRoot=LibraryCollection(try await Backend.call("get_collection",["collection_id":root.id]))!
            await s.openCollection(freshRoot)
            try check(s.total == 2,"set_displays_descendant_photos")
            await s.duplicateCollection(freshRoot)
            try check(s.activeCollection?.name == "Trip Copy" && s.total == 2,"subtree_duplicate_preserves_photos")
            await s.openCollection(album)
            await s.setTargetCollection(album)
            let deletion=LibraryCollection(try await Backend.call("get_collection",["collection_id":root.id]))!
            await s.deleteCollection(deletion)
            try check(s.collectionID == nil && s.total == ids.count,"subtree_delete_returns_deleted_source_to_catalog")
            try check(s.collectionState?.target.kind == "quick","deleted_target_falls_back_to_quick")
            try check(!s.expandedCollections.contains(root.id) && !s.expandedCollections.contains(child.id),"deleted_tree_releases_sidebar_pages")
            let reloaded=Store();await reloaded.refreshCollections()
            try check(reloaded.collectionState?.quick.id == quick.id && reloaded.collections.contains { $0.name == "Trip Copy" },"state_survives_new_native_store")
            let report:[String:Any]=["ok":true,"checks":checks,"desktop_ui":"NOT_VERIFIED"]
            print(String(data:try JSONSerialization.data(withJSONObject:report,options:[.prettyPrinted,.sortedKeys]),encoding:.utf8)!)
            exit(0)
        } catch {
            print(String(data:try! JSONSerialization.data(withJSONObject:["ok":false,"checks":checks,
                "error":error.localizedDescription,"store_error":s.error ?? ""],options:.prettyPrinted),encoding:.utf8)!)
            exit(1)
        }
    }
}
