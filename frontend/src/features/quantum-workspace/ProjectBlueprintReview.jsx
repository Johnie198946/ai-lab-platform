import { CheckCircle2, Edit3, FileText, GitBranch, Plus, RefreshCw, Save, Trash2, Users, X } from "lucide-react";
import { useEffect, useState } from "react";
import { ProjectBlueprintProtocol } from "./ProjectBlueprintProtocol";

const unique = (values = []) => [...new Set(values.map((value) => String(value || "").trim()).filter(Boolean))];
const lines = (value) => String(value || "").split("\n").map((item) => item.trim()).filter(Boolean);
const clone = (value) => JSON.parse(JSON.stringify(value || {}));
const nextKey = (prefix) => `${prefix}-${crypto.randomUUID().slice(0, 8)}`;

function BlueprintEditor({ blueprint, onCancel, onSave }) {
  const [draft, setDraft] = useState(() => clone(blueprint));
  const stages = Array.isArray(draft.stages) ? draft.stages : [];
  const tasks = Array.isArray(draft.tasks) ? draft.tasks : [];
  const documents = Array.isArray(draft.documents) ? draft.documents : [];
  const updateStage = (index, changes) => setDraft((current) => ({ ...current, stages: current.stages.map((item, itemIndex) => itemIndex === index ? { ...item, ...changes } : item) }));
  const updateTask = (index, changes) => setDraft((current) => ({ ...current, tasks: current.tasks.map((item, itemIndex) => itemIndex === index ? { ...item, ...changes } : item) }));
  const updateDocument = (index, changes) => setDraft((current) => ({ ...current, documents: current.documents.map((item, itemIndex) => itemIndex === index ? { ...item, ...changes } : item) }));
  const removeStage = (index) => {
    const removedKey = stages[index]?.key;
    setDraft((current) => ({ ...current, stages: current.stages.filter((_, itemIndex) => itemIndex !== index), tasks: current.tasks.filter((task) => task.stage_key !== removedKey) }));
  };
  return <div className="qw-blueprint-editor">
    <div className="qw-blueprint-editor-head"><div><strong>人工修订需求确认单</strong><small>保存后的内容就是派发真源，不再回用 AI 旧稿。</small></div><button type="button" onClick={onCancel} aria-label="取消编辑"><X size={16} /></button></div>
    <label>项目目标<textarea rows="4" value={draft.project_goal || ""} onChange={(event) => setDraft({ ...draft, project_goal: event.target.value })} /></label>
    <section><header><div><strong>任务阶段</strong><small>名称、目标和阶段验收均可改。</small></div><button type="button" onClick={() => setDraft((current) => ({ ...current, stages: [...stages, { key: nextKey("stage"), name: "新阶段", goal: "", acceptance_criteria: [] }] }))}><Plus size={13} />新增阶段</button></header>
      {stages.map((stage, index) => <article key={stage.key || index} className="qw-blueprint-edit-card"><div><strong>阶段 {index + 1}</strong><button type="button" onClick={() => removeStage(index)} aria-label={`删除阶段 ${index + 1}`}><Trash2 size={13} /></button></div><label>阶段名称<input value={stage.name || ""} onChange={(event) => updateStage(index, { name: event.target.value })} /></label><label>阶段目标<textarea rows="2" value={stage.goal || ""} onChange={(event) => updateStage(index, { goal: event.target.value })} /></label><label>阶段验收标准（每行一条）<textarea rows="3" value={(stage.acceptance_criteria || []).join("\n")} onChange={(event) => updateStage(index, { acceptance_criteria: lines(event.target.value) })} /></label></article>)}
    </section>
    <section><header><div><strong>任务与角色</strong><small>负责人角色、说明、交付物和验收标准均可改。</small></div><button type="button" disabled={!stages.length} onClick={() => setDraft((current) => ({ ...current, tasks: [...tasks, { key: nextKey("task"), stage_key: stages[0]?.key, title: "新任务", description: "", role: "", deliverables: [], acceptance_criteria: [] }] }))}><Plus size={13} />新增任务</button></header>
      {tasks.map((task, index) => <article key={task.key || index} className="qw-blueprint-edit-card task"><div><strong>任务 {index + 1}</strong><button type="button" onClick={() => setDraft((current) => ({ ...current, tasks: tasks.filter((_, itemIndex) => itemIndex !== index) }))} aria-label={`删除任务 ${index + 1}`}><Trash2 size={13} /></button></div><label>所属阶段<select value={task.stage_key || ""} onChange={(event) => updateTask(index, { stage_key: event.target.value })}>{stages.map((stage) => <option key={stage.key} value={stage.key}>{stage.name || stage.key}</option>)}</select></label><label>任务名称<input value={task.title || ""} onChange={(event) => updateTask(index, { title: event.target.value })} /></label><label>负责人角色<input value={task.role || ""} onChange={(event) => updateTask(index, { role: event.target.value })} /></label><label>任务说明<textarea rows="2" value={task.description || task.goal || ""} onChange={(event) => updateTask(index, { description: event.target.value })} /></label><label>交付物（每行一项）<textarea rows="3" value={(task.deliverables || []).join("\n")} onChange={(event) => updateTask(index, { deliverables: lines(event.target.value) })} /></label><label>验收标准（每行一条）<textarea rows="3" value={(task.acceptance_criteria || []).join("\n")} onChange={(event) => updateTask(index, { acceptance_criteria: lines(event.target.value) })} /></label></article>)}
    </section>
    <section><header><div><strong>项目文档</strong><small>可修改蓝图要求建立的文档；系统另生成顶设和逐任务记录。</small></div><button type="button" onClick={() => setDraft((current) => ({ ...current, documents: [...documents, { id: nextKey("doc"), title: "新文档", content: "" }] }))}><Plus size={13} />新增文档</button></header>
      {documents.map((document, index) => <article key={document.id || index} className="qw-blueprint-edit-card document"><div><strong>文档 {index + 1}</strong><button type="button" onClick={() => setDraft((current) => ({ ...current, documents: documents.filter((_, itemIndex) => itemIndex !== index) }))} aria-label={`删除文档 ${index + 1}`}><Trash2 size={13} /></button></div><label>文档名称<input value={document.title || ""} onChange={(event) => updateDocument(index, { title: event.target.value })} /></label><label>文档初始内容<textarea rows="4" value={document.content || ""} onChange={(event) => updateDocument(index, { content: event.target.value })} /></label></article>)}
    </section>
    <footer><button type="button" className="qw-button subtle" onClick={onCancel}>取消</button><button type="button" className="qw-button primary" disabled={!String(draft.project_goal || "").trim() || !stages.length || !tasks.length} onClick={() => onSave(draft)}><Save size={14} />保存人工修订</button></footer>
  </div>;
}

export function ProjectBlueprintReview({ blueprint, onChange, version, current = false, dispatchable = false }) {
  const [editing, setEditing] = useState(false);
  useEffect(() => setEditing(false), [version]);
  const stages = Array.isArray(blueprint?.stages) ? blueprint.stages : [];
  const tasks = Array.isArray(blueprint?.tasks) ? blueprint.tasks : [];
  const documents = Array.isArray(blueprint?.documents) ? blueprint.documents : [];
  const roles = unique(tasks.map((task) => task?.role));
  const acceptance = unique([...stages.flatMap((stage) => stage?.acceptance_criteria || []), ...tasks.flatMap((task) => task?.acceptance_criteria || [])]);
  return <section className={`qw-blueprint-review ${current ? "current" : "superseded"}`} aria-label={`需求确认单 v${version}`}>
    <header><div><span>需求确认单</span><strong>v{version}</strong></div><span className="qw-blueprint-review-actions"><small>{current ? "当前待确认版本" : "已由后续版本替代"}</small>{current && onChange && <button type="button" onClick={() => setEditing(true)}><Edit3 size={13} />人工修改</button>}</span></header>
    {editing ? <BlueprintEditor blueprint={blueprint} onCancel={() => setEditing(false)} onSave={(value) => { onChange(value); setEditing(false); }} /> : <>
      {blueprint.project_goal && <div className="qw-blueprint-goal"><span>项目目标</span><p>{blueprint.project_goal}</p></div>}
      <div className="qw-blueprint-facts"><span><GitBranch size={14} />{stages.length} 个阶段</span><span><CheckCircle2 size={14} />{tasks.length} 项任务</span><span><Users size={14} />{roles.length} 类角色</span><span><FileText size={14} />{documents.length} 份蓝图文档</span></div>
      <ol className="qw-blueprint-stages">{stages.map((stage, index) => { const stageTasks = tasks.filter((task) => task?.stage_key === stage?.key); return <li key={stage?.key || index}><span>{String(index + 1).padStart(2, "0")}</span><div><strong>{stage?.name || stage?.key}</strong>{stage?.goal && <p>{stage.goal}</p>}<small>{stageTasks.map((task) => task?.title).filter(Boolean).join(" · ") || "该阶段尚无任务"}</small></div></li>; })}</ol>
      {!!acceptance.length && <details><summary>查看全部验收标准（{acceptance.length}）</summary><ul>{acceptance.map((item) => <li key={item}>{item}</li>)}</ul></details>}
      <ProjectBlueprintProtocol protocol={JSON.stringify(blueprint, null, 2)} complete dispatchable={dispatchable} />
      {current && <p className="qw-blueprint-revise"><RefreshCw size={13} />可点“人工修改”逐项调整；派发只使用最后确认的版本。</p>}
    </>}
  </section>;
}
