import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const hostSource = await readFile(new URL("../src/features/quantum-workspace/DashiTaskboardHost.jsx", import.meta.url), "utf8");
const hostStyles = await readFile(new URL("../src/features/quantum-workspace/DashiTaskboardHost.css", import.meta.url), "utf8");

test("Dashi host is light-only and forwards the light theme", () => {
  assert.match(hostSource, /return "light"/);
  assert.match(hostSource, /type: "taskboard:theme"/);
  assert.doesNotMatch(hostSource, /prefers-color-scheme: dark/);
  assert.doesNotMatch(hostSource, /MutationObserver/);
});

test("Dashi host placeholder has no dark-mode override", () => {
  assert.match(hostStyles, /background: #f8fafc/);
  assert.doesNotMatch(hostStyles, /prefers-color-scheme: dark/);
  assert.doesNotMatch(hostStyles, /data-theme="dark"/);
});
