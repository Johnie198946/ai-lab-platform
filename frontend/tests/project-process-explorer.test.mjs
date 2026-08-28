import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

import { buildStageRail } from "../src/features/quantum-workspace/quantumProjection.js";

const pageSource = await readFile(new URL("../src/features/quantum-workspace/ProjectWorkspacePage.jsx", import.meta.url), "utf8");
const resourceSource = await readFile(new URL("../src/features/quantum-workspace/AIResourceWorkbench.jsx", import.meta.url), "utf8");
const apiSource = await readFile(new URL("../src/services/platformApi.js", import.meta.url), "utf8");
const appSource = await readFile(new URL("../src/app/App.jsx", import.meta.url), "utf8");
const railSource = await readFile(new URL("../src/features/quantum-workspace/StageRail.jsx", import.meta.url), "utf8");
const styles = await readFile(new URL("../src/features/quantum-workspace/quantumWorkspace.css", import.meta.url), "utf8");

test("project navigation removes the duplicate top-level Gantt entry", () => {
  assert.doesNotMatch(pageSource, /<NavLink to=\{`\/projects\/\$\{projectId\}\/schedule`\}/);
  assert.doesNotMatch(pageSource, /Rows3/);
  assert.match(appSource, /path="\/projects\/:projectId\/schedule"/);
});

test("AI Resource opens a configurable planning and operations workbench", () => {
  assert.match(pageSource, /getProjectResourcePlan/);
  assert.match(pageSource, /<AIResourceWorkbench/);
  assert.match(resourceSource, /资源配置/);
  assert.match(resourceSource, /架构与拓扑/);
  assert.match(resourceSource, /运行监控/);
  assert.match(resourceSource, /Token Factory/);
  assert.doesNotMatch(resourceSource, /\["token-factory", "Token Factory"/);
  assert.match(resourceSource, /WHY TOKEN FACTORY/);
  assert.match(resourceSource, /DEMO · 原型数据/);
  assert.match(resourceSource, /SCENARIO ENVIRONMENT TWIN/);
  assert.match(resourceSource, /场景 Subagent/);
  assert.match(resourceSource, /SIMULATED/);
  assert.match(resourceSource, /业务仿真轨迹/);
  assert.match(resourceSource, /技术资源监控/);
  assert.match(resourceSource, /SIMULATION SPEC/);
  assert.match(resourceSource, /ERP 行为模拟 Agent/);
  assert.match(resourceSource, /SYNTHETIC DATA GENERATOR/);
  assert.match(resourceSource, /数据集 manifest/);
  assert.match(resourceSource, /CONTEXT COPILOT/);
  assert.match(resourceSource, /ContextChatButton/);
  assert.match(resourceSource, /AI 一键推荐/);
  assert.match(apiSource, /resource-plan\/recommend/);
  assert.match(apiSource, /resource-plan\/simulations/);
  assert.match(apiSource, /resource-plan\/chat/);
  assert.match(styles, /\.qw-resource-workbench\{width:min\(1840px,calc\(100% - 48px\)\)/);
});

test("AI Resource labels disconnected truth instead of fabricating live infrastructure", () => {
  assert.match(resourceSource, /具体规格与收益以压测和商务方案为准/);
  assert.match(resourceSource, /当前展示原型数据/);
  assert.match(resourceSource, /不代表资源已经部署/);
  assert.match(resourceSource, /canonical Execution/);
  assert.match(resourceSource, /不会自动部署资源/);
});

test("AI Resource aligns datasets, models, topology configuration, and monitoring", () => {
  assert.match(resourceSource, /模拟数据集工作区/);
  assert.match(resourceSource, /Schema、版本、质量、血缘和使用关系/);
  assert.match(resourceSource, /大模型仓库/);
  assert.match(resourceSource, /ONLINE/);
  assert.match(resourceSource, /OFFLINE/);
  assert.match(resourceSource, /NODE CONFIGURATION/);
  assert.match(resourceSource, /dataset_binding/);
  assert.match(resourceSource, /配置对齐监控矩阵/);
  assert.match(resourceSource, /resource_inventory/);
  assert.match(resourceSource, /跨可用区部署拓扑/);
  assert.match(resourceSource, /Agent Runtime A/);
  assert.match(resourceSource, /模型仓库 ·/);
  assert.match(resourceSource, /场景数据与推理流/);
  assert.match(resourceSource, /Prompt \/ Context/);
  assert.match(resourceSource, /Token Stream/);
  assert.match(resourceSource, /决策证据/);
  assert.match(apiSource, /projects\/\$\{projectId\}\/datasets/);
  assert.match(apiSource, /projects\/\$\{projectId\}\/models/);
  assert.match(apiSource, /topology\/nodes/);
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
