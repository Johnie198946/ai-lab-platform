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
const DATA_FIELDS = new Set(["name", "label", "parameters", "retry", "loop", "loops", "parallel", "parallels"]);
const EDGE_FIELDS = new Set(["id", "source", "target", "sourceHandle", "targetHandle"]);
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

function canonicalType(node, index) {
  const type = node.type ?? SERVER_NODE_TYPE_MAP[node.node_type];
  return text(type, `canonical node[${index}].type`);
}

function canonicalName(node, index) {
  return text(node.name ?? node.data?.name ?? node.data?.label, `canonical node[${index}].name`);
}

function canonicalParameters(node, index) {
  return parameters(node.parameters ?? node.data?.parameters, `canonical node[${index}].parameters`);
}

function canonicalNode(node, index) {
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
  const name = data.name ?? data.label;
  return {
    id,
    type,
    name: text(name, `node[${index}].data.name`),
    parameters: parameters(data.parameters, `node[${index}].data.parameters`),
  };
}

function canonicalEdge(edge, index, nodes) {
  object(edge, `edge[${index}]`);
  strictFields(edge, EDGE_FIELDS, "edge");
  const source = text(edge.source, `edge[${index}].source`);
  const target = text(edge.target, `edge[${index}].target`);
  if (!nodes.has(source) || !nodes.has(target)) throw new Error(`dangling edge: ${source}->${target}`);
  const sourceType = nodes.get(source).type;
  const targetType = nodes.get(target).type;
  const sourceHandle = edge.sourceHandle ?? null;
  const targetHandle = edge.targetHandle ?? null;
  const validSource = sourceHandle === null || (sourceType === "agent" && sourceHandle === "out") || (sourceType === "gate" && ["yes", "no", "out"].includes(sourceHandle));
  const validTarget = targetHandle === null || (targetType === "artifact" && targetHandle === "in") || (targetType !== "artifact" && targetHandle === "in");
  if (!validSource || !validTarget) throw new Error(`unknown edge handle: ${sourceHandle || targetHandle}`);
  return {
    id: edge.id === undefined ? `${source}->${target}` : text(edge.id, `edge[${index}].id`),
    source,
    target,
    ...(sourceHandle === null ? {} : { sourceHandle }),
    ...(targetHandle === null ? {} : { targetHandle }),
  };
}

export function simLikeToCanonicalPlan(simLike) {
  const input = object(simLike, "sim-like canvas");
  strictFields(input, new Set(["nodes", "edges", "viewport", "truth"]), "canvas");
  if (input.truth !== undefined && !["SIMULATION", "UNCONNECTED"].includes(input.truth)) {
    throw new Error("invalid non-LIVE canvas truth");
  }
  if (!Array.isArray(input.nodes) || !Array.isArray(input.edges)) throw new Error("nodes and edges are required");
  const nodes = input.nodes.map(canonicalNode);
  const nodeMap = new Map(nodes.map((node) => [node.id, node]));
  const edges = input.edges.map((edge, index) => canonicalEdge(edge, index, nodeMap));
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
      data: { name: canonicalName(node, index), parameters: canonicalParameters(node, index) },
      position: { x: 80, y: index * 120 },
    };
  });
  const edges = canonical.edges.map((edge, index) => canonicalEdge(edge, index, new Map(nodes.map((node) => [node.id, { type: node.type }]))));
  return { nodes, edges, truth: "SIMULATION" };
}
