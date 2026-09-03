import { useCallback, useEffect, useMemo, useState } from "react";
import { platformApi } from "../../services/platformApi";

export function ProjectGovernancePanel({ project, process, onChanged }) {
  const [intent, setIntent] = useState(null);
  const [proposals, setProposals] = useState([]);
  const [draftText, setDraftText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    const [intentPayload, proposalPayload] = await Promise.all([
      platformApi.getProjectIntent(project.id),
      platformApi.listProjectChangeProposals(project.id),
    ]);
    setIntent(intentPayload);
    setProposals((proposalPayload.proposals || []).filter((item) => ["PROPOSED", "NEEDS_REBASE"].includes(item.status)));
    const draft = (intentPayload.revisions || []).find((item) => item.status === "DRAFT");
    if (draft) setDraftText(JSON.stringify(draft.snapshot, null, 2));
  }, [project.id]);

  useEffect(() => {
    const refresh = () => load().catch((reason) => setError(reason.message));
    refresh();
    window.addEventListener("qws:governance-changed", refresh);
    return () => window.removeEventListener("qws:governance-changed", refresh);
  }, [load, process.process_revision]);
  const active = useMemo(
    () => (intent?.revisions || []).find((item) => item.status === "CONFIRMED" && item.revision === intent.active_revision),
    [intent],
  );
  const draft = (intent?.revisions || []).find((item) => item.status === "DRAFT");

  const generateDraft = async () => {
    setBusy(true); setError("");
    try { await platformApi.createProjectIntentMigrationDraft(project.id); await load(); }
    catch (reason) { setError(reason.message); }
    finally { setBusy(false); }
  };
  const confirmDraft = async () => {
    setBusy(true); setError("");
    try {
      const snapshot = JSON.parse(draftText);
      await platformApi.confirmProjectIntent(project.id, {
        expected_process_revision: process.process_revision,
        snapshot,
      });
      await load(); await onChanged?.();
    } catch (reason) { setError(reason.message || "意图 JSON 无效"); }
    finally { setBusy(false); }
  };
  const decide = async (proposal, decision) => {
    setBusy(true); setError("");
    try {
      await platformApi.decideProjectChangeProposal(project.id, proposal.id, {
        expected_process_revision: process.process_revision,
        decision,
      });
      await load(); await onChanged?.();
    } catch (reason) { setError(reason.message); await load(); }
    finally { setBusy(false); }
  };

  return <section className="qw-governance" aria-label="项目意图治理">
    <header>
      <div><strong>项目意图基线</strong><small>{active ? `已确认 r${active.revision} · ${active.canonical_hash.slice(0, 10)}` : "尚未确认，自动执行已暂停"}</small></div>
      {!active && !draft && <button type="button" disabled={busy} onClick={generateDraft}>生成迁移草案</button>}
    </header>
    {error && <p className="qw-error">{error}</p>}
    {draft && <div className="qw-intent-draft">
      {!!draft.conflicts?.length && <div className="qw-intent-conflicts"><strong>发现冲突，请确认后编辑草案：</strong>{draft.conflicts.map((item) => <p key={`${item.source}-${item.value}`}>{item.source}：{item.value}</p>)}</div>}
      <textarea aria-label="项目意图迁移草案" value={draftText} onChange={(event) => setDraftText(event.target.value)} />
      <button type="button" className="qw-button primary" disabled={busy} onClick={confirmDraft}>确认项目意图基线</button>
    </div>}
    {!!proposals.length && <div className="qw-change-proposals">
      <strong>待确认变更</strong>
      {proposals.map((proposal) => <article key={proposal.id}>
        <div><b>{proposal.impact?.title || proposal.change_kind}</b><small>{proposal.impact?.change_count || 0} 项变化 · 基于 process r{proposal.base_process_revision}</small></div>
        {!!proposal.impact?.changes?.length && <details>
          <summary>查看前后差异</summary>
          <ul>{proposal.impact.changes.slice(0, 30).map((change, index) => <li key={`${change.path}-${index}`}>
            <code>{change.path}</code>：{change.change}
            {Object.hasOwn(change, "before") && <del>{JSON.stringify(change.before)}</del>}
            {Object.hasOwn(change, "after") && <ins>{JSON.stringify(change.after)}</ins>}
          </li>)}</ul>
        </details>}
        {proposal.status === "NEEDS_REBASE" ? <span>项目已变化，请重新发起该操作。</span> : <nav><button type="button" disabled={busy} onClick={() => decide(proposal, "REJECT")}>拒绝</button><button type="button" className="qw-button primary" disabled={busy} onClick={() => decide(proposal, "APPROVE")}>批准并升级顶设</button></nav>}
      </article>)}
    </div>}
  </section>;
}
