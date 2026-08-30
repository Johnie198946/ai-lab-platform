import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

import {
  buildBoardColumns,
  buildLifecycleColumns,
  buildStageRail,
  buildScheduleRows,
  layoutProjectGraph,
} from "../src/features/quantum-workspace/quantumProjection.js";
import { workflowIdFromSearch } from "../src/architectContract.js";
import { parseSseFrame, splitSseFrames } from "../src/services/sseFrames.js";
import { restoreTaskMessages } from "../src/features/quantum-workspace/taskChatMessages.js";
import { buildTaskboardRelationProjection, groupCanonicalRelations, qwsTaskMarker } from "../src/features/quantum-workspace/relationProjection.js";

const process = {
  process_revision: 4,
  stages: [
    { id: "s1", name: "概念", order: 0, status: "IN_PROGRESS", progress: 50 },
    { id: "s2", name: "计划", order: 1, status: "NOT_STARTED", progress: 0 },
  ],
  gates: [
    { id: "g1", stage_id: "s1", name: "TR1", node_type: "TR", status: "DONE" },
    { id: "g2", stage_id: "s1", name: "CDCP", node_type: "DCP", status: "NOT_STARTED" },
  ],
  tasks: [
    { id: "t1", stage_id: "s1", title: "需求基线", status: "IN_PROGRESS", planned_start_at: null, planned_finish_at: null },
    { id: "t2", stage_id: "s2", title: "架构基线", status: "PAUSED", planned_start_at: "2027-01-01T00:00:00Z", planned_finish_at: "2027-01-05T00:00:00Z" },
  ],
};

test("board keeps four visible columns and maps PAUSED without inventing state", () => {
  const columns = buildBoardColumns(process);
  assert.deepEqual(columns.map((item) => item.key), ["TODO", "IN_PROGRESS", "BLOCKED", "DONE"]);
  assert.equal(columns[1].tasks[0].id, "t1");
  assert.equal(columns[2].tasks[0].id, "t2");
  assert.equal(columns[2].tasks[0].displayStatus, "PAUSED");
});

test("stage rail preserves TR and DCP semantics", () => {
  const rail = buildStageRail(process);
  assert.deepEqual(rail[0].gates.map((gate) => gate.node_type), ["TR", "DCP"]);
  assert.equal(rail[0].progress, 50);
});

test("schedule marks missing dates unscheduled instead of using today", () => {
  const rows = buildScheduleRows(process);
  assert.equal(rows[0].scheduleStatus, "UNSCHEDULED");
  assert.equal(rows[0].start, null);
  assert.equal(rows[1].scheduleStatus, "SCHEDULED");
});

test("graph layout is deterministic and preserves canonical edge ids", () => {
  const result = layoutProjectGraph({
    nodes: [
      { id: "a", label: "A" },
      { id: "b", label: "B" },
    ],
    edges: [{ id: "e1", source: "a", target: "b" }],
  });
  assert.deepEqual(result.nodes.map((node) => node.position), [
    { x: 80, y: 80 },
    { x: 360, y: 80 },
  ]);
  assert.equal(result.edges[0].id, "e1");
});

test("SSE parser preserves chunk boundaries and flushes a terminal tail frame", () => {
  const first = splitSseFrames(
    'data: {"type":"delta","content":"A"}\r\n\r\n' +
      'data: {"type":"done","answer":"A"}',
  );
  assert.equal(first.frames.length, 1);
  assert.equal(parseSseFrame(first.frames[0]).type, "delta");
  const terminal = splitSseFrames(first.remainder, true);
  assert.equal(terminal.remainder, "");
  assert.deepEqual(parseSseFrame(terminal.frames[0]), { type: "done", answer: "A" });
});

test("task chat history restores terminal errors as failed messages", () => {
  const restored = restoreTaskMessages([
    {
      id: "message-1",
      role: "assistant",
      content: "bridge unavailable",
      event_metadata: { terminal_type: "error" },
    },
  ]);
  assert.equal(restored[0].failed, true);
});

test("Dashi lifecycle parity projects canonical workflow and execution truth into six lanes", () => {
  const lifecycle = buildLifecycleColumns(
    {
      tasks: [
        { id: "t-intake", workflow_id: "wf_intake", workflow_status: "clarifying" },
        { id: "t-run", workflow_id: "wf_run", workflow_status: "ready" },
        { id: "t-review", workflow_id: "wf_review", workflow_status: "running" },
        { id: "t-unconnected", workflow_id: null, workflow_status: "UNCONNECTED" },
      ],
    },
    [
      { id: "wf_intake", status: "clarifying", latest_execution: null },
      { id: "wf_run", status: "ready", latest_execution: { id: "exe-run", status: "running", truth: "LIVE", started_at: "2026-08-27T01:00:00Z", input_tokens: 10, output_tokens: 5, reasoning_tokens: 2, artifact_count: 3, progress: 45, estimated_cost_usd: 0.12 } },
      { id: "wf_review", status: "running", latest_execution: { id: "exe-review", status: "awaiting_review", truth: "LIVE", hermes_session_id: "session-1", artifact_count: 2 } },
    ],
  );

  assert.deepEqual(lifecycle.map((column) => column.key), ["intake", "planning", "execution", "review", "completed", "attention"]);
  assert.deepEqual(lifecycle.map((column) => column.tasks.length), [1, 0, 1, 1, 0, 1]);
  assert.equal(lifecycle[2].tasks[0].truth, "LIVE");
  assert.equal(lifecycle[2].tasks[0].tokenUsed, 17);
  assert.equal(lifecycle[2].tasks[0].artifactCount, 3);
  assert.equal(lifecycle[2].tasks[0].estimatedCostUsd, 0.12);
  assert.equal(lifecycle[5].tasks[0].truth, "UNCONNECTED");
});

test("queued LIVE claims stay PLAN until a provider run receipt exists", () => {
  const lifecycle = buildLifecycleColumns(
    { tasks: [{ id: "t1", workflow_id: "wf_queue" }] },
    [{ id: "wf_queue", status: "queued", latest_execution: { id: "exe-q", status: "queued", truth: "LIVE" } }],
  );
  assert.equal(lifecycle[2].tasks[0].truth, "PLAN");
});

test("QuantumWorkspace opens a specifically requested canonical workflow", () => {
  assert.equal(workflowIdFromSearch("?workflow_id=wf_abc-123"), "wf_abc-123");
  assert.equal(workflowIdFromSearch("?workflow_id=../../bad"), "");
});

test("QWS relation snapshot is canonical and Taskboard drift never replaces it", () => {
  const digest = {
    canonical_source: "QWS_PROCESS_SNAPSHOT",
    canonical_source_hash: "a".repeat(64),
    external_projection_mode: "READ_ONLY_CONSUMER_REQUIRED",
    entries: [{ relation_type: "blocks", effective_task_id: "qws-target", title: "目标" }],
  };
  const qwsTasks = [{ id: "qws-target" }, { id: "qws-extra" }];
  const dashiTarget = { id: "d-target", labels: [qwsTaskMarker("qws-target")] };
  const dashiExtra = { id: "d-extra", labels: [qwsTaskMarker("qws-extra")] };
  const projection = buildTaskboardRelationProjection({
    digest,
    qwsTasks,
    dashiTask: { id: "d-root", relations: { blocks: [dashiTarget], related: [dashiExtra] } },
    allTasks: [dashiTarget, dashiExtra],
  });
  assert.equal(projection.status, "DRIFT");
  assert.equal(projection.canonical_hash, "a".repeat(64));
  assert.equal(projection.taskboard_mode, "READ_ONLY_CONSUMER_REQUIRED");
  assert.deepEqual(projection.extra_in_taskboard, ["related:qws-extra"]);
  assert.equal(groupCanonicalRelations(projection.canonical_entries).blocks[0].effective_task_id, "qws-target");
  assert.equal(groupCanonicalRelations(projection.canonical_entries).related.length, 0);
});

test("task drawer exposes server-backed Challenge decisions and relation drift", () => {
  const drawer = readFileSync(new URL("../src/features/quantum-workspace/TaskChatDrawer.jsx", import.meta.url), "utf8");
  const api = readFileSync(new URL("../src/services/platformApi.js", import.meta.url), "utf8");
  assert.match(drawer, /TaskGovernancePanel/);
  assert.match(drawer, /填写决策理由（必填）/);
  assert.match(drawer, /Taskboard 投影/);
  assert.match(drawer, /字段级合并预览/);
  assert.match(drawer, /验收通过/);
  assert.match(api, /resolveProjectTaskChallenge/);
  assert.match(api, /createProjectTaskMergePreview/);
  assert.match(api, /decideProjectTaskDeliveryManifest/);
  assert.match(api, /challenge-reviews\/\$\{reviewId\}\/decision/);
});
