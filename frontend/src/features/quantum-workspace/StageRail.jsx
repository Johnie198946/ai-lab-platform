import { buildStageRail } from "./quantumProjection";

const statusLabel = {
  NOT_STARTED: "未开始",
  IN_PROGRESS: "进行中",
  BLOCKED: "阻塞",
  PAUSED: "暂停",
  DONE: "完成",
};

export function StageRail({ process, selectedStageId, onSelect }) {
  const stages = buildStageRail(process);
  if (!stages.length) return null;
  return (
    <section className="qw-stage-rail" aria-label="IPD 阶段流程">
      {stages.map((stage, index) => (
        <button
          key={stage.id}
          type="button"
          className={selectedStageId === stage.id ? "active" : ""}
          onClick={() => onSelect?.(stage.id)}
        >
          <span className="qw-stage-index">{String(index + 1).padStart(2, "0")}</span>
          <span className="qw-stage-name">{stage.name}<small>{statusLabel[stage.status] ?? stage.status} · {stage.progress}%</small></span>
          <span className="qw-gates">{stage.gates.map((gate) => <i key={gate.id} className={gate.node_type.toLowerCase()} title={`${gate.node_type}: ${gate.name}`}>{gate.name}</i>)}</span>
        </button>
      ))}
    </section>
  );
}
