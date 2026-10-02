// Purpose: verify source-scoped native stack actions with a real engine.
// Inputs: five generated photos and an isolated catalog. Outputs: state receipts.
// Covers selection, full-stack ordinals, stale actions, source changes and external polling.
// Offscreen badge snapshots are layout evidence only; desktop/VoiceOver are NOT_VERIFIED.
import AppKit
import Foundation
import SwiftUI

@main struct NativeStackRegression {
    @MainActor static func main() async {
        _ = NSApplication.shared
        let s=Store()
        var checks: [String:Bool] = [:]
        var screenshots: [String]=[]
        func check(_ value: Bool,_ name: String) throws {
            checks[name]=value
            if !value { throw EngineFailure(message:name) }
        }
        func snapshot<V: View>(_ name: String,_ view: V,_ size: NSSize,_ root: URL) async throws {
            let host=NSHostingView(rootView:view.background(Color(nsColor:.windowBackgroundColor)))
            host.frame=NSRect(origin:.zero,size:size)
            host.layoutSubtreeIfNeeded()
            try await Task.sleep(nanoseconds:100_000_000)
            host.layoutSubtreeIfNeeded()
            guard let bitmap=host.bitmapImageRepForCachingDisplay(in:host.bounds) else {
                throw EngineFailure(message:"No offscreen bitmap for \(name)")
            }
            host.cacheDisplay(in:host.bounds,to:bitmap)
            guard let png=bitmap.representation(using:.png,properties:[:]) else {
                throw EngineFailure(message:"No offscreen PNG for \(name)")
            }
            try png.write(to:root.appendingPathComponent(name));screenshots.append(name)
        }
        func loaded() async throws {
            for _ in 0..<400 {
                if s.photo?.id == s.selected && s.photo != nil && !s.loading { return }
                try await Task.sleep(nanoseconds:20_000_000)
            }
            throw EngineFailure(message:"Stack selection did not load")
        }
        do {
            let fixtures=ProcessInfo.processInfo.environment["LUMARAW_TEST_FIXTURES"]!.components(separatedBy:"|")
            let root=URL(fileURLWithPath:ProcessInfo.processInfo.environment["LUMARAW_CATALOG"]!)
                .deletingLastPathComponent()
            await s.importPaths(fixtures);try await loaded()
            try check(s.photos.count == 5 && s.total == 5,"five_isolated_photo_fixtures_imported")
            s.choose(4);try await loaded();s.selection=[3,4,5]
            await s.changeStack("group")
            try check(s.error == nil && s.photos.map(\.id) == [4,2,1],"group_uses_active_cover_and_collapses")
            try check(s.selection == [4] && s.selected == 4,"hidden_members_leave_selection")
            try check(s.photoStacks[4]?.count == 3 && s.photoStacks[4]?.collapsed == true,"page_adopts_scoped_stack_badge")
            try check(s.photoStacks[4]?.ordinal == 1 && s.photoStacks[4]?.badgeValue == 3,
                "collapsed_top_ordinal_is_one_and_badge_shows_member_count")
            try await snapshot("stack-badge-collapsed.png",
                StackBadge(photoID:4).environmentObject(s),NSSize(width:100,height:36),root)
            await s.ratePhotos(s.actionPhotoIDs,patch:["rating":5])
            let hidden=try await Backend.call("get_photo",["photo_id":3])
            try check(hidden["rating"] as? Int == 0,"collapsed_rating_does_not_modify_hidden_photo")
            await s.changeStack("toggle",ids:[4])
            try check(s.photos.map(\.id) == [4,5,3,2,1],"expanded_members_stay_contiguous")
            try check(s.photoStacks[4]?.ordinal == 1 && s.photoStacks[5]?.ordinal == 2
                && s.photoStacks[3]?.ordinal == 3 && s.photoStacks[4]?.badgeValue == 1
                && s.photoStacks[5]?.badgeValue == 2 && s.photoStacks[3]?.badgeValue == 3,
                "expanded_badges_use_full_stack_ordinals")
            try await snapshot("stack-badge-expanded.png",
                StackBadge(photoID:5).environmentObject(s),NSSize(width:100,height:36),root)
            s.choose(3);try await loaded()
            await s.changeStack("top",ids:[3])
            try check(s.photoStacks[3]?.top == 3 && s.photos.map(\.id) == [3,4,5,2,1],"move_to_top_changes_cover_and_sort_anchor")
            try check(s.photoStacks[3]?.ordinal == 1 && s.photoStacks[4]?.ordinal == 2
                && s.photoStacks[5]?.ordinal == 3,"move_to_top_recomputes_member_ordinals")
            let stale=s.stackRevision
            _=try await Backend.call("stack_photos",["action":"collapse","photo_ids":[3],"expected_revision":stale])
            await s.changeStack("remove",ids:[3])
            try check(s.error?.contains("Stack conflict") == true,"stale_stack_action_is_visible_conflict")
            s.error=nil
            await s.refreshVisibleSummaries()
            try check(s.photos.map(\.id) == [3,2,1] && s.stackRevision != stale,"external_stack_change_refreshes_visible_page")
            let album=try await Backend.call("save_collection",["name":"Scoped","kind":"regular","photo_ids":[3,4,5]])
            await s.openCollection(LibraryCollection(album)!)
            try check(s.total == 3 && s.photoStacks.isEmpty,"folder_stack_does_not_leak_into_collection")
            s.choose(4);try await loaded();s.selection=[3,4]
            await s.changeStack("group")
            try check(s.total == 2 && s.photoStacks[4]?.count == 2,"collection_has_independent_stack")
            try check(s.activeCollection!.revision > 0,"native_adopts_collection_revision_after_stack_change")
            await s.changeMembership(s.activeCollection!,action:"remove",ids:[3])
            try check(s.total == 2 && s.photoStacks.isEmpty,"membership_removal_dissolves_singleton_stack")
            s.collectionID=nil;s.activeCollection=nil;await s.refresh()
            try check(s.total == 3 && s.photoStacks[3]?.count == 3,"collection_cleanup_preserves_folder_stack")
            await s.setStackVisibility(collapsed:false)
            try check(s.total == 5,"expand_all_restores_hidden_rows")
            await s.setStackVisibility(collapsed:true)
            try check(s.total == 3,"collapse_all_restores_cover_only_rows")
            s.libraryFilters=["text":"photo-3"];await s.refresh()
            try check(s.photos.isEmpty,"collapsed_noncover_filter_can_be_empty")
            _=try await Backend.call("stack_photos",["action":"expand","photo_ids":[3],"expected_revision":s.stackRevision])
            await s.refreshVisibleSummaries()
            try check(s.photos.map(\.id) == [4],"empty_page_poll_observes_external_expansion")
            try check(s.photoStacks[4]?.ordinal == 2,
                "filtered_stack_member_keeps_full_stack_ordinal")
            s.libraryFilters=[:];await s.refresh()
            let smart=try await Backend.call("save_collection",["name":"Smart","kind":"smart"])
            await s.openCollection(LibraryCollection(smart)!)
            try check(!s.canStack && s.photoStacks.isEmpty,"smart_collection_stack_actions_disabled")
            s.collectionID=nil;s.activeCollection=nil;s.showStacks=false;await s.refresh()
            try check(s.total == 5 && s.photoStacks.isEmpty && !s.canStack,"flat_view_exposes_all_photos_without_modifying_stacks")
            s.showStacks=true;await s.refresh()
            await s.changeStack("split",ids:[4,5])
            try check(s.photoStacks[3] == nil && s.photoStacks[4]?.count == 2,"split_leaves_singleton_and_new_selected_stack")
            try check(s.photoStacks[4]?.ordinal == 1 && s.photoStacks[5]?.ordinal == 2,
                "split_stack_ordinals_restart_at_one")
            try check(s.photoStacks[5]?.top == 4 && s.total == 5,"split_keeps_internal_order_and_all_photos")
            print(String(data:try JSONSerialization.data(withJSONObject:["ok":true,"passed":checks.count,"checks":checks,
                "offscreen_screenshots":screenshots,"desktop_ui":"NOT_VERIFIED"],options:[.prettyPrinted,.sortedKeys]),encoding:.utf8)!)
            exit(0)
        } catch {
            print(String(data:try! JSONSerialization.data(withJSONObject:["ok":false,"checks":checks,
                "error":error.localizedDescription,"store_error":s.error ?? "",
                "offscreen_screenshots":screenshots,"desktop_ui":"NOT_VERIFIED"],options:.prettyPrinted),encoding:.utf8)!)
            exit(1)
        }
    }
}
