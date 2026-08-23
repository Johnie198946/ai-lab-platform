export const POLL_INTERVAL_MS = 1000;
export const PLAN_POLL_ATTEMPTS = 360;
export const EXECUTION_POLL_ATTEMPTS = 900;

export function projectPlanToCanvas(plan) {
  const dsl = plan?.dsl ?? {};
  return {
    nodes: Array.isArray(dsl.nodes) ? dsl.nodes.map((node) => ({ ...node })) : [],
    edges: Array.isArray(dsl.edges) ? dsl.edges.map((edge) => ({ ...edge })) : [],
  };
}

export function projectPlanToReactFlow(plan) {
  const { nodes, edges } = projectPlanToCanvas(plan);
  return {
    nodes: nodes.map((node, index) => ({
      ...node,
      id: String(node.id),
      position: node.position || { x: 80, y: index * 120 },
      data: node.data || {
        label: `${node.name || node.label || node.id}${node.parameters?.capability_status ? ` · ${node.parameters.capability_status}` : ""}`,
        serverNode: node,
      },
    })),
    edges: edges.map((edge) => ({
      ...edge,
      id: String(edge.id || `${edge.source}->${edge.target}`),
      source: String(edge.source),
      target: String(edge.target),
    })),
  };
}

export function isStrictlyNewerPlan(next, previous) {
  if (!next?.id) return false;
  if (!previous?.id) return true;
  return next.id !== previous.id && Number(next.version) > Number(previous.version);
}

export async function pollForNewPlan(workflowId, previous, { getPlan, getLifecycleEvents, delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms)), attempts = PLAN_POLL_ATTEMPTS } = {}) {
  let cursor = 0;
  for (let attempt = 0; attempt < attempts; attempt += 1) {
    const events = await getLifecycleEvents(workflowId, cursor);
    cursor = Math.max(cursor, ...(events || []).map((event) => Number(event.id || event.seq || 0)));
    const failed = (events || []).find((event) =>
      String(event.event_type || event.type || "").includes("failed") || event.payload?.status === "failed",
    );
    if (failed) throw new Error(failed.message || "服务端规划失败");
    let next = null;
    try {
      next = await getPlan(workflowId);
    } catch (error) {
      if (error?.status !== 404) throw error;
      // The first plan legitimately returns 404 while the durable planning job is running.
    }
    if (isStrictlyNewerPlan(next, previous)) return next;
    await delay(POLL_INTERVAL_MS);
  }
  throw new Error("规划版本刷新超时，仍未收到新的服务端方案。");
}

export async function pollExecutionUntilTerminal(executionId, { getExecution, getExecutionEvents, getExecutionArtifacts, onUpdate = () => {}, delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms)), attempts = EXECUTION_POLL_ATTEMPTS } = {}) {
  let cursor = 0;
  let events = [];
  for (let attempt = 0; attempt < attempts; attempt += 1) {
    const execution = await getExecution(executionId);
    const nextEvents = await getExecutionEvents(executionId, cursor);
    events = events.concat(nextEvents || []);
    cursor = Math.max(cursor, ...(events || []).map((event) => Number(event.id || event.seq || 0)));
    onUpdate({ execution, events: [...events] });
    if (["awaiting_review", "completed", "failed", "cancelled"].includes(execution?.status)) {
      return { execution, events, artifacts: await getExecutionArtifacts(executionId) };
    }
    await delay(POLL_INTERVAL_MS);
  }
  throw new Error("执行状态刷新超时，服务端未返回终态。");
}

export function diffPlanVersions(previous, next) {
  const oldNodes = new Map(projectPlanToCanvas(previous).nodes.map((node) => [node.id, node]));
  const newNodes = new Map(projectPlanToCanvas(next).nodes.map((node) => [node.id, node]));
  return {
    added: [...newNodes.keys()].filter((id) => !oldNodes.has(id)),
    removed: [...oldNodes.keys()].filter((id) => !newNodes.has(id)),
    changed: [...newNodes.keys()].filter((id) => oldNodes.has(id) && JSON.stringify(oldNodes.get(id)) !== JSON.stringify(newNodes.get(id))),
    impact: next?.id && previous?.id ? "re-run scope: server plan changed" : "unconnected",
  };
}

export function assertRevisionAllowed(execution) {
  if (["queued", "running"].includes(execution?.status)) {
    throw new Error("active run cannot be revised");
  }
  return true;
}

export function canStartWorkflow(status, execution = null) {
  if (["queued", "running", "awaiting_review"].includes(execution?.status)) return false;
  return ["agent_ready", "ready"].includes(status);
}

const PLAN_ELIGIBLE_STATES = new Set([
  "planning",
  "awaiting_approval",
  "agent_ready",
  "ready",
  "queued",
  "running",
  "awaiting_review",
  "completed",
  "failed",
]);

export function shouldFetchWorkflowPlan(workflow, clarification = null) {
  const workflowStatus = textValue(workflow?.status).toLowerCase();
  const clarificationPhase = textValue(clarification?.session?.phase).toLowerCase();
  return Boolean(textValue(workflow?.active_plan_id))
    || PLAN_ELIGIBLE_STATES.has(workflowStatus)
    || PLAN_ELIGIBLE_STATES.has(clarificationPhase);
}

export function hasResultData(value) {
  if (Array.isArray(value)) return value.length > 0;
  if (value && typeof value === "object") return Object.keys(value).length > 0;
  return value !== null && value !== undefined;
}

export const RESULT_VIEW_TYPES = ["requirement", "evidence", "gate", "artifact"];

export function projectResultViews({ requirement, evidence = [], gate, artifact } = {}) {
  return [
    { type: "requirement", data: requirement ?? null },
    { type: "evidence", data: Array.isArray(evidence) ? evidence : [] },
    { type: "gate", data: gate ?? null },
    { type: "artifact", data: artifact ?? null },
  ];
}

export function showroomSessionIdFromSearch(search = "") {
  const value = new URLSearchParams(search).get("showroom_session_id")?.trim() || "";
  return /^[A-Za-z0-9._:-]{1,120}$/.test(value) ? value : "";
}

export function customerDemandIdFromSearch(search = "") {
  const value = new URLSearchParams(search).get("customer_demand_id")?.trim() || "";
  return /^dmd_[A-Za-z0-9_-]{1,44}$/.test(value) ? value : "";
}

const ARCHITECT_VIEWS = new Set(["office", "workbench"]);

export function architectViewFromSearch(search = "", defaultView = "workbench") {
  const fallback = ARCHITECT_VIEWS.has(defaultView) ? defaultView : "workbench";
  const requested = new URLSearchParams(search).get("view") || "";
  return ARCHITECT_VIEWS.has(requested) ? requested : fallback;
}

export function architectSearchWithView(search = "", view = "workbench") {
  const params = new URLSearchParams(search);
  params.set("view", ARCHITECT_VIEWS.has(view) ? view : "workbench");
  const next = params.toString();
  return next ? `?${next}` : "";
}

export function architectWorkflowForContext(workflows = [], { customerDemandId = "", showroomSessionId = "" } = {}) {
  const rows = Array.isArray(workflows) ? workflows : [];
  if (customerDemandId && showroomSessionId) return null;
  if (customerDemandId) {
    return rows.find((row) => String(row?.requirements_snapshot?.customer_demand?.source?.demand_id || "") === customerDemandId) || null;
  }
  if (showroomSessionId) {
    return rows.find((row) => String(row?.requirements_snapshot?.showroom_context?.source?.session_id || "") === showroomSessionId) || null;
  }
  return rows[0] || null;
}

const arrayValue = (value) => (Array.isArray(value) ? value : []);
const textValue = (value) => value === null || value === undefined ? "" : String(value).trim();
const nodeValueList = (...values) => {
  for (const value of values) {
    if (Array.isArray(value) && value.length) return value.map(textValue).filter(Boolean);
    const text = textValue(value);
    if (text) return [text];
  }
  return [];
};

function explicitNodeId(value) {
  if (!value || typeof value !== "object") return "";
  for (const source of [value, value.metadata, value.payload]) {
    if (!source || typeof source !== "object") continue;
    for (const key of ["source_node_id", "node_id", "producer_node_id", "plan_node_id"]) {
      const candidate = textValue(source[key]);
      if (candidate) return candidate;
    }
  }
  return "";
}

function explicitAgentId(value) {
  if (!value || typeof value !== "object") return "";
  return textValue(value.agent_id) || textValue(value.metadata?.agent_id);
}

function explicitArtifactNodeId(value) {
  if (!value || typeof value !== "object") return "";
  for (const source of [value, value.metadata]) {
    if (!source || typeof source !== "object") continue;
    for (const key of ["source_node_id", "node_id", "producer_node_id"]) {
      const candidate = textValue(source[key]);
      if (candidate) return candidate;
    }
  }
  return "";
}

function officeNodeStatus(planNode, runtimeNode) {
  const parameters = planNode?.parameters && typeof planNode.parameters === "object" ? planNode.parameters : {};
  const capability = textValue(planNode?.capability_status || parameters.capability_status).toUpperCase();
  if (capability === "UNCONNECTED") return "UNCONNECTED";
  if (planNode?.execution_disabled === true || parameters.execution_disabled === true || planNode?.execution_enabled === false || parameters.execution_enabled === false || capability.includes("REFERENCE")) return "reference";

  const status = textValue(runtimeNode?.status).toLowerCase();
  if (["pending", "queued", "waiting"].includes(status)) return "waiting";
  if (status === "planned") return "planned";
  if (status === "running") return "running";
  if (["blocked", "failed"].includes(status)) return status;
  if (["completed", "done"].includes(status)) return "done";
  if (status === "succeeded") return "succeeded";
  if (["cancelled", "canceled"].includes(status)) return "cancelled";
  if (status === "awaiting_review") return "awaiting_review";
  return "planned";
}

function trustedExecutionTruth(execution) {
  if (!textValue(execution?.id)) return "PLAN";
  const truth = textValue(execution?.truth).toUpperCase();
  if (["REPLAY", "SIMULATION"].includes(truth)) return truth;
  if (truth !== "LIVE") return "PLAN";
  const status = textValue(execution?.status).toLowerCase();
  const hasRunReceipt = Boolean(textValue(execution?.started_at || execution?.hermes_session_id));
  return hasRunReceipt && !["", "draft", "pending", "queued"].includes(status) ? "LIVE" : "PLAN";
}

function officeTruthState(planNode, runtimeNode, executionTruth) {
  const parameters = planNode?.parameters && typeof planNode.parameters === "object" ? planNode.parameters : {};
  const capability = textValue(planNode?.capability_status || parameters.capability_status).toUpperCase();
  if (capability === "UNCONNECTED" || planNode?.execution_disabled === true || parameters.execution_disabled === true || planNode?.execution_enabled === false || parameters.execution_enabled === false) {
    return { status: "UNCONNECTED" };
  }
  if (!runtimeNode) return { status: "PLAN" };
  return { status: executionTruth };
}

export function projectOfficeProjection({ workflow, plan, execution, events, artifacts, connectionState } = {}) {
  const dsl = plan?.dsl && typeof plan.dsl === "object" ? plan.dsl : plan && typeof plan === "object" ? plan : {};
  const planNodes = arrayValue(dsl.nodes).filter((node) => node && typeof node === "object" && textValue(node.id));
  const planNodeIds = new Set(planNodes.map((node) => textValue(node.id)));
  const runtimeByNodeId = new Map();
  for (const runtimeNode of arrayValue(execution?.nodes)) {
    const nodeId = explicitNodeId(runtimeNode);
    if (planNodeIds.has(nodeId) && !runtimeByNodeId.has(nodeId)) runtimeByNodeId.set(nodeId, runtimeNode);
  }

  const latestEventByNodeId = new Map();
  let latestSeq = null;
  for (const event of arrayValue(events)) {
    const eventReceiptId = textValue(event?.event_id || event?.id);
    if (!eventReceiptId) continue;
    const numericSeq = Number(event?.seq ?? event?.id);
    if (Number.isFinite(numericSeq)) latestSeq = Math.max(latestSeq ?? numericSeq, numericSeq);
    const nodeId = explicitNodeId(event);
    if (planNodeIds.has(nodeId)) latestEventByNodeId.set(nodeId, event);
  }

  const runtimeNodeIdsByAgent = new Map();
  for (const [nodeId, runtimeNode] of runtimeByNodeId) {
    const agentId = explicitAgentId(runtimeNode);
    if (!agentId) continue;
    if (!runtimeNodeIdsByAgent.has(agentId)) runtimeNodeIdsByAgent.set(agentId, new Set());
    runtimeNodeIdsByAgent.get(agentId).add(nodeId);
  }

  const safeArtifacts = arrayValue(artifacts);
  const executionTruth = trustedExecutionTruth(execution);
  const artifactsByNodeId = new Map(planNodes.map((node) => [textValue(node.id), []]));
  for (const artifact of safeArtifacts) {
    if (!artifact || typeof artifact !== "object") continue;
    let nodeId = explicitArtifactNodeId(artifact);
    if (!planNodeIds.has(nodeId)) {
      const agentNodes = runtimeNodeIdsByAgent.get(explicitAgentId(artifact));
      nodeId = agentNodes?.size === 1 ? [...agentNodes][0] : "";
    }
    if (planNodeIds.has(nodeId)) artifactsByNodeId.get(nodeId).push(artifact);
  }

  const seats = planNodes.map((node) => {
    const id = textValue(node.id);
    const parameters = node.parameters && typeof node.parameters === "object" ? node.parameters : {};
    const runtimeNode = runtimeByNodeId.get(id) || null;
    const roleIds = arrayValue(parameters.role_ids).map(textValue).filter(Boolean);
    return {
      id,
      name: textValue(node.name || node.label || node.id),
      businessRole: textValue(node.business_role || parameters.business_role || parameters.role) || roleIds.join(" · "),
      roleIds,
      runtimeAgentId: explicitAgentId(runtimeNode) || null,
      input: nodeValueList(
        node.inputs,
        parameters.inputs,
        parameters.input_artifacts,
        node.input,
        parameters.input,
        node.task,
        parameters.task,
        node.goal,
        parameters.goal,
        workflow?.description,
      ),
      expectedOutput: nodeValueList(
        node.outputs,
        parameters.outputs,
        parameters.output_deliverables,
        node.output_deliverables,
        node.output,
        parameters.output,
        node.deliverable,
        parameters.deliverable,
        plan?.deliverable,
      ),
      status: officeNodeStatus(node, runtimeNode),
      truthState: officeTruthState(node, runtimeNode, executionTruth),
      lastEvent: latestEventByNodeId.get(id) || null,
      artifacts: artifactsByNodeId.get(id),
    };
  });

  const truthMode = executionTruth !== "PLAN" || textValue(plan?.id || dsl.plan_id) || seats.length
    ? executionTruth
    : "UNCONNECTED";
  const normalizedConnection = textValue(connectionState).toUpperCase();
  const projectedConnection = ["CONNECTED", "SYNCING", "UNCONNECTED"].includes(normalizedConnection) ? normalizedConnection : "UNCONNECTED";
  const governance = textValue(plan?.capability?.status).toUpperCase();
  const governanceState = ["CONNECTED", "UNCONNECTED"].includes(governance) ? governance : "UNCONNECTED";
  const governanceTruth = textValue(plan?.capability?.truth).toUpperCase();
  const governanceCheckedAt = textValue(plan?.capability?.checked_at) || null;
  const approvalState = plan?.frozen_at
    ? "APPROVED"
    : (["awaiting_approval", "planning"].includes(textValue(workflow?.status).toLowerCase()) ? "PENDING" : "UNAPPROVED");
  const timestampCandidates = [
    workflow?.updated_at,
    workflow?.created_at,
    plan?.frozen_at,
    plan?.created_at,
    execution?.finished_at,
    execution?.started_at,
    execution?.created_at,
    ...arrayValue(events).map((event) => event?.created_at),
  ].map(textValue).filter((value) => value && Number.isFinite(Date.parse(value)));
  const updatedAt = timestampCandidates.sort((left, right) => Date.parse(right) - Date.parse(left))[0] || null;
  const nodeIndexById = new Map(planNodes.map((node, index) => [textValue(node.id), index]));
  const transfers = [];
  for (const artifact of safeArtifacts) {
    const sourceNodeId = explicitArtifactNodeId(artifact);
    if (!planNodeIds.has(sourceNodeId)) continue;
    for (const edge of arrayValue(dsl.edges)) {
      const targetNodeId = textValue(edge?.target);
      if (textValue(edge?.source) !== sourceNodeId || !planNodeIds.has(targetNodeId)) continue;
      transfers.push({
        id: `${textValue(artifact.id) || textValue(artifact.title)}:${targetNodeId}`,
        artifactId: textValue(artifact.id) || null,
        artifactTitle: textValue(artifact.title) || "输出物",
        sourceNodeId,
        targetNodeId,
        sourceIndex: nodeIndexById.get(sourceNodeId),
        targetIndex: nodeIndexById.get(targetNodeId),
      });
    }
  }

  return {
    schemaVersion: "office-projection/v1",
    workflowId: textValue(workflow?.id) || null,
    planId: textValue(plan?.id || dsl.plan_id) || null,
    executionId: textValue(execution?.id) || null,
    snapshotVersion: textValue(execution?.snapshot_version || execution?.snapshotVersion || plan?.snapshot_version) || null,
    cursor: latestSeq,
    latestSeq,
    truthMode,
    connectionState: projectedConnection,
    updatedAt,
    approvalState,
    governanceState,
    governanceTruth: ["LIVE", "UNCONNECTED"].includes(governanceTruth) ? governanceTruth : "UNCONNECTED",
    governanceCheckedAt,
    title: textValue(workflow?.title || dsl.name) || "未命名任务",
    stage: textValue(execution?.status || workflow?.status) || (seats.length ? "planned" : "draft"),
    seats,
    artifacts: safeArtifacts,
    transfers,
  };
}
