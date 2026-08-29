import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

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
  for (const eventType of [
    "status",
    "triage_route",
    "capability_route",
    "tool_start",
    "tool_complete",
  ]) assert.match(drawerSource, new RegExp(eventType));
  assert.match(drawerSource, /候选技能/);
  assert.match(drawerSource, /模型响应较慢/);
  assert.match(drawerSource, /最多等待 60 秒/);
  assert.doesNotMatch(drawerSource, /chain.of.thought|思维链/i);
});
