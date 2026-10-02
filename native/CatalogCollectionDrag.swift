// Purpose: carry a captured collection identity across a native drag gesture.
// Inputs: the current Store session, collection ID and source revision.
// Outputs: a small Codable drag payload suitable for same-process transfer.
// Boundaries: no mutable collection metadata or parent information is trusted;
// drop handling resolves the authoritative row before saving a new parent.
import Foundation
import SwiftUI
import UniformTypeIdentifiers

struct CatalogCollectionDrag: Codable, Transferable, Equatable {
    let session: String
    let collectionID: Int
    let revision: Int

    init(session: String, collectionID: Int, revision: Int) {
        self.session = session
        self.collectionID = collectionID
        self.revision = revision
    }

    func isValid(session expectedSession: String) -> Bool {
        session == expectedSession && collectionID > 0 && revision >= 0
    }

    static var transferRepresentation: some TransferRepresentation {
        CodableRepresentation(contentType: UTType(
            exportedAs: "local.lumaraw.catalog-collection-node",
            conformingTo: .data
        ))
    }
}
