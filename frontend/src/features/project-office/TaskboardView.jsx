import { AlertTriangle, ArrowRight, CircleCheck, Clock3, FileCheck2, PlayCircle, Plus } from "lucide-react";
import "./TaskboardView.css";

const ICONS = {
  intake: Clock3,
  planning: FileCheck2,
  execution: PlayCircle,
  review: AlertTriangle,
  completed: CircleCheck,
  attention: AlertTriangle,
};

const label = (item) => item.executionStatus || item.workflowStatus || "unknown";
const formattedCost = (value) => `$${Number(value || 0).toFixed(4)}`;

function TaskCard({ item, onOpenWorkflow }) {
  return <button className="taskboard-card" type="button" onClick={() => onOpenWorkflow(item.workflowId)}>
    <span className="taskboard-card__truth" data-truth={item.truth}>{item.truth}</span>
    <strong>{item.title}</strong>
    <p>{item.description || item.desiredOutput || "服务端未提供任务摘要"}</p>
    <div className="taskboard-card__state"><span>{label(item)}</span>{item.executionId && <span>{item.progress}%</span>}</div>
    {item.errorMessage && <small className="taskboard-card__error">{item.errorMessage}</small>}
    <dl>
      <div><dt>Workflow</dt><dd>{item.workflowId}</dd></div>
      <div><dt>Execution</dt><dd>{item.executionId || "尚未创建"}</dd></div>
      <div><dt>工件</dt><dd>{item.artifactCount}</dd></div>
      <div><dt>Token / 费用</dt><dd>{item.tokenUsed} / {formattedCost(item.estimatedCostUsd)}</dd></div>
    </dl>
    <span className="taskboard-card__open">打开真实工作流 <ArrowRight size={14} /></span>
  </button>;
}

export default function TaskboardView({ projection, onOpenWorkflow, onCreateTask, error = "", busy = false }) {
  return <section className="taskboard" aria-label="AI Lab Taskboard">
    <header className="taskboard__header">
      <div><span>WORK OFFICE · AI LAB CANONICAL</span><h1>项目任务板</h1><p>Workflow、Execution、Event、Artifact 与 Usage 均来自 AI Lab；此视图不执行任务，也不维护第二状态源。</p></div>
      <button type="button" onClick={onCreateTask}><Plus size={16} />新任务</button>
    </header>
    <div className="taskboard__status"><span>{busy ? "SYNCING" : error ? "UNCONNECTED" : "CONNECTED"}</span><b>{projection.items.length} 个服务端任务</b></div>
    {error && <div className="taskboard__error" role="alert"><strong>UNCONNECTED</strong><span>{error}</span></div>}
    <div className="taskboard__lanes">
      {projection.lanes.map((lane) => {
        const Icon = ICONS[lane.id] || Clock3;
        return <section className={`taskboard-lane taskboard-lane--${lane.id}`} key={lane.id}>
          <header><Icon size={16} /><div><strong>{lane.label}</strong><small>{lane.description}</small></div><span>{lane.items.length}</span></header>
          <div className="taskboard-lane__items">
            {lane.items.length
              ? lane.items.map((item) => <TaskCard item={item} onOpenWorkflow={onOpenWorkflow} key={item.workflowId} />)
              : <p className="taskboard-lane__empty">暂无服务端记录</p>}
          </div>
        </section>;
      })}
    </div>
  </section>;
}
