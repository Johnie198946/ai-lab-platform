import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

const app = readFileSync(new URL('../public/showroom/app.js', import.meta.url), 'utf8');
const styles = readFileSync(new URL('../public/showroom/styles.css', import.meta.url), 'utf8');
const index = readFileSync(new URL('../public/showroom/legacy.html', import.meta.url), 'utf8');

test('ending a reception opens a confirmation before the atomic rollover', () => {
  assert.match(app, /结束本次接待？/);
  assert.match(app, /当前接待将归档，并为下一位客户创建全新的 Session/);
  assert.match(app, /data-visit-end-cancel/);
  assert.match(app, /data-visit-end-confirm/);
  assert.match(app, /rolloverVisit\('controller'\)/);
  assert.doesNotMatch(app, /data-visit-rollover/);
  assert.match(styles, /\.visit-end-overlay/);
  assert.match(styles, /\.visit-end-dialog/);
  assert.match(index, /app\.js\?v=20260821-progress-contract-v1/);
  assert.match(index, /showroom-api\.js\?v=20260820-showroom-recovery-v2/);
});

test('session rollover clears reception-only UI state and preserves static displays', () => {
  assert.match(app, /function resetSessionUiState\(nextSession = null\)/);
  assert.match(app, /chatMessages: \[\]/);
  assert.match(app, /reviewStates: \{\}/);
  assert.match(app, /insightAssistantMessages: \[\]/);
  assert.match(app, /selectedArtifact: null/);
  assert.match(app, /const STATIC_DISPLAY_VIEWS = new Set\(\['screen-00', 'screen-01', 'screen-02'\]\)/);
});
