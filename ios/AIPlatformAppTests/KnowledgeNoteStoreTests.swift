import CryptoKit
import Security
import XCTest

final class SignedKeychainAcceptanceTests: XCTestCase {
    func testSecureCredentialRoundTripInSignedHost() throws {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: "com.ailab.acceptance.\(UUID())",
            kSecAttrAccount as String: "noncredential-probe"
        ]
        defer { SecItemDelete(query as CFDictionary) }
        let expected = Data("keychain-acceptance-not-a-token".utf8)
        var add = query
        add[kSecValueData as String] = expected
        add[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
        XCTAssertEqual(SecItemAdd(add as CFDictionary, nil), errSecSuccess,
                       "Real login acceptance requires a signed test host with Keychain entitlements")
        var read = query
        read[kSecReturnData as String] = true
        var value: AnyObject?
        XCTAssertEqual(SecItemCopyMatching(read as CFDictionary, &value), errSecSuccess)
        XCTAssertEqual(value as? Data, expected)
        XCTAssertEqual(SecItemDelete(query as CFDictionary), errSecSuccess)
        XCTAssertEqual(SecItemCopyMatching(read as CFDictionary, &value), errSecItemNotFound)
    }
}
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

    func testMultiTagSearchUsesLogicalAnd() throws {
        let store = KnowledgeNoteStore.shared
        store.activate(tenantKey: "tag-tenant-\(UUID())", userId: "tag-user")
        let both = try XCTUnwrap(store.createNote(title: "双标签", tags: ["旅行", "日本"]))
        let one = try XCTUnwrap(store.createNote(title: "单标签", tags: ["旅行"]))
        defer { store.moveToTrash(id: both.id); store.moveToTrash(id: one.id) }

        XCTAssertEqual(store.search("", tags: ["旅行", "日本"]).map(\.id), [both.id])
        XCTAssertEqual(Set(store.search("", tags: ["旅行"]).map(\.id)), Set([both.id, one.id]))
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

    func testKnowledgeMergePrimaryRequiresExplicitTarget() {
        let explicit = KnowledgeActionStep(
            kind: "merge_notes",
            targetNoteId: "note-z",
            sourceNoteIds: ["note-a", "note-z"],
            markdown: "# merged"
        )
        XCTAssertEqual(KnowledgeActionExecutor.mergePrimaryNoteID(step: explicit), "note-z")
        XCTAssertEqual(
            KnowledgeActionExecutor.mergeArchiveSourceIDs(step: explicit, primaryID: "note-z"),
            ["note-a"]
        )
        XCTAssertNil(KnowledgeActionExecutor.mergePrimaryNoteID(step: .init(
            kind: "merge_notes", sourceNoteIds: ["note-a"], markdown: "# merged"
        )))
        XCTAssertNil(KnowledgeActionExecutor.mergePrimaryNoteID(step: .init(
            kind: "merge_notes", targetNoteId: " note-z ", markdown: "# merged"
        )))
    }

    func testLegacyDraftMergeNeverArchivesUpdatedPrimaryOrDuplicates() {
        let candidates = [
            NoteMergeCandidate(id: "source-a", title: "来源 A", snippet: ""),
            NoteMergeCandidate(id: "target", title: "目标", snippet: ""),
            NoteMergeCandidate(id: "source-a", title: "来源 A 重复", snippet: ""),
            NoteMergeCandidate(id: "source-b", title: "来源 B", snippet: "")
        ]

        XCTAssertEqual(
            TenantSessionCoordinator.mergeArchiveCandidateIDs(candidates, primaryNoteID: "target"),
            ["source-a", "source-b"]
        )

        let draft = NoteDraftBlock(
            id: "draft", title: "九州旅行纲要", markdown: "# 九州旅行纲要\n\n完整正文",
            tags: ["九州"], sourceSessionId: nil, sourceMessageIds: [],
            mergeCandidates: candidates, mergedTitle: "九州旅行纲要",
            mergedMarkdown: "（以上为合并后的完整笔记）", mergedTags: ["九州", "交通"],
            operation: "update", targetNoteId: "target", targetNoteTitle: "九州旅行纲要",
            targetContentHash: String(repeating: "a", count: 64)
        )
        let resolved = TenantSessionCoordinator.resolveLegacyNoteDraft(draft, shouldMerge: true)
        XCTAssertEqual(resolved.markdown, draft.markdown)
        XCTAssertEqual(resolved.tags, ["九州", "交通"])
    }

    func testExplicitTargetOnlyMergeUpdatesInPlaceAndPreservesMetadata() async throws {
        let (store, executor) = isolatedStoreAndExecutor()
        defer { removeVault(store) }
        let target = try XCTUnwrap(store.createNote(
            id: "target-only", title: "原标题", body: "旧正文", tags: ["原标签"]
        ))
        store.togglePin(id: target.id)
        let before = try XCTUnwrap(store.note(id: target.id))
        let action = mergeAction(step: .init(
            kind: "merge_notes", targetNoteId: target.id, title: "新标题",
            markdown: "# 新标题\n\n合并草稿", originalContentHash: store.contentHash(for: before)
        ))

        let result = await executor.execute(action)
        let merged = try XCTUnwrap(store.note(id: target.id))
        XCTAssertTrue([KnowledgeActionState.synced, .syncPending].contains(result.state))
        XCTAssertEqual(result.noteIds, [target.id])
        XCTAssertEqual(merged.body, "# 新标题\n\n合并草稿")
        XCTAssertEqual(merged.createdAt, before.createdAt)
        XCTAssertEqual(merged.tags, before.tags)
        XCTAssertEqual(merged.isPinned, before.isPinned)
        XCTAssertEqual(Set(store.notes.map(\.id) + store.archivedNotes.map(\.id)), [target.id])
        XCTAssertFalse(store.notes.contains { $0.id.hasPrefix("ka-") })
    }

    func testExplicitTargetAndSourceMergeNeverCreatesReplacementID() async throws {
        let (store, executor) = isolatedStoreAndExecutor()
        defer { removeVault(store) }
        let target = try XCTUnwrap(store.createNote(id: "merge-target", title: "目标", body: "旧稿"))
        let source = try XCTUnwrap(store.createNote(id: "merge-source", title: "来源", body: "材料"))
        let originalIDs = Set(store.notes.map(\.id))
        let action = mergeAction(step: .init(
            kind: "merge_notes", targetNoteId: target.id, sourceNoteIds: [source.id],
            markdown: "合并完成", originalContentHash: store.contentHash(for: target),
            sourceContentHashes: [source.id: store.contentHash(for: source)]
        ))

        let result = await executor.execute(action)
        XCTAssertTrue([KnowledgeActionState.synced, .syncPending].contains(result.state))
        XCTAssertEqual(Set(result.noteIds), originalIDs)
        XCTAssertEqual(store.note(id: target.id)?.body, "合并完成")
        XCTAssertEqual(Set(store.notes.map(\.id) + store.archivedNotes.map(\.id)), originalIDs)
        XCTAssertFalse((store.notes + store.archivedNotes).contains { $0.id.hasPrefix("ka-") })
    }

    func testExecutorUsesAtomicMergeContractWithExactVersions() async throws {
        let store = KnowledgeNoteStore()
        store.activate(tenantKey: "merge-contract-\(UUID())", userId: "merge-user")
        defer { removeVault(store) }
        let synchronizer = FakeKnowledgeActionSynchronizer()
        let executor = KnowledgeActionExecutor(store: store, synchronizer: synchronizer)
        let target = try XCTUnwrap(store.createNote(id: "contract-target", title: "目标", body: "旧稿"))
        let source = try XCTUnwrap(store.createNote(id: "contract-source", title: "来源", body: "材料"))
        let targetHash = store.contentHash(for: target)
        let sourceHash = store.contentHash(for: source)
        let action = mergeAction(step: .init(
            kind: "merge_notes", targetNoteId: target.id, sourceNoteIds: [source.id],
            markdown: "合并完成", originalContentHash: targetHash,
            sourceContentHashes: [source.id: sourceHash]
        ))

        let result = await executor.execute(action)

        XCTAssertEqual(result.state, .synced)
        XCTAssertEqual(synchronizer.mergeRequests.count, 1)
        let request = try XCTUnwrap(synchronizer.mergeRequests.first)
        XCTAssertEqual(request.operationId, action.id)
        XCTAssertEqual(request.targetNoteId, target.id)
        XCTAssertEqual(request.targetBaseHash, targetHash)
        XCTAssertEqual(request.sourceVersions, [source.id: sourceHash])
        XCTAssertEqual(request.revisedContent, store.markdown(for: try XCTUnwrap(store.note(id: target.id))))
        XCTAssertEqual(synchronizer.legacyMergeMutationCount, 0)
    }

    func testMergeRejectsMissingMalformedHashesAndSourceOnlyLegacyRequestsBeforeMutation() async throws {
        let (store, executor) = isolatedStoreAndExecutor()
        defer { removeVault(store) }
        let target = try XCTUnwrap(store.createNote(id: "hash-target", title: "目标", body: "原文"))
        let source = try XCTUnwrap(store.createNote(id: "hash-source", title: "来源", body: "材料"))
        let targetHash = store.contentHash(for: target)
        let invalidSteps: [KnowledgeActionStep] = [
            .init(kind: "merge_notes", sourceNoteIds: [source.id], markdown: "拒绝"),
            .init(kind: "merge_notes", targetNoteId: target.id, markdown: "拒绝"),
            .init(kind: "merge_notes", targetNoteId: target.id, markdown: "拒绝", originalContentHash: String(repeating: "A", count: 64)),
            .init(kind: "merge_notes", targetNoteId: target.id, sourceNoteIds: [source.id], markdown: "拒绝", originalContentHash: targetHash),
            .init(kind: "merge_notes", targetNoteId: target.id, sourceNoteIds: [source.id], markdown: "拒绝", originalContentHash: targetHash, sourceContentHashes: [source.id: "bad-hash"]),
        ]

        for step in invalidSteps {
            let result = await executor.execute(mergeAction(step: step))
            XCTAssertEqual(result.state, .stale)
            XCTAssertEqual(store.note(id: target.id)?.body, "原文")
            XCTAssertEqual(store.note(id: source.id)?.body, "材料")
            XCTAssertEqual(Set(store.notes.map(\.id)), [target.id, source.id])
        }
    }

    func testMergeRejectsMissingOrArchivedTargetBeforeMutation() async throws {
        let (store, executor) = isolatedStoreAndExecutor()
        defer { removeVault(store) }
        let target = try XCTUnwrap(store.createNote(id: "archived-target", title: "目标", body: "原文"))
        let hash = store.contentHash(for: target)
        _ = try XCTUnwrap(store.archive(id: target.id, mergedInto: "prior-target"))

        for targetID in [target.id, "missing-target"] {
            let result = await executor.execute(mergeAction(step: .init(
                kind: "merge_notes", targetNoteId: targetID, markdown: "拒绝",
                originalContentHash: hash
            )))
            XCTAssertEqual(result.state, .stale)
        }
        XCTAssertNil(store.note(id: target.id))
        XCTAssertEqual(store.archivedNote(id: target.id)?.body, "原文")
    }

    func testMergeRejectsChangedTargetAndSourceVersionsBeforeMutation() async throws {
        let (store, executor) = isolatedStoreAndExecutor()
        defer { removeVault(store) }
        let target = try XCTUnwrap(store.createNote(id: "changed-target", title: "目标", body: "目标 v1"))
        let source = try XCTUnwrap(store.createNote(id: "changed-source", title: "来源", body: "来源 v1"))
        let originalTargetHash = store.contentHash(for: target)
        let originalSourceHash = store.contentHash(for: source)
        _ = try XCTUnwrap(store.save(id: target.id, title: target.title, body: "目标 v2", tags: target.tags, isPinned: target.isPinned))
        var result = await executor.execute(mergeAction(step: .init(
            kind: "merge_notes", targetNoteId: target.id, sourceNoteIds: [source.id], markdown: "拒绝",
            originalContentHash: originalTargetHash, sourceContentHashes: [source.id: originalSourceHash]
        )))
        XCTAssertEqual(result.state, .stale)
        XCTAssertEqual(store.note(id: target.id)?.body, "目标 v2")

        let currentTarget = try XCTUnwrap(store.note(id: target.id))
        _ = try XCTUnwrap(store.save(id: source.id, title: source.title, body: "来源 v2", tags: source.tags, isPinned: source.isPinned))
        result = await executor.execute(mergeAction(step: .init(
            kind: "merge_notes", targetNoteId: target.id, sourceNoteIds: [source.id], markdown: "拒绝",
            originalContentHash: store.contentHash(for: currentTarget), sourceContentHashes: [source.id: originalSourceHash]
        )))
        XCTAssertEqual(result.state, .stale)
        XCTAssertEqual(store.note(id: target.id)?.body, "目标 v2")
        XCTAssertEqual(store.note(id: source.id)?.body, "来源 v2")
    }

    func testSourceOnlySavedReceiptIsRejectedDuringRecoveryWithoutCreatingID() async throws {
        let (store, executor) = isolatedStoreAndExecutor()
        defer { removeVault(store) }
        let source = try XCTUnwrap(store.createNote(id: "legacy-source", title: "来源", body: "原文"))
        let action = mergeAction(step: .init(
            kind: "merge_notes", sourceNoteIds: [source.id], markdown: "旧版合并",
            sourceContentHashes: [source.id: store.contentHash(for: source)]
        ))
        try FileManager.default.createDirectory(at: store.actionDirectory, withIntermediateDirectories: true)
        let receipt = try JSONSerialization.data(withJSONObject: [
            "actionId": action.id,
            "actionDigest": action.actionDigest,
            "accountFingerprint": store.accountFingerprint,
            "status": "local_applied",
            "resultNoteIds": [source.id],
            "updatedAt": 0,
        ])
        try receipt.write(to: store.actionDirectory.appendingPathComponent("\(action.id).json"), options: .atomic)

        let result = await executor.execute(action)
        XCTAssertEqual(result.state, .stale)
        XCTAssertEqual(store.note(id: source.id)?.body, "原文")
        XCTAssertEqual(store.notes.map(\.id), [source.id])
        XCTAssertFalse(store.notes.contains { $0.id.hasPrefix("ka-") })
    }

    func testServerSyncedNotesParticipateInKnowledgeWorkspaceSnapshot() {
        let server = ChatLocalNoteDTO(
            id: "server-only",
            title: "服务端笔记",
            markdown: "# 服务端笔记\n\n正文",
            updatedAt: "2026-09-05T01:00:00Z",
            contentHash: String(repeating: "a", count: 64)
        )
        let local = ChatLocalNoteDTO(
            id: "local-only",
            title: "本地笔记",
            markdown: "# 本地笔记",
            updatedAt: "2026-09-05T02:00:00Z",
            contentHash: String(repeating: "b", count: 64)
        )
        let snapshot = TenantSessionCoordinator.mergeWorkspaceNotes(
            server: [server], local: [local]
        )
        XCTAssertEqual(Set(snapshot.map(\.id)), Set(["server-only", "local-only"]))
        XCTAssertEqual(snapshot.first(where: { $0.id == "server-only" })?.contentHash, server.contentHash)
    }

    func testCloudSnapshotWithoutFrontmatterPreservesServerNoteID() throws {
        let store = KnowledgeNoteStore.shared
        store.activate(tenantKey: "cloud-id-tenant-\(UUID())", userId: "cloud-id-user")
        let snapshot = CloudKnowledgeNoteDTO(
            noteId: "server-stable-id",
            markdown: "# 服务端原始笔记\n\n没有 frontmatter。",
            contentHash: String(repeating: "a", count: 64),
            updatedAt: "2026-09-06T00:00:00Z",
            archived: false,
            mergedIntoNoteId: nil
        )
        try store.restoreFromCloudSnapshot(CloudKnowledgeNotesResponse(
            items: [snapshot], count: 1, compileStatus: "private_index_ready"
        ))
        defer { store.moveToTrash(id: snapshot.noteId) }

        XCTAssertEqual(store.note(id: snapshot.noteId)?.id, snapshot.noteId)
        XCTAssertNil(store.notes.first(where: { $0.fileURL.lastPathComponent == "server-stable-id.md" && $0.id != snapshot.noteId }))
    }

    func testCloudRestoreRemovesArchivedDuplicateOfActiveNoteID() throws {
        let store = KnowledgeNoteStore.shared
        store.activate(tenantKey: "cloud-dedupe-tenant-\(UUID())", userId: "cloud-dedupe-user")
        let note = try XCTUnwrap(store.createNote(id: "dedupe-id", title: "九州旅行纲要", body: "完整正文"))
        defer { store.moveToTrash(id: note.id) }
        try FileManager.default.createDirectory(at: store.archiveDirectory, withIntermediateDirectories: true)
        let duplicate = store.archiveDirectory.appendingPathComponent("stale-copy.md")
        try store.markdown(for: note).write(to: duplicate, atomically: true, encoding: .utf8)
        store.reload()
        XCTAssertNotNil(store.archivedNote(id: note.id))

        let markdown = store.markdown(for: try XCTUnwrap(store.note(id: note.id)))
        let hash = SHA256.hash(data: Data(markdown.utf8)).map { String(format: "%02x", $0) }.joined()
        try store.restoreFromCloudSnapshot(CloudKnowledgeNotesResponse(
            items: [.init(
                noteId: note.id, markdown: markdown, contentHash: hash,
                updatedAt: "2099-09-06T00:00:00Z", archived: false, mergedIntoNoteId: nil
            )],
            count: 1,
            compileStatus: "private_index_ready"
        ))

        XCTAssertNotNil(store.note(id: note.id))
        XCTAssertNil(store.archivedNote(id: note.id))
        XCTAssertFalse(FileManager.default.fileExists(atPath: duplicate.path))
    }

    func testNewerLocalEditWinsOverServerSnapshotOfSameNote() {
        let server = ChatLocalNoteDTO(
            id: "same",
            title: "服务端",
            markdown: "old",
            updatedAt: "2026-09-05T01:00:00Z",
            contentHash: String(repeating: "a", count: 64)
        )
        let local = ChatLocalNoteDTO(
            id: "same",
            title: "本地",
            markdown: "new",
            updatedAt: "2026-09-05T02:00:00Z",
            contentHash: String(repeating: "b", count: 64)
        )
        let snapshot = TenantSessionCoordinator.mergeWorkspaceNotes(
            server: [server], local: [local]
        )
        XCTAssertEqual(snapshot.map(\.markdown), ["new"])
    }

    func testSaveIntentRequiresProposalButUnrelatedSaveQuestionDoesNot() {
        XCTAssertTrue(TenantSessionCoordinator.requiresKnowledgeActionProposal("保存"))
        XCTAssertTrue(TenantSessionCoordinator.requiresKnowledgeActionProposal("把这段整理成笔记并保存"))
        XCTAssertTrue(TenantSessionCoordinator.requiresKnowledgeActionProposal("合并这两篇笔记"))
        XCTAssertTrue(TenantSessionCoordinator.requiresKnowledgeActionProposal("以上所有关于采尔马特的都帮我保存"))
        XCTAssertTrue(TenantSessionCoordinator.requiresKnowledgeActionProposal("关于伊斯坦布尔交通信息，帮我保存"))
        XCTAssertTrue(TenantSessionCoordinator.requiresKnowledgeActionProposal("把刚才的内容都记下来"))
        XCTAssertFalse(TenantSessionCoordinator.requiresKnowledgeActionProposal("iOS 如何保存图片到相册？"))
        XCTAssertFalse(TenantSessionCoordinator.requiresKnowledgeActionProposal("解释一下这段内容"))
        XCTAssertFalse(TenantSessionCoordinator.shouldAttachClientSessionContext(
            userText: "解释一下这段内容", hasRecoveryContext: false, hasLocalNotes: false
        ))
        XCTAssertTrue(TenantSessionCoordinator.shouldAttachClientSessionContext(
            userText: "保存为笔记", hasRecoveryContext: false, hasLocalNotes: false
        ))
        XCTAssertTrue(TenantSessionCoordinator.shouldAttachClientSessionContext(
            userText: "继续", hasRecoveryContext: true, hasLocalNotes: false
        ))
        XCTAssertTrue(TenantSessionCoordinator.shouldShowKnowledgeProposalRetry(
            userText: "保存为笔记", hasProposal: false
        ))
        XCTAssertFalse(TenantSessionCoordinator.shouldShowKnowledgeProposalRetry(
            userText: "保存为笔记", hasProposal: true
        ))
    }

    private func isolatedStoreAndExecutor() -> (KnowledgeNoteStore, KnowledgeActionExecutor) {
        let store = KnowledgeNoteStore()
        store.activate(tenantKey: "merge-tenant-\(UUID())", userId: "merge-user")
        return (store, KnowledgeActionExecutor(store: store, synchronizer: FakeKnowledgeActionSynchronizer()))
    }

    private func removeVault(_ store: KnowledgeNoteStore) {
        try? FileManager.default.removeItem(at: store.vaultDirectory)
        store.reload()
    }

    private func mergeAction(step: KnowledgeActionStep) -> KnowledgeActionBlock {
        let id = UUID().uuidString.lowercased()
        return KnowledgeActionBlock(
            id: id, summary: "合并", steps: [step], actionDigest: "digest-\(id)",
            transientCapability: "test-capability",
            expiresAt: Int(Date().timeIntervalSince1970) + 3_600
        )
    }
}

@MainActor
private final class FakeKnowledgeActionSynchronizer: KnowledgeActionSynchronizing {
    private var notes: [String: CloudKnowledgeNoteDTO] = [:]
    private(set) var mergeRequests: [KnowledgeNoteMergeRequestDTO] = []
    private(set) var legacyMergeMutationCount = 0

    func fetchKnowledgeNotes(includeArchived: Bool) async throws -> CloudKnowledgeNotesResponse {
        let items = notes.values.filter { includeArchived || !$0.archived }
        return .init(items: items, count: items.count, compileStatus: "ready")
    }

    func syncKnowledgeNote(id: String, markdown: String, updatedAt: Date, baseHash: String?, credentialGeneration: UInt64) async throws {
        legacyMergeMutationCount += 1
        let hash = SHA256.hash(data: Data(markdown.utf8)).map { String(format: "%02x", $0) }.joined()
        notes[id] = .init(
            noteId: id, markdown: markdown, contentHash: hash, updatedAt: nil,
            archived: false, mergedIntoNoteId: nil
        )
    }

    func archiveKnowledgeNote(id: String, mergedIntoNoteId: String, expectedContentHash: String?) async throws {
        legacyMergeMutationCount += 1
        guard let note = notes[id] else { return }
        notes[id] = .init(
            noteId: note.noteId, markdown: note.markdown, contentHash: note.contentHash,
            updatedAt: note.updatedAt, archived: true, mergedIntoNoteId: mergedIntoNoteId
        )
    }

    func mergeKnowledgeNotes(_ body: KnowledgeNoteMergeRequestDTO) async throws -> KnowledgeNoteMergeResponseDTO {
        mergeRequests.append(body)
        let hash = SHA256.hash(data: Data(body.revisedContent.utf8)).map { String(format: "%02x", $0) }.joined()
        notes[body.targetNoteId] = .init(
            noteId: body.targetNoteId, markdown: body.revisedContent, contentHash: hash,
            updatedAt: nil, archived: false, mergedIntoNoteId: nil
        )
        for (id, version) in body.sourceVersions {
            notes[id] = .init(
                noteId: id, markdown: "", contentHash: version, updatedAt: nil,
                archived: true, mergedIntoNoteId: body.targetNoteId
            )
        }
        return .init(
            operationId: body.operationId, targetNoteId: body.targetNoteId,
            status: "completed", revisedHash: hash
        )
    }

    func restoreKnowledgeNote(id: String) async throws {}
    func trashKnowledgeNote(id: String) async throws {}
    func commitKnowledgeAction(id: String, capability: String, actionDigest: String, status: String, resultNoteIds: [String], errorCode: String?) async throws {}
    func resumeKnowledgeActionSync(id: String, actionDigest: String, status: String, resultNoteIds: [String], errorCode: String?) async throws {}
    func discardKnowledgeAction(id: String, capability: String, actionDigest: String) async throws {}
}
