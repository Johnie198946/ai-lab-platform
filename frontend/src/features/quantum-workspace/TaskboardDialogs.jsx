import { Link2, Plus, X } from "lucide-react";
import { useEffect, useState } from "react";

export function NewProjectTaskDialog({ stages, roles = [], busy, error, onClose, onSubmit }) {
  const [form, setForm] = useState({ stage_id: stages[0]?.id || "", title: "", summary: "", assignee_role: "" });

  const submit = (event) => {
    event.preventDefault();
    onSubmit({ ...form, title: form.title.trim(), summary: form.summary.trim(), assignee_role: form.assignee_role.trim() || null });
  };

  return <div className="qw-modal" role="dialog" aria-modal="true" aria-labelledby="qw-new-task-title">
    <form className="qw-modal-card" onSubmit={submit}>
      <div className="qw-dialog-title"><div><span className="qw-eyebrow">ProjectProcess task</span><h2 id="qw-new-task-title">新建项目任务</h2></div><button type="button" onClick={onClose} aria-label="关闭"><X size={17} /></button></div>
      <label>所属阶段<select value={form.stage_id} onChange={(event) => setForm((current) => ({ ...current, stage_id: event.target.value }))} required>{stages.map((stage) => <option value={stage.id} key={stage.id}>{stage.name}</option>)}</select></label>
      <label>任务名称<input value={form.title} onChange={(event) => setForm((current) => ({ ...current, title: event.target.value }))} required maxLength={160} autoFocus /></label>
      <label>任务说明<textarea value={form.summary} onChange={(event) => setForm((current) => ({ ...current, summary: event.target.value }))} required rows={4} maxLength={4000} /></label>
      <label>负责角色<select value={form.assignee_role} onChange={(event) => setForm((current) => ({ ...current, assignee_role: event.target.value }))}><option value="">待分配</option>{roles.map((role) => <option key={role.id} value={role.name}>{role.name}</option>)}</select></label>
      <p className="qw-note">新任务先进入 TODO / PLAN，不会自动创建或执行 Workflow。</p>
      {error && <p className="qw-error">{error}</p>}
      <div className="qw-actions"><button type="button" className="qw-button ghost" onClick={onClose}>取消</button><button className="qw-button primary" disabled={busy || !form.stage_id || !form.title.trim() || !form.summary.trim()}><Plus size={15} />{busy ? "创建中…" : "创建任务"}</button></div>
    </form>
  </div>;
}

export function EditProjectTaskDialog({ task, stages, roles = [], busy, error, onClose, onSubmit }) {
  const [form, setForm] = useState({ stage_id: task.stage_id || stages[0]?.id || "", title: task.title || "", summary: task.summary || "", assignee_role: task.assignee_role || "" });
  const submit = (event) => { event.preventDefault(); onSubmit({ ...form, title: form.title.trim(), summary: form.summary.trim(), assignee_role: form.assignee_role.trim() || null }); };
  return <div className="qw-modal" role="dialog" aria-modal="true" aria-labelledby="qw-edit-task-title">
    <form className="qw-modal-card" onSubmit={submit}>
      <div className="qw-dialog-title"><div><span className="qw-eyebrow">Dashi taskboard</span><h2 id="qw-edit-task-title">编辑任务卡片</h2></div><button type="button" onClick={onClose} aria-label="关闭"><X size={17} /></button></div>
      <label>所属阶段<select value={form.stage_id} onChange={(event) => setForm((current) => ({ ...current, stage_id: event.target.value }))} required>{stages.map((stage) => <option value={stage.id} key={stage.id}>{stage.name}</option>)}</select></label>
      <label>任务名称<input value={form.title} onChange={(event) => setForm((current) => ({ ...current, title: event.target.value }))} required maxLength={160} autoFocus /></label>
      <label>任务说明<textarea value={form.summary} onChange={(event) => setForm((current) => ({ ...current, summary: event.target.value }))} required rows={4} maxLength={4000} /></label>
      <label>负责角色<select value={form.assignee_role} onChange={(event) => setForm((current) => ({ ...current, assignee_role: event.target.value }))}><option value="">待分配</option>{roles.map((role) => <option key={role.id} value={role.name}>{role.name}</option>)}</select></label>
      <p className="qw-note">保存只更新 ProjectProcess 任务卡片，不会自动执行 Workflow。</p>
      {error && <p className="qw-error">{error}</p>}
      <div className="qw-actions"><button type="button" className="qw-button ghost" onClick={onClose}>取消</button><button className="qw-button primary" disabled={busy || !form.title.trim() || !form.summary.trim()}>{busy ? "保存中…" : "保存修改"}</button></div>
    </form>
  </div>;
}

export function BindWorkflowDialog({ task, workflows, busy, error, onClose, onBind, onCreateAndBind }) {
  const available = workflows.filter((workflow) => workflow?.id);
  const [workflowId, setWorkflowId] = useState(available[0]?.id || "");
  useEffect(() => { setWorkflowId(available[0]?.id || ""); }, [task?.id]);

  return <div className="qw-modal" role="dialog" aria-modal="true" aria-labelledby="qw-bind-workflow-title">
    <div className="qw-modal-card">
      <div className="qw-dialog-title"><div><span className="qw-eyebrow">AI Lab canonical</span><h2 id="qw-bind-workflow-title">绑定真实工作流</h2><p>{task.title}</p></div><button type="button" onClick={onClose} aria-label="关闭"><X size={17} /></button></div>
      {available.length ? <label>已有工作流<select value={workflowId} onChange={(event) => setWorkflowId(event.target.value)}>{available.map((workflow) => <option key={workflow.id} value={workflow.id}>{workflow.title} · {workflow.status}</option>)}</select></label> : <p className="qw-note">当前没有可绑定的自有 Workflow，可以直接按任务内容创建。</p>}
      <p className="qw-note">一个 canonical Workflow 只能绑定本项目中的一个任务。绑定后，生命周期、Execution、Artifact、Token 和费用都来自该真实工作流。</p>
      {error && <p className="qw-error">{error}</p>}
      <div className="qw-actions split"><button type="button" className="qw-button subtle" disabled={busy} onClick={() => onCreateAndBind(task)}><Plus size={15} />创建并绑定</button><span /><button type="button" className="qw-button ghost" onClick={onClose}>取消</button><button type="button" className="qw-button primary" disabled={busy || !workflowId} onClick={() => onBind(task, workflowId)}><Link2 size={15} />{busy ? "绑定中…" : "绑定所选"}</button></div>
    </div>
  </div>;
}
