// Adapted from Sim Studio workflow canvas interaction patterns.
// Source: simstudioai/sim@981be9322dd0c63e323927a3a9410237b2c25b68 (Apache-2.0).

export const CANVAS_LAYOUT_VERSION = 1;

export function canvasLayoutStorageKey(workflowId) {
  return `ai-lab:sim-canvas-layout:v${CANVAS_LAYOUT_VERSION}:${workflowId || "draft"}`;
}

export function readCanvasLayout(workflowId, storage = globalThis.localStorage) {
  if (!storage) return { nodes: {}, viewport: null };
  try {
    const value = JSON.parse(storage.getItem(canvasLayoutStorageKey(workflowId)) || "null");
    if (!value || value.version !== CANVAS_LAYOUT_VERSION || typeof value.nodes !== "object") return { nodes: {}, viewport: null };
    const nodes = Object.fromEntries(Object.entries(value.nodes).filter(([, point]) => Number.isFinite(point?.x) && Number.isFinite(point?.y)));
    const viewport = Number.isFinite(value.viewport?.x) && Number.isFinite(value.viewport?.y) && Number.isFinite(value.viewport?.zoom) ? value.viewport : null;
    return { nodes, viewport };
  } catch {
    return { nodes: {}, viewport: null };
  }
}

export function writeCanvasLayout(workflowId, nodes, viewport, storage = globalThis.localStorage) {
  if (!storage) return false;
  const positions = Object.fromEntries(nodes.map((node) => [node.id, { x: Number(node.position.x), y: Number(node.position.y) }]));
  try {
    storage.setItem(canvasLayoutStorageKey(workflowId), JSON.stringify({ version: CANVAS_LAYOUT_VERSION, nodes: positions, viewport: viewport || null }));
    return true;
  } catch {
    return false;
  }
}

export function wouldCreateWorkflowCycle(edges, source, target) {
  const next = new Map();
  for (const edge of edges) {
    if (!next.has(edge.source)) next.set(edge.source, []);
    next.get(edge.source).push(edge.target);
  }
  const stack = [target];
  const visited = new Set();
  while (stack.length) {
    const node = stack.pop();
    if (node === source) return true;
    if (visited.has(node)) continue;
    visited.add(node);
    stack.push(...(next.get(node) || []));
  }
  return false;
}

export function validateCanvasConnection(connection, nodes, edges) {
  const source = connection?.source;
  const target = connection?.target;
  if (!source || !target) return "连接缺少源节点或目标节点";
  if (source === target) return "节点不能连接到自身";
  const ids = new Set(nodes.map((node) => node.id));
  if (!ids.has(source) || !ids.has(target)) return "连接引用了不存在的节点";
  const duplicate = edges.some((edge) => edge.source === source && edge.target === target && (edge.sourceHandle || null) === (connection.sourceHandle || null) && (edge.targetHandle || null) === (connection.targetHandle || null));
  if (duplicate) return "该连接已经存在";
  if (wouldCreateWorkflowCycle(edges, source, target)) return "Hermes 当前执行合同不允许循环依赖";
  return "";
}

export function autoLayoutWorkflowNodes(nodes, edges) {
  const ids = new Set(nodes.map((node) => node.id));
  const indegree = new Map(nodes.map((node) => [node.id, 0]));
  const outgoing = new Map(nodes.map((node) => [node.id, []]));
  for (const edge of edges) {
    if (!ids.has(edge.source) || !ids.has(edge.target)) continue;
    indegree.set(edge.target, (indegree.get(edge.target) || 0) + 1);
    outgoing.get(edge.source).push(edge.target);
  }
  const rank = new Map();
  const queue = [...nodes.filter((node) => indegree.get(node.id) === 0).map((node) => node.id)];
  queue.forEach((id) => rank.set(id, 0));
  while (queue.length) {
    const id = queue.shift();
    for (const target of outgoing.get(id) || []) {
      rank.set(target, Math.max(rank.get(target) || 0, (rank.get(id) || 0) + 1));
      indegree.set(target, indegree.get(target) - 1);
      if (indegree.get(target) === 0) queue.push(target);
    }
  }
  nodes.forEach((node) => { if (!rank.has(node.id)) rank.set(node.id, 0); });
  const rows = new Map();
  return nodes.map((node) => {
    const column = rank.get(node.id) || 0;
    const row = rows.get(column) || 0;
    rows.set(column, row + 1);
    return { ...node, position: { x: 90 + column * 330, y: 90 + row * 150 } };
  });
}
