import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { extractProjectBlueprint, projectPlanningVisibleAnswer } from "../src/features/quantum-workspace/projectBlueprintPresentation.js";

const hostSource = await readFile(
  new URL("../src/features/quantum-workspace/DashiTaskboardHost.jsx", import.meta.url),
  "utf8",
);
const drawerSource = await readFile(
  new URL("../src/features/quantum-workspace/TaskChatDrawer.jsx", import.meta.url),
  "utf8",
);
const clarificationSource = await readFile(
  new URL("../src/features/quantum-workspace/HermesClarificationCard.jsx", import.meta.url),
  "utf8",
);
const planningSource = await readFile(
  new URL("../src/features/quantum-workspace/ProjectPlanningDialog.jsx", import.meta.url),
  "utf8",
);
const executionTraceSource = await readFile(
  new URL("../src/features/quantum-workspace/HermesExecutionTrace.jsx", import.meta.url),
  "utf8",
);
const homeSource = await readFile(
  new URL("../src/features/quantum-workspace/WorkspaceHomePage.jsx", import.meta.url),
  "utf8",
);
const backendSource = await readFile(
  new URL("../../backend/api/quantum_workspace.py", import.meta.url),
  "utf8",
);

test("opening a card session never creates a canonical task in the web host", () => {
  const openHandler = hostSource.slice(hostSource.indexOf('event.data.type !== "taskboard:create-thread"'));
  assert.doesNotMatch(openHandler, /createProjectTask/);
  assert.match(hostSource, /resolveCanonicalTask/);
  assert.match(hostSource, /binding_kind: "taskboard_card"/);
  assert.match(openHandler, /onOpenTaskChat\?\.\(\{/);
  assert.doesNotMatch(hostSource, /dashiRequest\("\/api\/tasks",\s*\{\s*method: "POST"/);
  assert.match(hostSource, /body: JSON\.stringify\(\{ project_id: project\.id \}\)/);
});

test("card session sends versionable full card context to the backend", () => {
  for (const field of [
    "business_goal",
    "parent_issue",
    "descriptions",
    "sub_issues",
    "comments",
    "status",
    "priority",
    "assignee",
    "labels",
    "development_context",
    "start_date",
    "due_date",
    "recurrence",
    "attachments",
    "related_issues",
  ]) assert.match(hostSource, new RegExp(field));
  assert.match(drawerSource, /card_context: cardContext/);
  assert.match(drawerSource, /contextSync\.mode === "incremental"/);
});

test("card backfill requires confirmation and routes overflow through session inbox", () => {
  assert.match(hostSource, /session_registry/);
  assert.doesNotMatch(hostSource, /method: "PATCH"/);
  assert.match(backendSource, /async def _apply_taskboard_backfill/);
  assert.match(backendSource, /"createIssues"/);
  assert.match(backendSource, /"addAttachments"/);
  assert.match(backendSource, /"relationChanges"/);
  assert.match(backendSource, /relations\/parent/);
  assert.match(drawerSource, /materializeTaskBackfillProposal/);
  assert.match(drawerSource, /window\.confirm/);
  assert.match(drawerSource, /completeTaskBackfillProposal/);
  assert.match(drawerSource, /applyTaskBackfillProposal/);
  assert.match(drawerSource, /确认回填/);
  assert.match(drawerSource, /BackfillChangeList/);
  assert.match(backendSource, /"Host": "127\.0\.0\.1"/);
  assert.match(drawerSource, /再次点击“确认回填”重试/);
});

test("card session presents and routes through the project AI employee", () => {
  assert.match(backendSource, /_ensure_project_ai_employees/);
  assert.match(backendSource, /"qws_employee"/);
  assert.match(backendSource, /agent_id=\(None if planning_session else str\(\(conversation\.binding/);
  assert.match(drawerSource, /AI Lab · AI 员工 Session/);
  assert.match(drawerSource, /aiEmployee\.display_name/);
  assert.match(drawerSource, /AI Lab AI 员工/);
});

test("card session renders and submits Hermes clarification instead of waiting silently", () => {
  assert.match(drawerSource, /streamEvent\.type === "clarify"/);
  assert.match(clarificationSource, /AI 需要补充信息/);
  assert.match(drawerSource, /submitTaskClarification/);
  assert.match(drawerSource, /clarify_id: clarification\.clarify_id/);
  assert.match(drawerSource, /等待你补充信息/);
});

test("new projects automatically enter the shared Hermes clarification protocol", () => {
  assert.match(planningSource, /trigger: "project_created"/);
  assert.match(planningSource, /project-intake-\$\{project\.id\}/);
  assert.match(planningSource, /HermesClarificationCard/);
  assert.match(planningSource, /submitTaskClarification/);
  assert.match(planningSource, /activeConversation\.binding\?\.session_id/);
  assert.match(backendSource, /"system" if body\.trigger == "project_created"/);
  assert.match(backendSource, /use the same Hermes clarify capability as the iOS main session/);
  assert.match(backendSource, /持续询问用户至需求收敛/);
});

test("unfinished project planning can be resumed and deletion has explicit progress", () => {
  assert.match(homeSource, /继续 AI 生成/);
  assert.match(homeSource, /planning_state === "dispatched"/);
  assert.match(homeSource, /deletingProjectId/);
  assert.match(homeSource, /删除中…/);
  assert.match(planningSource, /resumeNeeded/);
  assert.match(planningSource, /上次 AI 生成尚未完成/);
});

test("dispatch persists a structured task contract for every card session", () => {
  assert.match(backendSource, /_seed_project_session_registry/);
  assert.match(backendSource, /_task_registry_profile/);
  for (const field of ["goal", "current_state", "progress", "acceptance_criteria", "deliverables", "handoff"]) {
    assert.match(backendSource, new RegExp(`"${field}"`));
  }
  assert.match(backendSource, /"task_profile": row\.task_profile/);
});

test("card session exposes safe skill execution progress without chain-of-thought", () => {
  const executionSources = `${drawerSource}\n${executionTraceSource}`;
  for (const eventType of [
    "status",
    "triage_route",
    "capability_route",
    "tool_start",
    "tool_complete",
  ]) assert.match(executionSources, new RegExp(eventType));
  assert.match(executionTraceSource, /候选技能/);
  assert.match(executionTraceSource, /模型响应较慢/);
  assert.match(executionTraceSource, /60 秒达到保护时限/);
  assert.doesNotMatch(executionSources, /chain.of.thought|思维链/i);
});

test("project planning reuses the safe Hermes execution trace", () => {
  assert.match(planningSource, /HermesExecutionTrace/);
  assert.match(planningSource, /updateHermesExecution/);
  assert.match(planningSource, /variant="planning"/);
  assert.match(executionTraceSource, /planning_context/);
  assert.match(executionTraceSource, /候选技能/);
  assert.match(executionTraceSource, /不是页面卡死/);
  assert.match(executionTraceSource, /60 秒达到保护时限/);
  assert.doesNotMatch(executionTraceSource, /chain.of.thought|思维链/i);
});

test("project planning hides blueprint protocol while streaming and renders a natural summary", () => {
  const partial = "方案已收敛。\n```project_blueprint\n{\"project_goal\":\"建设人脸识别门禁\",\"stages\":[";
  assert.equal(projectPlanningVisibleAnswer(partial, { pending: true }), "方案已收敛。");
  assert.doesNotMatch(projectPlanningVisibleAnswer(partial, { pending: true }), /project_goal|stages|```/);

  const blueprint = {
    project_goal: "建设人脸识别门禁",
    stages: [{ key: "plan", name: "方案设计", acceptance_criteria: ["需求已确认"] }, { key: "delivery", name: "开发交付" }],
    tasks: [
      { key: "T1", stage_key: "plan", title: "确认业务需求", role: "产品经理", deliverables: ["需求说明书"] },
      { key: "T2", stage_key: "delivery", title: "设计系统架构", role: "架构师", deliverables: ["架构图"] },
    ],
    documents: [{ id: "D1", title: "项目实施方案" }],
  };
  const completed = `蓝图可供确认。\n\`\`\`project_blueprint\n${JSON.stringify(blueprint)}\n\`\`\``;
  assert.deepEqual(extractProjectBlueprint(completed), blueprint);
  const visible = projectPlanningVisibleAnswer(completed);
  assert.match(visible, /项目蓝图已经整理完成，共 2 个阶段、2 项任务和 1 份项目文档/);
  assert.match(visible, /项目目标：建设人脸识别门禁/);
  assert.match(visible, /执行流程：方案设计 → 开发交付/);
  assert.match(visible, /1\. 方案设计：确认业务需求/);
  assert.match(visible, /关键验收：需求已确认/);
  assert.match(visible, /产品经理、架构师/);
  assert.doesNotMatch(visible, /project_goal|stages|tasks|```|\{|\}/);
});
