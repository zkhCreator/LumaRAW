// Purpose: bounded native presentation values for portable library commands.
// Inputs: service JSON and native filter controls. Outputs: typed display values.
// Boundaries: no SQL, file operations or authoritative business validation.
import Foundation
import SwiftUI

struct LibraryCollection: Identifiable {
    let id: Int
    let name: String
    let kind: String
    let revision: Int
    let rules: [String: Any]
    let match: String
    let parentID: Int?
    var symbol: String { kind == "set" ? "folder" : kind == "smart" ? "gearshape.2" : kind == "quick" ? "circle.dashed" : "square.stack" }

    init?(_ row: [String: Any]) {
        guard let id=row["id"] as? Int, let name=row["name"] as? String else { return nil }
        self.id=id; self.name=name;parentID=row["parent_id"] as? Int
        kind=row["kind"] as? String ?? "regular"
        revision=row["revision"] as? Int ?? 0
        rules=row["rules"] as? [String: Any] ?? [:]
        match=row["match"] as? String ?? "all"
    }
}

struct CollectionPage {
    let items: [LibraryCollection]
    let offset: Int
    let total: Int
}

struct CollectionState {
    let revision: Int
    let quick: LibraryCollection
    let target: LibraryCollection
    let members: Set<Int>
    init?(_ row: [String:Any]) {
        guard let quick=LibraryCollection(row["quick"] as? [String:Any] ?? [:]),
              let target=LibraryCollection(row["target"] as? [String:Any] ?? [:]) else { return nil }
        self.quick=quick;self.target=target
        revision=row["revision"] as? Int ?? 0
        members=Set(row["members"] as? [Int] ?? [])
    }
}

enum LibraryLabels {
    static let names=["none", "red", "yellow", "green", "blue", "purple"]
    static func color(_ name: String) -> Color {
        switch name {
        case "red": return .red
        case "yellow": return .yellow
        case "green": return .green
        case "blue": return .blue
        case "purple": return .purple
        default: return .secondary
        }
    }
}

struct LibraryFilterDraft {
    var minimum = -1
    var maximum = -1
    var flag = 2
    var color = "any"
    var keyword = ""
    var keywordPresence = "any"
    var text = ""
    var camera = ""
    var folder = ""
    var virtualType = "all"
    var copyName = ""
    private var retained: [String: Any] = [:]

    init(_ rules: [String: Any] = [:]) {
        retained=rules
        if let virtual=rules["is_virtual"] as? Bool { virtualType=virtual ? "copies":"masters" }
        copyName=rules["copy_name"] as? String ?? ""
        minimum=rules["rating_min"] as? Int ?? -1
        maximum=rules["rating_max"] as? Int ?? -1
        flag=rules["flag"] as? Int ?? 2
        color=rules["color_label"] as? String ?? "any"
        keyword=rules["keyword"] as? String ?? ""
        if let present=rules["has_keywords"] as? Bool { keywordPresence=present ? "present":"absent" }
        text=rules["text"] as? String ?? ""
        camera=rules["camera"] as? String ?? ""
        folder=rules["folder"] as? String ?? ""
    }

    var rules: [String: Any] {
        var result=retained
        for key in ["rating_min", "rating_max", "flag", "color_label", "keyword", "has_keywords", "text", "camera", "folder", "is_virtual", "copy_name"] {
            result.removeValue(forKey: key)
        }
        if virtualType != "all" { result["is_virtual"]=virtualType == "copies" }
        if minimum >= 0 { result["rating_min"]=minimum }
        if maximum >= 0 { result["rating_max"]=maximum }
        if flag != 2 { result["flag"]=flag }
        if color != "any" { result["color_label"]=color }
        if keywordPresence != "any" { result["has_keywords"]=keywordPresence == "present" }
        for (key, value) in [("copy_name",copyName), ("keyword",keyword), ("text",text), ("camera",camera), ("folder",folder)] {
            let trimmed=value.trimmingCharacters(in: .whitespacesAndNewlines)
            if !trimmed.isEmpty { result[key]=trimmed }
        }
        return result
    }
}
