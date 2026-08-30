import {
  addEdge,
  Background,
  Controls,
  Handle,
  MarkerType,
  MiniMap,
  Position,
  ReactFlow,
  useEdgesState,
  useNodesState,
} from "@xyflow/react";
import {
  Bot,
  Check,
  CirclePlay,
  Database,
  GitBranch,
  HardDrive,
  PackageCheck,
  Plus,
  Save,
  ShieldCheck,
  Sparkles,
  Trash2,
  UsersRound,
  Wrench,
  Zap,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import "@xyflow/react/dist/style.css";

const kindMeta = {
  trigger: { label: "阶段起点", description: "定义本阶段何时开始", icon: CirclePlay, tone: "blue" },
  action: { label: "执行步骤", description: "由人或 Agent 完成工作", icon: Zap, tone: "teal" },
  decision: { label: "条件分支", description: "根据条件选择下一路径", icon: GitBranch, tone: "violet" },
  approval: { label: "人工审批", description: "等待评审或放行", icon: ShieldCheck, tone: "amber" },
  deliverable: { label: "交付节点", description: "产出并移交成果", icon: PackageCheck, tone: "green" },
};

const executionModeLabel = {
  human: "人工执行",
  ai: "AI 自动执行",
  human_ai: "人机协同",
};

const textList = (value) => Array.isArray(value)
  ? [...new Set(value.map((item) => String(item || "").trim()).filter(Boolean))]
  : [];
const parseList = (value) => [...new Set(String(value || "").split(/[,，、\n]/).map((item) => item.trim()).filter(Boolean))];

function WorkflowNode({ data, selected }) {
  const meta = kindMeta[data.kind] || kindMeta.action;
  const Icon = meta.icon;
  const configured = [data.participants, data.tools, data.data_sources, data.devices, data.deliverables, data.acceptance_criteria]
    .filter((items) => items?.length).length;
  return <article className={`qw-workflow-node kind-${meta.tone} ${selected ? "selected" : ""}`}>
    <Handle type="target" position={Position.Left} className="qw-workflow-handle" />
    <header><span><Icon size={15} /></span><small>{meta.label}</small><em>{data.kind === "trigger" ? "START" : `STEP ${String(data.stepNumber || 1).padStart(2, "0")}`}</em></header>
    <strong>{data.label || "未命名步骤"}</strong>
    <p>{data.description || meta.description}</p>
    <footer>
      <span><UsersRound size={11} />{data.participants?.[0] || executionModeLabel[data.execution_mode] || "待配置"}</span>
      <span className={configured >= 4 ? "ready" : ""}>{configured >= 4 ? <Check size={11} /> : <Sparkles size={11} />}{configured}/6</span>
    </footer>
    <Handle type="source" position={Position.Right} className="qw-workflow-handle" />
  </article>;
}

const nodeTypes = { workflow_step: WorkflowNode };

const resourceNames = (value) => Array.isArray(value)
  ? value.map((item) => typeof item === "string" ? item : item?.name || item?.title || item?.label || item?.id).filter(Boolean)
  : [];

function resourceDefaults(process) {
  const plan = process.resource_plan || {};
  const twin = plan.scenario_twin || {};
  const infrastructure = plan.infrastructure || {};
  const configuredInfrastructure = Object.entries(infrastructure)
    .filter(([, value]) => value && typeof value === "object" && Object.values(value).some((item) => ![null, "", 0, "待配置", "待选型"].includes(item)))
    .map(([key]) => key.replaceAll("_", " "));
  return {
    tools: textList([
      ...resourceNames(plan.tools), ...resourceNames(plan.services), ...resourceNames(plan.systems),
      ...resourceNames(twin.systems), ...resourceNames(plan.model_registry?.models),
    ]),
    dataSources: textList([
      ...resourceNames(plan.datasets), ...resourceNames(plan.data_sources), ...resourceNames(plan.data),
      ...resourceNames(twin.datasets),
    ]),
    devices: textList([
      ...resourceNames(plan.environments), ...resourceNames(plan.devices),
      ...resourceNames(plan.topology?.nodes), ...configuredInfrastructure,
    ]),
  };
}

function initialCanvas(graph, process) {
  const taskById = new Map((process.tasks || []).map((task) => [task.id, task]));
  const linkedResources = resourceDefaults(process);
  const stageIndexes = new Map();
  const nodes = (graph.nodes || []).map((rawNode) => {
    const task = taskById.get(rawNode.id) || taskById.get(rawNode.data?.task_id);
    const stageId = rawNode.stage_id || task?.stage_id || process.stages?.[0]?.id;
    const index = stageIndexes.get(stageId) || 0;
    stageIndexes.set(stageId, index + 1);
    const data = rawNode.data || {};
    const hasPosition = Number.isFinite(Number(rawNode.position?.x)) && Number.isFinite(Number(rawNode.position?.y));
    return {
      ...rawNode,
      id: rawNode.id,
      type: "workflow_step",
      stage_id: stageId,
      position: hasPosition ? { x: Number(rawNode.position.x), y: Number(rawNode.position.y) } : { x: 360 + index * 320, y: 190 + (index % 2) * 170 },
      data: {
        kind: data.kind || "action",
        label: data.label || rawNode.label || rawNode.title || task?.title || "未命名步骤",
        description: data.description || task?.summary || "",
        execution_mode: data.execution_mode || (task?.assignee_id ? "ai" : "human_ai"),
        participants: textList(data.participants?.length ? data.participants : [task?.assignee_role]),
        tools: textList(data.tools?.length ? data.tools : linkedResources.tools),
        data_sources: textList(data.data_sources?.length ? data.data_sources : linkedResources.dataSources),
        devices: textList(data.devices?.length ? data.devices : linkedResources.devices),
        resource_refs: data.resource_refs || {},
        deliverables: textList(data.deliverables?.length ? data.deliverables : task?.deliverables),
        acceptance_criteria: textList(data.acceptance_criteria?.length ? data.acceptance_criteria : task?.acceptance_criteria),
        condition: data.condition || "",
        task_id: data.task_id || task?.id || null,
      },
    };
  });
  const edges = (graph.edges || []).map((edge) => ({
    ...edge,
    type: "smoothstep",
    markerEnd: { type: MarkerType.ArrowClosed, width: 15, height: 15, color: "#8793a6" },
  }));

  (process.stages || []).forEach((stage) => {
    const stageNodes = nodes.filter((node) => node.stage_id === stage.id);
    if (stageNodes.some((node) => node.data.kind === "trigger")) return;
    const triggerId = `workflow_start_${stage.id}`;
    nodes.push({
      id: triggerId,
      type: "workflow_step",
      stage_id: stage.id,
      position: { x: 60, y: 220 },
      data: {
        kind: "trigger",
        label: `${stage.name}开始`,
        description: stage.goal || "进入本阶段后启动工作流",
        execution_mode: "human_ai",
        participants: [], tools: [], data_sources: [], devices: [], deliverables: [], acceptance_criteria: [], condition: "", task_id: null,
      },
    });
    const first = [...stageNodes].sort((left, right) => left.position.x - right.position.x || left.position.y - right.position.y)[0];
    if (first && !edges.some((edge) => edge.target === first.id && nodes.find((node) => node.id === edge.source)?.stage_id === stage.id)) {
      edges.push({
        id: `workflow_edge_${triggerId}_${first.id}`,
        source: triggerId,
        target: first.id,
        type: "smoothstep",
        markerEnd: { type: MarkerType.ArrowClosed, width: 15, height: 15, color: "#8793a6" },
      });
    }
  });

  return { nodes, edges };
}

function ListField({ icon: Icon, label, value, placeholder, onChange }) {
  return <label className="qw-workflow-field">
    <span><Icon size={13} />{label}</span>
    <input value={textList(value).join("、")} placeholder={placeholder} onChange={(event) => onChange(parseList(event.target.value))} />
    <small>用逗号或顿号分隔多个项目</small>
  </label>;
}

export function ProjectGraph({ graph, process, onSave }) {
  const initial = useMemo(() => initialCanvas(graph, process), [graph, process]);
  const [nodes, setNodes, applyNodeChanges] = useNodesState(initial.nodes);
  const [edges, setEdges, applyEdgeChanges] = useEdgesState(initial.edges);
  const [selectedStageId, setSelectedStageId] = useState(process.stages?.[0]?.id || "");
  const [selectedNodeId, setSelectedNodeId] = useState(null);
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState("");
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    setNodes(initial.nodes);
    setEdges(initial.edges);
    setDirty(false);
  }, [initial, setEdges, setNodes]);

  const visibleBaseNodes = nodes.filter((node) => node.stage_id === selectedStageId);
  const sequence = new Map([...visibleBaseNodes]
    .filter((node) => node.data.kind !== "trigger")
    .sort((left, right) => left.position.x - right.position.x || left.position.y - right.position.y)
    .map((node, index) => [node.id, index + 1]));
  const visibleNodes = visibleBaseNodes.map((node) => ({ ...node, data: { ...node.data, stepNumber: sequence.get(node.id) || 0 } }));
  const visibleNodeIds = new Set(visibleNodes.map((node) => node.id));
  const visibleEdges = edges.filter((edge) => visibleNodeIds.has(edge.source) && visibleNodeIds.has(edge.target));
  const selectedNode = nodes.find((node) => node.id === selectedNodeId) || null;
  const selectedStage = (process.stages || []).find((stage) => stage.id === selectedStageId);

  const onNodesChange = useCallback((changes) => {
    applyNodeChanges(changes);
    if (changes.some((change) => ["add", "remove", "replace", "position"].includes(change.type))) {
      setDirty(true);
      setSaved(false);
    }
  }, [applyNodeChanges]);
  const onEdgesChange = useCallback((changes) => {
    applyEdgeChanges(changes);
    if (changes.some((change) => ["add", "remove", "replace"].includes(change.type))) {
      setDirty(true);
      setSaved(false);
    }
  }, [applyEdgeChanges]);
  const onConnect = useCallback((connection) => {
    setEdges((current) => addEdge({
      ...connection,
      id: `workflow_edge_${crypto.randomUUID()}`,
      type: "smoothstep",
      markerEnd: { type: MarkerType.ArrowClosed, width: 15, height: 15, color: "#8793a6" },
    }, current));
    setDirty(true);
    setSaved(false);
  }, [setEdges]);

  const addNode = (kind) => {
    const meta = kindMeta[kind];
    const stageCount = visibleBaseNodes.length;
    const id = `workflow_node_${crypto.randomUUID()}`;
    const node = {
      id,
      type: "workflow_step",
      stage_id: selectedStageId,
      position: { x: 120 + (stageCount % 3) * 300, y: 110 + Math.floor(stageCount / 3) * 180 },
      data: {
        kind,
        label: kind === "trigger" ? `${selectedStage?.name || "阶段"}开始` : meta.label,
        description: "",
        execution_mode: "human_ai",
        participants: [], tools: [], data_sources: [], devices: [], deliverables: [], acceptance_criteria: [], condition: "", task_id: null,
      },
    };
    setNodes((current) => [...current, node]);
    setSelectedNodeId(id);
    setDirty(true);
    setSaved(false);
  };

  const updateNodeData = (key, value) => {
    setNodes((current) => current.map((node) => node.id === selectedNodeId ? { ...node, data: { ...node.data, [key]: value } } : node));
    setDirty(true);
    setSaved(false);
  };

  const deleteSelectedNode = () => {
    if (!selectedNode) return;
    setNodes((current) => current.filter((node) => node.id !== selectedNode.id));
    setEdges((current) => current.filter((edge) => edge.source !== selectedNode.id && edge.target !== selectedNode.id));
    setSelectedNodeId(null);
    setDirty(true);
    setSaved(false);
  };

  const saveGraph = async () => {
    setSaving(true);
    setSaveError("");
    try {
      await onSave?.({
        nodes: nodes.map((node) => ({
          id: node.id,
          type: "workflow_step",
          stage_id: node.stage_id,
          position: node.position,
          data: node.data,
          status: node.status,
          task_status: node.task_status,
          workflow_id: node.workflow_id,
        })),
        edges: edges.map((edge) => ({ id: edge.id, source: edge.source, target: edge.target, sourceHandle: edge.sourceHandle, targetHandle: edge.targetHandle })),
      });
      setDirty(false);
      setSaved(true);
    } catch (reason) {
      setSaveError(reason.message);
    } finally {
      setSaving(false);
    }
  };

  return <section className="qw-graph qw-workflow-designer">
    <header className="qw-workflow-designer-head">
      <div><span className="qw-eyebrow">Project workflow studio</span><h2>Workflow 编排</h2><p>每个节点完整配置角色、工具、数据、设备环境、交付物与验收标准；资源字段与 AI Resource 共用项目真源。</p></div>
      <div className="qw-graph-actions">
        <span className={`qw-workflow-save-state ${saveError ? "error" : saved ? "saved" : dirty ? "dirty" : ""}`}>{saveError ? "保存失败" : saving ? "保存中…" : saved ? "已保存" : dirty ? "有未保存修改" : `Revision ${graph.process_revision}`}</span>
        <button className="qw-button primary" type="button" onClick={saveGraph} disabled={saving || !dirty}><Save size={14} />{saving ? "保存中…" : "保存 Workflow"}</button>
      </div>
    </header>
    {saveError && <p className="qw-workflow-error" role="alert">{saveError}</p>}
    <nav className="qw-workflow-stage-tabs" aria-label="选择要编排的项目阶段">
      {(process.stages || []).map((stage, index) => {
        const count = nodes.filter((node) => node.stage_id === stage.id && node.data.kind !== "trigger").length;
        return <button key={stage.id} type="button" className={selectedStageId === stage.id ? "active" : ""} onClick={() => { setSelectedStageId(stage.id); setSelectedNodeId(null); }}>
          <span>{String(index + 1).padStart(2, "0")}</span><strong>{stage.name}</strong><small>{count} 个步骤</small>
        </button>;
      })}
    </nav>
    <div className="qw-workflow-layout">
      <aside className="qw-workflow-library">
        <header><Plus size={15} /><div><strong>节点库</strong><small>点击添加到当前阶段</small></div></header>
        <div>{Object.entries(kindMeta).map(([kind, meta]) => {
          const Icon = meta.icon;
          return <button key={kind} type="button" onClick={() => addNode(kind)}><span className={`tone-${meta.tone}`}><Icon size={15} /></span><span><strong>{meta.label}</strong><small>{meta.description}</small></span><Plus size={13} /></button>;
        })}</div>
        <section><Bot size={14} /><p><strong>编排提示</strong><small>从起点向右连接步骤。节点位置表示顺序，连线决定真实流向。</small></p></section>
      </aside>
      <div className="qw-workflow-canvas" aria-label={`${selectedStage?.name || "当前阶段"}工作流画布`}>
        <div className="qw-workflow-canvas-label"><span>{selectedStage?.name}</span><small>{selectedStage?.goal || "配置本阶段的执行步骤与责任边界"}</small></div>
        <ReactFlow
          nodes={visibleNodes}
          edges={visibleEdges}
          nodeTypes={nodeTypes}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onConnect={onConnect}
          onNodeClick={(_, node) => setSelectedNodeId(node.id)}
          onPaneClick={() => setSelectedNodeId(null)}
          nodesDraggable
          nodesConnectable
          elementsSelectable
          deleteKeyCode={null}
          fitView
          fitViewOptions={{ padding: 0.25 }}
          minZoom={0.35}
          maxZoom={1.5}
        >
          <Background color="#d8dde6" gap={20} size={1} />
          <MiniMap pannable zoomable nodeColor={(node) => ({ trigger: "#2f6fed", action: "#0f9f94", decision: "#7655d9", approval: "#cf851f", deliverable: "#2f9b65" }[node.data?.kind] || "#718096")} />
          <Controls showInteractive={false} />
        </ReactFlow>
      </div>
      <aside className="qw-workflow-inspector">
        {!selectedNode ? <div className="qw-workflow-inspector-empty"><Sparkles size={22} /><strong>选择一个节点进行配置</strong><p>每个步骤都可以明确参与角色、工具、输入数据、设备环境、交付物和验收标准。</p><div><span><UsersRound size={13} />谁参与</span><span><Wrench size={13} />用什么工具</span><span><Database size={13} />使用什么数据</span><span><HardDrive size={13} />在哪种设备/环境</span><span><PackageCheck size={13} />交付什么</span></div></div> : <div className="qw-workflow-inspector-form">
          <header><span className={`tone-${kindMeta[selectedNode.data.kind]?.tone || "teal"}`}>{(() => { const Icon = kindMeta[selectedNode.data.kind]?.icon || Zap; return <Icon size={16} />; })()}</span><div><strong>节点配置</strong><small>{kindMeta[selectedNode.data.kind]?.label}</small></div><button type="button" onClick={deleteSelectedNode} aria-label="删除当前节点"><Trash2 size={15} /></button></header>
          <label className="qw-workflow-field"><span>步骤名称</span><input value={selectedNode.data.label || ""} onChange={(event) => updateNodeData("label", event.target.value)} placeholder="例如：收集并确认访客需求" /></label>
          <label className="qw-workflow-field"><span>步骤说明</span><textarea rows={3} value={selectedNode.data.description || ""} onChange={(event) => updateNodeData("description", event.target.value)} placeholder="说明这一步做什么、何时完成" /></label>
          <label className="qw-workflow-field"><span>执行方式</span><select value={selectedNode.data.execution_mode || "human_ai"} onChange={(event) => updateNodeData("execution_mode", event.target.value)}><option value="human_ai">人机协同</option><option value="human">人工执行</option><option value="ai">AI 自动执行</option></select></label>
          <ListField icon={UsersRound} label="参与角色" value={selectedNode.data.participants} placeholder="需求经理、业务负责人" onChange={(value) => updateNodeData("participants", value)} />
          <ListField icon={Wrench} label="工具 · AI Resource 联动" value={selectedNode.data.tools} placeholder="从 AI Resource 继承，也可补充" onChange={(value) => updateNodeData("tools", value)} />
          <ListField icon={Database} label="输入数据 · AI Resource 联动" value={selectedNode.data.data_sources} placeholder="从数据集与数据源继承，也可补充" onChange={(value) => updateNodeData("data_sources", value)} />
          <ListField icon={HardDrive} label="设备 / 环境 · AI Resource 联动" value={selectedNode.data.devices} placeholder="从部署资源继承，也可补充" onChange={(value) => updateNodeData("devices", value)} />
          <ListField icon={PackageCheck} label="交付物" value={selectedNode.data.deliverables} placeholder="需求定义、访谈纪要、评审结论" onChange={(value) => updateNodeData("deliverables", value)} />
          <ListField icon={ShieldCheck} label="验收标准" value={selectedNode.data.acceptance_criteria} placeholder="业务负责人确认、字段覆盖完整" onChange={(value) => updateNodeData("acceptance_criteria", value)} />
          {selectedNode.data.kind === "decision" && <label className="qw-workflow-field"><span><GitBranch size={13} />分支条件</span><textarea rows={2} value={selectedNode.data.condition || ""} onChange={(event) => updateNodeData("condition", event.target.value)} placeholder="例如：需求信息是否完整？" /></label>}
        </div>}
      </aside>
    </div>
  </section>;
}
