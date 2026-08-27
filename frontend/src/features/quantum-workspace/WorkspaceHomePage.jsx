import { ArrowRight, Boxes, Clock3, Plus, ShieldCheck } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { platformApi } from "../../services/platformApi";

const NewProjectForm = ({ template, onClose, onCreated }) => {
  const [name, setName] = useState("");
  const [goal, setGoal] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const submit = async (event) => {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const result = await platformApi.instantiateProject(template.id, {
        request_id: `ui-project-${crypto.randomUUID()}`,
        name,
        goal,
        desired_outputs: template.deliverables,
        inputs: {},
        truth_mode: "PLANNED",
        resource_overrides: {},
      });
      onCreated(result.project_id);
    } catch (reason) {
      setError(reason.message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="qw-modal" role="dialog" aria-modal="true" aria-labelledby="new-project-title">
      <form className="qw-modal-card" onSubmit={submit}>
        <div><span className="qw-eyebrow">从模板创建</span><h2 id="new-project-title">{template.name}</h2></div>
        <label>项目名称<input value={name} onChange={(e) => setName(e.target.value)} required maxLength={160} autoFocus /></label>
        <label>业务目标<textarea value={goal} onChange={(e) => setGoal(e.target.value)} required rows={4} maxLength={4000} /></label>
        <p className="qw-note">创建项目不会自动审批或执行。进入项目后先完成 Business Intake，再审阅 ProcessDraft。</p>
        {error && <p className="qw-error">{error}</p>}
        <div className="qw-actions"><button type="button" className="qw-button ghost" onClick={onClose}>取消</button><button className="qw-button primary" disabled={busy}>{busy ? "创建中…" : "创建项目"}</button></div>
      </form>
    </div>
  );
};

export function WorkspaceHomePage() {
  const [projects, setProjects] = useState([]);
  const [templates, setTemplates] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [selectedTemplate, setSelectedTemplate] = useState(null);
  const navigate = useNavigate();
  const location = useLocation();

  useEffect(() => {
    Promise.all([platformApi.listProjects(), platformApi.listProjectTemplates()])
      .then(([projectRows, templateRows]) => { setProjects(projectRows); setTemplates(templateRows); })
      .catch((reason) => setError(reason.message))
      .finally(() => setLoading(false));
  }, []);

  const showTemplatesOnly = location.pathname === "/templates";
  return (
    <div className="qw-home">
      <section className="qw-hero">
        <div><span className="qw-eyebrow">Product delivery workspace</span><h1>从业务意图到可验证交付</h1><p>项目、IPD 流程、任务、Workflow 与真实执行证据，统一在同一版本化工作台中。</p></div>
        <button className="qw-button primary" onClick={() => setSelectedTemplate(templates[0])} disabled={!templates.length}><Plus size={16} /> 新建项目</button>
      </section>

      {error && <p className="qw-error">{error}</p>}
      {!showTemplatesOnly && (
        <section className="qw-section">
          <div className="qw-section-head"><div><span className="qw-eyebrow">Projects</span><h2>我的项目</h2></div><span>{projects.length} 个</span></div>
          {loading ? <div className="qw-empty">正在读取项目…</div> : projects.length ? (
            <div className="qw-project-grid">{projects.map((project) => (
              <Link className="qw-project-card" key={project.id} to={`/projects/${project.id}/taskboard`}>
                <div className="qw-project-icon"><Boxes size={18} /></div>
                <div><h3>{project.name}</h3><p>{project.goal}</p></div>
                <div className="qw-project-meta"><span><Clock3 size={14} /> revision {project.process_revision}</span><span>{project.task_count} tasks</span></div>
                <ArrowRight className="qw-card-arrow" size={18} />
              </Link>
            ))}</div>
          ) : <div className="qw-empty"><ShieldCheck size={22} /><strong>还没有项目</strong><span>从版本化模板创建，第一个动作是提交 Business Intake。</span></div>}
        </section>
      )}

      <section className="qw-section" id="templates">
        <div className="qw-section-head"><div><span className="qw-eyebrow">Versioned templates</span><h2>模板库</h2></div><span>只显示已发布模板</span></div>
        <div className="qw-template-grid">{templates.map((template) => (
          <article className="qw-template-card" key={template.id}>
            <div className="qw-template-top"><span className="qw-chip">{template.category}</span><span>v{template.version}</span></div>
            <h3>{template.name}</h3><p>{template.summary}</p>
            <div className="qw-stage-mini">{template.stages.map((stage) => <span key={stage}>{stage}</span>)}</div>
            <div className="qw-template-footer"><span>{template.resource_envelope.source_status}</span><button className="qw-button subtle" onClick={() => setSelectedTemplate(template)}>使用模板 <ArrowRight size={15} /></button></div>
          </article>
        ))}</div>
      </section>
      {selectedTemplate && <NewProjectForm template={selectedTemplate} onClose={() => setSelectedTemplate(null)} onCreated={(id) => navigate(`/projects/${id}/taskboard`)} />}
    </div>
  );
}
