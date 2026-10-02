// Purpose: encode a bounded, same-session photo drag for native catalog workflows.
// Inputs: a stable session token, an anchor photo ID and optionally captured photo IDs.
// Outputs: a Codable transfer payload that remains valid across asynchronous UI work.
// Boundaries: this file defines identity and payload validation only; it does not
// decide which photos a view captures or what a Reference/collection drop does.
import Foundation
import SwiftUI
import UniformTypeIdentifiers

struct CatalogPhotoDrag: Codable, Transferable, Equatable {
    let session: String
    let photoID: Int
    let photoIDs: [Int]?

    init(session: String, photoID: Int) {
        self.session = session
        self.photoID = photoID
        photoIDs = nil
    }

    init(session: String, photoID: Int, photoIDs: [Int]) {
        self.session = session
        self.photoID = photoID
        self.photoIDs = photoIDs
    }

    var resolvedPhotoIDs: [Int] { photoIDs ?? [photoID] }

    func isValid(session expectedSession: String, visiblePhotoIDs: Set<Int>) -> Bool {
        let ids = resolvedPhotoIDs
        guard session == expectedSession, photoID > 0,
              !ids.isEmpty, ids.count <= 60, ids.allSatisfy({ $0 > 0 }),
              Set(ids).count == ids.count, ids.contains(photoID) else { return false }
        return ids.allSatisfy(visiblePhotoIDs.contains)
    }

    static var transferRepresentation: some TransferRepresentation {
        CodableRepresentation(contentType: UTType(exportedAs: "local.lumaraw.catalog-photo", conformingTo: .data))
    }
}
