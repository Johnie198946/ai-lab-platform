import XCTest
@testable import AIPlatformApp

final class WorkflowLifecycleDTOTests: XCTestCase {
    private func decoder() -> JSONDecoder {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return decoder
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
}
