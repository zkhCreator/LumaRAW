// Purpose: in-process integration test for native Store and offscreen SwiftUI layout.
// Inputs: disposable catalog + explicit test original via environment. Outputs:
// JSON receipts and NSHostingView renders. Not a desktop or VoiceOver test.
import SwiftUI
import AppKit

@main struct NativeHarness {
    @MainActor static func main() async {
        _ = NSApplication.shared
        let store=Store()
        let destination=ProcessInfo.processInfo.environment["LUMARAW_TEST_OUTPUT"]!
        let fixture=ProcessInfo.processInfo.environment["LUMARAW_TEST_FIXTURE"]!
        let root=URL(fileURLWithPath:destination)
        try? FileManager.default.createDirectory(at:root,withIntermediateDirectories:true)
        var report:[String:Any]=[:]
        func check(_ condition:Bool,_ label:String)throws{report[label]=condition;if !condition{throw EngineFailure(message:label)}}
        do {
            await store.start();await store.importPaths([fixture])
            try check(store.photos.count>0,"native_import")
            guard let id=store.photos.first?.id else{throw EngineFailure(message:"No photo")}
            store.selected=id;await store.load(id)
            for _ in 0..<200{if store.preview != nil{break};try await Task.sleep(nanoseconds:100_000_000)}
            try check(store.preview != nil,"native_preview")
            store.set("exposure",0.35);store.set("highlights",-22)
            try check(await store.flushEdits(),"native_save")
            let saved=try await Backend.call("get_photo",["photo_id":id])
            try check((saved["recipe"] as? [String:Any])?["exposure"] as? Double == 0.35,"native_to_service_recipe")
            // Simulate an independent agent client at the actual JSON boundary.
            let external=try await Backend.call("edit_photo",["photo_id":id,"expected_revision":saved["revision"]!,"patch":["shadows":18]])
            for _ in 0..<80{if (store.recipe["shadows"] as? NSNumber)?.intValue==18{break};try await Task.sleep(nanoseconds:100_000_000)}
            try check((store.recipe["shadows"] as? NSNumber)?.intValue==18,"service_to_native_live_refresh")
            report["final_revision"]=external["revision"]
            store.develop=true
            let content=ContentView().environmentObject(store).frame(width:1400,height:900)
            let host=NSHostingView(rootView:content)
            let window=NSWindow(contentRect:NSRect(x:0,y:0,width:1400,height:900),styleMask:[.titled,.closable,.resizable],backing:.buffered,defer:false)
            window.contentView=host;host.frame=NSRect(x:0,y:0,width:1400,height:900)
            try await Task.sleep(nanoseconds:800_000_000)
            host.layoutSubtreeIfNeeded();host.displayIfNeeded()
            if let bitmap=host.bitmapImageRepForCachingDisplay(in:host.bounds){host.cacheDisplay(in:host.bounds,to:bitmap);if let png=bitmap.representation(using:.png,properties:[:]){try png.write(to:root.appendingPathComponent("native-develop.png"));report["offscreen_capture"]="CAPTURED_NOT_ACCEPTED: system material layers require desktop verification"}}
            store.develop=false
            try await Task.sleep(nanoseconds:500_000_000);host.layoutSubtreeIfNeeded();host.displayIfNeeded()
            if let bitmap=host.bitmapImageRepForCachingDisplay(in:host.bounds){host.cacheDisplay(in:host.bounds,to:bitmap);if let png=bitmap.representation(using:.png,properties:[:]){try png.write(to:root.appendingPathComponent("native-library.png"))}}
            report["desktop_ui"]="NOT_VERIFIED";report["voiceover"]="NOT_VERIFIED"
            report["ok"]=true
        }catch{report["ok"]=false;report["error"]=error.localizedDescription}
        let data=(try? JSONSerialization.data(withJSONObject:report,options:[.prettyPrinted,.sortedKeys])) ?? Data()
        try? data.write(to:root.appendingPathComponent("native-report.json"));print(String(data:data,encoding:.utf8) ?? "")
        exit(report["ok"] as? Bool == true ? 0:1)
    }
}
