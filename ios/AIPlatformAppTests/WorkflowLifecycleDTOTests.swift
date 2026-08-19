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
}
