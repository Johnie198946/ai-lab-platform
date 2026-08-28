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
});

test("card session renders and submits Hermes clarification instead of waiting silently", () => {
  assert.match(drawerSource, /streamEvent\.type === "clarify"/);
  assert.match(drawerSource, /AI 需要补充信息/);
  assert.match(drawerSource, /submitTaskClarification/);
  assert.match(drawerSource, /clarify_id: clarification\.clarify_id/);
  assert.match(drawerSource, /等待你补充信息/);
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
