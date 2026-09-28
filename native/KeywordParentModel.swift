// Purpose: bounded parent-keyword navigation and complete, captured selection.
// Inputs: the editor's vocabulary revision and explicit browse/select actions.
// Outputs: one 60-row page, full selected paths and visible stale-read failures.
// No catalog writes. Generation checks discard superseded or dismissed requests.
import Foundation
import Combine

struct KeywordParentChoice {
    let id: Int?
    let path: String
}

@MainActor final class KeywordParentModel: ObservableObject {
    let revision: Int
    @Published private(set) var parents: [LibraryKeyword]=[]
    @Published private(set) var items: [LibraryKeyword]=[]
    @Published private(set) var offset=0
    @Published private(set) var total=0
    @Published private(set) var loading=false
    @Published private(set) var error: String?
    private var generation=0

    init(revision: Int) { self.revision=revision }

    private func begin() -> Int {
        generation+=1;loading=true;error=nil
        return generation
    }

    func cancel() { generation+=1;loading=false }

    private func page(parent: Int?, offset: Int) async throws -> KeywordPage {
        var params: [String:Any]=["offset":offset]
        if let parent { params["parent_id"]=parent }
        let result=try await Backend.call("list_keywords",params)
        guard result["keyword_revision"] as? Int == revision else {
            throw EngineFailure(message:"Keyword list changed; reopen the editor before choosing a parent")
        }
        return KeywordPage(items:(result["keywords"] as? [[String:Any]] ?? []).compactMap {
            LibraryKeyword($0,revision:revision,selection:[])
        },offset:result["offset"] as? Int ?? 0,total:result["total"] as? Int ?? 0)
    }

    private func adopt(_ page: KeywordPage) {
        items=page.items;offset=page.offset;total=page.total
    }

    func load(offset: Int=0) async {
        let token=begin(),parent=parents.last?.id
        defer { if token == generation { loading=false } }
        do {
            let value=try await page(parent:parent,offset:offset)
            guard token == generation else { return }
            adopt(value)
        } catch { if token == generation { self.error=error.localizedDescription } }
    }

    func browse(_ keyword: LibraryKeyword) async {
        let token=begin()
        defer { if token == generation { loading=false } }
        do {
            let full=try await keyword.complete()
            guard token == generation else { return }
            let value=try await page(parent:full.id,offset:0)
            guard token == generation else { return }
            parents.append(full);adopt(value)
        } catch { if token == generation { self.error=error.localizedDescription } }
    }

    func up() async {
        guard !parents.isEmpty else { return }
        let token=begin(),next=Array(parents.dropLast())
        defer { if token == generation { loading=false } }
        do {
            let value=try await page(parent:next.last?.id,offset:0)
            guard token == generation else { return }
            parents=next;adopt(value)
        } catch { if token == generation { self.error=error.localizedDescription } }
    }

    func choose(_ keyword: LibraryKeyword?) async -> KeywordParentChoice? {
        let token=begin()
        defer { if token == generation { loading=false } }
        do {
            guard let keyword else { return KeywordParentChoice(id:nil,path:"None") }
            guard keyword.revision == revision else {
                throw EngineFailure(message:"Keyword list changed; reopen the editor before choosing a parent")
            }
            let full=try await keyword.complete()
            guard token == generation else { return nil }
            return KeywordParentChoice(id:full.id,path:full.path)
        } catch {
            if token == generation { self.error=error.localizedDescription }
            return nil
        }
    }
}
