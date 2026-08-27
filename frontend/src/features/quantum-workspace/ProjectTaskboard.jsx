import { ArrowUpRight, Bot, CalendarDays, CircleAlert, Link2, MessageSquare, Plus, UserRound } from "lucide-react";
import { buildBoardColumns, buildLifecycleColumns } from "./quantumProjection";

const statusTone = { TODO: "neutral", IN_PROGRESS: "blue", BLOCKED: "red", PAUSED: "amber", DONE: "green" };

const formattedCost = (value) => `$${Number(value || 0).toFixed(4)}`;

export function ProjectTaskboard({
  process,
  workflows,
  selectedStageId,
  onTaskOpen,
  onStatusChange,
  onWorkflowOpen,
  onBindWorkflow,
  onCreateTask,
  boardMode,
  onBoardModeChange,
  workflowState,
  intake,
}) {
  const sourceColumns = boardMode === "lifecycle"
    ? buildLifecycleColumns(process, workflows)
    : buildBoardColumns(process);
  const columns = sourceColumns.map((column) => ({
    ...column,
    tasks: selectedStageId ? column.tasks.filter((task) => task.stage_id === selectedStageId) : column.tasks,
  }));
  const stages = new Map((process.stages ?? []).map((stage) => [stage.id, stage]));
  const drop = (event, status) => {
    event.preventDefault();
    const taskId = event.dataTransfer.getData("text/qw-task-id");
    if (taskId) onStatusChange(taskId, status);
  };

  return (
    <section className="qw-taskboard-shell" aria-label="QuantumWorkspace Taskboard">
      <header className="qw-board-toolbar">
        <div className="qw-board-mode" aria-label="Taskboard 数据视图">
          <button type="button" className={boardMode === "status" ? "active" : ""} aria-pressed={boardMode === "status"} onClick={() => onBoardModeChange("status")}>项目状态</button>
          <button type="button" className={boardMode === "lifecycle" ? "active" : ""} aria-pressed={boardMode === "lifecycle"} onClick={() => onBoardModeChange("lifecycle")}>Dashi 生命周期</button>
        </div>
        <div className={`qw-canonical-state ${workflowState.toLowerCase()}`}><span>{workflowState}</span><small>{boardMode === "lifecycle" ? "Workflow / Execution / Artifact / Usage" : "ProjectProcess"}</small></div>
        <button type="button" className="qw-button primary" onClick={onCreateTask} disabled={!process.process_instance_id}><Plus size={15} />新任务</button>
      </header>
      {boardMode === "lifecycle" && <p className="qw-board-contract">生命周期列是 AI Lab canonical 数据的只读投影；拖拽只在“项目状态”视图生效。</p>}
      <div className="qw-board-scroll">
      <div className={`qw-board ${boardMode === "lifecycle" ? "lifecycle" : ""}`}>
        {boardMode === "status" && <div className="qw-intake-column"><div className="qw-column-head"><span>需求收敛</span><small>Business Intake</small></div>{intake}</div>}
        {columns.map((column) => (
          <section className="qw-board-column" key={column.key} onDragOver={boardMode === "status" ? (event) => event.preventDefault() : undefined} onDrop={boardMode === "status" ? (event) => drop(event, column.key) : undefined}>
            <div className="qw-column-head"><span>{column.label}{column.description && <em>{column.description}</em>}</span><small>{column.tasks.length}</small></div>
            <div className="qw-card-stack">{column.tasks.map((task) => (
              <article className="qw-task-card" key={task.id} draggable={boardMode === "status"} onDragStart={boardMode === "status" ? (event) => { event.dataTransfer.setData("text/qw-task-id", task.id); event.dataTransfer.effectAllowed = "move"; } : undefined} onClick={() => onTaskOpen(task)}>
                <div className="qw-task-top"><span className={`qw-status-dot ${statusTone[task.displayStatus]}`} /><span>{stages.get(task.stage_id)?.name ?? "未分阶段"}</span>{task.risk === "MEDIUM" && <CircleAlert size={14} />}</div>
                <h4>{task.title}</h4><p>{task.summary}</p>
                <div className="qw-task-tags"><span><UserRound size={13} />{task.assignee_id || task.assignee_role || "待分配"}</span><span><Bot size={13} />{task.workflowStatus || task.workflow_status}</span>{task.truth && <span className={`qw-truth ${task.truth.toLowerCase()}`}>{task.truth}</span>}</div>
                {boardMode === "lifecycle" && <dl className="qw-canonical-facts"><div><dt>Execution</dt><dd>{task.executionId ? task.executionId.slice(-8) : "尚未创建"}</dd></div><div><dt>工件</dt><dd>{task.artifactCount}</dd></div><div><dt>Token / 费用</dt><dd>{task.tokenUsed} / {formattedCost(task.estimatedCostUsd)}</dd></div><div><dt>进度</dt><dd>{task.executionId ? `${task.progress}%` : "—"}</dd></div></dl>}
                {task.errorMessage && <p className="qw-task-runtime-error">{task.errorMessage}</p>}
                <div className="qw-task-footer"><span><CalendarDays size={13} />{task.planned_finish_at ? task.planned_finish_at.slice(0, 10) : "待排期"}</span><span className="qw-card-actions">{task.workflowId || task.workflow_id ? <button type="button" aria-label={`打开 ${task.title} 真实工作流`} onClick={(event) => { event.stopPropagation(); onWorkflowOpen(task.workflowId || task.workflow_id); }}><ArrowUpRight size={15} /></button> : <button type="button" aria-label={`为 ${task.title} 绑定工作流`} onClick={(event) => { event.stopPropagation(); onBindWorkflow(task); }}><Link2 size={15} /></button>}<button type="button" aria-label={`打开 ${task.title} 对话`}><MessageSquare size={15} /></button></span></div>
              </article>
            ))}{!column.tasks.length && <div className="qw-column-empty">{boardMode === "status" ? "拖动任务到这里" : "暂无 canonical 记录"}</div>}</div>
          </section>
        ))}
      </div>
      </div>
    </section>
  );
}
