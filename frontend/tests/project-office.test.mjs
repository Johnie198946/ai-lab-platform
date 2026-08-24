import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

import {
  architectSearchWithView,
  architectViewFromSearch,
  architectWorkflowForContext,
  projectOfficeProjection,
} from "../src/architectContract.js";
import {
  artifactPresentation,
  parseStructuredArtifact,
} from "../src/features/project-office/artifactPresentation.js";

const plan = {
  dsl: {
    nodes: [
      {
        id: "research",
        name: "市场证据",
        inputs: ["客户目标"],
        outputs: ["证据包"],
        parameters: {
          role_ids: ["researcher", "reviewer"],
          agent_id: "plan-profile-is-not-runtime",
          capability_status: "EXECUTABLE",
          execution_enabled: true,
        },
      },
      {
        id: "gate",
        name: "人工决策门",
        parameters: {
          role_ids: ["approver"],
          role: "决策复核负责人",
          input_artifacts: ["证据包"],
          output_deliverables: ["批准记录"],
          capability_status: "UNCONNECTED",
          execution_enabled: false,
        },
      },
      {
        id: "write",
        name: "形成方案",
        parameters: { role_ids: ["writer"], execution_enabled: true },
      },
    ],
  },
};

test("Office projection creates seats only from server plan nodes and keeps roles separate from runtime agents", () => {
  const projection = projectOfficeProjection({
    workflow: { id: "wf-1", title: "客户洞察", status: "running" },
    plan,
    execution: {
      id: "exe-1",
      truth: "LIVE",
      status: "running",
      started_at: "2026-08-23T00:00:00Z",
      nodes: [
        { id: "run-row-1", node_id: "research", agent_id: "agent-runtime-7", status: "running" },
        { id: "run-row-2", node_id: "write", agent_id: "agent-runtime-7", status: "pending" },
        { id: "orphan", node_id: "not-in-plan", agent_id: "orphan-agent", status: "running" },
      ],
    },
    events: [],
    artifacts: [],
  });

  assert.equal(projection.title, "客户洞察");
  assert.deepEqual(projection.seats.map((seat) => seat.id), ["research", "gate", "write"]);
  assert.deepEqual(projection.seats[0].roleIds, ["researcher", "reviewer"]);
  assert.equal(projection.seats[0].runtimeAgentId, "agent-runtime-7");
  assert.notEqual(projection.seats[0].runtimeAgentId, projection.seats[0].roleIds[0]);
  assert.equal(projection.seats[0].status, "running");
  assert.equal(projection.seats[1].status, "UNCONNECTED");
  assert.equal(projection.seats[1].businessRole, "决策复核负责人");
  assert.deepEqual(projection.seats[1].input, ["证据包"]);
  assert.deepEqual(projection.seats[1].expectedOutput, ["批准记录"]);
  assert.equal(projection.seats[2].status, "waiting");
  assert.deepEqual(projection.seats.map((seat) => seat.truthState.status), ["LIVE", "UNCONNECTED", "LIVE"]);
});

test("plan-only seats show the real workflow goal when a node has no explicit input", () => {
  const projection = projectOfficeProjection({
    workflow: { id: "wf-goal", description: "为客户形成可审阅的业务方案", status: "planning" },
    plan: { dsl: { nodes: [{ id: "n1", name: "方案节点", parameters: {} }] } },
  });

  assert.deepEqual(projection.seats[0].input, ["为客户形成可审阅的业务方案"]);
  assert.equal(projection.seats[0].status, "planned");
});

test("real artifacts create an output card and a transfer only along a server edge", () => {
  const projection = projectOfficeProjection({
    plan: {
      dsl: {
        nodes: [
          { id: "source", name: "检索", parameters: { output_deliverables: ["证据包"] } },
          { id: "next", name: "分析", parameters: {} },
        ],
        edges: [{ source: "source", target: "next" }],
      },
    },
    execution: { id: "exe-1", status: "completed", truth: "LIVE", started_at: "2026-08-23T00:00:00Z" },
    artifacts: [{ id: "artifact-1", title: "证据包", metadata: { source_node_id: "source" } }],
  });

  assert.deepEqual(projection.seats[0].artifacts.map((item) => item.title), ["证据包"]);
  assert.deepEqual(projection.transfers.map((item) => [item.sourceNodeId, item.targetNodeId]), [["source", "next"]]);
});

test("artifact presentation recognizes markdown, Word, charts, topology, and flowcharts from real metadata", () => {
  assert.equal(artifactPresentation({ relative_path: "outputs/report.md" }).type, "markdown");
  assert.equal(artifactPresentation({ relative_path: "outputs/review.docx" }).type, "word");
  assert.equal(artifactPresentation({ metadata: { render_type: "chart" }, relative_path: "outputs/data.json" }).type, "chart");
  assert.equal(artifactPresentation({ metadata: { render_type: "topology" }, title: "园区网络拓扑图", relative_path: "outputs/model.json" }).type, "topology");
  assert.equal(artifactPresentation({ metadata: { render_type: "flowchart" }, title: "需求审批流程图", relative_path: "outputs/model.json" }).type, "flowchart");
  assert.equal(artifactPresentation({ mime_type: "text/csv", extension: "csv", relative_path: "outputs/table.csv" }).type, "data");
  assert.equal(artifactPresentation({ source_kind: "word", relative_path: "outputs/facts.md" }).type, "markdown");
  assert.equal(artifactPresentation({ title: "Word 报告", extension: "md", relative_path: "outputs/facts" }).type, "markdown");
  assert.equal(artifactPresentation({ relative_path: "outputs/final" }).type, "file");
});

test("structured artifact parsing accepts real JSON objects and rejects prose", () => {
  assert.deepEqual(parseStructuredArtifact('{"labels":["A"],"values":[3]}'), { labels: ["A"], values: [3] });
  assert.equal(parseStructuredArtifact("# 普通 Markdown"), null);
  assert.equal(parseStructuredArtifact("[]"), null);
  assert.equal(parseStructuredArtifact(`{"padding":"${"x".repeat(600_000)}"}`), null);
});

test("truth badges remain conservative for plan-only, replay, simulation, and malformed execution data", () => {
  assert.deepEqual(
    projectOfficeProjection({ plan, execution: null }).seats.map((seat) => seat.truthState.status),
    ["PLAN", "UNCONNECTED", "PLAN"],
  );
  assert.equal(projectOfficeProjection({ plan, execution: { id: "x", truth: "REPLAY", nodes: [{ node_id: "research" }] } }).seats[0].truthState.status, "REPLAY");
  assert.equal(projectOfficeProjection({ plan, execution: { id: "x", truth: "SIMULATION", nodes: [{ node_id: "research" }] } }).seats[0].truthState.status, "SIMULATION");
  assert.equal(projectOfficeProjection({ plan, execution: { id: "x", truth: "LIVE", status: "queued", nodes: [{ node_id: "research", status: "pending" }] } }).seats[0].truthState.status, "PLAN");
  assert.equal(projectOfficeProjection({ plan, execution: { id: "x", truth: "LIVE", status: "running", nodes: [{ node_id: "research", status: "running" }] } }).seats[0].truthState.status, "PLAN");
  assert.equal(projectOfficeProjection({ plan, execution: { id: "x", truth: "LIVE", status: "running", started_at: "2026-08-23T00:00:00Z", nodes: [{ node_id: "research", status: "running" }] } }).seats[0].truthState.status, "LIVE");
  assert.equal(projectOfficeProjection({ plan, execution: { id: "x", truth: "unexpected", nodes: [{ node_id: "research" }] } }).seats[0].truthState.status, "PLAN");
  assert.deepEqual(projectOfficeProjection({ workflow: {}, plan: { dsl: { nodes: {} } }, execution: { nodes: "bad" }, events: {}, artifacts: null }).seats, []);
});

test("Office status vocabulary preserves every honest server state and root execution disablement", () => {
  const statuses = ["planned", "running", "blocked", "failed", "done", "succeeded", "cancelled", "awaiting_review"];
  const statusPlan = {
    dsl: {
      nodes: [
        ...statuses.map((status) => ({ id: status, name: status, parameters: { execution_enabled: true } })),
        { id: "root-reference", name: "root reference", execution_disabled: true },
        { id: "root-unconnected", name: "root unconnected", capability_status: "UNCONNECTED" },
      ],
    },
  };
  const projection = projectOfficeProjection({
    plan: statusPlan,
    execution: {
      id: "exe-status",
      truth: "LIVE",
      status: "running",
      started_at: "2026-08-23T00:00:00Z",
      nodes: statuses.map((status) => ({ node_id: status, status })),
    },
  });

  assert.deepEqual(projection.seats.slice(0, statuses.length).map((seat) => seat.status), statuses);
  assert.equal(projection.seats.at(-2).status, "reference");
  assert.equal(projection.seats.at(-2).truthState.status, "UNCONNECTED");
  assert.equal(projection.seats.at(-1).status, "UNCONNECTED");
  assert.equal(projection.seats.at(-1).truthState.status, "UNCONNECTED");
});

test("events map by explicit node id and retain their real ids without fabricated activity", () => {
  const eventForResearch = { id: 41, type: "node_started", message: "检索已开始", payload: { node_id: "research" } };
  const newerForResearch = { event_id: "evt-42", event_type: "tool_complete", message: "证据已返回", metadata: { source_node_id: "research" } };
  const positionalTrap = { id: 99, message: "不能按位置映射" };
  const missingReceipt = { type: "tool_complete", message: "没有事件回执不能显示", payload: { node_id: "write" } };
  const projection = projectOfficeProjection({ plan, execution: { id: "exe", truth: "LIVE", nodes: [{ node_id: "research", status: "succeeded" }] }, events: [eventForResearch, positionalTrap, newerForResearch, missingReceipt] });

  assert.equal(projection.seats[0].lastEvent, newerForResearch);
  assert.equal(projection.seats[0].lastEvent.event_id, "evt-42");
  assert.equal(projection.seats[1].lastEvent, null);
  assert.equal(projection.seats[2].lastEvent, null);
  assert.doesNotMatch(JSON.stringify(projection), /thinking|busy/i);
});

test("projection exposes only server-backed phase-zero identity and cursor fields", () => {
  const projection = projectOfficeProjection({
    workflow: { id: "wf-identity", title: "投影合同", status: "agent_ready", updated_at: "2026-08-23T00:01:00Z" },
    plan: { id: "plan-identity", version: 7, frozen_at: "2026-08-23T00:00:30Z", capability: { status: "CONNECTED", truth: "LIVE", checked_at: "2026-08-23T00:00:45Z" }, dsl: { nodes: [{ id: "n1" }] } },
    execution: { id: "exe-identity", truth: "LIVE", status: "running", started_at: "2026-08-23T00:00:45Z", snapshot_version: "snap-9", nodes: [{ node_id: "n1", status: "running" }] },
    connectionState: "CONNECTED",
    events: [
      { id: 4, type: "node_started", payload: { node_id: "n1" } },
      { id: 9, type: "tool_complete", payload: { node_id: "n1" } },
    ],
  });

  assert.equal(projection.schemaVersion, "office-projection/v1");
  assert.equal(projection.workflowId, "wf-identity");
  assert.equal(projection.planId, "plan-identity");
  assert.equal(projection.executionId, "exe-identity");
  assert.equal(projection.snapshotVersion, "snap-9");
  assert.equal(projection.cursor, 9);
  assert.equal(projection.latestSeq, 9);
  assert.equal(projection.truthMode, "LIVE");
  assert.equal(projection.connectionState, "CONNECTED");
  assert.equal(projection.updatedAt, "2026-08-23T00:01:00Z");
  assert.equal(projection.approvalState, "APPROVED");
  assert.equal(projection.governanceState, "CONNECTED");
  assert.equal(projection.governanceTruth, "LIVE");
  assert.equal(projection.governanceCheckedAt, "2026-08-23T00:00:45Z");

  const absent = projectOfficeProjection({ plan: { dsl: { nodes: [] } } });
  assert.equal(absent.snapshotVersion, null);
  assert.equal(absent.cursor, null);
  assert.equal(absent.truthMode, "UNCONNECTED");
  assert.equal(absent.connectionState, "UNCONNECTED");
});

test("artifacts map only by an explicit node reference or unique explicit runtime agent binding", () => {
  const direct = { id: "a1", title: "证据包", metadata: { source_node_id: "research" } };
  const uniqueAgent = { id: "a2", title: "审批记录", metadata: { agent_id: "gate-agent" } };
  const ambiguousAgent = { id: "a3", title: "共享代理产物", metadata: { agent_id: "shared-agent" } };
  const positionalTrap = { id: "a4", title: "无来源工件" };
  const payloadTrap = { id: "a5", title: "payload 不是获准来源", payload: { node_id: "write" } };
  const projection = projectOfficeProjection({
    plan,
    execution: {
      id: "exe",
      truth: "LIVE",
      nodes: [
        { node_id: "research", agent_id: "shared-agent", status: "done" },
        { node_id: "gate", agent_id: "gate-agent", status: "awaiting_review" },
        { node_id: "write", agent_id: "shared-agent", status: "done" },
      ],
    },
    artifacts: [direct, uniqueAgent, ambiguousAgent, positionalTrap, payloadTrap],
  });

  assert.deepEqual(projection.seats[0].artifacts, [direct]);
  assert.deepEqual(projection.seats[1].artifacts, [uniqueAgent]);
  assert.deepEqual(projection.seats[2].artifacts, []);
  assert.deepEqual(projection.artifacts, [direct, uniqueAgent, ambiguousAgent, positionalTrap, payloadTrap]);
});

test("architect view helpers validate view names and preserve every other query parameter", () => {
  assert.equal(architectViewFromSearch("?customer_demand_id=dmd_1&view=office&x=two", "workbench"), "office");
  assert.equal(architectViewFromSearch("?view=unknown", "office"), "office");
  assert.equal(architectViewFromSearch("", "unknown"), "workbench");

  const officeSearch = architectSearchWithView("?customer_demand_id=dmd_1&x=two&x=three", "office");
  const officeParams = new URLSearchParams(officeSearch);
  assert.equal(officeParams.get("view"), "office");
  assert.equal(officeParams.get("customer_demand_id"), "dmd_1");
  assert.deepEqual(officeParams.getAll("x"), ["two", "three"]);
  assert.equal(new URLSearchParams(architectSearchWithView("?keep=yes", "invalid")).get("view"), "workbench");
});

test("Showroom context selects only its bound workflow and never falls back to an unrelated first row", () => {
  const unrelated = { id: "wf-old", requirements_snapshot: { clarification_mode: "dynamic" } };
  const demandBound = { id: "wf-demand", requirements_snapshot: { customer_demand: { source: { demand_id: "dmd_1" } } } };
  const showroomBound = { id: "wf-showroom", requirements_snapshot: { showroom_context: { source: { session_id: "visit-7" } } } };
  const rows = [unrelated, demandBound, showroomBound];

  assert.equal(architectWorkflowForContext(rows, { customerDemandId: "dmd_1" }), demandBound);
  assert.equal(architectWorkflowForContext(rows, { showroomSessionId: "visit-7" }), showroomBound);
  assert.equal(architectWorkflowForContext(rows, { customerDemandId: "dmd_missing" }), null);
  assert.equal(architectWorkflowForContext(rows, {}), unrelated);
});

test("Office UI is server-dynamic, read-only, accessible, and free of a fixed-height clipped scene", () => {
  const source = fs.readFileSync(new URL("../src/features/project-office/ProjectOfficeView.jsx", import.meta.url), "utf8");
  const styles = fs.readFileSync(new URL("../src/features/project-office/ProjectOfficeView.css", import.meta.url), "utf8");

  assert.match(source, /projection\.seats\.map/);
  assert.match(source, /<button[\s\S]*className="office-seat/);
  assert.match(source, /aria-label=/);
  assert.match(source, /aria-pressed=/);
  assert.match(source, /切换到工作台/);
  assert.match(source, /projection\.truthMode/);
  assert.match(source, /UNCONNECTED/);
  assert.doesNotMatch(source, /createWorkflow|answerClarification|approveWorkflowPlan|startWorkflow|\bfetch\s*\(|axios\.|platformApi/);
  assert.doesNotMatch(source, /张明|林薇|陈浩|周岑|王芳|刘静|Project Lead|Requirement Analyst/);
  assert.match(styles, /min-height:\s*48px/);
  assert.match(styles, /grid-template-columns:\s*repeat\(3/);
  assert.match(styles, /prefers-reduced-motion:\s*reduce/);
  assert.doesNotMatch(styles, /\.office-(?:scene|stage)[^{]*\{[^}]*height:\s*\d+px/s);
  assert.doesNotMatch(styles, /\.office-(?:scene|stage)[^{]*\{[^}]*overflow:\s*hidden/s);
  assert.doesNotMatch(styles, /linear-gradient|radial-gradient|backdrop-filter/);
});

test("Office detail sheet starts closed and remains closed after the close action", () => {
  const source = fs.readFileSync(new URL("../src/features/project-office/ReferenceOfficeView.jsx", import.meta.url), "utf8");

  assert.match(source, /useState\(\"\"\)/);
  assert.match(source, /const selected = seats\.find\(\(seat\) => seat\.id === selectedId\) \|\| null/);
  assert.match(source, /if \(selectedId && !seats\.some\(\(seat\) => seat\.id === selectedId\)\) setSelectedId\(""\)/);
  assert.match(source, /onClose=\{\(\) => setSelectedId\(""\)\}/);
});

test("Office artifact gallery opens real content with dedicated accessible previews", () => {
  const source = fs.readFileSync(new URL("../src/features/project-office/ReferenceOfficeView.jsx", import.meta.url), "utf8");
  const api = fs.readFileSync(new URL("../src/services/platformApi.js", import.meta.url), "utf8");
  const styles = fs.readFileSync(new URL("../src/features/project-office/ReferenceOfficeView.css", import.meta.url), "utf8");

  assert.match(source, /ArtifactGallery/);
  assert.match(source, /ArtifactPreview/);
  assert.match(source, /ReactMarkdown/);
  assert.match(source, /platformApi\.getArtifactContent/);
  assert.match(source, /role="dialog"/);
  assert.doesNotMatch(source, /dangerouslySetInnerHTML|<iframe/);
  assert.match(api, /getArtifactContent\(executionId, artifactId\)/);
  assert.match(styles, /reference-artifact-gallery/);
  assert.match(styles, /reference-artifact-preview--word/);
  assert.match(styles, /reference-structured-preview/);
  assert.match(source, /typeof value === "number"/);
  assert.match(source, /node && typeof node === "object"/);
  assert.match(source, /edge && typeof edge === "object"/);
});

test("Architect integrates the view toggle without replacing Workbench actions", () => {
  const source = fs.readFileSync(new URL("../src/pages/ArchitectWorkbenchPage.jsx", import.meta.url), "utf8");
  assert.match(source, /isShowroomAccount\(authSession\?\.user\)/);
  assert.match(source, /architectViewFromSearch/);
  assert.match(source, /architectSearchWithView/);
  assert.match(source, /architectWorkflowForContext/);
  assert.match(source, /已登录/);
  assert.doesNotMatch(source, />已连接</);
  assert.match(source, /<ProjectOfficeView/);
  assert.match(source, /error=\{error\}/);
  assert.match(source, /Office/);
  assert.match(source, /Workbench/);
  assert.match(source, /platformApi\.createWorkflow/);
  assert.match(source, /platformApi\.answerClarification/);
  assert.match(source, /platformApi\.approveWorkflowPlan/);
  assert.match(source, /platformApi\.startWorkflow/);
});
