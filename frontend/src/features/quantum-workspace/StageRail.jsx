import { Bot, CalendarDays, CheckCircle2, ChevronRight, Edit3, Layers3, Save, ShieldCheck, Sparkles, UserRound, UsersRound, X } from "lucide-react";
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
const ownerOf = (item) => item.assignee_id || item.assignee_role || "待分配";

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
  const ensureRole = (name) => {
    if (!name || name === "待分配") return null;
    if (!roles.has(name)) roles.set(name, { name, tasks: [], gates: [], stageIds: new Set(), employee: employeeByRole.get(name) || null });
    return roles.get(name);
  };

  stages.forEach((stage) => {
    stage.tasks.forEach((task) => {
      const employee = employeeById.get(task.assignee_id) || null;
      const role = ensureRole(task.assignee_role || employee?.job_title || task.assignee_id);
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
      profile: process.role_profiles?.[role.name] || {},
      stages: [...role.stageIds].map((id) => stageById.get(id)).filter(Boolean),
      baseLabel: base?.label || (role.gates.length ? "流程评审角色" : "能力基座待配置"),
      skills: uniqueText([...(base?.skills || []), ...gateSkills]),
      capabilityVersions: uniqueText(capabilityVersions),
    };
  }).sort((left, right) => (left.stages[0]?.order ?? 999) - (right.stages[0]?.order ?? 999) || left.name.localeCompare(right.name, "zh-CN"));
}

function RoleOverviewDialog({ process, stages, onClose, onSaveRole }) {
  const dialogRef = useRef(null);
  const roles = useMemo(() => buildRoleOverview(process, stages), [process, stages]);
  const [selectedRoleName, setSelectedRoleName] = useState(() => roles[0]?.name || "");
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState({ name: "", description: "", responsibilities: "", decision_rights: "", collaboration_boundaries: "" });
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState("");
  const [validation, setValidation] = useState(null);
  const selectedRole = roles.find((role) => role.name === selectedRoleName) || roles[0];
  const taskCount = roles.reduce((total, role) => total + role.tasks.length, 0);
  const gateCount = roles.reduce((total, role) => total + role.gates.length, 0);

  const beginEdit = () => {
    const profile = selectedRole?.profile || {};
    setDraft({
      name: selectedRole.name,
      description: profile.description || selectedRole.baseLabel || "",
      responsibilities: (profile.responsibilities || selectedRole.tasks.map((task) => task.title)).join("\n"),
      decision_rights: (profile.decision_rights || selectedRole.gates.map((gate) => gate.name)).join("\n"),
      collaboration_boundaries: (profile.collaboration_boundaries || []).join("\n"),
    });
    setSaveError("");
    setEditing(true);
  };

  const saveRole = async (event) => {
    event.preventDefault();
    if (!draft.name.trim() || !selectedRole || saving) return;
    setSaving(true); setSaveError("");
    try {
      const result = await onSaveRole(selectedRole.name, {
        name: draft.name.trim(),
        description: draft.description.trim(),
        responsibilities: draft.responsibilities.split("\n").map((item) => item.trim()).filter(Boolean),
        decision_rights: draft.decision_rights.split("\n").map((item) => item.trim()).filter(Boolean),
        collaboration_boundaries: draft.collaboration_boundaries.split("\n").map((item) => item.trim()).filter(Boolean),
      });
      setSelectedRoleName(result.role.name);
      setEditing(false);
      setValidation(result.validation);
    } catch (reason) { setSaveError(reason.message); } finally { setSaving(false); }
  };

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
          <button type="button" onClick={onClose} aria-label="关闭项目角色全景" autoFocus><X size={18} /></button>
        </header>
        <div className="qw-role-dialog-metrics" aria-label="角色全景统计">
          <span><UsersRound size={16} /><strong>{roles.length}</strong>个角色</span>
          <span><CheckCircle2 size={16} /><strong>{taskCount}</strong>项责任任务</span>
          <span><ShieldCheck size={16} /><strong>{gateCount}</strong>个评审节点</span>
        </div>
        {!selectedRole ? <p className="qw-role-dialog-empty">当前流程尚未配置责任角色。</p> : <div className="qw-role-dialog-body">
          <nav className="qw-role-directory" aria-label="项目角色目录">
            {roles.map((role) => {
              const active = role.name === selectedRole.name;
              return <button key={role.name} type="button" className={active ? "active" : ""} aria-current={active ? "true" : undefined} onClick={() => setSelectedRoleName(role.name)}>
                <span className="qw-role-avatar">{role.employee ? <Bot size={16} /> : <UserRound size={16} />}</span>
                <span><strong>{role.name}</strong><small>{role.employee ? `${role.employee.display_name} · AI 员工` : role.baseLabel}</small></span>
                <em>{role.tasks.length + role.gates.length}</em>
              </button>;
            })}
          </nav>
          <section className="qw-role-profile" aria-live="polite">
            <header>
              <div className="qw-role-avatar large">{selectedRole.employee ? <Bot size={21} /> : <UserRound size={21} />}</div>
              <div><span>{selectedRole.employee ? "AI EMPLOYEE" : "PROCESS ROLE"}{selectedRole.profile?.source === "USER_EDITED" ? " · USER EDITED" : " · AI PROPOSED"}</span><h3>{selectedRole.name}</h3><p>{selectedRole.profile?.description || (selectedRole.employee ? `${selectedRole.employee.display_name} · ${selectedRole.baseLabel}` : selectedRole.baseLabel)}</p></div>
              <button type="button" className="qw-role-edit-button" onClick={beginEdit}><Edit3 size={14} />编辑角色</button>
            </header>
            {editing && <form className="qw-role-editor" onSubmit={saveRole}>
              <label>角色名称<input value={draft.name} maxLength={160} onChange={(event) => setDraft((current) => ({ ...current, name: event.target.value }))} autoFocus /></label>
              <label>角色说明<textarea rows="2" value={draft.description} onChange={(event) => setDraft((current) => ({ ...current, description: event.target.value }))} /></label>
              <label>责任边界（每行一项）<textarea rows="4" value={draft.responsibilities} onChange={(event) => setDraft((current) => ({ ...current, responsibilities: event.target.value }))} /></label>
              <label>决策权限（每行一项）<textarea rows="3" value={draft.decision_rights} onChange={(event) => setDraft((current) => ({ ...current, decision_rights: event.target.value }))} /></label>
              <label>交接边界（每行一项）<textarea rows="3" value={draft.collaboration_boundaries} onChange={(event) => setDraft((current) => ({ ...current, collaboration_boundaries: event.target.value }))} placeholder="例如：完成候选清单后交给行程策划师；不替代预算审批" /></label>
              {saveError && <p role="alert">{saveError}</p>}
              <div><button type="button" onClick={() => setEditing(false)}>取消</button><button type="submit" disabled={saving || !draft.name.trim()}><Save size={14} />{saving ? "保存并校验中…" : "保存并全局校验"}</button></div>
            </form>}
            <div className="qw-role-stage-strip"><Layers3 size={14} /><span>涉及阶段</span>{selectedRole.stages.map((stage) => <i key={stage.id}>{stage.name}</i>)}</div>
            <div className="qw-role-profile-grid">
              <section className="qw-role-responsibilities">
                <h4>责任边界 <span>{selectedRole.tasks.length + selectedRole.gates.length}</span></h4>
                <div>
                  {!!selectedRole.profile?.responsibilities?.length && selectedRole.profile.responsibilities.map((responsibility, index) => <article key={`profile-responsibility-${index}`}>
                    <div><CheckCircle2 size={14} /><strong>{responsibility}</strong><span>人工定义</span></div>
                    <p>{selectedRole.profile.description || "这是你为该角色明确的工作范围。"}</p>
                  </article>)}
                  {!selectedRole.profile?.responsibilities?.length && selectedRole.tasks.map((task) => <article key={task.id}>
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
                    {!!selectedRole.profile?.collaboration_boundaries?.length && selectedRole.profile.collaboration_boundaries.map((boundary, index) => <p key={`boundary-${index}`}><strong>人工定义</strong><span>{boundary}</span><small>保存后立即作为该角色的协作边界</small></p>)}
                    {!selectedRole.profile?.collaboration_boundaries?.length && selectedRole.tasks.map((task) => {
                      const handoff = task.handoff || {};
                      return <p key={task.id}><strong>{task.title}</strong><span>{handoff.to ? `交给 ${handoff.to}` : "交给下游责任角色"}</span><small>{handoff.completion_definition || (task.deliverables?.length ? `完成 ${task.deliverables.join("、")}` : "达到任务卡片验收标准")}</small></p>;
                    })}
                    {!selectedRole.tasks.length && <p><span>评审结论交回项目流程</span><small>仅负责 Gate 判断，不承担具体交付任务</small></p>}
                  </div>
                </section>
              </aside>
            </div>
          </section>
        </div>}
        {validation && <div className="qw-consistency-popup" role="alertdialog" aria-label="项目一致性校验结果">
          <section><header><ShieldCheck size={18} /><div><strong>{validation.blocking ? "角色已保存，但有问题需要先处理" : validation.counts.error || validation.counts.warning ? "角色已保存，请检查以下提醒" : "角色修改成功，相关信息已同步"}</strong><small>{validation.blocking ? "为避免错误执行，系统已暂停受影响的自动任务；你的修改不会丢失。处理下方问题后即可继续。" : validation.counts.error || validation.counts.warning ? "你的修改已经生效。下面会用具体任务说明哪里需要补充，不影响你继续查看和编辑。" : "角色名称、责任范围和交接关系已更新；后续任务会使用这份最新设置。"}</small></div></header>
          {!!validation.issues?.length && <ul>{validation.issues.slice(0, 8).map((issue) => <li key={`${issue.code}-${issue.scope}`} className={issue.severity.toLowerCase()}><b>{issue.severity === "CRITICAL" ? "必须处理" : issue.severity === "ERROR" ? "执行前处理" : issue.severity === "WARNING" ? "建议检查" : "提示"}</b><span><strong>{issue.title}</strong><small>{issue.detail} · 处理办法：{issue.repair}</small></span></li>)}</ul>}
          <button type="button" onClick={() => setValidation(null)}>知道了</button></section>
        </div>}
      </div>
    </dialog>
  );
}

function StageDetail({ stage, index, employeesById, onClose }) {
  const ownerLabel = (task) => {
    const employee = employeesById.get(task.assignee_id);
    return employee ? `${employee.display_name} · ${employee.job_title}` : task.assignee_role || "待分配";
  };
  const owners = [...new Set(stage.tasks.map(ownerLabel).filter((owner) => owner !== "待分配"))];
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
            {stage.tasks.map((task) => <div key={task.id}><UserRound size={14} /><span><strong>{ownerLabel(task)}</strong><small>{task.title}</small></span></div>)}
            {stage.gates.map((gate) => <div key={gate.id}><ShieldCheck size={14} /><span><strong>{gate.responsible_role || "待分配"}</strong><small>{gate.node_type} · {gate.name}</small></span></div>)}
            {!stage.tasks.length && !stage.gates.length && <p className="qw-stage-empty">暂无责任分工。</p>}
          </div>
        </section>
      </div>
    </section>
  );
}

export function StageRail({ process, selectedStageId, onSelect, onSaveRole }) {
  const stages = buildStageRail(process);
  const [expanded, setExpanded] = useState(false);
  const [roleOverviewOpen, setRoleOverviewOpen] = useState(false);
  const roleCount = useMemo(() => buildRoleOverview(process, stages).length, [process, stages]);
  const employeesById = useMemo(() => new Map((process.ai_employees || []).map((employee) => [employee.employee_id, employee])), [process.ai_employees]);
  const selectedIndex = stages.findIndex((stage) => stage.id === selectedStageId);
  const selectedStage = selectedIndex >= 0 ? stages[selectedIndex] : null;
  if (!stages.length) return null;
  return (
    <div className={`qw-stage-explorer ${expanded ? "is-expanded" : "is-collapsed"} ${selectedStage ? "is-open" : ""}`}>
      <div className="qw-stage-rail-head">
        <div><span className="qw-eyebrow">Project process</span><strong>项目流程</strong></div>
        <div className="qw-stage-rail-actions"><span>{expanded ? "点击节点查看内容与负责人" : "工作状态下已收起"}</span><button type="button" onClick={() => setRoleOverviewOpen(true)}><UsersRound size={14} />角色全景<strong>{roleCount}</strong></button><button type="button" aria-expanded={expanded} onClick={() => { setExpanded((current) => !current); if (expanded) onSelect?.(null); }}><Layers3 size={14} />{expanded ? "收起流程" : "查看流程"}<ChevronRight className="qw-stage-toggle-chevron" size={14} /></button></div>
      </div>
      {expanded && <nav className="qw-stage-rail" aria-label="项目流程">
        {stages.map((stage, index) => {
          const ownerCount = new Set(stage.tasks.map(ownerOf).filter((owner) => owner !== "待分配")).size;
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
      </nav>}
      {expanded && selectedStage && <StageDetail stage={selectedStage} index={selectedIndex} employeesById={employeesById} onClose={() => onSelect?.(null)} />}
      {roleOverviewOpen && <RoleOverviewDialog process={process} stages={stages} onClose={() => setRoleOverviewOpen(false)} onSaveRole={onSaveRole} />}
    </div>
  );
}
