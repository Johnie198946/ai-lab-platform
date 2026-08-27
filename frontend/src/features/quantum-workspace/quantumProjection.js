const BOARD_COLUMNS = [
  { key: "TODO", label: "待开始" },
  { key: "IN_PROGRESS", label: "进行中" },
  { key: "BLOCKED", label: "阻塞 / 暂停" },
  { key: "DONE", label: "已完成" },
];

const boardStatus = (status) => (status === "PAUSED" ? "BLOCKED" : status);

export function buildBoardColumns(process = {}) {
  const tasks = Array.isArray(process.tasks) ? process.tasks : [];
  return BOARD_COLUMNS.map((column) => ({
    ...column,
    tasks: tasks
      .filter((task) => boardStatus(task.status) === column.key)
      .map((task) => ({ ...task, displayStatus: task.status })),
  }));
}

export function buildStageRail(process = {}) {
  const gates = Array.isArray(process.gates) ? process.gates : [];
  return [...(process.stages ?? [])]
    .sort((left, right) => (left.order ?? 0) - (right.order ?? 0))
    .map((stage) => ({
      ...stage,
      gates: gates.filter((gate) => gate.stage_id === stage.id),
    }));
}

export function buildScheduleRows(process = {}) {
  return (process.tasks ?? []).map((task) => ({
    ...task,
    start: task.planned_start_at ?? null,
    finish: task.planned_finish_at ?? null,
    scheduleStatus:
      task.planned_start_at && task.planned_finish_at ? "SCHEDULED" : "UNSCHEDULED",
  }));
}

export function layoutProjectGraph(graph = {}) {
  const nodes = (graph.nodes ?? []).map((node, index) => ({
    ...node,
    position: {
      x: 80 + (index % 4) * 280,
      y: 80 + Math.floor(index / 4) * 150,
    },
    data: { ...node, label: node.label ?? node.id },
  }));
  return {
    nodes,
    edges: (graph.edges ?? []).map((edge) => ({
      ...edge,
      type: edge.type ?? "smoothstep",
    })),
  };
}
