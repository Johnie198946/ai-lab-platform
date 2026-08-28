import { ArrowRight, Boxes, Clock3, Pencil, Plus, ShieldCheck, Sparkles, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { platformApi } from "../../services/platformApi";
import { ProjectPlanningDialog } from "./ProjectPlanningDialog";

const EditProjectForm = ({ project, onClose, onSaved }) => {
  const [name, setName] = useState(project.name);
  const [goal, setGoal] = useState(project.goal);
  const [outputs, setOutputs] = useState((project.desired_outputs || []).join("、"));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const submit = async (event) => {
    event.preventDefault(); setBusy(true); setError("");
    try {
      await platformApi.updateProject(project.id, { name, goal, desired_outputs: outputs.split(/[、,，]/).map((item) => item.trim()).filter(Boolean) });
      await onSaved(); onClose();
    } catch (reason) { setError(reason.message); } finally { setBusy(false); }
  };
  return <div className="qw-modal" role="dialog" aria-modal="true" aria-labelledby="edit-project-title"><form className="qw-modal-card" onSubmit={submit}><div><span className="qw-eyebrow">Project settings</span><h2 id="edit-project-title">编辑项目</h2></div><label>项目名称<input value={name} onChange={(event) => setName(event.target.value)} required /></label><label>业务目标<textarea rows={5} value={goal} onChange={(event) => setGoal(event.target.value)} required /></label><label>期望输出<input value={outputs} onChange={(event) => setOutputs(event.target.value)} /></label>{error && <p className="qw-error" role="alert">{error}</p>}<div className="qw-actions"><button type="button" className="qw-button ghost" onClick={onClose}>取消</button><button className="qw-button primary" disabled={busy}>{busy ? "保存中…" : "保存"}</button></div></form></div>;
};

export function WorkspaceHomePage() {
  const [projects, setProjects] = useState([]);
  const [templates, setTemplates] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [planningProject, setPlanningProject] = useState(undefined);
  const [editingProject, setEditingProject] = useState(null);
  const location = useLocation();

  const load = () => Promise.all([platformApi.listProjects(), platformApi.listProjectTemplates()])
      .then(([projectRows, templateRows]) => { setProjects(projectRows); setTemplates(templateRows); })
      .catch((reason) => setError(reason.message))
      .finally(() => setLoading(false));
  useEffect(() => { void load(); }, []);

  const removeProject = async (project) => {
    if (!window.confirm(`永久删除项目“${project.name}”及其流程、会话和任务绑定？此操作不可撤销。`)) return;
    try { await platformApi.deleteProject(project.id); await load(); }
    catch (reason) { setError(reason.message); }
  };

  const showTemplatesOnly = location.pathname === "/templates";
  return (
    <div className="qw-home">
      <section className="qw-hero">
        <div><span className="qw-eyebrow">Product delivery workspace</span><h1>从业务意图到可验证交付</h1><p>先由 Hermes 完成需求收敛，再一次派发动态流程、AI 员工、任务、甘特与项目文档。</p></div>
        <button className="qw-button primary" onClick={() => setPlanningProject(null)} disabled={!templates.length}><Plus size={16} /> 新建项目</button>
      </section>

      {error && <p className="qw-error">{error}</p>}
      {!showTemplatesOnly && (
        <section className="qw-section">
          <div className="qw-section-head"><div><span className="qw-eyebrow">Projects</span><h2>我的项目</h2></div><span>{projects.length} 个</span></div>
          {loading ? <div className="qw-empty">正在读取项目…</div> : projects.length ? (
            <div className="qw-project-grid">{projects.map((project) => (
              <article className="qw-project-card" key={project.id}>
              <Link className="qw-project-card-main" to={`/projects/${project.id}/taskboard`}>
                <div className="qw-project-icon"><Boxes size={18} /></div>
                <div><h3>{project.name}</h3><p>{project.goal}</p></div>
                <div className="qw-project-meta"><span><Clock3 size={14} /> revision {project.process_revision}</span><span>{project.task_count} tasks</span></div>
                <ArrowRight className="qw-card-arrow" size={18} />
              </Link>
              <div className="qw-project-actions"><button type="button" onClick={() => setPlanningProject(project)}><Sparkles size={13} />AI 收敛</button><button type="button" onClick={() => setEditingProject(project)}><Pencil size={13} />编辑</button><button type="button" className="danger" onClick={() => removeProject(project)}><Trash2 size={13} />删除</button></div>
              </article>
            ))}</div>
          ) : <div className="qw-empty"><ShieldCheck size={22} /><strong>还没有项目</strong><span>创建草稿并与 Hermes 完整沟通，确认后再派发。</span></div>}
        </section>
      )}

      <section className="qw-section" id="templates">
        <div className="qw-section-head"><div><span className="qw-eyebrow">Project starting points</span><h2>模板库</h2></div><span>模板只提供起点，不固定流程</span></div>
        <div className="qw-template-grid">{templates.map((template) => (
          <article className="qw-template-card" key={template.id}>
            <div className="qw-template-top"><span className="qw-chip">{template.category}</span><span>v{template.version}</span></div>
            <h3>{template.name}</h3><p>{template.summary}</p>
            <div className="qw-stage-mini">{template.stages.map((stage) => <span key={stage}>{stage}</span>)}</div>
            <div className="qw-template-footer"><span>Hermes 动态裁剪</span><button className="qw-button subtle" onClick={() => setPlanningProject(null)}>开始对话 <ArrowRight size={15} /></button></div>
          </article>
        ))}</div>
      </section>
      {planningProject !== undefined && templates[0] && <ProjectPlanningDialog template={templates[0]} initialProject={planningProject} onClose={() => setPlanningProject(undefined)} onChanged={load} />}
      {editingProject && <EditProjectForm project={editingProject} onClose={() => setEditingProject(null)} onSaved={load} />}
    </div>
  );
}
