import { Bot, CalendarDays, CircleAlert, MessageSquare, UserRound } from "lucide-react";
import { buildBoardColumns } from "./quantumProjection";

const statusTone = { TODO: "neutral", IN_PROGRESS: "blue", BLOCKED: "red", PAUSED: "amber", DONE: "green" };

export function ProjectTaskboard({ process, selectedStageId, onTaskOpen, onStatusChange, intake }) {
  const columns = buildBoardColumns(process).map((column) => ({
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
    <div className="qw-board-scroll">
      <div className="qw-board">
        <div className="qw-intake-column"><div className="qw-column-head"><span>需求收敛</span><small>Business Intake</small></div>{intake}</div>
        {columns.map((column) => (
          <section className="qw-board-column" key={column.key} onDragOver={(event) => event.preventDefault()} onDrop={(event) => drop(event, column.key)}>
            <div className="qw-column-head"><span>{column.label}</span><small>{column.tasks.length}</small></div>
            <div className="qw-card-stack">{column.tasks.map((task) => (
              <article className="qw-task-card" key={task.id} draggable onDragStart={(event) => { event.dataTransfer.setData("text/qw-task-id", task.id); event.dataTransfer.effectAllowed = "move"; }} onClick={() => onTaskOpen(task)}>
                <div className="qw-task-top"><span className={`qw-status-dot ${statusTone[task.displayStatus]}`} /><span>{stages.get(task.stage_id)?.name ?? "未分阶段"}</span>{task.risk === "MEDIUM" && <CircleAlert size={14} />}</div>
                <h4>{task.title}</h4><p>{task.summary}</p>
                <div className="qw-task-tags"><span><UserRound size={13} />{task.assignee_id || task.assignee_role || "待分配"}</span><span><Bot size={13} />{task.workflow_status}</span></div>
                <div className="qw-task-footer"><span><CalendarDays size={13} />{task.planned_finish_at ? task.planned_finish_at.slice(0, 10) : "待排期"}</span><button aria-label={`打开 ${task.title} 对话`}><MessageSquare size={15} /></button></div>
              </article>
            ))}{!column.tasks.length && <div className="qw-column-empty">拖动任务到这里</div>}</div>
          </section>
        ))}
      </div>
    </div>
  );
}
