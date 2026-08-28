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
