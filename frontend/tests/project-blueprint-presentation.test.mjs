import test from "node:test";
import assert from "node:assert/strict";

import {
  extractProjectBlueprint,
  extractProjectBlueprintProtocol,
  projectPlanningVisibleAnswer,
} from "../src/features/quantum-workspace/projectBlueprintPresentation.js";

test("exposes a streaming project_blueprint protocol instead of hiding it", () => {
  const content = "项目蓝图正在整理。\n```project_blueprint\n{\n  \"project_goal\": \"日本行程\",\n  \"stages\":";
  assert.deepEqual(extractProjectBlueprintProtocol(content), {
    payload: '{\n  "project_goal": "日本行程",\n  "stages":',
    complete: false,
  });
  assert.equal(projectPlanningVisibleAnswer(content, { pending: true }), "项目蓝图正在整理。");
});

test("formats and exposes the complete dispatchable protocol", () => {
  const content = '```project_blueprint\n{"project_goal":"日本行程","stages":[],"tasks":[]}\n```';
  const blueprint = extractProjectBlueprint(content);
  const protocol = extractProjectBlueprintProtocol(content);
  assert.equal(blueprint.project_goal, "日本行程");
  assert.equal(protocol.complete, true);
  assert.equal(protocol.payload, JSON.stringify(blueprint, null, 2));
});

test("does not mistake ordinary assistant text for a protocol", () => {
  assert.equal(extractProjectBlueprintProtocol("还需要确认预算和日期。"), null);
});