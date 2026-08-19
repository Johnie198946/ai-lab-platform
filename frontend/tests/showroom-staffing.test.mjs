import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

const app = readFileSync(new URL('../public/showroom/app.js', import.meta.url), 'utf8');
const styles = readFileSync(new URL('../public/showroom/styles.css', import.meta.url), 'utf8');

test('confirmed demand enters the dedicated 003.5 staffing route', () => {
  assert.match(app, /await beginInsightFlow\(demand\)/);
  assert.match(app, /setView\('screen-03-team'\)/);
  assert.match(app, /'screen-03-team': staffingView/);
  assert.doesNotMatch(app, /generateInsight\(\);\s*state\.session = await window\.showroomApi\.generateIpdArtifacts/);
});

test('customer UI presents controlled AI employees and technical badges', () => {
  for (const label of ['AI项目组', 'AI员工', '基础 Agent', '已加载 Skill', '可调用工具', '权限边界']) {
    assert.match(app, new RegExp(label));
  }
  assert.match(app, /状态来自Hermes真实任务事件/);
  assert.match(app, /aria-live="polite"/);
});

test('summary completion drives incremental 004 reveal without fake progress', () => {
  assert.match(app, /event\.section === 'summary'\) startInsightAutoAdvance/);
  assert.match(app, /setView\('screen-04'\)/);
  assert.match(app, /insight-skeleton/);
  assert.match(styles, /prefers-reduced-motion:reduce/);
  assert.match(styles, /--employee-index/);
});

test('a failed final callback cannot overwrite an already completed report', () => {
  assert.match(app, /const recovered = await window\.showroomApi\.failInsightJob/);
  assert.match(app, /recovered\.job\?\.status === 'completed'/);
  assert.match(app, /全部章节已保存，项目组已完成/);
});
