import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const ganttSource = readFileSync(new URL("../web/src/components/GanttView.tsx", import.meta.url), "utf8");
const styles = readFileSync(new URL("../web/src/styles.css", import.meta.url), "utf8");

function cssBlock(selector, marker = "") {
  const escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const matches = [...styles.matchAll(new RegExp(`${escaped}\\s*\\{([\\s\\S]*?)\\}`, "g"))];
  assert.ok(matches.length, `missing CSS block for ${selector}`);
  const match = marker ? matches.find((candidate) => candidate[1].includes(marker)) : matches.at(-1);
  assert.ok(match, `missing CSS block for ${selector} containing ${marker}`);
  return match[1];
}

test("gantt uses the shared centered workspace canvas without page overflow", () => {
  const ganttView = cssBlock(".gantt-view", "display: flex");
  const canvasShell = cssBlock(".gantt-canvas-shell", "width: min(100%, 1840px)");
  assert.match(ganttView, /padding: 0 clamp\(8px, 2vw, 28px\) clamp\(8px, 2vw, 24px\)/);
  assert.match(ganttView, /overflow: hidden/);
  assert.match(canvasShell, /width: min\(100%, 1840px\)/);
  assert.match(canvasShell, /min-width: 0/);
  assert.match(canvasShell, /margin-inline: auto/);
  assert.match(canvasShell, /overflow: hidden/);
});

test("gantt keeps wide timelines inside a visible local scrollbar", () => {
  assert.match(ganttSource, /instance\.config\.scroll_size = 10/);
  assert.match(cssBlock(".gantt_hor_scroll"), /height: 10px !important/);
  assert.match(cssBlock(".gantt_hor_scroll"), /scrollbar-width: thin/);
  assert.doesNotMatch(cssBlock(".gantt_hor_scroll"), /scrollbar-width: none/);
});

test("gantt title grid yields usable timeline space at compact widths", () => {
  assert.match(ganttSource, /const compact = width < 720/);
  assert.match(ganttSource, /const minGridWidth = compact \? 190 : medium \? 240 : 320/);
  assert.match(ganttSource, /const maxGridWidth = compact \? 240 : medium \? 360 : 460/);
  assert.match(ganttSource, /const ratio = compact \? 0\.44 : medium \? 0\.34 : 0\.3/);
  assert.match(cssBlock(".gantt-toolbar-controls"), /flex: 0 0 auto/);
});

test("gantt explains that it is the taskboard schedule and exposes its visual grammar", () => {
  assert.match(ganttSource, /任务排期与前后依赖/);
  assert.match(ganttSource, /前面任务看板中的同一批任务/);
  assert.match(ganttSource, /横条：任务起止时间/);
  assert.match(ganttSource, /箭头：前置任务 → 后续任务/);
  assert.match(ganttSource, /左侧按状态分组，并显示项目阶段、负责人和日期/);
  assert.match(styles, /\.gantt-context/);
  assert.match(styles, /\.gantt-legend/);
});

test("gantt rows connect canonical project stages, owners, dates, and dependencies", () => {
  assert.match(ganttSource, /qwsTaskContext/);
  assert.match(ganttSource, /taskboardStageName/);
  assert.match(ganttSource, /taskboardAssigneeName/);
  assert.match(ganttSource, /taskboardScheduleLabel/);
  assert.match(ganttSource, /taskboardDependencyLabel/);
  assert.match(ganttSource, /按状态/);
  assert.match(ganttSource, /前置 \$\{blockedByCount\}/);
  assert.match(ganttSource, /后续 \$\{blocksCount\}/);
});

test("short gantt bars prioritize the task title over the assignee avatar", () => {
  const titleIndex = ganttSource.indexOf('<span class="gantt-bar-copy">');
  const avatarIndex = ganttSource.indexOf('<i class="gantt-bar-assignee');
  assert.ok(titleIndex > 0 && avatarIndex > titleIndex);
  assert.match(styles, /@container \(max-width: 138px\)/);
  assert.match(styles, /\.gantt-bar-assignee \{ display: none; \}/);
});
