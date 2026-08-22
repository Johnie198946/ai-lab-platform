import XCTest
@testable import AIPlatformApp

@MainActor
final class KnowledgeNoteStoreTests: XCTestCase {
    func testCreateNoteWritesObsidianCompatibleMarkdown() throws {
        let store = KnowledgeNoteStore.shared
        let title = "双链测试-\(UUID().uuidString.prefix(8))"
        let note = try XCTUnwrap(store.createNote(
            title: title,
            body: "连接 [[欢迎使用知识笔记|开始]] #测试/双链",
            tags: ["spec"]
        ))
        defer { store.moveToTrash(id: note.id) }

        XCTAssertEqual(note.outgoingLinks, ["欢迎使用知识笔记"])
        XCTAssertTrue(note.tags.contains("测试/双链"))

        let markdown = try String(contentsOf: note.fileURL, encoding: .utf8)
        XCTAssertTrue(markdown.hasPrefix("---\n"))
        XCTAssertTrue(markdown.contains("title: \"\(title)\""))
        XCTAssertTrue(markdown.contains("tags:\n"))
        XCTAssertTrue(markdown.contains("[[欢迎使用知识笔记|开始]]"))
    }

    func testRenamingNoteUpdatesIncomingWikiLinks() throws {
        let store = KnowledgeNoteStore.shared
        let suffix = UUID().uuidString.prefix(8)
        let originalTitle = "原始页面-\(suffix)"
        let renamedTitle = "重命名页面-\(suffix)"
        let source = try XCTUnwrap(store.createNote(title: originalTitle))
        let linker = try XCTUnwrap(store.createNote(
            title: "引用页面-\(suffix)",
            body: "参见 [[\(originalTitle)|详情]]"
        ))
        defer {
            store.moveToTrash(id: source.id)
            store.moveToTrash(id: linker.id)
        }

        _ = try XCTUnwrap(store.save(
            id: source.id,
            title: renamedTitle,
            body: source.body,
            tags: source.tags,
            isPinned: source.isPinned
        ))

        let updatedLinker = try XCTUnwrap(store.note(id: linker.id))
        XCTAssertTrue(updatedLinker.body.contains("[[\(renamedTitle)|详情]]"))
        XCTAssertEqual(store.backlinks(to: try XCTUnwrap(store.note(id: source.id))).map(\.id), [linker.id])
    }
}
