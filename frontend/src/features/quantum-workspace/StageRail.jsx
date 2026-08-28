import { CalendarDays, CheckCircle2, ChevronRight, ShieldCheck, UserRound, X } from "lucide-react";
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

function StageDetail({ stage, index, onClose }) {
  const owners = [...new Set(stage.tasks.map(ownerOf).filter((owner) => owner !== "待分配"))];
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
            {stage.tasks.map((task) => <div key={task.id}><UserRound size={14} /><span><strong>{ownerOf(task)}</strong><small>{task.title}</small></span></div>)}
            {stage.gates.map((gate) => <div key={gate.id}><ShieldCheck size={14} /><span><strong>{gate.responsible_role || "待分配"}</strong><small>{gate.node_type} · {gate.name}</small></span></div>)}
            {!stage.tasks.length && !stage.gates.length && <p className="qw-stage-empty">暂无责任分工。</p>}
          </div>
        </section>
      </div>
    </section>
  );
}

export function StageRail({ process, selectedStageId, onSelect }) {
  const stages = buildStageRail(process);
  const selectedIndex = stages.findIndex((stage) => stage.id === selectedStageId);
  const selectedStage = selectedIndex >= 0 ? stages[selectedIndex] : null;
  if (!stages.length) return null;
  return (
    <div className={`qw-stage-explorer ${selectedStage ? "is-open" : ""}`}>
      <div className="qw-stage-rail-head">
        <div><span className="qw-eyebrow">Project process</span><strong>项目流程</strong></div>
        <span>点击节点查看内容与负责人</span>
      </div>
      <nav className="qw-stage-rail" aria-label="IPD 项目流程">
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
      </nav>
      {selectedStage && <StageDetail stage={selectedStage} index={selectedIndex} onClose={() => onSelect?.(null)} />}
    </div>
  );
}
