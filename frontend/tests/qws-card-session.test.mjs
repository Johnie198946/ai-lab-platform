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

test("opening a card session never creates a canonical task in the web host", () => {
  const openHandler = hostSource.slice(hostSource.indexOf('event.data.type !== "taskboard:create-thread"'));
  assert.doesNotMatch(openHandler, /createProjectTask/);
  assert.match(openHandler, /resolveCanonicalTask/);
  assert.match(openHandler, /onOpenTaskChat\?\.\(\{ task: qwsTask, cardContext \}\)/);
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
    "related_issues",
  ]) assert.match(hostSource, new RegExp(field));
  assert.match(drawerSource, /card_context: cardContext/);
  assert.match(drawerSource, /contextSync\.mode === "incremental"/);
});
