import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const source = readFileSync(new URL('../public/showroom/app.js', import.meta.url), 'utf8');
const helperSource = source.match(
  /function hasDemandConfirmationContent\(demand = \{\}\) \{[\s\S]*?\n\}/,
)?.[0];

assert.ok(helperSource, 'demand confirmation visibility helper must exist');
const sandbox = { currentDemandDocument: () => ({}) };
vm.runInNewContext(`${helperSource}; this.hasDemandConfirmationContent = hasDemandConfirmationContent;`, sandbox);
const hasContent = sandbox.hasDemandConfirmationContent;

test('an empty demand does not display the confirmation sheet', () => {
  assert.equal(hasContent({}), false);
  assert.equal(hasContent({ completeness: 0, core_problem: '   ' }), false);
});

test('real demand content displays the confirmation sheet', () => {
  assert.equal(hasContent({ core_problem: '降低产线换模停机时间' }), true);
  assert.equal(hasContent({ completeness: 20 }), true);
  assert.equal(hasContent({ confirmed: true }), true);
});

test('the confirmation sheet is conditionally mounted instead of hidden with CSS', () => {
  assert.match(source, /const demandSheet = showDemandSheet \?/);
  assert.match(source, /: '';\n  return `<div class="screen">/);
  assert.match(source, /conversation-only/);
});

test('recognized documents use the controlled renderer registry', () => {
  assert.match(source, /const demandSectionRegistry = \{/);
  for (const type of ['facts', 'goal', 'non_goals', 'constraints', 'acceptance', 'solution_direction', 'unknown']) {
    assert.match(source, new RegExp(`${type}:`));
  }
  assert.match(source, /window\.showroomApi\.extractDemand\(content\)/);
  assert.match(source, /<details class="demand-document">/);
});
