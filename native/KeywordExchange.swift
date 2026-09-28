// Purpose: native keyword-dictionary file selection and explicit exchange actions.
// Inputs: selected UTF-8 files/new destinations and a captured vocabulary revision.
// Outputs: portable commands, refreshed tree state and concise result/error text.
// No parsing, SQL, original-file writes or implicit retry of uncertain imports.
import SwiftUI
import AppKit
import UniformTypeIdentifiers

struct KeywordExchangeActions: View {
    @EnvironmentObject var s: Store
    var body: some View {
        Button("Import Keywords…") { s.importKeywordsPanel() }
            .disabled(s.keywordBusy || s.keywordRevision < 0)
        Menu("Export Keywords") {
            Button("Include Keyword Tag Options… (.csv)") { s.exportKeywordsPanel(format:"csv") }
            Button("Exclude Keyword Tag Options… (.txt)") { s.exportKeywordsPanel(format:"text") }
        }.disabled(s.keywordBusy || s.keywordRevision < 0)
    }
}

extension Store {
    func importKeywordsPanel() {
        guard !keywordBusy,keywordRevision >= 0 else { return }
        let revision=keywordRevision
        let panel=NSOpenPanel()
        panel.canChooseDirectories=false;panel.allowsMultipleSelection=false
        panel.allowedContentTypes=[.plainText,.commaSeparatedText]
        panel.prompt="Import Keywords"
        panel.message="Add a UTF-8 keyword dictionary. Existing keywords, their options and photo assignments are preserved."
        if panel.runModal() == .OK,let path=panel.url?.path {
            Task { _=await exchangeKeywords(path:path,importing:true,revision:revision) }
        }
    }

    func exportKeywordsPanel(format: String) {
        guard !keywordBusy,keywordRevision >= 0 else { return }
        let revision=keywordRevision
        let panel=NSSavePanel()
        panel.allowedContentTypes=format == "csv" ? [.commaSeparatedText]:[.plainText]
        panel.nameFieldStringValue="LumaRAW Keywords.\(format == "csv" ? "csv":"txt")"
        panel.message=format == "csv" ? "Save the hierarchy, synonyms and keyword options to a new file.":"Save hierarchy, synonyms and Include on Export. CSV also preserves the other keyword options. Choose a new filename."
        if panel.runModal() == .OK,let path=panel.url?.path {
            Task { _=await exchangeKeywords(path:path,importing:false,format:format,revision:revision) }
        }
    }

    @discardableResult
    func exchangeKeywords(path: String, importing: Bool, format: String="text", revision: Int) async -> Bool {
        guard !keywordBusy else { return false }
        keywordBusy=true;defer { keywordBusy=false }
        message=importing ? "Importing keyword dictionary…":"Exporting keyword dictionary…"
        var params: [String:Any]=["path":path,"expected_revision":revision]
        if !importing { params["format"]=format }
        do {
            let result=try await Backend.call(importing ? "import_keywords":"export_keywords",params)
            if importing {
                await refreshKeywords(reset:true)
                message="Imported \(result["created"] as? Int ?? 0) new keywords; preserved \(result["existing"] as? Int ?? 0) existing keywords"
            } else {
                message="Exported \(result["keywords"] as? Int ?? 0) keywords and \(result["synonyms"] as? Int ?? 0) synonyms"
                if let omitted=result["omitted_options"] as? Int,omitted > 0 {
                    message+=". Use CSV to retain all options for \(omitted) keywords."
                }
            }
            return true
        } catch {
            message="";self.error=error.localizedDescription
            await refreshKeywords()
            return false
        }
    }
}
