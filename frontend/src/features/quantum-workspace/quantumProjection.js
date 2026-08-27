const BOARD_COLUMNS = [
  { key: "TODO", label: "待开始" },
  { key: "IN_PROGRESS", label: "进行中" },
  { key: "BLOCKED", label: "阻塞 / 暂停" },
  { key: "DONE", label: "已完成" },
];

export const LIFECYCLE_COLUMNS = [
  { key: "intake", label: "需求收敛", description: "需求输入、澄清与确认" },
  { key: "planning", label: "方案与批准", description: "计划生成、评审与人工门禁" },
  { key: "execution", label: "真实执行", description: "AI Lab canonical 执行台账" },
  { key: "review", label: "成果复核", description: "工件与证据等待人工确认" },
  { key: "completed", label: "已完成", description: "已由服务端确认完成" },
  { key: "attention", label: "需要处理", description: "失败、取消、未连接或未知状态" },
];

const LIFECYCLE_STATUS = new Map([
  ["draft", "intake"],
  ["clarifying", "intake"],
  ["clarifying_pending", "intake"],
  ["awaiting_requirement_confirmation", "intake"],
  ["planning", "planning"],
  ["building_agent", "planning"],
  ["awaiting_approval", "planning"],
  ["agent_ready", "execution"],
  ["ready", "execution"],
  ["queued", "execution"],
  ["running", "execution"],
  ["awaiting_review", "review"],
  ["completed", "completed"],
  ["succeeded", "completed"],
  ["failed", "attention"],
  ["cancelled", "attention"],
  ["canceled", "attention"],
  ["needs_attention", "attention"],
]);

const cleanText = (value) => value === null || value === undefined ? "" : String(value).trim();

function canonicalTruth(execution) {
  if (!cleanText(execution?.id)) return "PLAN";
  const declared = cleanText(execution?.truth).toUpperCase();
  if (["REPLAY", "SIMULATION"].includes(declared)) return declared;
  if (declared !== "LIVE") return "PLAN";
  const status = cleanText(execution?.status).toLowerCase();
  const receipt = Boolean(cleanText(execution?.started_at || execution?.hermes_session_id));
  return receipt && !["", "draft", "pending", "queued"].includes(status) ? "LIVE" : "PLAN";
}

function lifecycleItem(task, workflow) {
  const execution = workflow?.latest_execution && typeof workflow.latest_execution === "object"
    ? workflow.latest_execution
    : null;
  const workflowStatus = cleanText(workflow?.status || task.workflow_status).toLowerCase();
  const executionStatus = cleanText(execution?.status).toLowerCase();
  const laneId = LIFECYCLE_STATUS.get(executionStatus) || LIFECYCLE_STATUS.get(workflowStatus) || "attention";
  return {
    ...task,
    laneId,
    workflow: workflow || null,
    workflowId: cleanText(workflow?.id || task.workflow_id) || null,
    workflowStatus: workflowStatus || "unconnected",
    executionId: cleanText(execution?.id) || null,
    executionStatus: executionStatus || null,
    truth: workflow ? canonicalTruth(execution) : "UNCONNECTED",
    progress: Number.isFinite(Number(execution?.progress)) ? Number(execution.progress) : 0,
    artifactCount: Number(execution?.artifact_count || 0),
    tokenUsed: Number(execution?.input_tokens || 0) + Number(execution?.output_tokens || 0) + Number(execution?.reasoning_tokens || 0),
    estimatedCostUsd: Number(execution?.estimated_cost_usd || 0),
    provider: cleanText(execution?.provider_used),
    model: cleanText(execution?.model_used),
    errorMessage: cleanText(execution?.error_message),
  };
}

export function buildLifecycleColumns(process = {}, workflows = []) {
  const byId = new Map(
    (Array.isArray(workflows) ? workflows : [])
      .filter((workflow) => workflow && cleanText(workflow.id))
      .map((workflow) => [cleanText(workflow.id), workflow]),
  );
  const items = (Array.isArray(process.tasks) ? process.tasks : [])
    .map((task) => lifecycleItem(task, byId.get(cleanText(task.workflow_id))));
  return LIFECYCLE_COLUMNS.map((column) => ({
    ...column,
    tasks: items.filter((item) => item.laneId === column.key),
  }));
}

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
