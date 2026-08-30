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
    <header><div><span className="qw-eyebrow">Automation wizard</span><h2>规则、Run 与 Recommendation</h2></div><span><ShieldCheck size={15} /> Hermes-only · L1</span></header>
    {error && <p className="qw-error">{error}</p>}
    <div className="qw-automation-grid">
      <form onSubmit={(event) => { event.preventDefault(); save(); }}>
        <label>Rule ID<input value={draft.id} onChange={(event) => setDraft({ ...draft, id: event.target.value })} /></label>
        <label>名称<input value={draft.name} onChange={(event) => setDraft({ ...draft, name: event.target.value })} /></label>
        <label>Cron<input value={draft.cron} onChange={(event) => setDraft({ ...draft, cron: event.target.value })} /></label>
        <label>Timezone<input value={draft.timezone} onChange={(event) => setDraft({ ...draft, timezone: event.target.value })} /></label>
        <label>Misfire<select value={draft.misfire_policy} onChange={(event) => setDraft({ ...draft, misfire_policy: event.target.value })}><option>SKIP</option><option>RUN_ONCE</option><option>CATCH_UP</option></select></label>
        <label>Concurrency<select value={draft.concurrency_policy} onChange={(event) => setDraft({ ...draft, concurrency_policy: event.target.value })}><option>FORBID</option><option>REPLACE</option><option>ALLOW</option></select></label>
        <label>扫描预算<input type="number" min="1" value={draft.max_candidates_scanned} onChange={(event) => setDraft({ ...draft, max_candidates_scanned: event.target.value })} /></label>
        <label>推荐预算<input type="number" min="1" value={draft.max_recommendations} onChange={(event) => setDraft({ ...draft, max_recommendations: event.target.value })} /></label>
        <label><input type="checkbox" checked={draft.enabled} onChange={(event) => setDraft({ ...draft, enabled: event.target.checked })} />启用下一版本 v{latestVersion + 1}</label>
        <button type="submit" disabled={busy}><Save size={15} />保存版本</button>
        <small>规则配置由交互式人类完成；调度触发仅接受专用 service scope，推荐不会自动执行。</small>
      </form>
      <div>
        <h3><Clock3 size={16} /> Rules</h3>
        {data.rules.map((rule) => <article key={`${rule.id}-${rule.version}`}><strong>{rule.name || rule.id} · v{rule.version}</strong><small>{rule.cron} · {rule.timezone} · {rule.enabled ? "enabled" : "disabled"}</small></article>)}
        {!data.rules.length && <p>尚无规则。</p>}
        <h3><Sparkles size={16} /> Run reports</h3>
        {data.runs.map((run) => <article key={run.id}><strong>{run.status} · {run.scheduled_for_utc}</strong><small>scanned {run.report?.candidates_scanned || 0} · emitted {run.report?.recommendations_created || 0} · suppressed {run.report?.novelty_suppressed || 0}</small>{(run.recommendations || []).map((item) => <div key={item.id}><span>{item.title} · {item.decision || item.status}</span>{item.decision === "PENDING" && <span><button type="button" disabled={busy} onClick={() => decide(run.id, item.id, "ACCEPT")}>采纳</button><button type="button" disabled={busy} onClick={() => decide(run.id, item.id, "REJECT")}>拒绝</button></span>}</div>)}</article>)}
        {!data.runs.length && <p>尚无 Run；等待受信服务按计划触发。</p>}
      </div>
    </div>
  </section>;
}
