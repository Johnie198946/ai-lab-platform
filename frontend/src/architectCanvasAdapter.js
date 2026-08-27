const NODE_TYPES = new Set(["agent", "artifact", "gate", "human"]);
const SERVER_NODE_TYPE_MAP = {
  KNOWLEDGE_RETRIEVAL: "agent",
  LLM_INFERENCE: "agent",
  PROMPT_TRANSFORM: "agent",
  FILTER_PASS: "gate",
  AGGREGATION: "agent",
  OUTPUT_FORMAT: "artifact",
};
const NODE_FIELDS = new Set(["id", "type", "data", "position"]);
const DATA_FIELDS = new Set(["name", "label", "node_type", "parameters", "retry", "loop", "loops", "parallel", "parallels"]);
const EDGE_FIELDS = new Set(["id", "source", "target", "sourceHandle", "targetHandle", "condition"]);
const UNSUPPORTED_SEMANTICS = new Set(["loop", "loops", "parallel", "parallels", "retry"]);

function object(value, label) {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error(`${label} must be an object`);
  }
  return value;
}

function strictFields(value, allowed, label) {
  for (const key of Object.keys(value)) {
    if (!allowed.has(key)) throw new Error(`unknown ${label} field: ${key}`);
  }
}

function text(value, label) {
  if (typeof value !== "string" || value.length === 0) throw new Error(`${label} is required`);
  return value;
}

function parameters(value, label) {
  const result = value === undefined ? {} : object(value, label);
  for (const key of Object.keys(result)) {
    if (UNSUPPORTED_SEMANTICS.has(key)) throw new Error(`unsupported execution semantics: ${key}`);
  }
  return { ...result };
}

function edgeCondition(edge, index) {
  if (!Object.prototype.hasOwnProperty.call(edge, "condition")) return {};
  if (edge.condition !== null && typeof edge.condition !== "string") {
    throw new Error(`edge[${index}].condition must be a string or null`);
  }
  return { condition: edge.condition };
}

function canonicalType(node, index) {
  const mappedType = node.node_type === undefined ? undefined : SERVER_NODE_TYPE_MAP[node.node_type];
  if (node.node_type !== undefined && mappedType === undefined) {
    throw new Error(`unsupported node_type: ${node.node_type}`);
  }
  if (node.type !== undefined && mappedType !== undefined && node.type !== mappedType) {
    throw new Error(`node_type and visual type mismatch: ${node.node_type}/${node.type}`);
  }
  return text(node.type ?? mappedType, `canonical node[${index}].type`);
}

function canonicalName(node, index) {
  return text(node.name ?? node.data?.name ?? node.data?.label, `canonical node[${index}].name`);
}

function canonicalParameters(node, index) {
  return parameters(node.parameters ?? node.data?.parameters, `canonical node[${index}].parameters`);
}

function serverNode(node, index) {
  object(node, `node[${index}]`);
  strictFields(node, NODE_FIELDS, "node");
  const id = text(node.id, `node[${index}].id`);
  const type = text(node.type, `node[${index}].type`);
  if (!NODE_TYPES.has(type)) throw new Error(`unsupported node type: ${type}`);
  const data = node.data === undefined ? {} : object(node.data, `node[${index}].data`);
  strictFields(data, DATA_FIELDS, "node data");
  for (const key of UNSUPPORTED_SEMANTICS) {
    if (Object.prototype.hasOwnProperty.call(data, key)) {
      throw new Error(`unsupported execution semantics: ${key}`);
    }
  }
  const nodeType = text(data.node_type, `node[${index}].data.node_type`);
  if (SERVER_NODE_TYPE_MAP[nodeType] !== type) {
    throw new Error(`node_type and visual type mismatch: ${nodeType}/${type}`);
  }
  const name = data.name ?? data.label;
  return {
    id,
    node_type: nodeType,
    name: text(name, `node[${index}].data.name`),
    parameters: parameters(data.parameters, `node[${index}].data.parameters`),
  };
}

function serverEdge(edge, index, nodes) {
  object(edge, `edge[${index}]`);
  strictFields(edge, EDGE_FIELDS, "edge");
  const source = text(edge.source, `edge[${index}].source`);
  const target = text(edge.target, `edge[${index}].target`);
  if (!nodes.has(source) || !nodes.has(target)) throw new Error(`dangling edge: ${source}->${target}`);
  const sourceType = nodes.get(source);
  const targetType = nodes.get(target);
  const sourceHandle = edge.sourceHandle ?? null;
  const targetHandle = edge.targetHandle ?? null;
  const validSource = sourceHandle === null || (sourceType === "agent" && sourceHandle === "out") || (sourceType === "gate" && ["yes", "no", "out"].includes(sourceHandle));
  const validTarget = targetHandle === null || (targetType === "artifact" && targetHandle === "in") || (targetType !== "artifact" && targetHandle === "in");
  if (!validSource || !validTarget) throw new Error(`unknown edge handle: ${sourceHandle || targetHandle}`);
  return { source, target, ...edgeCondition(edge, index) };
}

export function simLikeToCanonicalPlan(simLike) {
  const input = object(simLike, "sim-like canvas");
  strictFields(input, new Set(["nodes", "edges", "viewport", "truth"]), "canvas");
  if (input.truth !== undefined && !["SIMULATION", "UNCONNECTED"].includes(input.truth)) {
    throw new Error("invalid non-LIVE canvas truth");
  }
  if (!Array.isArray(input.nodes) || !Array.isArray(input.edges)) throw new Error("nodes and edges are required");
  const nodes = input.nodes.map(serverNode);
  const nodeTypes = new Map(input.nodes.map((node) => [node.id, node.type]));
  const edges = input.edges.map((edge, index) => serverEdge(edge, index, nodeTypes));
  return { nodes, edges };
}

export function canonicalPlanToSimLike(plan) {
  const canonical = object(plan, "canonical plan");
  if (!Array.isArray(canonical.nodes) || !Array.isArray(canonical.edges)) throw new Error("canonical nodes and edges are required");
  const nodes = canonical.nodes.map((node, index) => {
    object(node, `canonical node[${index}]`);
    const type = canonicalType(node, index);
    if (!NODE_TYPES.has(type)) throw new Error(`unsupported node type: ${type}`);
    return {
      id: text(node.id, `canonical node[${index}].id`),
      type,
      data: {
        name: canonicalName(node, index),
        parameters: canonicalParameters(node, index),
        ...(node.node_type === undefined ? {} : { node_type: node.node_type }),
      },
      position: { x: 80, y: index * 120 },
    };
  });
  const nodeTypes = new Map(nodes.map((node) => [node.id, node.type]));
  const edges = canonical.edges.map((edge, index) => {
    object(edge, `canonical edge[${index}]`);
    strictFields(edge, new Set(["source", "target", "condition"]), "edge");
    const projected = serverEdge(edge, index, nodeTypes);
    return { id: `${projected.source}->${projected.target}`, ...projected };
  });
  return { nodes, edges, truth: "SIMULATION" };
}
