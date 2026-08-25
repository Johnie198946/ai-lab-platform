import assert from "node:assert/strict";
import test from "node:test";
import {
  agencyRunbooks,
  buildAgencyPrompt,
} from "../src/data/agencyRunbooks.js";

test("001 business surface publishes twelve unique runbooks", () => {
  assert.equal(agencyRunbooks.length, 12);
  assert.equal(new Set(agencyRunbooks.map((item) => item.id)).size, 12);
  assert.equal(new Set(agencyRunbooks.map((item) => item.slug)).size, 12);
  for (const runbook of agencyRunbooks) {
    assert.ok(runbook.agents.length >= 3);
    assert.ok(runbook.capabilities.length >= 2);
    assert.ok(runbook.outputs.length >= 3);
  }
});

test("business prompt keeps Agency orchestration above AI Lab capabilities", () => {
  const prompt = buildAgencyPrompt(agencyRunbooks[0], "分析制造企业的停机问题");
  assert.match(prompt, /Agency Agents 业务层/);
  assert.match(prompt, /AI Lab 仅作为能力提供方/);
  assert.match(prompt, /agency-agents-router/);
  assert.match(prompt, /ai_lab_execute/);
  assert.match(prompt, /分析制造企业的停机问题/);
});
