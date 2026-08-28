import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const hostSource = await readFile(new URL("../src/features/quantum-workspace/DashiTaskboardHost.jsx", import.meta.url), "utf8");
const hostStyles = await readFile(new URL("../src/features/quantum-workspace/DashiTaskboardHost.css", import.meta.url), "utf8");

test("Dashi host follows explicit or system theme and forwards runtime changes", () => {
  assert.match(hostSource, /data-theme/);
  assert.match(hostSource, /prefers-color-scheme: dark/);
  assert.match(hostSource, /type: "taskboard:theme"/);
  assert.match(hostSource, /addEventListener\?\.\("change"/);
  assert.match(hostSource, /MutationObserver/);
});

test("Dashi host placeholder is light by default with dark-mode overrides", () => {
  assert.match(hostStyles, /background: #f8fafc/);
  assert.match(hostStyles, /@media \(prefers-color-scheme: dark\)/);
  assert.match(hostStyles, /data-theme="dark"/);
});
