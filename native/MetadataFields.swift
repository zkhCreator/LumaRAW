// Purpose: service-defined metadata field forms and explicit partial selections.
// Inputs: field descriptors and local drafts. Outputs: checked values only.
// Arrays use one value per line, preserving commas inside creator names. No SQL,
// XMP mapping, vocabulary resolution or source EXIF/date interpretation lives here.
import SwiftUI

struct MetadataField: Identifiable {
    let key: String
    let label: String
    let group: String
    let kind: String
    var id: String { key }
    init?(_ row: [String:Any],prefix: String="") {
        guard let key=row["key"] as? String,let label=row["label"] as? String,
              let group=row["group"] as? String,let kind=row["kind"] as? String else { return nil }
        self.key=prefix+key;self.label=label;self.group=group;self.kind=kind
    }
    func filled(_ value: Any?) -> Bool {
        switch kind {
        case "array","keywords": return (value as? [String])?.isEmpty == false
        case "rating": return (value as? Int ?? 0)>0
        case "label": return (value as? String ?? "none") != "none"
        case "status": return (value as? String ?? "unknown") != "unknown"
        default: return !(value as? String ?? "").trimmingCharacters(in:.whitespacesAndNewlines).isEmpty
        }
    }
}

enum MetadataDraft {
    static func flatten(_ patch: [String:Any]) -> [String:Any] {
        var result=patch.filter { $0.key != "iptc" }
        for (key,value) in patch["iptc"] as? [String:Any] ?? [:] { result["iptc."+key]=value }
        return result
    }
    static func patch(values: [String:Any],selected: Set<String>,fields: [MetadataField]) -> [String:Any] {
        var result: [String:Any]=[:],iptc: [String:Any]=[:]
        for field in fields where selected.contains(field.key) {
            let fallback: Any=["array","keywords"].contains(field.kind) ? [String]():
                field.kind == "rating" ? 0:field.kind == "label" ? "none":field.kind == "status" ? "unknown":""
            let value=values[field.key] ?? fallback
            if field.key.hasPrefix("iptc.") { iptc[String(field.key.dropFirst(5))]=value }
            else { result[field.key]=value }
        }
        if !iptc.isEmpty { result["iptc"]=iptc }
        return result
    }
    static func display(_ value: Any) -> String {
        if let values=value as? [String] { return values.joined(separator:"\n") }
        return String(describing:value)
    }
}

struct MetadataFieldsEditor: View {
    let fields: [MetadataField]
    @Binding var values: [String:Any]
    @Binding var selected: Set<String>
    // Preserve a trailing newline while typing; normalized arrays are output only.
    @State private var arrayText: [String:String]=[:]
    var body: some View {
        VStack(alignment:.leading,spacing:12) {
            HStack {
                Button("Check All") { selected.formUnion(fields.map(\.key)) }
                Button("Check None") { selected.subtract(fields.map(\.key)) }
                Button("Check Filled") {
                    selected.subtract(fields.map(\.key))
                    selected.formUnion(fields.filter { $0.filled(values[$0.key]) }.map(\.key))
                }
            }
            ForEach(Array(Set(fields.map(\.group))).sorted(),id:\.self) { group in
                DisclosureGroup(group) {
                    VStack(alignment:.leading,spacing:10) {
                        ForEach(fields.filter { $0.group == group }) { field in
                            VStack(alignment:.leading,spacing:5) {
                                Toggle("Apply \(field.label)",isOn:Binding(get:{selected.contains(field.key)},set:{value in
                                    if value {selected.insert(field.key)} else {selected.remove(field.key)}
                                }))
                                control(field).disabled(!selected.contains(field.key))
                            }
                        }
                    }.padding(.leading,12).padding(.vertical,8)
                }
            }
        }
    }
    @ViewBuilder func control(_ field: MetadataField) -> some View {
        if field.kind == "rating" {
            Picker(field.label,selection:Binding(get:{values[field.key] as? Int ?? 0},set:{values[field.key]=$0})) {
                Text("Unrated").tag(0)
                ForEach(1...5,id:\.self) { Text("\($0) stars").tag($0) }
            }
        } else if field.kind == "label" {
            Picker(field.label,selection:text(field.key,default:"none")) {
                ForEach(LibraryLabels.names,id:\.self) { Text($0.capitalized).tag($0) }
            }
        } else if field.kind == "status" {
            Picker(field.label,selection:text(field.key,default:"unknown")) {
                Text("Unknown").tag("unknown");Text("Copyrighted").tag("copyrighted");Text("Public Domain").tag("public_domain")
            }
        } else if ["array","keywords"].contains(field.kind) {
            TextField(field.label,text:Binding(get:{arrayText[field.key] ?? (values[field.key] as? [String] ?? []).joined(separator:"\n")},set:{value in
                arrayText[field.key]=value
                values[field.key]=value.components(separatedBy:"\n").filter { !$0.trimmingCharacters(in:.whitespaces).isEmpty }
            }),axis:.vertical).lineLimit(2...5).textFieldStyle(.roundedBorder)
            Text(field.kind == "keywords" ? "One keyword path per line. Parent | Child creates a hierarchy. Existing keywords are preserved.":"One value per line.").font(.caption).foregroundStyle(.secondary)
        } else {
            TextField(field.label,text:text(field.key),axis:.vertical).lineLimit(field.kind == "multiline" ? 2...5:1...2).textFieldStyle(.roundedBorder)
            if field.kind == "date" { Text("ISO 8601 date or date/time. This does not change source capture time.").font(.caption).foregroundStyle(.secondary) }
        }
    }
    func text(_ key: String,default fallback: String="") -> Binding<String> {
        Binding(get:{values[key] as? String ?? fallback},set:{values[key]=$0})
    }
}

struct IPTCValuesView: View {
    let values: [String:Any]
    var body: some View {
        ForEach(values.keys.sorted(),id:\.self) { key in
            VStack(alignment:.leading,spacing:3) {
                Text(key.replacingOccurrences(of:"_",with:" ").capitalized).font(.caption).foregroundStyle(.secondary)
                Text(MetadataDraft.display(values[key]!).isEmpty ? "(empty)":MetadataDraft.display(values[key]!)).textSelection(.enabled)
            }
        }
    }
}
