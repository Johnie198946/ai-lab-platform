import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

const app = readFileSync(new URL('../public/showroom/app.js', import.meta.url), 'utf8');
const styles = readFileSync(new URL('../public/showroom/styles.css', import.meta.url), 'utf8');
const index = readFileSync(new URL('../public/showroom/legacy.html', import.meta.url), 'utf8');

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

test('model-authored progress envelopes are normalized before the progress API call', () => {
  assert.match(app, /\['progress', 'stage', \/<!--\\s\*AI_LAB_INSIGHT_STAGE_V1/);
  assert.match(app, /\['progress', 'section', \/<!--\\s\*AI_LAB_INSIGHT_SECTION_V1/);
  assert.match(app, /normalizeInsightProgressEvent\(payload, defaultKind\)/);
  assert.match(app, /employee_status: 'employee'/);
  assert.match(app, /insightPendingEventIds\.add\(event\.event_id\)/);
  assert.match(app, /insightEventIds\.add\(event\.event_id\);\s+state\.session = result\.session/);
  assert.match(app, /insightPendingEventIds\.delete\(event\.event_id\)/);
  assert.match(index, /app\.js\?v=20260821-progress-contract-v1/);
});

test('003.5 observes one server execution and 004 uses an isolated review lane', () => {
  const api = readFileSync(new URL('../public/showroom/showroom-api.js', import.meta.url), 'utf8');
  assert.match(api, /view === "screen-04"\) return "insight-review"/);
  assert.doesNotMatch(api, /\["screen-03-team", "screen-04"\]\.includes\(view\) return "insight"/);
  assert.match(app, /getInsightJob\(job\.job_id\)/);
  assert.match(app, /window\.setInterval\(pollInsightServerJob, 2000\)/);
  assert.match(app, /job\.execution_id/);
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
  assert.match(app, /data-readiness-continue/);
  assert.match(app, /让AI继续完善报告/);
  assert.match(app, /insightBackfillInstruction/);
  assert.match(app, /autoApply: true/);
  assert.match(app, /applyInsightRevision\(result\.revision\.revision_id\)/);
  assert.match(app, /backfill_required_fields/);
  assert.match(app, /已完成IPD-01洞察快照/);
  assert.match(app, /reasoning\.delta/);
  assert.match(app, /tool\.start/);
  assert.match(app, /WORK TRACE · 角色化模拟视图/);
  assert.match(app, /不展示模型内部隐性思考/);
  assert.match(app, /INSIGHT_BACKFILL_EMPLOYEES/);
  assert.match(styles, /backfill-trace/);
  assert.match(styles, /trace-employees/);
});

test('a failed final callback cannot overwrite an already completed report', () => {
  assert.match(app, /const recovered = await window\.showroomApi\.failInsightJob/);
  assert.match(app, /recovered\.job\?\.status === 'completed'/);
  assert.match(app, /全部章节已保存，项目组已完成/);
});
