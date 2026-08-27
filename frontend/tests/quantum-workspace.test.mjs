import test from "node:test";
import assert from "node:assert/strict";

import {
  buildBoardColumns,
  buildStageRail,
  buildScheduleRows,
  layoutProjectGraph,
} from "../src/features/quantum-workspace/quantumProjection.js";
import { parseSseFrame, splitSseFrames } from "../src/services/sseFrames.js";
import { restoreTaskMessages } from "../src/features/quantum-workspace/taskChatMessages.js";

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
