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
  showroomSessionIdFromSearch,
  customerDemandIdFromSearch,
  shouldFetchWorkflowPlan,
} from "../src/architectContract.js";

import {
  canonicalPlanToSimLike,
  simLikeToCanonicalPlan,
} from "../src/architectCanvasAdapter.js";

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
  const source = fs.readFileSync(new URL("../src/pages/ArchitectWorkbenchPage.jsx", import.meta.url), "utf8");
  assert.match(source, /import\s+\{\s*ReactFlow(?:,\s*applyNodeChanges)?\s*\}\s+from\s+["']@xyflow\/react["']/);
  assert.match(source, /<ReactFlow[\s\S]*nodes=\{nodes\}[\s\S]*edges=\{edges\}/);
  assert.match(source, /nodesDraggable=\{simulation\}/);
  assert.match(source, /nodesConnectable=\{false\}/);
  assert.match(source, /SIMULATION/);
  assert.match(source, /projectPlanToCanvas\(plan\)/);
});

test("requirement confirmation actions send structured confirm and revise intents", () => {
  const page = fs.readFileSync(new URL("../src/pages/ArchitectWorkbenchPage.jsx", import.meta.url), "utf8");
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

test("showroom journey hands a confirmed CustomerDemand to Architect", () => {
  const index = fs.readFileSync(new URL("../public/showroom/index.html", import.meta.url), "utf8");
  const journey = fs.readFileSync(new URL("../public/showroom/showroom-journey.js", import.meta.url), "utf8");
  assert.match(index, /showroom-journey\.js/);
  assert.doesNotMatch(index, /legacy\.html/);
  assert.match(journey, /state\.demand\?\.status === ['"]confirmed['"]/);
  assert.match(journey, /\/architect\?customer_demand_id=/);
});

test("App root route uses the destructured authSession", () => {
  const source = fs.readFileSync(new URL("../src/app/App.jsx", import.meta.url), "utf8");
  assert.match(source, /const\s+\{\s*isAuthenticated\s*,\s*authSession\s*\}\s*=\s*useAuth\(\)/);
});

test("an empty workbench can submit the first requirement", () => {
  const source = fs.readFileSync(new URL("../src/pages/ArchitectWorkbenchPage.jsx", import.meta.url), "utf8");
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

test("initial plan polling waits for plan_ready before reading the first server plan", async () => {
  let lifecycleCalls = 0;
  let planCalls = 0;
  let ready = false;
  const result = await pollForNewPlan("wf-1", null, {
    getPlan: async () => {
      planCalls += 1;
      assert.equal(ready, true, "the first plan must not be read while planning is still running");
      return { id: "v1", version: 1 };
    },
    getLifecycleEvents: async () => {
      lifecycleCalls += 1;
      if (lifecycleCalls === 1) return [{ event_type: "planning_queued" }];
      ready = true;
      return [{ event_type: "plan_ready" }];
    },
    delay: async () => {},
    attempts: 3,
  });
  assert.equal(result.id, "v1");
  assert.equal(planCalls, 1);
  assert.equal(isStrictlyNewerPlan(result, null), true);
});

test("revision plan polling does not disguise server failures as an empty plan", async () => {
  await assert.rejects(
    pollForNewPlan("wf-1", { id: "v1", version: 1 }, {
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

test("plan is not requested while a workflow is still clarifying", () => {
  assert.equal(shouldFetchWorkflowPlan({ status: "clarifying" }, { session: { phase: "clarifying" } }), false);
  assert.equal(shouldFetchWorkflowPlan({ status: "awaiting_requirement_confirmation" }, { session: { phase: "awaiting_requirement_confirmation" } }), false);
  assert.equal(shouldFetchWorkflowPlan({ status: "planning" }, { session: { phase: "planning" } }), true);
  assert.equal(shouldFetchWorkflowPlan({ status: "clarifying", active_plan_id: "plan-1" }), true);
});

test("empty evidence arrays render as an honest empty state", () => {
  assert.equal(hasResultData([]), false);
  assert.equal(hasResultData({}), false);
  assert.equal(hasResultData([{ id: "e1" }]), true);
});

test("architect only accepts an explicit showroom business session from the URL", () => {
  assert.equal(
    showroomSessionIdFromSearch("?showroom_session_id=visit-001"),
    "visit-001",
  );
  assert.equal(showroomSessionIdFromSearch("?showroom_session_id="), "");
  assert.equal(showroomSessionIdFromSearch("?session_id=private-hermes"), "");
});

test("architect accepts an explicit customer demand id from the URL", () => {
  assert.equal(customerDemandIdFromSearch("?customer_demand_id=dmd_abc123"), "dmd_abc123");
  assert.equal(customerDemandIdFromSearch("?customer_demand_id=../../bad"), "");
});

test("Sim-like adapter preserves execution semantics and excludes view position", () => {
  const sim = {
    nodes: [
      { id: "n1", type: "agent", data: { name: "Research", parameters: { capability_status: "UNCONNECTED" } }, position: { x: 10, y: 20 } },
      { id: "n2", type: "artifact", data: { name: "Report" }, position: { x: 300, y: 20 } },
    ],
    edges: [{ id: "e1", source: "n1", target: "n2", sourceHandle: "out", targetHandle: "in" }],
    viewport: { x: 1, y: 2, zoom: 0.8 },
  };
  const plan = simLikeToCanonicalPlan(sim);
  assert.deepEqual(plan.nodes, [
    { id: "n1", type: "agent", name: "Research", parameters: { capability_status: "UNCONNECTED" } },
    { id: "n2", type: "artifact", name: "Report", parameters: {} },
  ]);
  assert.deepEqual(plan.edges, [{ id: "e1", source: "n1", target: "n2", sourceHandle: "out", targetHandle: "in" }]);
  assert.deepEqual(simLikeToCanonicalPlan({ ...sim, viewport: { x: 99, y: 99, zoom: 2 } }), plan);
});

test("Sim-like adapter fails closed for unknown node types, fields, dangling edges, and handles", () => {
  assert.throws(() => simLikeToCanonicalPlan({ nodes: [{ id: "n1", type: "mystery", data: {} }], edges: [] }), /unsupported node type/);
  assert.throws(() => simLikeToCanonicalPlan({ nodes: [{ id: "n1", type: "agent", data: {}, extra: true }], edges: [] }), /unknown node field/);
  assert.throws(() => simLikeToCanonicalPlan({ nodes: [{ id: "n1", type: "agent", data: { name: "A" } }], edges: [{ source: "n1", target: "missing" }] }), /dangling edge/);
  assert.throws(() => simLikeToCanonicalPlan({ nodes: [{ id: "n1", type: "agent", data: { name: "A" } }, { id: "n2", type: "artifact", data: { name: "B" } }], edges: [{ source: "n1", target: "n2", sourceHandle: "unknown" }] }), /unknown edge handle/);
});

test("Sim-like adapter rejects undefined execution semantics and never returns LIVE", () => {
  assert.throws(() => simLikeToCanonicalPlan({ nodes: [{ id: "n1", type: "agent", data: { retry: 3 } }], edges: [] }), /unsupported execution semantics/);
  const view = canonicalPlanToSimLike({ nodes: [{ id: "n1", type: "agent", name: "Research", parameters: {} }], edges: [] });
  assert.equal(view.truth, "SIMULATION");
  assert.notEqual(view.truth, "LIVE");
});

test("Sim-like adapter round-trips canonical execution semantics", () => {
  const canonical = {
    nodes: [{ id: "n1", type: "agent", name: "Research", parameters: { capability_status: "UNCONNECTED" } }],
    edges: [],
  };
  assert.deepEqual(simLikeToCanonicalPlan(canonicalPlanToSimLike(canonical)), canonical);
});

test("Gate-2 platform API exposes CAS-safe plan save and rollback helpers", () => {
  const api = fs.readFileSync(new URL("../src/services/platformApi.js", import.meta.url), "utf8");
  assert.match(api, /patchWorkflowPlan\(workflowId, payload\)/);
  assert.match(api, /PATCH/);
  assert.match(api, /rollbackWorkflowPlan\(workflowId, payload\)/);
  assert.match(api, /\/plan\/rollback/);
});

test("Gate-2 PlanCanvas exposes explicit save and keeps execution actions out of the canvas", () => {
  const source = fs.readFileSync(new URL("../src/pages/ArchitectWorkbenchPage.jsx", import.meta.url), "utf8");
  const canvas = source.slice(source.indexOf("function PlanCanvas"), source.indexOf("function DetailDrawer"));
  assert.match(canvas, /保存 SIMULATION 编辑/);
  assert.match(canvas, /request_id/);
  assert.doesNotMatch(canvas, /approveWorkflowPlan|startWorkflow|Runtime|Realtime/);
});

test("Gate-3 exposes a read-only workflow plan versions API", () => {
  const api = fs.readFileSync(new URL("../src/services/platformApi.js", import.meta.url), "utf8");
  assert.match(api, /listWorkflowPlanVersions\(workflowId\)/);
  assert.match(api, /\/plan\/versions/);
});

test("Gate-3 PlanCanvas uses an explicit server-selected rollback target", () => {
  const source = fs.readFileSync(new URL("../src/pages/ArchitectWorkbenchPage.jsx", import.meta.url), "utf8");
  const canvas = source.slice(source.indexOf("function PlanCanvas"), source.indexOf("function DetailDrawer"));
  assert.match(canvas, /listWorkflowPlanVersions/);
  assert.match(canvas, /rollbackWorkflowPlan/);
  assert.match(canvas, /从历史版本回滚/);
  assert.match(canvas, /source_plan_id/);
  assert.doesNotMatch(canvas, /useEffect\([^)]*rollbackWorkflowPlan/);
});
