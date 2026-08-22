import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

import {
  RESULT_VIEW_TYPES,
  diffPlanVersions,
  projectPlanToCanvas,
  projectPlanToReactFlow,
  projectResultViews,
  isStrictlyNewerPlan,
  pollForNewPlan,
  pollExecutionUntilTerminal,
  canStartWorkflow,
  hasResultData,
  PLAN_POLL_ATTEMPTS,
  EXECUTION_POLL_ATTEMPTS,
} from "../src/architectContract.js";

test("plan-to-canvas projection uses only server nodes and edges", () => {
  const result = projectPlanToCanvas({ dsl: { nodes: [{ id: "n1" }], edges: [{ source: "n1", target: "n2" }] } });
  assert.deepEqual(result, { nodes: [{ id: "n1" }], edges: [{ source: "n1", target: "n2" }] });
});

test("React Flow projection does not create server nodes", () => {
  const result = projectPlanToReactFlow({ dsl: { nodes: [{ id: "n1", name: "Server" }], edges: [{ source: "n1", target: "n2" }] } });
  assert.deepEqual(result.nodes.map(({ id }) => id), ["n1"]);
  assert.deepEqual(result.edges.map(({ source, target }) => [source, target]), [["n1", "n2"]]);
});

test("plan diff reports added, removed, and changed nodes", () => {
  const diff = diffPlanVersions(
    { id: "v1", dsl: { nodes: [{ id: "keep", label: "old" }, { id: "remove" }], edges: [] } },
    { id: "v2", dsl: { nodes: [{ id: "keep", label: "new" }, { id: "add" }], edges: [] } },
  );
  assert.deepEqual(diff.added, ["add"]);
  assert.deepEqual(diff.removed, ["remove"]);
  assert.deepEqual(diff.changed, ["keep"]);
});

test("result area exposes exactly four server-backed view types and honest empties", () => {
  assert.deepEqual(RESULT_VIEW_TYPES, ["requirement", "evidence", "gate", "artifact"]);
  assert.deepEqual(projectResultViews(), [
    { type: "requirement", data: null },
    { type: "evidence", data: [] },
    { type: "gate", data: null },
    { type: "artifact", data: null },
  ]);
});

test("ArchitectPage uses real React Flow with server-only nodes and edges", () => {
  const source = fs.readFileSync(new URL("../src/pages/ArchitectPage.jsx", import.meta.url), "utf8");
  assert.match(source, /import\s+\{\s*ReactFlow\s*\}\s+from\s+["']@xyflow\/react["']/);
  assert.match(source, /<ReactFlow[\s\S]*nodes=\{nodes\}[\s\S]*edges=\{edges\}/);
  assert.match(source, /nodesDraggable=\{false\}/);
  assert.match(source, /nodesConnectable=\{false\}/);
  assert.match(source, /elementsSelectable=\{true\}/);
  assert.match(source, /projectPlanToCanvas\(plan\)/);
});

test("requirement confirmation actions send structured confirm and revise intents", () => {
  const page = fs.readFileSync(new URL("../src/pages/ArchitectPage.jsx", import.meta.url), "utf8");
  const api = fs.readFileSync(new URL("../src/services/platformApi.js", import.meta.url), "utf8");
  assert.match(page, /确认并生成流程/);
  assert.match(page, /继续修改/);
  assert.match(page, /submitClarification\(["']confirm["']\)/);
  assert.match(page, /submitClarification\(["']revise["']\)/);
  assert.match(api, /body:\s*\{\s*response,\s*intent\s*\}/);
});

test("UNCONNECTED server nodes remain honestly labelled and never become LIVE locally", () => {
  const result = projectPlanToReactFlow({ dsl: { nodes: [{
    id: "gate",
    name: "TR2决策门",
    parameters: { capability_status: "UNCONNECTED", execution_enabled: false },
  }], edges: [] } });
  assert.match(result.nodes[0].data.label, /UNCONNECTED/);
  assert.doesNotMatch(result.nodes[0].data.label, /LIVE/);
});

test("showroom static entry redirects without changing legacy journey", () => {
  const index = fs.readFileSync(new URL("../public/showroom/index.html", import.meta.url), "utf8");
  const legacy = fs.readFileSync(new URL("../public/showroom/legacy.html", import.meta.url), "utf8");
  assert.match(index, /\/login\?next=\/architect|location\.(?:replace|href)\s*=\s*["']\/architect/);
  assert.equal(legacy.length > 0, true);
});

test("App root route uses the destructured authSession", () => {
  const source = fs.readFileSync(new URL("../src/app/App.jsx", import.meta.url), "utf8");
  assert.match(source, /const\s+\{\s*isAuthenticated\s*,\s*authSession\s*\}\s*=\s*useAuth\(\)/);
});

test("an empty workbench can submit the first requirement", () => {
  const source = fs.readFileSync(new URL("../src/pages/ArchitectPage.jsx", import.meta.url), "utf8");
  assert.match(source, /onSubmit=\{workflow\s*\?\s*send\s*:\s*create\}/);
  assert.match(source, /rows\.filter\(\(item\)\s*=>\s*item\.clarification_session_id\)/);
  assert.match(source, /workflow\s*\?\s*["']提交回复["']\s*:\s*["']开始澄清["']/);
});

test("revision polling waits for a strictly newer server plan", async () => {
  assert.equal(PLAN_POLL_ATTEMPTS >= 360, true);
  const plans = [
    { id: "v1", version: 1 },
    { id: "v2", version: 2 },
  ];
  const result = await pollForNewPlan("wf-1", plans[0], {
    getPlan: async () => plans.shift(),
    getLifecycleEvents: async () => [],
    delay: async () => {},
    attempts: 3,
  });
  assert.equal(result.id, "v2");
  assert.equal(isStrictlyNewerPlan(result, { id: "v1", version: 1 }), true);
});

test("initial plan polling tolerates a missing plan before the first server version", async () => {
  let calls = 0;
  const result = await pollForNewPlan("wf-1", null, {
    getPlan: async () => {
      calls += 1;
      if (calls === 1) throw Object.assign(new Error("404"), { status: 404 });
      return { id: "v1", version: 1 };
    },
    getLifecycleEvents: async () => [],
    delay: async () => {},
    attempts: 3,
  });
  assert.equal(result.id, "v1");
  assert.equal(isStrictlyNewerPlan(result, null), true);
});

test("plan polling does not disguise server failures as an empty plan", async () => {
  await assert.rejects(
    pollForNewPlan("wf-1", null, {
      getPlan: async () => { throw Object.assign(new Error("server failed"), { status: 500 }); },
      getLifecycleEvents: async () => [],
      delay: async () => {},
      attempts: 2,
    }),
    /server failed/,
  );
});

test("planning failure events stop polling instead of becoming a generic timeout", async () => {
  await assert.rejects(
    pollForNewPlan("wf-1", null, {
      getPlan: async () => null,
      getLifecycleEvents: async () => [{ event_type: "planning_failed", message: "bridge failed" }],
      delay: async () => {},
      attempts: 3,
    }),
    /bridge failed/,
  );
});

test("execution polling returns only server terminal snapshot", async () => {
  assert.equal(EXECUTION_POLL_ATTEMPTS >= 900, true);
  const snapshots = [{ id: "run-1", status: "running" }, { id: "run-1", status: "completed", token_used: 8 }];
  const updates = [];
  const result = await pollExecutionUntilTerminal("run-1", {
    getExecution: async () => snapshots.shift(),
    getExecutionEvents: async () => [],
    getExecutionArtifacts: async () => [{ id: "artifact-1" }],
    onUpdate: (value) => updates.push(value.execution.status),
    delay: async () => {},
    attempts: 3,
  });
  assert.deepEqual(updates, ["running", "completed"]);
  assert.deepEqual(result, { execution: { id: "run-1", status: "completed", token_used: 8 }, events: [], artifacts: [{ id: "artifact-1" }] });
});

test("the real post-approval agent_ready state can start a workflow", () => {
  assert.equal(canStartWorkflow("agent_ready"), true);
  assert.equal(canStartWorkflow("ready"), true);
  assert.equal(canStartWorkflow("ready", { status: "running" }), false);
  assert.equal(canStartWorkflow("ready", { status: "awaiting_review" }), false);
  assert.equal(canStartWorkflow("awaiting_approval"), false);
});

test("empty evidence arrays render as an honest empty state", () => {
  assert.equal(hasResultData([]), false);
  assert.equal(hasResultData({}), false);
  assert.equal(hasResultData([{ id: "e1" }]), true);
});
