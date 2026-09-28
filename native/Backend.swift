// Purpose: asynchronous JSON client for the packaged portable engine.
// Input: domain command + JSON parameters. Output: JSON result or typed failure.
// Boundaries: no pixel processing, SQL, credentials, network or shell evaluation.
import Foundation
import AppKit

struct EngineFailure: LocalizedError {
    let message: String
    var canActivateService=false
    var errorDescription: String? { message }
}
struct Backend {
    static var catalog: String {
        if let i=CommandLine.arguments.firstIndex(of:"--catalog"),CommandLine.arguments.count>i+1{return CommandLine.arguments[i+1]}
        return ProcessInfo.processInfo.environment["LUMARAW_CATALOG"] ??
        FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Library/Application Support/LumaRAW Native").path
    }
    static var executable: String {
        ProcessInfo.processInfo.environment["LUMARAW_ENGINE"] ??
        Bundle.main.resourceURL!.appendingPathComponent("Engine/LumaRAWEngine").path
    }
    static func call(_ method: String, _ params: [String: Any] = [:]) async throws -> [String: Any] {
        let payload = try JSONSerialization.data(withJSONObject: params)
        return try await withCheckedThrowingContinuation { continuation in
            DispatchQueue.global(qos: .userInitiated).async {
                do {
                    let process = Process()
                    process.executableURL = URL(fileURLWithPath: executable)
                    process.arguments = ["--catalog", catalog, method]
                    let input = Pipe(), output = Pipe()
                    process.standardInput = input; process.standardOutput = output
                    process.standardError = FileHandle.nullDevice
                    try process.run()
                    if method != "status" && method != "recipe_schema" {
                        try input.fileHandleForWriting.write(contentsOf: payload + Data([10]))
                    }
                    try input.fileHandleForWriting.close()
                    let data = output.fileHandleForReading.readDataToEndOfFile()
                    process.waitUntilExit()
                    guard let envelope = try JSONSerialization.jsonObject(with: data) as? [String: Any] else {
                        throw EngineFailure(message: "The service returned an invalid response")
                    }
                    guard envelope["ok"] as? Bool == true, let result = envelope["result"] as? [String: Any] else {
                        throw EngineFailure(message: envelope["error"] as? String ?? "The service request failed",
                                            canActivateService:envelope["can_activate"] as? Bool ?? false)
                    }
                    continuation.resume(returning: result)
                } catch { continuation.resume(throwing: error) }
            }
        }
    }
}

struct Photo: Identifiable {
    let id: Int
    var name: String
    var path: String
    var revision: Int
    var rating: Int
    var flag: Int
    var title: String
    var caption: String
    var copyright: String
    var colorLabel: String
    var keywords: [String]
    var keywordIDs: [Int]
    var keywordCount: Int
    var keywordsDeferred: Bool
    var sourceID: Int
    var sourceRevision: Int
    var masterID: Int
    var isVirtual: Bool
    var copyName: String
    var displayName: String { copyName.isEmpty ? name : "\(name) · \(copyName)" }
    var metadataRevision: Int
    var recipe: [String: Any]
    var metadata: [String: Any]
    init?(_ row: [String: Any]) {
        guard let id = row["id"] as? Int else { return nil }
        self.id=id; name=row["name"] as? String ?? "Photo"; path=row["path"] as? String ?? ""
        revision=row["revision"] as? Int ?? 0; rating=row["rating"] as? Int ?? 0; flag=row["flag"] as? Int ?? 0
        title=row["title"] as? String ?? ""; caption=row["caption"] as? String ?? ""
        copyright=row["copyright"] as? String ?? ""; colorLabel=row["color_label"] as? String ?? "none"
        keywords=row["keywords"] as? [String] ?? []; metadataRevision=row["metadata_revision"] as? Int ?? 0
        keywordIDs=row["keyword_ids"] as? [Int] ?? []
        keywordCount=row["keyword_count"] as? Int ?? keywords.count
        keywordsDeferred=row["keywords_deferred"] as? Bool ?? false
        sourceID=row["source_id"] as? Int ?? id; sourceRevision=row["source_revision"] as? Int ?? 0
        masterID=row["master_id"] as? Int ?? id;isVirtual=(row["is_virtual"] as? Int ?? 0) == 1
        copyName=row["copy_name"] as? String ?? ""
        recipe=row["recipe"] as? [String: Any] ?? [:]; metadata=row["metadata"] as? [String: Any] ?? [:]
    }

    mutating func adoptLibraryPatch(_ patch: [String: Any], revision: Int) {
        if let value=patch["copy_name"] as? String { copyName=value }
        if let value=patch["title"] as? String { title=value }
        if let value=patch["caption"] as? String { caption=value }
        if let value=patch["copyright"] as? String { copyright=value }
        if let value=patch["color_label"] as? String { colorLabel=value }
        if let value=patch["keywords"] as? [String] { keywords=value }
        if let value=patch["keyword_ids"] as? [Int] { keywordIDs=value }
        if let value=patch["keyword_count"] as? Int { keywordCount=value }
        if let value=patch["keywords_deferred"] as? Bool { keywordsDeferred=value }
        metadataRevision=revision
    }
}
