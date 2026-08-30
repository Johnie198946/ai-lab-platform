import XCTest
@testable import AIPlatformApp

@MainActor
final class KnowledgeNoteStoreTests: XCTestCase {
    func testArchiveExcludesNoteFromActiveSearchAndCanRestore() throws {
        let store = KnowledgeNoteStore.shared
        store.activate(tenantKey: "archive-tenant-\(UUID())", userId: "archive-user")
        let note = try XCTUnwrap(store.createNote(title: "待合并", body: "超聚变内容"))
        let archived = try XCTUnwrap(store.archive(id: note.id, mergedInto: "merged-id"))
        XCTAssertNil(store.note(id: note.id))
        XCTAssertTrue(store.search("超聚变").isEmpty)
        XCTAssertEqual(store.archivedNotes.first(where: { $0.id == note.id })?.id, archived.id)
        XCTAssertNotNil(store.restoreArchivedNote(id: note.id))
        XCTAssertEqual(store.note(id: note.id)?.body, "超聚变内容")
        store.moveToTrash(id: note.id)
    }

    func testNotesAreIsolatedByTenantAndUser() throws {
        let store = KnowledgeNoteStore.shared
        let tenantA = "tenant-a-\(UUID().uuidString)"
        let tenantB = "tenant-b-\(UUID().uuidString)"
        let user = "same-user"
        store.activate(tenantKey: tenantA, userId: user)
        let note = try XCTUnwrap(store.createNote(title: "租户隔离", body: "只属于 A"))
        store.activate(tenantKey: tenantB, userId: user)
        XCTAssertNil(store.note(id: note.id))
        store.activate(tenantKey: tenantA, userId: user)
        XCTAssertEqual(store.note(id: note.id)?.body, "只属于 A")
        store.moveToTrash(id: note.id)
    }

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

    func testReloadAndIndexedSearchScaleToOneThousandNotes() throws {
        let store = KnowledgeNoteStore.shared
        let tenantKey = "scale-tenant-\(UUID())"
        let userId = "scale-user"
        store.activate(tenantKey: tenantKey, userId: userId)
        let fm = FileManager.default
        let root = store.vaultDirectory
        for index in 0..<1_000 {
            let url = root.appendingPathComponent("scale-\(index).md")
            try "---\ntitle: Scale \(index)\ntags:\n  - scale\n---\n\n内容 \(index) [[Scale 0]]".write(to: url, atomically: true, encoding: .utf8)
        }
        defer {
            try? fm.removeItem(at: root)
            store.reload()
        }
        measure {
            store.activate(tenantKey: tenantKey, userId: userId)
            store.reload()
            _ = store.search("内容 999")
            if let first = store.notes.first { _ = store.backlinks(to: first) }
        }
        // The host app may publish an account lifecycle notification while the
        // performance block runs. Reassert the test account before verification.
        store.activate(tenantKey: tenantKey, userId: userId)
        store.reload()
        XCTAssertEqual(store.notes.count, 1_000)
    }
}
