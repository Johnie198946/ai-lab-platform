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

    func testWikiLinkParserSupportsObsidianTargetsAliasesAnchorsAndEmbeds() throws {
        let source = """
        [[产品说明]] [[产品说明|查看详情]] [[产品说明#核心结论]]
        [[产品说明#^decision-1]] [[#当前标题]] ![[架构图]]
        """
        let links = WikiLinkParser.parse(source)

        XCTAssertEqual(links.count, 6)
        XCTAssertEqual(links[0].target, "产品说明")
        XCTAssertEqual(links[1].displayText, "查看详情")
        XCTAssertEqual(links[2].anchor, .heading("核心结论"))
        XCTAssertEqual(links[3].anchor, .block("decision-1"))
        XCTAssertEqual(links[4].target, "")
        XCTAssertEqual(links[4].anchor, .heading("当前标题"))
        XCTAssertTrue(links[5].isEmbed)
    }

    func testWikiLinkParserIgnoresFrontmatterCodeCommentsAndMalformedTriples() {
        let source = """
        ---
        related: [[元数据链接]]
        ---
        正常 [[有效笔记]]
        `[[行内代码]]`
        ```swift
        let sample = "[[代码块]]"
        ```
        %% [[隐藏评论]] %%
        [[[错误占位]]]
        """

        XCTAssertEqual(WikiLinkParser.parse(source).map(\.target), ["有效笔记"])
    }

    func testRenamePreservesAliasAndAnchorAndQueuesEveryChangedNoteForSync() throws {
        let store = KnowledgeNoteStore.shared
        store.activate(tenantKey: "rename-tenant-\(UUID())", userId: "rename-user")
        let target = try XCTUnwrap(store.createNote(title: "旧标题"))
        let linker = try XCTUnwrap(store.createNote(
            title: "引用者",
            body: "参考 [[旧标题#核心结论|阅读原文]]"
        ))
        store.markSynced(noteID: target.id)
        store.markSynced(noteID: linker.id)
        defer {
            store.moveToTrash(id: target.id)
            store.moveToTrash(id: linker.id)
        }

        _ = try XCTUnwrap(store.save(
            id: target.id,
            title: "新标题",
            body: target.body,
            tags: target.tags,
            isPinned: target.isPinned
        ))

        XCTAssertEqual(store.note(id: linker.id)?.body, "参考 [[新标题#核心结论|阅读原文]]")
        XCTAssertEqual(Set(store.pendingSyncNotes().map(\.id)), Set([target.id, linker.id]))
        XCTAssertEqual(store.backlinkReferences(to: try XCTUnwrap(store.note(id: target.id))).first?.sourceNote.id, linker.id)
    }

    func testWikiLinkParserHandlesLargeVaultPayloadWithinBudget() {
        let source = (0..<1_000).map { index in
            "## Note \(index)\n\nSee [[Entity \(index)|detail]] and [[Entity \(index)#Overview]] ![[Attachment \(index)]]"
        }.joined(separator: "\n\n")
        let start = Date()
        let links = WikiLinkParser.parse(source)
        let elapsed = Date().timeIntervalSince(start)

        XCTAssertEqual(links.count, 3_000)
        XCTAssertLessThan(elapsed, 3.0, "WikiLink parsing regressed for a 1,000-note equivalent payload")
    }
}
