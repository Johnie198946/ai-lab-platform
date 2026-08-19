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
  assert.match(app, /insight-empty/);
  assert.match(styles, /prefers-reduced-motion:reduce/);
  assert.match(styles, /--employee-index/);
});

test('004 is a conversational IPD review workbench with controlled revisions', () => {
  for (const label of ['洞察共创助手', '待回填内容 · 尚未应用', '应用回填到报告', '确认当前洞察，提交AI评审', '需求理解有误，退回003修订', 'AI 概念评审会', '进入下一步前还缺什么']) {
    assert.match(app, new RegExp(label));
  }
  assert.match(app, /submitHermesSkill\(insightExecutionPrompt\(job, plan\), 'ipd-01-market-insight'/);
  assert.match(app, /submitHermesSkill\(requirementAnalysisPrompt\(job\), 'ipd-02-requirement-analysis'/);
  assert.match(app, /extractInsightRevision/);
  assert.match(app, /applyInsightRevision/);
  assert.match(app, /completeInsightAssistantRequest\(rawAnswer, answer\)/);
  assert.match(app, /INSIGHT_REVISION_INTENT/);
  assert.match(app, /回填\|填入\|写入\|同步\|替换/);
  assert.match(app, /repairInsightRevision/);
  assert.match(app, /focusAppliedInsightSections/);
  assert.match(styles, /insight-cocreation-shell/);
  assert.match(styles, /revision-preview/);
  assert.match(styles, /insight-just-filled/);
  assert.match(app, /AI_LAB_INSIGHT_REVISION_V2/);
  assert.match(app, /createInsightReviewTask/);
  assert.match(app, /registerInsightTbd/);
});

test('a failed final callback cannot overwrite an already completed report', () => {
  assert.match(app, /const recovered = await window\.showroomApi\.failInsightJob/);
  assert.match(app, /recovered\.job\?\.status === 'completed'/);
  assert.match(app, /全部章节已保存，项目组已完成/);
});
