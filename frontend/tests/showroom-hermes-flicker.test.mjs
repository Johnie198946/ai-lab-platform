import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

const source = readFileSync(new URL('../public/showroom/app.js', import.meta.url), 'utf8');
const indexSource = readFileSync(new URL('../public/showroom/legacy.html', import.meta.url), 'utf8');

test('background Hermes connection states update indicators without rebuilding the canvas', () => {
  assert.match(source, /function updateHermesStatusIndicators\(\)/);
  assert.match(source, /data-hermes-status-indicator/);
  const handler = source.slice(
    source.indexOf("window.showroomApi?.on('hermes-status'"),
    source.indexOf("window.showroomApi?.on('hermes-ready'"),
  );
  assert.match(handler, /requiresStructuralRender/);
  assert.match(handler, /updateHermesStatusIndicators\(\)/);
});

test('showroom entry point cache-busts both changed Hermes scripts', () => {
  assert.match(indexSource, /showroom-api\.js\?v=20260820-showroom-recovery-v2/);
  assert.match(indexSource, /app\.js\?v=20260821-progress-contract-v1/);
});
