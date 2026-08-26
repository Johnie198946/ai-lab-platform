// Modified adaptation of Sim Studio's Workflow canvas interaction model.
// Source: simstudioai/sim@981be9322dd0c63e323927a3a9410237b2c25b68 (Apache-2.0).
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Background,
  Handle,
  MarkerType,
  Position,
  ReactFlow,
  ReactFlowProvider,
  addEdge,
  applyEdgeChanges,
  applyNodeChanges,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import {
  Bot,
  Box,
  GitBranch,
  Hand,
  Maximize2,
  MousePointer2,
  Plus,
  Redo2,
  Save,
  ShieldCheck,
  Sparkles,
  Trash2,
  Undo2,
  WandSparkles,
} from "lucide-react";
import { canonicalPlanToSimLike, simLikeToCanonicalPlan } from "../../architectCanvasAdapter";
import { projectPlanToCanvas } from "../../architectContract";
import { platformApi } from "../../services/platformApi";
import {
  autoLayoutWorkflowNodes,
  readCanvasLayout,
  validateCanvasConnection,
  writeCanvasLayout,
} from "./workflowCanvasModel";
import "./SimWorkflowCanvas.css";

const PALETTE = [
  { type: "agent", nodeType: "LLM_INFERENCE", label: "AI 节点", icon: Bot },
  { type: "gate", nodeType: "FILTER_PASS", label: "决策 Gate", icon: ShieldCheck },
  { type: "artifact", nodeType: "OUTPUT_FORMAT", label: "交付物", icon: Box },
];

const statusFor = (status) => {
  if (["running", "queued"].includes(status)) return "running";
  if (["done", "succeeded", "completed"].includes(status)) return "done";
  if (["blocked", "failed"].includes(status)) return "blocked";
  return "idle";
};

function SimNode({ id, data, selected }) {
  const type = data.visualType || "agent";
  const Icon = type === "artifact" ? Box : type === "gate" ? ShieldCheck : Bot;
  const runtime = statusFor(data.runtimeStatus);
  return <article className={`hermes-sim-node hermes-sim-node--${type} is-${runtime}${selected ? " is-selected" : ""}`} aria-label={`${data.name} · ${data.runtimeStatus || data.capabilityStatus || "PLAN"}`}>
    {selected && data.editing && <div className="hermes-sim-node__actions"><button type="button" onClick={(event) => { event.stopPropagation(); data.onDelete(id); }} aria-label={`删除 ${data.name}`}><Trash2 size={13} /></button></div>}
    <Handle className="hermes-sim-node__handle is-target" type="target" position={Position.Left} />
    <div className="hermes-sim-node__icon"><Icon size={16} /></div>
    <div className="hermes-sim-node__copy"><strong>{data.name}</strong><span>{data.agentId || data.nodeType || type}</span></div>
    <span className={`hermes-sim-node__status is-${runtime}`}><i />{data.runtimeStatus || data.capabilityStatus || "PLAN"}</span>
    <Handle className={`hermes-sim-node__handle is-source${type === "gate" ? " is-gate" : ""}`} type="source" position={Position.Right} />
  </article>;
}

const nodeTypes = { agent: SimNode, gate: SimNode, artifact: SimNode, human: SimNode };
const snapshot = (nodes, edges) => ({ nodes: nodes.map((node) => ({ ...node, data: { ...node.data } })), edges: edges.map((edge) => ({ ...edge })) });
const sameGraph = (a, b) => JSON.stringify(a) === JSON.stringify(b);

function buildDraft(plan, workflowId) {
  const view = canonicalPlanToSimLike(projectPlanToCanvas(plan));
  const stored = readCanvasLayout(workflowId);
  const hasStored = Object.keys(stored.nodes).length > 0;
  const nodes = view.nodes.map((node) => ({
    ...node,
    type: node.type,
    position: stored.nodes[node.id] || node.position,
    data: {
      name: node.data.name,
      nodeType: node.data.node_type,
      parameters: node.data.parameters || {},
      visualType: node.type,
      agentId: node.data.parameters?.agent_id || "",
      capabilityStatus: node.data.parameters?.capability_status || "PLAN",
    },
  }));
  return {
    nodes: hasStored ? nodes : autoLayoutWorkflowNodes(nodes, view.edges),
    edges: view.edges.map((edge) => ({
      ...edge,
      type: "smoothstep",
      markerEnd: { type: MarkerType.ArrowClosed },
    })),
    viewport: stored.viewport,
  };
}

function CanvasContent({ plan, workflowId = "", onSaved, executionNodes = [], canEdit = true, variant = "dark", showHistory = true }) {
  const [editing, setEditing] = useState(false);
  const [mode, setMode] = useState("pointer");
  const [draft, setDraft] = useState(() => buildDraft(plan, workflowId));
  const [history, setHistory] = useState({ past: [], future: [] });
  const [selectedNodeId, setSelectedNodeId] = useState("");
  const [selectedEdgeId, setSelectedEdgeId] = useState("");
  const [flow, setFlow] = useState(null);
  const [viewport, setViewport] = useState(draft.viewport);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const [historyVersions, setHistoryVersions] = useState([]);
  const [selectedHistoryId, setSelectedHistoryId] = useState("");
  const [rollingBack, setRollingBack] = useState(false);
  const canvasRef = useRef(null);
  const dragBeforeRef = useRef(null);
  const runtimeById = useMemo(() => new Map(executionNodes.map((node) => [String(node.node_id || node.id), node.status])), [executionNodes]);
  const editable = canEdit && editing;

  useEffect(() => {
    const next = buildDraft(plan, workflowId);
    setDraft(next);
    setViewport(next.viewport);
    setEditing(false);
    setHistory({ past: [], future: [] });
    setSelectedNodeId("");
    setSelectedEdgeId("");
  }, [plan?.id, plan?.content_hash, workflowId]);

  useEffect(() => {
    if (!workflowId || !showHistory) return undefined;
    let active = true;
    platformApi.listWorkflowPlanVersions(workflowId).then((rows) => { if (active) setHistoryVersions(Array.isArray(rows) ? rows : []); }).catch(() => { if (active) setHistoryVersions([]); });
    return () => { active = false; };
  }, [workflowId, plan?.id, showHistory]);

  const commit = useCallback((before, next) => {
    if (sameGraph(before, next)) return;
    setHistory((current) => ({ past: [...current.past.slice(-49), before], future: [] }));
  }, []);

  const replaceDraft = useCallback((updater, record = true) => {
    setDraft((current) => {
      const before = snapshot(current.nodes, current.edges);
      const next = updater(current);
      if (record) commit(before, snapshot(next.nodes, next.edges));
      return next;
    });
  }, [commit]);

  const removeSelection = useCallback((nodeIds = [], edgeIds = []) => {
    if (!editable) return;
    const nodesToRemove = new Set(nodeIds.length ? nodeIds : draft.nodes.filter((node) => node.selected).map((node) => node.id));
    const edgesToRemove = new Set(edgeIds.length ? edgeIds : draft.edges.filter((edge) => edge.selected).map((edge) => edge.id));
    if (!nodesToRemove.size && !edgesToRemove.size) return;
    replaceDraft((current) => ({ ...current, nodes: current.nodes.filter((node) => !nodesToRemove.has(node.id)), edges: current.edges.filter((edge) => !edgesToRemove.has(edge.id) && !nodesToRemove.has(edge.source) && !nodesToRemove.has(edge.target)) }));
    setSelectedNodeId(""); setSelectedEdgeId("");
  }, [draft.edges, draft.nodes, editable, replaceDraft]);

  useEffect(() => {
    if (!editable) return undefined;
    const keydown = (event) => {
      const target = event.target;
      if (target instanceof HTMLElement && (target.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName))) return;
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "z") { event.preventDefault(); event.shiftKey ? redo() : undo(); }
      else if (["Backspace", "Delete"].includes(event.key)) { event.preventDefault(); removeSelection(); }
    };
    window.addEventListener("keydown", keydown);
    return () => window.removeEventListener("keydown", keydown);
  });

  const undo = useCallback(() => {
    setHistory((current) => {
      if (!current.past.length) return current;
      const previous = current.past.at(-1);
      setDraft((present) => ({ ...present, ...snapshot(previous.nodes, previous.edges) }));
      return { past: current.past.slice(0, -1), future: [snapshot(draft.nodes, draft.edges), ...current.future].slice(0, 50) };
    });
  }, [draft.edges, draft.nodes]);
  const redo = useCallback(() => {
    setHistory((current) => {
      if (!current.future.length) return current;
      const next = current.future[0];
      setDraft((present) => ({ ...present, ...snapshot(next.nodes, next.edges) }));
      return { past: [...current.past, snapshot(draft.nodes, draft.edges)].slice(-50), future: current.future.slice(1) };
    });
  }, [draft.edges, draft.nodes]);

  const addBlock = useCallback((type, point) => {
    if (!editable) return;
    const config = PALETTE.find((item) => item.type === type);
    if (!config) return;
    const id = `canvas_${type}_${globalThis.crypto?.randomUUID?.() || Date.now()}`;
    const bounds = canvasRef.current?.getBoundingClientRect();
    const position = point || flow?.screenToFlowPosition(bounds
      ? { x: bounds.left + bounds.width / 2, y: bounds.top + bounds.height / 2 }
      : { x: window.innerWidth / 2, y: window.innerHeight / 2 }) || { x: 120, y: 120 };
    replaceDraft((current) => ({ ...current, nodes: [...current.nodes, { id, type, position, data: { name: config.label, nodeType: config.nodeType, parameters: {}, visualType: type, capabilityStatus: "PLAN" } }] }));
    setSelectedNodeId(id);
  }, [editable, flow, replaceDraft]);

  const connect = useCallback((connection) => {
    if (!editable) return;
    const error = validateCanvasConnection(connection, draft.nodes, draft.edges);
    if (error) { setMessage(error); return; }
    const edge = { ...connection, id: `${connection.source}:${connection.sourceHandle || "out"}->${connection.target}:${connection.targetHandle || "in"}`, type: "smoothstep", markerEnd: { type: MarkerType.ArrowClosed } };
    replaceDraft((current) => ({ ...current, edges: addEdge(edge, current.edges) }));
    setMessage("");
  }, [draft.edges, draft.nodes, editable, replaceDraft]);

  const displayNodes = draft.nodes.map((node) => ({ ...node, data: { ...node.data, runtimeStatus: runtimeById.get(node.id) || "", editing: editable, onDelete: (id) => removeSelection([id], []) } }));
  const displayEdges = draft.edges.map((edge) => {
    const sourceStatus = statusFor(runtimeById.get(edge.source));
    const targetStatus = statusFor(runtimeById.get(edge.target));
    const runtimeStatus = targetStatus === "running" && ["done", "running"].includes(sourceStatus) ? "running" : targetStatus === "done" ? "done" : "idle";
    return {
      ...edge,
      type: "smoothstep",
      data: { runtimeStatus },
      animated: runtimeStatus === "running",
      className: `hermes-sim-edge is-${runtimeStatus}`,
      markerEnd: { type: MarkerType.ArrowClosed },
    };
  });

  const save = async () => {
    if (!editable || saving || !workflowId || !plan?.content_hash || !plan?.activation_revision) return;
    setSaving(true); setMessage("");
    try {
      const nodes = draft.nodes.map((node) => ({ id: node.id, type: node.type, data: { name: node.data.name, node_type: node.data.nodeType, parameters: node.data.parameters || {} }, position: node.position }));
      const edges = draft.edges.map(({ id, source, target, sourceHandle, targetHandle, condition }) => ({ id, source, target, ...(sourceHandle ? { sourceHandle } : {}), ...(targetHandle ? { targetHandle } : {}), ...(condition !== undefined ? { condition } : {}) }));
      const editedDsl = simLikeToCanonicalPlan({ nodes, edges });
      const nextPlan = await platformApi.patchWorkflowPlan(workflowId, { dsl: { ...plan.dsl, ...editedDsl }, deliverable: plan.deliverable, allow_network: plan.allow_network, max_tokens: plan.max_tokens, knowledge_scope: plan.knowledge_scope || [], expected_hash: plan.content_hash, expected_revision: plan.activation_revision, request_id: `canvas-${globalThis.crypto?.randomUUID?.() || Date.now()}` });
      writeCanvasLayout(workflowId, draft.nodes, viewport);
      onSaved?.(nextPlan); setEditing(false); setMessage("画布已保存为新的 Hermes Plan 版本");
    } catch (error) { setMessage(error.message || "保存失败，当前本地编辑仍保留。"); }
    finally { setSaving(false); }
  };

  const rollback = async () => {
    if (!selectedHistoryId || rollingBack || !workflowId || !plan?.content_hash || !plan?.activation_revision) return;
    setRollingBack(true); setMessage("");
    try {
      const nextPlan = await platformApi.rollbackWorkflowPlan(workflowId, { source_plan_id: selectedHistoryId, expected_hash: plan.content_hash, expected_revision: plan.activation_revision, request_id: `rollback-${globalThis.crypto?.randomUUID?.() || Date.now()}` });
      onSaved?.(nextPlan); setSelectedHistoryId(""); setMessage("已从 Hermes 历史版本恢复");
    } catch (error) { setMessage(error.message || "回滚失败，当前计划保持不变。"); }
    finally { setRollingBack(false); }
  };

  const selectedNode = draft.nodes.find((node) => node.id === selectedNodeId);
  const selectedEdge = draft.edges.find((edge) => edge.id === selectedEdgeId);
  const autoLayout = () => replaceDraft((current) => ({ ...current, nodes: autoLayoutWorkflowNodes(current.nodes, current.edges) }));
  const updateSelectedNodeName = (name) => replaceDraft((current) => ({
    ...current,
    nodes: current.nodes.map((node) => node.id === selectedNodeId ? { ...node, data: { ...node.data, name } } : node),
  }));
  const updateSelectedEdgeCondition = (condition) => replaceDraft((current) => ({
    ...current,
    edges: current.edges.map((edge) => edge.id === selectedEdgeId ? { ...edge, condition: condition || null } : edge),
  }));
  const persistCurrentLayout = (nodes = draft.nodes, nextViewport = viewport) => { if (workflowId) writeCanvasLayout(workflowId, nodes, nextViewport); };

  return <section className="hermes-sim-canvas" data-variant={variant} aria-label="Sim Workflow 画布">
    <header className="hermes-sim-canvas__toolbar">
      <div className="hermes-sim-canvas__identity"><Sparkles size={15} /><span>{editing ? "SIM EDITOR · Hermes 草稿" : "HERMES PLAN · Sim Canvas"}</span></div>
      <div className="hermes-sim-canvas__actions">
        {canEdit && <button type="button" onClick={() => { setEditing((value) => !value); setMode("pointer"); setMessage(""); }} aria-pressed={editing}>{editing ? "退出编辑" : "编辑画布"}</button>}
        {editing && <button className="is-primary" type="button" onClick={save} disabled={saving || !workflowId || !plan?.content_hash}>{saving ? "保存中…" : <><Save size={14} />保存 Plan</>}</button>}
        {showHistory && historyVersions.length > 1 && !editing && <><select aria-label="历史 Plan 版本" value={selectedHistoryId} onChange={(event) => setSelectedHistoryId(event.target.value)}><option value="">历史版本</option>{historyVersions.filter((row) => row.id !== plan?.id).map((row) => <option value={row.id} key={row.id}>v{row.version}</option>)}</select><button type="button" disabled={!selectedHistoryId || rollingBack} onClick={rollback}>{rollingBack ? "恢复中…" : "恢复"}</button></>}
      </div>
    </header>
    {message && <div className="hermes-sim-canvas__message" role="status">{message}</div>}
    <div className="hermes-sim-canvas__body" ref={canvasRef} onDragOver={(event) => { if (editable) { event.preventDefault(); event.dataTransfer.dropEffect = "move"; } }} onDrop={(event) => { if (!editable || !flow) return; event.preventDefault(); const type = event.dataTransfer.getData("application/reactflow") || JSON.parse(event.dataTransfer.getData("application/json") || "{}").type; addBlock(type, flow.screenToFlowPosition({ x: event.clientX, y: event.clientY })); }}>
      {draft.nodes.length ? <ReactFlow
        nodes={displayNodes} edges={displayEdges} nodeTypes={nodeTypes} onInit={setFlow}
        onError={(code, detail) => setMessage(`React Flow ${code}: ${detail}`)}
        defaultViewport={draft.viewport || { x: 0, y: 0, zoom: 0.85 }} fitView={!draft.viewport} fitViewOptions={{ padding: .35, maxZoom: 1 }} minZoom={.2} maxZoom={1.8}
        nodesDraggable={editable && mode === "pointer"} nodesConnectable={editable && mode === "pointer"} elementsSelectable={mode === "pointer"} selectionOnDrag={editable && mode === "pointer"} panOnDrag={mode === "hand"}
        onNodeClick={(_, node) => { setSelectedNodeId(node.id); setSelectedEdgeId(""); }} onEdgeClick={(_, edge) => { setSelectedEdgeId(edge.id); setSelectedNodeId(""); }} onPaneClick={() => { setSelectedNodeId(""); setSelectedEdgeId(""); }}
        onNodeDragStart={() => { dragBeforeRef.current = snapshot(draft.nodes, draft.edges); }} onNodeDragStop={(_, __, nodes) => { if (dragBeforeRef.current) commit(dragBeforeRef.current, snapshot(draft.nodes, draft.edges)); dragBeforeRef.current = null; persistCurrentLayout(nodes); }}
        onNodesChange={(changes) => { if (mode === "pointer") setDraft((current) => ({ ...current, nodes: applyNodeChanges(changes.filter((change) => editable || ["select", "dimensions"].includes(change.type)), current.nodes) })); }}
        onEdgesChange={(changes) => setDraft((current) => ({ ...current, edges: applyEdgeChanges(changes.filter((change) => editable || change.type === "select"), current.edges) }))}
        onConnect={connect} onMoveEnd={(_, nextViewport) => { setViewport(nextViewport); persistCurrentLayout(draft.nodes, nextViewport); }} deleteKeyCode={null} defaultEdgeOptions={{ type: "smoothstep", markerEnd: { type: MarkerType.ArrowClosed } }}
      ><Background color="var(--hermes-sim-grid)" gap={24} size={1} /></ReactFlow> : <div className="hermes-sim-canvas__empty"><GitBranch size={20} /><strong>暂无 Hermes 流程节点</strong>{editable && <button type="button" onClick={() => addBlock("agent")}><Plus size={14} />添加 AI 节点</button>}</div>}

      {editing && <aside className="hermes-sim-palette" aria-label="Hermes 支持的 Block">{PALETTE.map(({ type, label, icon: Icon }) => <button type="button" draggable onDragStart={(event) => { event.dataTransfer.setData("application/reactflow", type); event.dataTransfer.setData("application/json", JSON.stringify({ type })); event.dataTransfer.effectAllowed = "move"; }} onClick={() => addBlock(type)} key={type}><Icon size={15} /><span>{label}</span><Plus size={13} /></button>)}</aside>}

      <div className="hermes-sim-controls" aria-label="画布控制">
        <button type="button" className={mode === "pointer" ? "is-active" : ""} onClick={() => setMode("pointer")} aria-label="选择模式"><MousePointer2 size={14} /></button><button type="button" className={mode === "hand" ? "is-active" : ""} onClick={() => setMode("hand")} aria-label="移动画布模式"><Hand size={14} /></button><i />
        <button type="button" onClick={undo} disabled={!editable || !history.past.length} aria-label="撤销"><Undo2 size={14} /></button><button type="button" onClick={redo} disabled={!editable || !history.future.length} aria-label="重做"><Redo2 size={14} /></button><i />
        <button type="button" onClick={autoLayout} disabled={!editable} aria-label="自动布局"><WandSparkles size={14} /></button><button type="button" onClick={() => flow?.fitView({ padding: .25, duration: 300 })} aria-label="适应画布"><Maximize2 size={14} /></button>
      </div>

      {(selectedNode || selectedEdge) && <aside className="hermes-sim-inspector" aria-label="画布元素详情">{selectedNode ? <><span>NODE</span><label>节点名称<input value={selectedNode.data.name} readOnly={!editable} onChange={(event) => updateSelectedNodeName(event.target.value)} /></label><dl><div><dt>节点类型</dt><dd>{selectedNode.data.nodeType}</dd></div><div><dt>能力状态</dt><dd>{selectedNode.data.capabilityStatus}</dd></div></dl>{editable && <button className="is-danger" type="button" onClick={() => removeSelection([selectedNode.id], [])}><Trash2 size={14} />删除节点</button>}</> : <><span>EDGE</span><strong>{selectedEdge.source} → {selectedEdge.target}</strong><label>执行条件<input value={selectedEdge.condition || ""} readOnly={!editable} onChange={(event) => updateSelectedEdgeCondition(event.target.value)} /></label>{editable && <button className="is-danger" type="button" onClick={() => removeSelection([], [selectedEdge.id])}><Trash2 size={14} />删除连接</button>}</>}</aside>}
    </div>
    <footer className="hermes-sim-canvas__footer"><span>{draft.nodes.length} nodes</span><span>{draft.edges.length} edges</span><span>{editing ? "布局保存在浏览器，执行语义保存到 Hermes" : "Hermes 服务端事实投影"}</span></footer>
  </section>;
}

export function SimWorkflowCanvas(props) {
  return <ReactFlowProvider><CanvasContent {...props} /></ReactFlowProvider>;
}

export default SimWorkflowCanvas;
