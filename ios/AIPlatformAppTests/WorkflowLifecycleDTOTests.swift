import XCTest
import SwiftUI
import SQLite3
@testable import AIPlatformApp

final class WorkflowLifecycleDTOTests: XCTestCase {
    private func decoder() -> JSONDecoder {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return decoder
    }

    func testChatRequestEncodesExplicitLocalOnlyNoteScope() throws {
        let request = ChatRequestDTO(
            question: "整理本地待办",
            contextScope: ChatContextScopeDTO(
                mode: .localOnly,
                localNotes: [ChatLocalNoteDTO(
                    id: "note-1",
                    title: "本地会议",
                    markdown: "# 本地会议\n- [ ] 回信"
                )]
            )
        )
        let object = try XCTUnwrap(
            JSONSerialization.jsonObject(with: JSONEncoder().encode(request)) as? [String: Any]
        )
        let scope = try XCTUnwrap(object["context_scope"] as? [String: Any])
        XCTAssertEqual(scope["mode"] as? String, "local_only")
        let notes = try XCTUnwrap(scope["local_notes"] as? [[String: Any]])
        XCTAssertEqual(notes.first?["title"] as? String, "本地会议")
    }

    func testChatRequestEncodesClientSessionContextWithoutTenantClaims() throws {
        let request = ChatRequestDTO(
            question: "总结并保存",
            requestId: "request-1234",
            sessionId: "session-1",
            clientSessionContext: ClientSessionContextDTO(
                sessionId: "session-1",
                messages: [ClientSessionMessageDTO(
                    id: "m1", role: "user", content: "超聚变是一家公司"
                )],
                truncated: false
            )
        )
        let object = try XCTUnwrap(
            JSONSerialization.jsonObject(with: JSONEncoder().encode(request)) as? [String: Any]
        )
        let context = try XCTUnwrap(object["client_session_context"] as? [String: Any])
        XCTAssertEqual(context["session_id"] as? String, "session-1")
        XCTAssertNil(object["tenant_key"])
        XCTAssertNil(object["user_id"])
    }

    func testMarkdownParserReusesBoundedMessageCache() {
        let key = "streaming-\(UUID().uuidString)"
        let first = MarkdownBlockParser.shared.parse("第一段", messageId: key)
        let cached = MarkdownBlockParser.shared.parse("已变化但仍在流式", messageId: key)
        let completed = MarkdownBlockParser.shared.parse(
            "已变化但仍在流式",
            messageId: "done-\(UUID().uuidString)"
        )

        XCTAssertEqual(cached, first)
        XCTAssertNotEqual(completed, first)
    }

    func testMarkdownParserKeepsRepeatedBlocksInSourceOrder() {
        let blocks = MarkdownBlockParser.shared.parse(
            "重复段落\n\n重复段落\n\n---\n\n---",
            messageId: "repeated-\(UUID().uuidString)"
        )

        XCTAssertEqual(blocks.count, 4)
        XCTAssertEqual(blocks[0], blocks[1])
        XCTAssertEqual(blocks[2], .divider)
        XCTAssertEqual(blocks[3], .divider)
    }

    @MainActor
    func testChatStreamRelayoutsAfterSendingBelowExtraTallMessage() async {
        let coordinator = TenantSessionCoordinator()
        let sessionId = coordinator.sessionManager.activeSessionID()
        let longAssessment = Array(
            repeating: """
            ### 三年级英语基础水平评估测试
            1. This is ___ apple. A. a B. an C. two
            2. I ___ a student. A. am B. is C. are
            3. What's your name? My name is Tom.

            ```text
            1-B
            2-A
            3-My name is Tom.
            ```
            """,
            count: 18
        ).joined(separator: "\n\n")
        coordinator.messages = [
            ChatMessage(sessionId: sessionId, role: .assistant, content: longAssessment)
        ]

        let host = UIHostingController(rootView: ChatMessageStreamView(coordinator: coordinator))
        let window = UIWindow(frame: CGRect(x: 0, y: 0, width: 393, height: 720))
        window.rootViewController = host
        window.isHidden = false
        defer { window.isHidden = true }

        host.view.layoutIfNeeded()

        coordinator.messages.append(
            ChatMessage(sessionId: sessionId, role: .user, content: "B A C A B A B C C D A B")
        )
        coordinator.messages.append(
            ChatMessage(
                sessionId: sessionId,
                role: .assistant,
                content: "",
                isStreaming: true,
                pending: true
            )
        )

        for _ in 0..<4 {
            await Task.yield()
            host.view.setNeedsLayout()
            host.view.layoutIfNeeded()
        }

        let scrollView = findScrollView(in: host.view)
        XCTAssertEqual(coordinator.messages.count, 3)
        XCTAssertGreaterThan(host.view.bounds.height, 0)
        XCTAssertNotNil(scrollView)
        XCTAssertGreaterThan(scrollView?.contentSize.height ?? 0, scrollView?.bounds.height ?? 0)

        if let scrollView {
            let maximumOffset = max(0, scrollView.contentSize.height - scrollView.bounds.height)
            for step in 1...12 {
                scrollView.setContentOffset(
                    CGPoint(x: 0, y: maximumOffset * CGFloat(step) / 12),
                    animated: false
                )
                scrollView.layoutIfNeeded()
                await Task.yield()
            }
            XCTAssertEqual(scrollView.contentOffset.y, maximumOffset, accuracy: 1)
        }
    }

    private func findScrollView(in view: UIView) -> UIScrollView? {
        if let scrollView = view as? UIScrollView {
            return scrollView
        }
        for subview in view.subviews {
            if let scrollView = findScrollView(in: subview) {
                return scrollView
            }
        }
        return nil
    }

    func testCreateDraftResponseDecodesClarificationSession() throws {
        let data = Data(
            """
            {
              "workflow": {
                "id": "wf_1",
                "title": "英语提升",
                "description": "生成学习计划",
                "desired_output": "Markdown",
                "status": "clarifying",
                "active_plan_id": null,
                "clarification_session_id": "wfs_1",
                "primary_agent_id": null,
                "created_at": "2026-08-19T10:00:00Z",
                "updated_at": "2026-08-19T10:00:00Z",
                "latest_execution": null
              },
              "clarification_session": {
                "id": "wfs_1",
                "workflow_id": "wf_1",
                "phase": "clarifying",
                "round_number": 1,
                "last_event_seq": 2
              }
            }
            """.utf8
        )

        let response = try decoder().decode(WorkflowCreateResponseDTO.self, from: data)
        XCTAssertEqual(response.workflow.status, "clarifying")
        XCTAssertEqual(response.workflow.clarificationSessionId, "wfs_1")
        XCTAssertEqual(response.clarificationSession.lastEventSeq, 2)
    }

    func testAgentBuildResponseDecodesCompositionAndDelegationPolicy() throws {
        let data = Data(
            """
            {
              "workflow": {
                "id": "wf_1", "title": "任务", "description": "目标",
                "desired_output": "报告", "status": "agent_ready",
                "active_plan_id": "wfp_1", "clarification_session_id": "wfs_1",
                "primary_agent_id": "agent_1", "created_at": null,
                "updated_at": null, "latest_execution": null
              },
              "agent": {
                "id": "agent_1", "owner_user_id": "user_1",
                "origin_workflow_id": "wf_1", "custom_name": "任务专属 Agent",
                "visibility": "private", "subscribed_knowledge_packs": ["wiki"],
                "is_active": true,
                "composition_manifest": {
                  "capability_agent_ids": ["main_agent", "knowledge"],
                  "invoked_agent_ids": [],
                  "delegation": {"max_concurrent_children": 3, "max_spawn_depth": 1},
                  "knowledge_scope": ["wiki"], "plan_id": "wfp_1"
                }
              }
            }
            """.utf8
        )

        let response = try decoder().decode(WorkflowAgentBuildResponseDTO.self, from: data)
        XCTAssertEqual(response.agent.visibility, "private")
        XCTAssertEqual(response.agent.compositionManifest.capabilityAgentIds, ["main_agent", "knowledge"])
        XCTAssertEqual(response.agent.compositionManifest.delegation.maxConcurrentChildren, 3)
        XCTAssertEqual(response.workflow.primaryAgentId, "agent_1")
    }

    func testLifecycleEventIgnoresPrivateReasoningPayload() throws {
        let data = Data(
            """
            {
              "id": 7, "workflow_id": "wf_1", "session_id": "wfs_1",
              "type": "plan_compiled", "message": "工作流 DAG 已编译",
              "payload": {"internal_reasoning": "must not be rendered"},
              "created_at": "2026-08-19T10:00:01Z"
            }
            """.utf8
        )

        let event = try decoder().decode(WorkflowLifecycleEventDTO.self, from: data)
        XCTAssertEqual(event.type, "plan_compiled")
        XCTAssertEqual(event.message, "工作流 DAG 已编译")
        XCTAssertNil(event.payload.question)
    }

    func testLegacyPlanWithoutNestedPlanIdStillDecodes() throws {
        let data = Data(
            """
            {
              "id": "wfp_legacy", "workflow_id": "wf_1", "version": 1,
              "goal": "英语评估", "deliverable": "Markdown",
              "allow_network": true, "max_tokens": 24000,
              "estimated_tokens": 12000, "knowledge_scope": [],
              "validation_errors": [],
              "dsl": {"name": "英语评估", "nodes": [], "edges": [], "version": "1.0.0"},
              "frozen_at": null, "created_at": null
            }
            """.utf8
        )

        let plan = try decoder().decode(WorkflowPlanDTO.self, from: data)
        XCTAssertEqual(plan.id, "wfp_legacy")
        XCTAssertEqual(plan.dsl.planId, "")
    }

    func testNestedPlanIdDecodesWithGlobalSnakeCaseStrategy() throws {
        let data = Data(
            """
            {
              "plan_id":"wfp_nested","name":"评估","version":"1.0.0","edges":[],
              "nodes":[{
                "id":"node_01","node_type":"FILTER_PASS","name":"安全检查",
                "parameters":{
                  "agent_id":"supervision","instruction":"检查方案",
                  "output_format":"Markdown","knowledge_scope":["wiki"],
                  "allow_network":true,"requires_review":true,
                  "max_tokens":1500,"revision_note":"复核"
                }
              }]
            }
            """.utf8
        )

        let dsl = try decoder().decode(WorkflowDSLDTO.self, from: data)
        XCTAssertEqual(dsl.planId, "wfp_nested")
        XCTAssertEqual(dsl.nodes.first?.nodeType, "FILTER_PASS")
        XCTAssertEqual(dsl.nodes.first?.parameters.agentId, "supervision")
        XCTAssertEqual(dsl.nodes.first?.parameters.outputFormat, "Markdown")
        XCTAssertEqual(dsl.nodes.first?.parameters.knowledgeScope, ["wiki"])
        XCTAssertEqual(dsl.nodes.first?.parameters.allowNetwork, true)
        XCTAssertEqual(dsl.nodes.first?.parameters.requiresReview, true)
        XCTAssertEqual(dsl.nodes.first?.parameters.maxTokens, 1500)
        XCTAssertEqual(dsl.nodes.first?.parameters.revisionNote, "复核")

        let encoded = try JSONEncoder().encode(dsl)
        let object = try XCTUnwrap(JSONSerialization.jsonObject(with: encoded) as? [String: Any])
        let nodes = try XCTUnwrap(object["nodes"] as? [[String: Any]])
        let first = try XCTUnwrap(nodes.first)
        XCTAssertEqual(first["node_type"] as? String, "FILTER_PASS")
        let parameters = try XCTUnwrap(first["parameters"] as? [String: Any])
        XCTAssertEqual(parameters["agent_id"] as? String, "supervision")
    }

    func testActivePlanningActivityDecodesStructuredPluginStep() throws {
        let data = Data(
            """
            [{
              "workflow": {
                "id": "wf_1", "title": "英语提升", "description": "目标",
                "desired_output": "Markdown", "status": "planning",
                "active_plan_id": null, "clarification_session_id": "wfs_1",
                "primary_agent_id": null, "created_at": null, "updated_at": null,
                "latest_execution": null
              },
              "session": {
                "id": "wfs_1", "workflow_id": "wf_1", "phase": "planning",
                "round_number": 3, "last_event_seq": 8
              },
              "latest_event": {
                "id": 8, "workflow_id": "wf_1", "session_id": "wfs_1",
                "type": "planner_step", "message": "加载技能: research",
                "payload": {
                  "step_id": "bridge-8", "category": "skill_load",
                  "status": "done", "tool": "research",
                  "detail": "已加载技能", "source": "hermes_reasoning_plugin"
                },
                "created_at": "2026-08-19T10:00:01Z"
              }
            }]
            """.utf8
        )

        let activities = try decoder().decode([WorkflowActiveActivityDTO].self, from: data)
        XCTAssertEqual(activities.first?.session.phase, "planning")
        XCTAssertEqual(activities.first?.latestEvent?.payload.category, "skill_load")
        XCTAssertEqual(activities.first?.latestEvent?.payload.source, "hermes_reasoning_plugin")
    }

    func testLegacySessionRecordDefaultsToMainAgent() throws {
        let data = Data(
            """
            {
              "id":"session-legacy","title":"旧会话",
              "updatedAt":"2026-08-20T10:00:00Z","messages":[]
            }
            """.utf8
        )
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601
        let record = try decoder.decode(SessionRecord.self, from: data)
        XCTAssertNil(record.agentId)
        XCTAssertNil(record.agentName)
    }

    func testSessionRecordPersistsSelectedAgent() throws {
        let record = SessionRecord(
            id: "session-agent", title: "英语评估", updatedAt: Date(), messages: [],
            agentId: "67d68724aefd431c967acdf0864e1949",
            agentName: "小学生英语评估 · 专属 Agent"
        )
        let data = try JSONEncoder().encode(record)
        let restored = try JSONDecoder().decode(SessionRecord.self, from: data)
        XCTAssertEqual(restored.agentId, "67d68724aefd431c967acdf0864e1949")
        XCTAssertEqual(restored.agentName, "小学生英语评估 · 专属 Agent")
    }

    func testAgentRouteSSEEventDecodesProvenance() throws {
        let event = try XCTUnwrap(APIClient.StreamEvent.parse([
            "type": "agent_route",
            "agent": [
                "id": "english-agent",
                "name": "小学生英语评估 · 专属 Agent",
                "delegated": true,
            ],
            "delegated_by": "main_agent",
        ]))
        guard case let .agentRoute(id, name, delegated, delegatedBy) = event else {
            return XCTFail("expected agentRoute event")
        }
        XCTAssertEqual(id, "english-agent")
        XCTAssertEqual(name, "小学生英语评估 · 专属 Agent")
        XCTAssertTrue(delegated)
        XCTAssertEqual(delegatedBy, "main_agent")
    }

    func testNoteDraftSSEEventDecodesForConfirmation() throws {
        let event = try XCTUnwrap(APIClient.StreamEvent.parse([
            "type": "note_draft",
            "draft_id": "draft-1",
            "title": "超聚变",
            "markdown": "# 超聚变\n\n正文",
            "tags": ["企业"],
            "source_session_id": "session-1",
            "source_message_ids": ["m1"],
            "account_scope": "tenant:user",
            "merge_candidates": [[
                "id": "old-1", "title": "旧笔记", "snippet": "旧内容"
            ]],
            "merged_title": "超聚变整理",
            "merged_markdown": "# 合并内容",
            "merged_tags": ["企业"],
        ]))
        guard case let .noteDraft(
            id, title, markdown, _, sessionId, messageIds, accountScope, candidates,
            mergedTitle, mergedMarkdown, _, _, _, _, _, _, _, _
        ) = event else {
            return XCTFail("expected noteDraft event")
        }
        XCTAssertEqual(id, "draft-1")
        XCTAssertEqual(title, "超聚变")
        XCTAssertTrue(markdown.contains("正文"))
        XCTAssertEqual(sessionId, "session-1")
        XCTAssertEqual(messageIds, ["m1"])
        XCTAssertEqual(accountScope, "tenant:user")
        XCTAssertEqual(candidates.map(\.id), ["old-1"])
        XCTAssertEqual(mergedTitle, "超聚变整理")
        XCTAssertEqual(mergedMarkdown, "# 合并内容")
    }

    func testClarifyStateSurvivesSessionPersistenceRoundTrip() throws {
        let block = ClarifyBlock(
            clarifyId: "cid-1",
            requestId: "request-1",
            sessionId: "session-1",
            agentId: "main_agent",
            expiresInSeconds: 123,
            submissionState: .submitting,
            question: "请提供具体任务",
            choices: [],
            source: "bridge",
            submittedSelection: "测试英语水平"
        )
        let message = ChatMessage(
            id: "message-1", sessionId: "session-1", role: .assistant,
            content: "", blocks: [.clarify(block)]
        )

        let data = try JSONEncoder().encode(PersistedMessage(message))
        let decoded = try JSONDecoder().decode(PersistedMessage.self, from: data)
        let restored = try XCTUnwrap(decoded.toChatMessage(sessionId: "session-1").clarifyBlock)

        XCTAssertEqual(restored.clarifyId, "cid-1")
        XCTAssertEqual(restored.requestId, "request-1")
        XCTAssertEqual(restored.submissionState, .submitting)
        XCTAssertEqual(restored.submittedSelection, "测试英语水平")
    }

    func testLegacyPersistedMessageWithoutClarifyStillDecodes() throws {
        let data = Data(
            """
            {
              "id":"m1","role":"assistant","content":"旧回答",
              "createdAt":0,"pending":false,"degraded":false,
              "isDemoSample":false,"reasoningDuration":null
            }
            """.utf8
        )
        let legacy = try JSONDecoder().decode(PersistedMessage.self, from: data)
        XCTAssertNil(legacy.clarify)
        XCTAssertEqual(legacy.toChatMessage(sessionId: "s1").content, "旧回答")
    }

    func testChatStatusDecodesRecoverableClarifyMetadata() throws {
        let data = Data(
            """
            {
              "status":"running","phase":"clarify","answer":"",
              "reasoning":[],"latest_step":"等待用户确认","consumed":false,
              "clarify":{
                "clarify_id":"cid-2","request_id":"request-2",
                "question":"选择目标","choices":["A","B"],
                "multi_select":false,"expires_in_seconds":88
              }
            }
            """.utf8
        )
        let status = try decoder().decode(ChatStatusDTO.self, from: data)
        XCTAssertEqual(status.phase, "clarify")
        XCTAssertEqual(status.clarify?.clarifyId, "cid-2")
        XCTAssertEqual(status.clarify?.requestId, "request-2")
        XCTAssertEqual(status.clarify?.expiresInSeconds, 88)
    }

    func testChatHistoryStorePagesOneThousandMessagesWithinBudgets() throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: root) }
        let store = try ChatHistoryStore(
            databaseURL: root.appendingPathComponent("history.sqlite"),
            legacyDirectory: root.appendingPathComponent("legacy")
        )
        let sessionId = "large-history"
        let messages = (0..<1_000).map { index in
            ChatMessage(
                id: "message-\(index)", sessionId: sessionId,
                role: index.isMultiple(of: 2) ? .user : .assistant,
                content: "正文-\(index)-" + String(repeating: "x", count: 120)
            )
        }

        XCTAssertEqual(try store.upsert(messages, sessionId: sessionId), 1_000)
        let latest = try store.latest(sessionId: sessionId)
        XCTAssertLessThanOrEqual(latest.messages.count, ChatHistoryStore.pageMessageLimit)
        XCTAssertLessThanOrEqual(latest.messages.reduce(0) { $0 + $1.content.count }, ChatHistoryStore.pageCharacterLimit)
        XCTAssertEqual(latest.messages.last?.id, "message-999")
        XCTAssertTrue(latest.hasOlder)
        XCTAssertFalse(latest.hasNewer)

        let older = try store.before(sessionId: sessionId, messageId: try XCTUnwrap(latest.messages.first?.id))
        XCTAssertLessThanOrEqual(older.messages.count, ChatHistoryStore.pageMessageLimit)
        XCTAssertTrue(older.hasNewer)
        let newer = try store.after(sessionId: sessionId, messageId: try XCTUnwrap(older.messages.last?.id))
        XCTAssertEqual(newer.messages.first?.id, latest.messages.first?.id)

        let longSession = "character-budget"
        let longMessages = (0..<3).map {
            ChatMessage(id: "long-\($0)", sessionId: longSession, role: .assistant, content: String(repeating: "长", count: 40_001))
        }
        _ = try store.upsert(longMessages, sessionId: longSession)
        let characterPage = try store.latest(sessionId: longSession)
        XCTAssertEqual(characterPage.messages.count, 1)
        XCTAssertEqual(characterPage.messages.first?.content.count, 40_001)

        XCTAssertEqual(try store.previousUser(sessionId: sessionId, before: "message-51")?.id, "message-50")
        try store.truncate(sessionId: sessionId, from: "message-51")
        XCTAssertEqual(try store.count(sessionId), 51)
        try store.clear(sessionId)
        XCTAssertEqual(try store.count(sessionId), 0)
        try store.delete(longSession)
        XCTAssertNil(try store.summaries().first(where: { $0.id == longSession }))
    }

    func testChatHistoryStoreMigratesLegacyJSONAndKeepsBackup() throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let legacy = root.appendingPathComponent("Sessions")
        try FileManager.default.createDirectory(at: legacy, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }
        let messages = (0..<30).map {
            PersistedMessage(ChatMessage(id: "legacy-\($0)", sessionId: "legacy", role: $0.isMultiple(of: 2) ? .user : .assistant, content: "历史 \($0)"))
        }
        let record = SessionRecord(
            id: "legacy", title: "迁移会话", updatedAt: Date(timeIntervalSince1970: 1_750_000_000),
            messages: messages, agentId: "english-agent", agentName: "英语评估"
        )
        let encoder = JSONEncoder()
        encoder.dateEncodingStrategy = .iso8601
        let source = legacy.appendingPathComponent("legacy.json")
        try encoder.encode(record).write(to: source)

        let store = try ChatHistoryStore(databaseURL: root.appendingPathComponent("history.sqlite"), legacyDirectory: legacy)
        XCTAssertEqual(try store.count("legacy"), 30)
        let latest = try store.latest(sessionId: "legacy")
        XCTAssertEqual(latest.messages.last?.id, "legacy-29")
        let summary = try XCTUnwrap(store.summaries().first)
        XCTAssertEqual(summary.title, "迁移会话")
        XCTAssertEqual(summary.agentId, "english-agent")
        XCTAssertFalse(FileManager.default.fileExists(atPath: source.path))
        XCTAssertTrue(FileManager.default.fileExists(atPath: legacy.appendingPathComponent("legacy.json.v1-backup").path))
    }

    func testChatHistoryStoreLeavesInvalidLegacyFileRecoverable() throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let legacy = root.appendingPathComponent("Sessions")
        try FileManager.default.createDirectory(at: legacy, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }
        let source = legacy.appendingPathComponent("broken.json")
        try Data("not-json".utf8).write(to: source)

        let store = try ChatHistoryStore(databaseURL: root.appendingPathComponent("history.sqlite"), legacyDirectory: legacy)
        XCTAssertTrue(try store.summaries().isEmpty)
        XCTAssertTrue(FileManager.default.fileExists(atPath: source.path))
    }

    func testChatHistoryStoreRollsBackFailedSessionMigration() throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let legacy = root.appendingPathComponent("Sessions")
        try FileManager.default.createDirectory(at: legacy, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }
        let duplicated = ChatMessage(id: "same-id", sessionId: "rollback", role: .assistant, content: "重复")
        let record = SessionRecord(
            id: "rollback", title: "应回滚", updatedAt: Date(),
            messages: [PersistedMessage(duplicated), PersistedMessage(duplicated)]
        )
        let encoder = JSONEncoder(); encoder.dateEncodingStrategy = .iso8601
        let source = legacy.appendingPathComponent("rollback.json")
        try encoder.encode(record).write(to: source)

        let store = try ChatHistoryStore(databaseURL: root.appendingPathComponent("history.sqlite"), legacyDirectory: legacy)
        XCTAssertNil(try store.summaries().first(where: { $0.id == "rollback" }))
        XCTAssertTrue(FileManager.default.fileExists(atPath: source.path))
        XCTAssertFalse(FileManager.default.fileExists(atPath: legacy.appendingPathComponent("rollback.json.v1-backup").path))
    }

    @MainActor
    func testSessionManagerColdStartLoadsOnlyMetadataAndLatestPageOnDemand() throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: root) }
        let store = try ChatHistoryStore(databaseURL: root.appendingPathComponent("history.sqlite"), legacyDirectory: root.appendingPathComponent("legacy"))
        let sessionId = "metadata-only"
        _ = try store.upsert((0..<100).map {
            ChatMessage(id: "cold-\($0)", sessionId: sessionId, role: .assistant, content: "消息 \($0)")
        }, sessionId: sessionId)

        let manager = SessionManager(store: store)
        XCTAssertEqual(manager.messageCount(for: sessionId), 100)
        XCTAssertTrue(manager.sessions.isEmpty)
        XCTAssertLessThanOrEqual(manager.latestPage(for: sessionId).messages.count, ChatHistoryStore.pageMessageLimit)
        XCTAssertEqual(manager.sessions[sessionId]?.last?.id, "cold-99")
    }

    @MainActor
    func testCoordinatorReplacesVisibleHistoryPages() throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: root) }
        let store = try ChatHistoryStore(databaseURL: root.appendingPathComponent("history.sqlite"), legacyDirectory: root.appendingPathComponent("legacy"))
        let sessionId = "paging-ui"
        _ = try store.upsert((0..<60).map {
            ChatMessage(id: "page-\($0)", sessionId: sessionId, role: .assistant, content: "消息 \($0)")
        }, sessionId: sessionId)
        let manager = SessionManager(store: store)
        let coordinator = TenantSessionCoordinator(sessionManager: manager)

        XCTAssertEqual(coordinator.messages.last?.id, "page-59")
        XCTAssertLessThanOrEqual(coordinator.messages.count, ChatHistoryStore.pageMessageLimit)
        XCTAssertTrue(coordinator.hasOlderMessages)
        XCTAssertTrue(coordinator.isLatestPage)
        coordinator.loadOlderMessagePage()
        XCTAssertFalse(coordinator.isLatestPage)
        XCTAssertTrue(coordinator.hasNewerMessages)
        XCTAssertLessThanOrEqual(coordinator.messages.count, ChatHistoryStore.pageMessageLimit)
        coordinator.loadNewerMessagePage()
        XCTAssertEqual(coordinator.messages.first?.id, "page-36")
        coordinator.returnToLatestMessages()
        XCTAssertEqual(coordinator.messages.last?.id, "page-59")
        XCTAssertTrue(coordinator.isLatestPage)
    }

    @MainActor
    func testSessionManagerPersistsMessagesOffMainActorInOrder() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: root) }
        let store = try ChatHistoryStore(
            databaseURL: root.appendingPathComponent("history.sqlite"),
            legacyDirectory: root.appendingPathComponent("legacy")
        )
        let manager = SessionManager(store: store)
        let sessionId = manager.createSession()
        let first = ChatMessage(
            id: "assistant", sessionId: sessionId, role: .assistant,
            content: "第一版", blocks: [.reasoning([
                ReasoningStep(type: .thought, title: "思考", detail: "第一步")
            ])]
        )
        var second = first
        second.content = "第二版"
        second.blocks = [.reasoning([
            ReasoningStep(type: .toolCall, title: "检索 Wiki", detail: "已完成")
        ])]

        manager.setMessages([first], for: sessionId)
        manager.setMessages([second], for: sessionId)

        XCTAssertEqual(manager.messages(for: sessionId).first?.content, "第二版")
        await manager.flushPendingPersistence()
        XCTAssertEqual(try store.message(sessionId: sessionId, id: "assistant")?.content, "第二版")
    }

    @MainActor
    func testSessionManagerDoesNotBlockMainActorWhenSQLiteWriterIsBusy() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: root) }
        let databaseURL = root.appendingPathComponent("history.sqlite")
        let store = try ChatHistoryStore(
            databaseURL: databaseURL,
            legacyDirectory: root.appendingPathComponent("legacy")
        )
        let manager = SessionManager(store: store)
        let sessionId = manager.createSession()

        var lockDatabase: OpaquePointer?
        XCTAssertEqual(sqlite3_open(databaseURL.path, &lockDatabase), SQLITE_OK)
        defer { sqlite3_close(lockDatabase) }
        XCTAssertEqual(sqlite3_exec(lockDatabase, "BEGIN IMMEDIATE", nil, nil, nil), SQLITE_OK)

        let startedAt = CFAbsoluteTimeGetCurrent()
        manager.setMessages([
            ChatMessage(id: "queued", sessionId: sessionId, role: .user, content: "立即发送")
        ], for: sessionId)
        let elapsed = CFAbsoluteTimeGetCurrent() - startedAt

        XCTAssertLessThan(elapsed, 0.2)
        XCTAssertEqual(manager.messages(for: sessionId).first?.content, "立即发送")
        XCTAssertEqual(sqlite3_exec(lockDatabase, "COMMIT", nil, nil, nil), SQLITE_OK)
        await manager.flushPendingPersistence()
        XCTAssertEqual(try store.message(sessionId: sessionId, id: "queued")?.content, "立即发送")
    }
}
