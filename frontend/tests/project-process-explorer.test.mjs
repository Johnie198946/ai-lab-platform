import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

import { buildStageRail } from "../src/features/quantum-workspace/quantumProjection.js";

const pageSource = await readFile(new URL("../src/features/quantum-workspace/ProjectWorkspacePage.jsx", import.meta.url), "utf8");
const appSource = await readFile(new URL("../src/app/App.jsx", import.meta.url), "utf8");
const railSource = await readFile(new URL("../src/features/quantum-workspace/StageRail.jsx", import.meta.url), "utf8");
const styles = await readFile(new URL("../src/features/quantum-workspace/quantumWorkspace.css", import.meta.url), "utf8");

test("project navigation removes the duplicate top-level Gantt entry", () => {
  assert.doesNotMatch(pageSource, /<NavLink to=\{`\/projects\/\$\{projectId\}\/schedule`\}/);
  assert.doesNotMatch(pageSource, /Rows3/);
  assert.match(appSource, /path="\/projects\/:projectId\/schedule"/);
});

test("project process explorer is sticky and rendered on the Dashi taskboard view", () => {
  assert.match(pageSource, /className="qw-project-sticky"/);
  assert.match(pageSource, /<StageRail process=\{process\}/);
  assert.doesNotMatch(pageSource, /view !== "taskboard" && <StageRail/);
  assert.match(styles, /\.qw-project-sticky\{position:sticky;top:64px/);
});

test("each stage projection includes its real tasks and responsibility fields", () => {
  const [stage] = buildStageRail({
    stages: [{ id: "s1", name: "概念", order: 0 }],
    gates: [{ id: "g1", stage_id: "s1", name: "TR1", responsible_role: "技术评审组" }],
    tasks: [{ id: "t1", stage_id: "s1", title: "需求基线", assignee_role: "需求经理" }],
  });
  assert.equal(stage.tasks[0].assignee_role, "需求经理");
  assert.equal(stage.gates[0].responsible_role, "技术评审组");
  assert.match(railSource, /阶段任务与内容/);
  assert.match(railSource, /责任分工/);
  assert.match(railSource, /assignee_id \|\| item\.assignee_role \|\| "待分配"/);
});

test("stage nodes expose keyboard-friendly expanded state and explicit close control", () => {
  assert.match(railSource, /aria-expanded=\{active\}/);
  assert.match(railSource, /aria-controls=/);
  assert.match(railSource, /aria-label=\{`关闭\$\{stage\.name\}阶段详情`\}/);
  assert.match(styles, /focus-visible/);
});
