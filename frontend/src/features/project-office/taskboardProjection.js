const text = (value) => value === null || value === undefined ? "" : String(value).trim();

export const TASKBOARD_LANES = [
  { id: "intake", label: "需求收敛", description: "需求输入、澄清与确认" },
  { id: "planning", label: "方案与批准", description: "计划生成、评审与人工门禁" },
  { id: "execution", label: "真实执行", description: "仅展示 AI Lab 执行台账" },
  { id: "review", label: "成果复核", description: "工件与证据等待人工确认" },
  { id: "completed", label: "已完成", description: "已由服务端确认完成" },
  { id: "attention", label: "需要处理", description: "失败、取消或未知状态" },
];

const STATUS_LANES = new Map([
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

export function taskboardStatus(workflow = {}) {
  const executionStatus = text(workflow.latest_execution?.status).toLowerCase();
  const workflowStatus = text(workflow.status).toLowerCase();
  return STATUS_LANES.get(executionStatus) || STATUS_LANES.get(workflowStatus) || "attention";
}

function executionTruth(execution) {
  if (!text(execution?.id)) return "PLAN";
  const declared = text(execution?.truth).toUpperCase();
  if (["REPLAY", "SIMULATION"].includes(declared)) return declared;
  if (declared !== "LIVE") return "PLAN";
  const status = text(execution?.status).toLowerCase();
  const receipt = Boolean(text(execution?.started_at || execution?.hermes_session_id));
  return receipt && !["", "draft", "pending", "queued"].includes(status) ? "LIVE" : "PLAN";
}

function boardItem(workflow) {
  const execution = workflow?.latest_execution && typeof workflow.latest_execution === "object"
    ? workflow.latest_execution
    : null;
  const knownWorkflowStatus = STATUS_LANES.has(text(workflow?.status).toLowerCase());
  const laneId = taskboardStatus(workflow);
  return {
    workflowId: text(workflow?.id) || null,
    executionId: text(execution?.id) || null,
    planId: text(execution?.plan_id || workflow?.active_plan_id) || null,
    title: text(workflow?.title) || "未命名任务",
    description: text(workflow?.description),
    desiredOutput: text(workflow?.desired_output),
    workflowStatus: text(workflow?.status).toLowerCase() || "unknown",
    executionStatus: text(execution?.status).toLowerCase() || null,
    laneId,
    truth: knownWorkflowStatus || execution ? executionTruth(execution) : "UNCONNECTED",
    progress: Number.isFinite(Number(execution?.progress)) ? Number(execution.progress) : 0,
    tokenUsed: Number(execution?.input_tokens || 0) + Number(execution?.output_tokens || 0) + Number(execution?.reasoning_tokens || 0),
    estimatedCostUsd: Number(execution?.estimated_cost_usd || 0),
    artifactCount: Number(execution?.artifact_count || 0),
    provider: text(execution?.provider_used),
    model: text(execution?.model_used),
    errorMessage: text(execution?.error_message),
    updatedAt: text(execution?.finished_at || execution?.started_at || execution?.created_at || workflow?.updated_at || workflow?.created_at) || null,
  };
}

export function taskboardProjection(workflows = []) {
  const items = (Array.isArray(workflows) ? workflows : [])
    .filter((workflow) => workflow && typeof workflow === "object" && text(workflow.id))
    .map(boardItem);
  return {
    schemaVersion: "taskboard-projection/v1",
    source: "AI_LAB_CANONICAL",
    items,
    lanes: TASKBOARD_LANES.map((lane) => ({
      ...lane,
      items: items.filter((item) => item.laneId === lane.id),
    })),
  };
}
