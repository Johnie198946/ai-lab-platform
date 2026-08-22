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
