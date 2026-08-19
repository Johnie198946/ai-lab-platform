import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const source = readFileSync(new URL('../public/showroom/app.js', import.meta.url), 'utf8');

function extractFunction(name) {
  const match = source.match(new RegExp(`function ${name}\\([^)]*\\) \\{[\\s\\S]*?\\n\\}`));
  assert.ok(match, `${name} must exist`);
  return match[0];
}

const sandbox = {};
vm.runInNewContext(
  `${extractFunction('friendlyHermesError')};${extractFunction('hermesFailureStatus')};`
    + 'this.friendlyHermesError=friendlyHermesError;this.hermesFailureStatus=hermesFailureStatus;',
  sandbox,
);

test('DeepSeek 402 errors are explained as an actionable quota problem', () => {
  const raw = "Error code: 402 - {'error': {'message': 'Insufficient Balance'}}";
  assert.match(sandbox.friendlyHermesError(raw), /DeepSeek 模型额度不足/);
  assert.equal(sandbox.hermesFailureStatus(raw), 'quota-required');
});

test('unrelated Hermes errors remain visible without being mislabeled as quota failures', () => {
  assert.equal(sandbox.friendlyHermesError('gateway timeout'), 'gateway timeout');
  assert.equal(sandbox.hermesFailureStatus('gateway timeout'), 'error');
});

test('host preparation is persisted only after a successful completion', () => {
  const starter = source.slice(source.indexOf('async function startHostGreeting'), source.indexOf('async function failControllerHermesTask'));
  assert.doesNotMatch(starter, /host_greeting_initialized:\s*true/);
  const completer = source.slice(source.indexOf('async function completeControllerHermesTask'), source.indexOf('function currentInsight'));
  assert.match(completer, /host_greeting_initialized:\s*true/);
});

test('controller failures release a running insight and expose retry controls', () => {
  assert.match(source, /customer_insight:\s*\{ status: 'failed', warnings: \[detail\] \}/);
  assert.match(source, /data-host-retry/);
  assert.match(source, /重新发起洞察/);
});
