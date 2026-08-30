import { Clock3, Save, ShieldCheck, Sparkles } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { platformApi } from "../../services/platformApi";

const initialRule = {
  id: "project-review",
  name: "项目复盘",
  cron: "0 9 * * 1",
  timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC",
  misfire_policy: "RUN_ONCE",
  concurrency_policy: "FORBID",
  enabled: true,
  max_candidates_scanned: 200,
  max_recommendations: 20,
};

export function ProjectAutomations({ projectId, onRevisionChange }) {
  const [data, setData] = useState({ process_revision: 0, rules: [], runs: [], metrics: {} });
  const [draft, setDraft] = useState(initialRule);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const load = async () => {
    const value = await platformApi.listProjectAutomations(projectId);
    setData(value);
    onRevisionChange?.(value.process_revision);
  };
  useEffect(() => { load().catch((reason) => setError(reason.message)); }, [projectId]);
  const latestVersion = useMemo(
    () => Math.max(0, ...data.rules.filter((rule) => rule.id === draft.id).map((rule) => Number(rule.version || 0))),
    [data.rules, draft.id],
  );
  const save = async () => {
    setBusy(true); setError("");
    try {
      const response = await platformApi.saveProjectAutomation(projectId, draft.id, {
        expected_revision: data.process_revision,
        rule: {
          name: draft.name,
          version: latestVersion + 1,
          cron: draft.cron,
          timezone: draft.timezone,
          misfire_policy: draft.misfire_policy,
          concurrency_policy: draft.concurrency_policy,
          enabled: draft.enabled,
          automation_level: "L1",
          output_status: "WAITING_CLAIM",
          budget: {
            max_candidates_scanned: Number(draft.max_candidates_scanned),
            max_recommendations_per_run: Number(draft.max_recommendations),
          },
        },
      });
      onRevisionChange?.(response.process_revision);
      await load();
    } catch (reason) { setError(reason.message); } finally { setBusy(false); }
  };
  const decide = async (runId, recommendationId, decision) => {
    setBusy(true); setError("");
    try {
      const response = await platformApi.decideProjectAutomationRecommendation(
        projectId, runId, recommendationId,
        { expected_revision: data.process_revision, decision, note: "Automation report review" },
      );
      onRevisionChange?.(response.process_revision);
      await load();
    } catch (reason) { setError(reason.message); } finally { setBusy(false); }
  };
  return <section className="qw-automation">
    <header><div><span className="qw-eyebrow">Project automation</span><h2>自动化控制中心</h2><p>定义什么时候检查项目、Hermes 可以提出什么建议，以及哪些动作必须由人确认。</p></div><span><ShieldCheck size={15} /> L1 · 建议不自动执行</span></header>
    <div className="qw-automation-flow" aria-label="自动化运行链路"><article><small>01 · TRIGGER</small><strong>触发条件</strong><span>按计划或项目事件启动检查</span></article><article><small>02 · VALIDATE</small><strong>全局校验</strong><span>角色、依赖、状态、资源与验收门禁</span></article><article><small>03 · REVIEW</small><strong>建议与人工确认</strong><span>保留 Run 记录，确认后才产生副作用</span></article></div>
    {error && <p className="qw-error">{error}</p>}
    <div className="qw-automation-grid">
      <form className="qw-automation-builder" onSubmit={(event) => { event.preventDefault(); save(); }}>
        <div><span className="qw-eyebrow">Rule builder</span><h3>规则配置</h3><p>业务用户只需确认名称、运行时间和处理策略；技术值保留为辅助说明。</p></div>
        <label>规则标识<input value={draft.id} onChange={(event) => setDraft({ ...draft, id: event.target.value })} /><small>用于审计与版本追踪</small></label>
        <label>规则名称<input value={draft.name} onChange={(event) => setDraft({ ...draft, name: event.target.value })} /></label>
        <label>运行计划<input value={draft.cron} onChange={(event) => setDraft({ ...draft, cron: event.target.value })} /><small>当前：每周一 09:00</small></label>
        <label>时区<input value={draft.timezone} onChange={(event) => setDraft({ ...draft, timezone: event.target.value })} /></label>
        <label>错过计划时<select value={draft.misfire_policy} onChange={(event) => setDraft({ ...draft, misfire_policy: event.target.value })}><option value="SKIP">跳过本次</option><option value="RUN_ONCE">恢复后补跑一次</option><option value="CATCH_UP">补齐全部</option></select></label>
        <label>已有任务运行时<select value={draft.concurrency_policy} onChange={(event) => setDraft({ ...draft, concurrency_policy: event.target.value })}><option value="FORBID">不重复启动</option><option value="REPLACE">替换旧任务</option><option value="ALLOW">允许并行</option></select></label>
        <label>扫描预算<input type="number" min="1" value={draft.max_candidates_scanned} onChange={(event) => setDraft({ ...draft, max_candidates_scanned: event.target.value })} /></label>
        <label>推荐预算<input type="number" min="1" value={draft.max_recommendations} onChange={(event) => setDraft({ ...draft, max_recommendations: event.target.value })} /></label>
        <label className="qw-automation-enable"><input type="checkbox" checked={draft.enabled} onChange={(event) => setDraft({ ...draft, enabled: event.target.checked })} /><span><strong>启用下一版本 v{latestVersion + 1}</strong><small>保存后按计划运行；建议仍需人工确认</small></span></label>
        <button className="qw-button primary" type="submit" disabled={busy}><Save size={15} />{busy ? "保存中…" : "保存规则版本"}</button>
      </form>
      <div className="qw-automation-ledger">
        <section><header><div><h3><Clock3 size={16} /> 已保存规则</h3><p>每次修改生成新版本，可审计、不静默覆盖。</p></div><strong>{data.rules.length}</strong></header>
        {data.rules.map((rule) => <article key={`${rule.id}-${rule.version}`}><strong>{rule.name || rule.id} · v{rule.version}</strong><small>{rule.cron} · {rule.timezone} · {rule.enabled ? "enabled" : "disabled"}</small></article>)}
        {!data.rules.length && <p className="qw-automation-empty">尚无规则。保存左侧配置后，规则版本会出现在这里。</p>}</section>
        <section><header><div><h3><Sparkles size={16} /> 运行与建议</h3><p>展示每次校验、暂停原因与待人工处理建议。</p></div><strong>{data.runs.length}</strong></header>
        {data.runs.map((run) => <article key={run.id}><strong>{run.status} · {run.scheduled_for_utc}</strong><small>scanned {run.report?.candidates_scanned || 0} · emitted {run.report?.recommendations_created || 0} · suppressed {run.report?.novelty_suppressed || 0}</small>{(run.recommendations || []).map((item) => <div key={item.id}><span>{item.title} · {item.decision || item.status}</span>{item.decision === "PENDING" && <span><button type="button" disabled={busy} onClick={() => decide(run.id, item.id, "ACCEPT")}>采纳</button><button type="button" disabled={busy} onClick={() => decide(run.id, item.id, "REJECT")}>拒绝</button></span>}</div>)}</article>)}
        {!data.runs.length && <p className="qw-automation-empty">尚无运行记录。规则触发后，这里会显示全局校验结果和建议。</p>}</section>
      </div>
    </div>
  </section>;
}
