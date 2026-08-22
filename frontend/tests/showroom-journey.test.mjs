import assert from 'node:assert/strict';
import { existsSync, readFileSync } from 'node:fs';
import test from 'node:test';

const root = new URL('../public/showroom/', import.meta.url);
const html = readFileSync(new URL('index.html', root), 'utf8');
const script = readFileSync(new URL('showroom-journey.js', root), 'utf8');
const updateScript = readFileSync(new URL('../../scripts/update.sh', import.meta.url), 'utf8');

test('new default entry is isolated from the legacy nine-screen app', () => {
  assert.match(html, /showroom-journey\.js/);
  assert.doesNotMatch(html, /app\.js/);
  assert.match(readFileSync(new URL('legacy.html', root), 'utf8'), /app\.js/);
});

test('journey defines S0 through S10 and the five evidence contract fields', () => {
  for (let index = 0; index <= 10; index += 1) assert.match(script, new RegExp(`['"]S${index}['"]`));
  for (const field of ['customerQuestion', 'screenGoal', 'coreArtifact', 'chat', 'agentDesign', 'businessSystemNeed', 'tokenFactoryFeature', 'hardwareCommercialValue', 'evidenceStatus']) {
    assert.match(script, new RegExp(field));
  }
});

test('CustomerDemand API is server-backed and the approved panorama is present', () => {
  assert.match(script, /\/api\/v1\/demands/);
  assert.match(script, /POST|PATCH/);
  assert.match(script, /\/confirm/);
  assert.ok(existsSync(new URL('assets/manufacturing-panorama.png', root)));
  assert.doesNotMatch(script, /localStorage\.setItem\([^)]*demand/i);
  assert.doesNotMatch(script, /LIVE[^\n]*(台|卡|%)/);
});

test('S3 and S4 use structured demand fields and the shared showroom API', () => {
  for (const field of ['business_scene', 'overall_goal', 'stakeholders', 'requirement_items', 'conflict_notes', 'constraints', 'acceptance_criteria']) {
    assert.match(script, new RegExp(field));
  }
  assert.match(script, /window\.showroomApi\.init\(\)/);
  assert.match(script, /window\.showroomApi\.submitHermesPrompt/);
  assert.match(html, /showroom-api\.js/);
  assert.doesNotMatch(script, /JsonRpcGatewayClient/);
});

test('deployment prepares runtime contracts and writes marker only after hard audit', () => {
  const restart = updateScript.indexOf('docker compose up -d --build');
  const health = updateScript.indexOf('if [ -z "${status:-}" ]');
  const runtimeDirs = updateScript.indexOf('mkdir -p data/manifests data/runtime');
  const matrixLink = updateScript.indexOf('ln -s vault/knowledge_matrix.json data/knowledge_matrix.json');
  const audit = updateScript.indexOf('audit_runtime_contracts.py');
  const marker = updateScript.indexOf('mv -f "$marker_tmp" .deployed-sha');
  assert.ok(restart >= 0 && health > restart);
  assert.ok(runtimeDirs > health && matrixLink > runtimeDirs && audit > matrixLink);
  assert.ok(marker > audit);
  assert.match(updateScript, /\[ "\$#" -ne 1 \]/);
  assert.match(updateScript, /\^\[0-9a-fA-F\]\{40\}\$/);
  assert.doesNotMatch(updateScript, /refs\/heads\/main/);
  assert.doesNotMatch(updateScript, /audit_runtime_contracts[^\n]*\|\|/);
  assert.match(updateScript, /trap cleanup EXIT/);
});
