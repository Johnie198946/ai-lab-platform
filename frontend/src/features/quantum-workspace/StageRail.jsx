import { AlertTriangle, Bot, CalendarDays, CheckCircle2, ChevronRight, Layers3, Pencil, Plus, Save, ShieldCheck, Sparkles, Trash2, UserRound, UsersRound, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { buildStageRail } from "./quantumProjection";

const statusLabel = {
  NOT_STARTED: "未开始",
  TODO: "待处理",
  IN_PROGRESS: "进行中",
  BLOCKED: "阻塞",
  PAUSED: "暂停",
  DONE: "完成",
};

const displayDate = (value) => {
  if (!value) return "未排期";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "日期待确认" : new Intl.DateTimeFormat("zh-CN", { month: "short", day: "numeric" }).format(date);
};
const ownerOf = (item, employeeById = new Map()) => {
  const employee = employeeById.get(item.assignee_id);
  return employee ? `${employee.display_name} · ${employee.job_title}` : item.assignee_role || "待分配";
};

const baseAgentPresentation = {
  main_agent: { label: "通用执行基座", skills: ["项目统筹", "需求澄清", "跨角色协同"] },
  knowledge: { label: "知识研究基座", skills: ["知识检索", "研究与洞察", "证据整理"] },
  coder: { label: "工程实现基座", skills: ["技术设计", "代码实现", "系统集成"] },
  supervision: { label: "监督评审基座", skills: ["质量评审", "风险验证", "验收把关"] },
};

const uniqueText = (values) => [...new Set(values.map((value) => String(value || "").trim()).filter(Boolean))];

function buildRoleOverview(process, stages) {
  const stageById = new Map(stages.map((stage) => [stage.id, stage]));
  const employees = Array.isArray(process.ai_employees) ? process.ai_employees : [];
  const employeeById = new Map(employees.map((employee) => [employee.employee_id, employee]));
  const employeeByRole = new Map(employees.map((employee) => [employee.job_title, employee]));
  const roles = new Map();
  const roleById = new Map();
  const ensureRole = (name, definition = null) => {
    if (!name || name === "待分配") return null;
    if (!roles.has(name)) {
      const role = {
        id: definition?.id || `derived:${name}`,
        name,
        description: definition?.description || "",
        responsibilities: uniqueText(definition?.responsibilities || []),
        configuredSkills: uniqueText(definition?.skills || []),
        assignee_id: definition?.assignee_id || null,
        source_status: definition?.source_status || "LEGACY_INFERRED",
        tasks: [], gates: [], stageIds: new Set(),
        employee: employeeById.get(definition?.assignee_id) || employeeByRole.get(name) || null,
      };
      roles.set(name, role);
      if (definition?.id) roleById.set(definition.id, role);
    }
    return roles.get(name);
  };

  (Array.isArray(process.roles) ? process.roles : []).forEach((definition) => ensureRole(definition?.name, definition));

  stages.forEach((stage) => {
    stage.tasks.forEach((task) => {
      const employee = employeeById.get(task.assignee_id) || null;
      const role = roleById.get(task.role_id) || ensureRole(employee?.job_title || task.assignee_role);
      if (!role) return;
      role.employee ||= employee;
      role.tasks.push({ ...task, stageName: stage.name });
      role.stageIds.add(stage.id);
    });
    stage.gates.forEach((gate) => {
      const role = ensureRole(gate.responsible_role);
      if (!role) return;
      role.gates.push({ ...gate, stageName: stage.name });
      role.stageIds.add(stage.id);
    });
  });

  return [...roles.values()].map((role) => {
    const base = baseAgentPresentation[role.employee?.base_agent_id] || null;
    const gateSkills = role.gates.map((gate) => gate.node_type === "TR" ? "技术评审" : gate.node_type === "DCP" ? "决策评审" : `${gate.node_type} 评审`);
    const capabilityVersions = role.tasks.flatMap((task) => (task.agent_candidates || []).map((candidate) => candidate.capability_version));
    return {
      ...role,
      stages: [...role.stageIds].map((id) => stageById.get(id)).filter(Boolean),
      baseLabel: base?.label || (role.gates.length ? "流程评审角色" : "能力基座待配置"),
      skills: uniqueText([...role.configuredSkills, ...(base?.skills || []), ...gateSkills]),
      capabilityVersions: uniqueText(capabilityVersions),
    };
  }).sort((left, right) => (left.stages[0]?.order ?? 999) - (right.stages[0]?.order ?? 999) || left.name.localeCompare(right.name, "zh-CN"));
}

const roleFormOf = (role = null) => ({
  name: role?.name || "",
  description: role?.description || "",
  responsibilities: (role?.responsibilities || []).join("\n"),
  skills: (role?.configuredSkills || role?.skills || []).join("\n"),
  assignee_id: role?.assignee_id || "",
});
const linesOf = (value) => uniqueText(String(value || "").split(/[\n,，]/));

function RoleOverviewDialog({ process, stages, onClose, onCreate, onUpdate, onDelete }) {
  const dialogRef = useRef(null);
  const roles = useMemo(() => buildRoleOverview(process, stages), [process, stages]);
  const employees = Array.isArray(process.ai_employees) ? process.ai_employees : [];
  const [selectedRoleId, setSelectedRoleId] = useState(() => roles[0]?.id || "");
  const [editorMode, setEditorMode] = useState("view");
  const [form, setForm] = useState(() => roleFormOf());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [deleteConfirm, setDeleteConfirm] = useState(false);
  const selectedRole = roles.find((role) => role.id === selectedRoleId) || roles[0];
  const taskCount = roles.reduce((total, role) => total + role.tasks.length, 0);
  const gateCount = roles.reduce((total, role) => total + role.gates.length, 0);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return undefined;
    dialog.showModal();
    return () => { if (dialog.open) dialog.close(); };
  }, []);

  useEffect(() => {
    const handleEscape = (event) => {
      if (event.key !== "Escape") return;
      event.preventDefault();
      onClose();
    };
    window.addEventListener("keydown", handleEscape);
    return () => window.removeEventListener("keydown", handleEscape);
  }, [onClose]);

  useEffect(() => {
    if (!selectedRole && roles[0]) setSelectedRoleId(roles[0].id);
  }, [roles, selectedRole]);

  const chooseRole = (role) => {
    setSelectedRoleId(role.id);
    setEditorMode("view");
    setDeleteConfirm(false);
    setError("");
  };
  const beginEdit = () => { setForm(roleFormOf(selectedRole)); setEditorMode("edit"); setDeleteConfirm(false); setError(""); };
  const beginCreate = () => { setForm(roleFormOf()); setEditorMode("create"); setDeleteConfirm(false); setError(""); };
  const submit = async (event) => {
    event.preventDefault();
    const payload = {
      name: form.name.trim(), description: form.description.trim(),
      responsibilities: linesOf(form.responsibilities), skills: linesOf(form.skills),
      assignee_id: form.assignee_id || null,
    };
    if (!payload.name) { setError("角色名称不能为空。"); return; }
    if (!payload.skills.length) { setError("请至少配置一项角色技能。"); return; }
    setBusy(true); setError("");
    try {
      const result = editorMode === "create" ? await onCreate(payload) : await onUpdate(selectedRole.id, payload);
      setSelectedRoleId(result?.role?.id || selectedRole?.id || "");
      setEditorMode("view");
    } catch (reason) { setError(reason.message); }
    finally { setBusy(false); }
  };
  const remove = async () => {
    setBusy(true); setError("");
    try { await onDelete(selectedRole.id); setSelectedRoleId(""); setEditorMode("view"); setDeleteConfirm(false); }
    catch (reason) { setError(reason.message); }
    finally { setBusy(false); }
  };

  return (
    <dialog
      ref={dialogRef}
      className="qw-role-dialog"
      aria-labelledby="qw-role-dialog-title"
      onCancel={(event) => { event.preventDefault(); onClose(); }}
      onClick={(event) => { if (event.target === dialogRef.current) onClose(); }}
    >
      <div className="qw-role-dialog-card">
        <header className="qw-role-dialog-head">
          <div>
            <span className="qw-eyebrow">Project role map</span>
            <h2 id="qw-role-dialog-title">项目角色全景</h2>
            <p>从当前项目流程中汇总角色、责任边界、交接关系与已配置能力。</p>
          </div>
          <div className="qw-role-head-actions"><button type="button" className="primary" onClick={beginCreate}><Plus size={15} />新增角色</button><button type="button" onClick={onClose} aria-label="关闭项目角色全景" autoFocus><X size={18} /></button></div>
        </header>
        <div className="qw-role-dialog-metrics" aria-label="角色全景统计">
          <span><UsersRound size={16} /><strong>{roles.length}</strong>个角色</span>
          <span><CheckCircle2 size={16} /><strong>{taskCount}</strong>项责任任务</span>
          <span><ShieldCheck size={16} /><strong>{gateCount}</strong>个评审节点</span>
        </div>
        {!selectedRole && editorMode === "view" ? <p className="qw-role-dialog-empty">当前流程尚未配置责任角色。点击“新增角色”开始配置。</p> : <div className="qw-role-dialog-body">
          <nav className="qw-role-directory" aria-label="项目角色目录">
            {roles.map((role) => {
              const active = role.id === selectedRole?.id;
              return <button key={role.id} type="button" className={active ? "active" : ""} aria-current={active ? "true" : undefined} onClick={() => chooseRole(role)}>
                <span className="qw-role-avatar">{role.employee ? <Bot size={16} /> : <UserRound size={16} />}</span>
                <span><strong>{role.name}</strong><small>{role.employee ? `${role.employee.display_name} · AI 员工` : role.baseLabel}</small></span>
                <em>{role.tasks.length + role.gates.length}</em>
              </button>;
            })}
          </nav>
          {editorMode !== "view" ? <section className="qw-role-editor" aria-live="polite">
            <header><div><span className="qw-eyebrow">{editorMode === "create" ? "Create role" : "Edit role"}</span><h3>{editorMode === "create" ? "新增项目角色" : `编辑 ${selectedRole?.name}`}</h3><p>负责人选择后，角色名称将自动使用该员工的岗位，确保角色与负责人一致。</p></div><button type="button" onClick={() => setEditorMode("view")} aria-label="取消编辑"><X size={17} /></button></header>
            <form onSubmit={submit}>
              <div className="qw-role-form-grid">
                <label>负责人<select value={form.assignee_id} onChange={(event) => { const employee = employees.find((item) => item.employee_id === event.target.value); setForm((current) => ({ ...current, assignee_id: event.target.value, name: employee?.job_title || current.name })); }}><option value="">暂不分配</option>{employees.map((employee) => <option key={employee.employee_id} value={employee.employee_id}>{employee.display_name} · {employee.job_title}</option>)}</select><small>仅展示本项目 AI 员工</small></label>
                <label>角色名称<input value={form.name} readOnly={!!form.assignee_id} onChange={(event) => setForm((current) => ({ ...current, name: event.target.value }))} maxLength={160} required /><small>{form.assignee_id ? "已与负责人岗位锁定" : "未分配负责人时可自定义"}</small></label>
              </div>
              <label>角色说明<textarea value={form.description} onChange={(event) => setForm((current) => ({ ...current, description: event.target.value }))} maxLength={2000} rows={3} placeholder="说明该角色存在的目的和不负责的范围" /></label>
              <label>责任边界<textarea value={form.responsibilities} onChange={(event) => setForm((current) => ({ ...current, responsibilities: event.target.value }))} rows={5} placeholder="每行一项，例如：负责发布包与回滚方案；不负责功能需求决策" /></label>
              <label>技能与能力<span className="required">必填</span><textarea value={form.skills} onChange={(event) => setForm((current) => ({ ...current, skills: event.target.value }))} rows={5} placeholder="每行一项，例如：CI/CD、灰度发布、回滚演练" required /></label>
              {error && <p className="qw-role-form-error" role="alert">{error}</p>}
              <footer><button type="button" onClick={() => setEditorMode("view")} disabled={busy}>取消</button><button type="submit" className="primary" disabled={busy}><Save size={14} />{busy ? "保存中…" : "保存角色"}</button></footer>
            </form>
          </section> : <section className="qw-role-profile" aria-live="polite">
            <header>
              <div className="qw-role-avatar large">{selectedRole.employee ? <Bot size={21} /> : <UserRound size={21} />}</div>
              <div><span>{selectedRole.employee ? "AI EMPLOYEE" : "PROCESS ROLE"}</span><h3>{selectedRole.name}</h3><p>{selectedRole.employee ? `${selectedRole.employee.display_name} · ${selectedRole.name}` : "负责人待分配"}</p></div>
              <div className="qw-role-profile-actions"><button type="button" onClick={beginEdit}><Pencil size={14} />编辑</button><button type="button" className="danger" onClick={() => setDeleteConfirm(true)}><Trash2 size={14} />删除</button></div>
            </header>
            {selectedRole.description && <p className="qw-role-description">{selectedRole.description}</p>}
            {selectedRole.employee && selectedRole.employee.job_title !== selectedRole.name && <p className="qw-role-mismatch"><AlertTriangle size={14} />负责人岗位与角色不匹配，请重新选择负责人。</p>}
            {deleteConfirm && <div className="qw-role-delete-confirm" role="alert"><AlertTriangle size={16} /><span><strong>确认删除“{selectedRole.name}”？</strong><small>关联任务和评审节点会被设为待分配。</small></span><button type="button" onClick={() => setDeleteConfirm(false)} disabled={busy}>取消</button><button type="button" className="danger" onClick={remove} disabled={busy}>{busy ? "删除中…" : "确认删除"}</button></div>}
            {error && <p className="qw-role-form-error" role="alert">{error}</p>}
            <div className="qw-role-stage-strip"><Layers3 size={14} /><span>涉及阶段</span>{selectedRole.stages.map((stage) => <i key={stage.id}>{stage.name}</i>)}</div>
            <div className="qw-role-profile-grid">
              <section className="qw-role-responsibilities">
                <h4>责任边界 <span>{selectedRole.tasks.length + selectedRole.gates.length}</span></h4>
                <div>
                  {selectedRole.responsibilities.map((item) => <article key={`defined:${item}`} className="defined"><div><CheckCircle2 size={14} /><strong>{item}</strong><span>角色定义</span></div></article>)}
                  {selectedRole.tasks.map((task) => <article key={task.id}>
                    <div><CheckCircle2 size={14} /><strong>{task.title}</strong><span>{task.stageName}</span></div>
                    <p>{task.summary || "按任务卡片要求完成工作与验收。"}</p>
                    {!!task.deliverables?.length && <small>交付物：{task.deliverables.join("、")}</small>}
                  </article>)}
                  {selectedRole.gates.map((gate) => <article key={gate.id} className="gate">
                    <div><ShieldCheck size={14} /><strong>{gate.name}</strong><span>{gate.stageName} · {gate.node_type}</span></div>
                    <p>负责该节点的评审与放行判断，不替代任务执行角色。</p>
                  </article>)}
                </div>
              </section>
              <aside>
                <section>
                  <h4><Sparkles size={14} />技能与能力</h4>
                  <div className="qw-role-skills">
                    {selectedRole.skills.length ? selectedRole.skills.map((skill) => <span key={skill}>{skill}</span>) : <small>尚未配置明确技能</small>}
                  </div>
                  {!!selectedRole.capabilityVersions.length && <p>能力版本 · {selectedRole.capabilityVersions.join("、")}</p>}
                </section>
                <section>
                  <h4>交接边界</h4>
                  <div className="qw-role-handoffs">
                    {selectedRole.tasks.map((task) => {
                      const handoff = task.handoff || {};
                      return <p key={task.id}><strong>{task.title}</strong><span>{handoff.to ? `交给 ${handoff.to}` : "交给下游责任角色"}</span><small>{handoff.completion_definition || (task.deliverables?.length ? `完成 ${task.deliverables.join("、")}` : "达到任务卡片验收标准")}</small></p>;
                    })}
                    {!selectedRole.tasks.length && <p><span>评审结论交回项目流程</span><small>仅负责 Gate 判断，不承担具体交付任务</small></p>}
                  </div>
                </section>
              </aside>
            </div>
          </section>}
        </div>}
      </div>
    </dialog>
  );
}

function StageDetail({ stage, index, onClose, employeeById }) {
  const owners = [...new Set(stage.tasks.map((task) => ownerOf(task, employeeById)).filter((owner) => owner !== "待分配"))];
  return (
    <section id={`qw-stage-detail-${stage.id}`} className="qw-stage-detail" aria-label={`${stage.name}阶段详情`}>
      <header>
        <div>
          <span className="qw-eyebrow">阶段 {String(index + 1).padStart(2, "0")} · {statusLabel[stage.status] ?? stage.status}</span>
          <h2>{stage.name}</h2>
        </div>
        <button type="button" onClick={onClose} aria-label={`关闭${stage.name}阶段详情`}><X size={17} /></button>
      </header>
      <div className="qw-stage-detail-summary">
        <div className="qw-stage-progress" aria-label={`阶段进度 ${stage.progress || 0}%`}>
          <span><strong>{stage.progress || 0}%</strong> 阶段进度</span>
          <i><b style={{ width: `${Math.min(100, Math.max(0, stage.progress || 0))}%` }} /></i>
        </div>
        <div><CalendarDays size={15} /><span>计划周期<strong>{displayDate(stage.planned_start_at)} — {displayDate(stage.planned_finish_at)}</strong></span></div>
        <div><UserRound size={15} /><span>参与责任人<strong>{owners.length ? owners.join("、") : "待分配"}</strong></span></div>
        <div><ShieldCheck size={15} /><span>评审节点<strong>{stage.gates.length ? stage.gates.map((gate) => gate.name).join("、") : "无 Gate"}</strong></span></div>
      </div>
      <div className="qw-stage-detail-grid">
        <section>
          <h3>阶段任务与内容 <span>{stage.tasks.length}</span></h3>
          <div className="qw-stage-task-list">
            {stage.tasks.length ? stage.tasks.map((task) => (
              <article key={task.id}>
                <div className="qw-stage-task-heading"><CheckCircle2 size={15} /><strong>{task.title}</strong><span>{statusLabel[task.status] ?? task.status}</span></div>
                <p>{task.summary || "暂无任务说明"}</p>
                {!!task.deliverables?.length && <small>交付物：{task.deliverables.join("、")}</small>}
              </article>
            )) : <p className="qw-stage-empty">该阶段尚未建立任务。</p>}
          </div>
        </section>
        <section>
          <h3>责任分工</h3>
          <div className="qw-stage-owner-list">
            {stage.tasks.map((task) => <div key={task.id}><UserRound size={14} /><span><strong>{ownerOf(task, employeeById)}</strong><small>{task.title}</small></span></div>)}
            {stage.gates.map((gate) => <div key={gate.id}><ShieldCheck size={14} /><span><strong>{gate.responsible_role || "待分配"}</strong><small>{gate.node_type} · {gate.name}</small></span></div>)}
            {!stage.tasks.length && !stage.gates.length && <p className="qw-stage-empty">暂无责任分工。</p>}
          </div>
        </section>
      </div>
    </section>
  );
}

export function StageRail({ process, selectedStageId, onSelect, onCreateRole, onUpdateRole, onDeleteRole }) {
  const stages = buildStageRail(process);
  const employeeById = useMemo(() => new Map((process.ai_employees || []).map((employee) => [employee.employee_id, employee])), [process.ai_employees]);
  const [roleOverviewOpen, setRoleOverviewOpen] = useState(false);
  const roleCount = useMemo(() => buildRoleOverview(process, stages).length, [process, stages]);
  const selectedIndex = stages.findIndex((stage) => stage.id === selectedStageId);
  const selectedStage = selectedIndex >= 0 ? stages[selectedIndex] : null;
  if (!stages.length) return null;
  return (
    <div className={`qw-stage-explorer ${selectedStage ? "is-open" : ""}`}>
      <div className="qw-stage-rail-head">
        <div><span className="qw-eyebrow">Project process</span><strong>项目流程</strong></div>
        <div className="qw-stage-rail-actions"><span>点击节点查看内容与负责人</span><button type="button" onClick={() => setRoleOverviewOpen(true)}><UsersRound size={14} />角色全景<strong>{roleCount}</strong></button></div>
      </div>
      <nav className="qw-stage-rail" aria-label="IPD 项目流程">
        {stages.map((stage, index) => {
          const ownerCount = new Set(stage.tasks.map((task) => ownerOf(task, employeeById)).filter((owner) => owner !== "待分配")).size;
          const active = selectedStageId === stage.id;
          return (
            <button
              key={stage.id}
              type="button"
              className={`${active ? "active" : ""} status-${String(stage.status || "not_started").toLowerCase()}`}
              onClick={() => onSelect?.(active ? null : stage.id)}
              aria-expanded={active}
              aria-controls={`qw-stage-detail-${stage.id}`}
            >
              <span className="qw-stage-node"><i />{String(index + 1).padStart(2, "0")}</span>
              <span className="qw-stage-name">{stage.name}<small>{statusLabel[stage.status] ?? stage.status} · {stage.progress || 0}%</small></span>
              <span className="qw-stage-owner"><UserRound size={12} />{ownerCount ? `${ownerCount} 个责任角色` : "待分配"}</span>
              <span className="qw-gates">{stage.gates.map((gate) => <i key={gate.id} className={gate.node_type.toLowerCase()} title={`${gate.node_type}: ${gate.name} · ${gate.responsible_role || "待分配"}`}>{gate.name}</i>)}</span>
              <ChevronRight className="qw-stage-chevron" size={16} />
            </button>
          );
        })}
      </nav>
      {selectedStage && <StageDetail stage={selectedStage} index={selectedIndex} employeeById={employeeById} onClose={() => onSelect?.(null)} />}
      {roleOverviewOpen && <RoleOverviewDialog process={process} stages={stages} onClose={() => setRoleOverviewOpen(false)} onCreate={onCreateRole} onUpdate={onUpdateRole} onDelete={onDeleteRole} />}
    </div>
  );
}
