import { Background, Controls, MiniMap, ReactFlow } from "@xyflow/react";
import { Pencil, Plus } from "lucide-react";
import "@xyflow/react/dist/style.css";
import { layoutProjectGraph } from "./quantumProjection";

export function ProjectGraph({ graph, process, onEditTask, onCreateTask }) {
  const projected = layoutProjectGraph(graph);
  const nodes = projected.nodes.map((node) => ({
    ...node,
    className: `qw-flow-node ${node.availability === "UNAVAILABLE" || node.status === "UNCONNECTED" ? "unconnected" : ""}`,
  }));
  return (
    <section className="qw-graph">
      <div className="qw-graph-head"><div><span className="qw-eyebrow">Project graph studio</span><h2>{graph.view_type === "workflow" ? "Workflow 设计" : "AI Resource 视图"}</h2></div><div className="qw-graph-actions"><span className={`qw-chip ${graph.source_status === "UNCONNECTED" ? "warning" : ""}`}>{graph.source_status}</span>{onCreateTask && <button className="qw-button primary" type="button" onClick={onCreateTask}><Plus size={14} />新增任务节点</button>}</div></div>
      {process?.stages?.length > 0 && <div className="qw-workflow-stage-list">{process.stages.map((stage) => <section key={stage.id}><header><span>{String(stage.order + 1).padStart(2, "0")}</span><div><strong>{stage.name}</strong><small>{stage.goal || "动态流程阶段"}</small></div></header><div>{process.tasks.filter((task) => task.stage_id === stage.id).map((task) => <button type="button" key={task.id} onClick={() => onEditTask?.(task)}><span><strong>{task.title}</strong><small>{task.assignee_role || "待分配角色"} · {(task.acceptance_criteria || []).length} 条验收标准</small></span><Pencil size={13} /></button>)}</div></section>)}</div>}
      <div className="qw-graph-canvas">
        <ReactFlow nodes={nodes} edges={projected.edges} nodesDraggable={false} nodesConnectable={false} elementsSelectable fitView minZoom={0.35} maxZoom={1.5}>
          <Background color="#d9dde5" gap={20} size={1} />
          <MiniMap pannable zoomable nodeColor={(node) => node.className?.includes("unconnected") ? "#d97706" : "#2f6fed"} />
          <Controls showInteractive={false} />
        </ReactFlow>
      </div>
      <p className="qw-note">阶段和依赖来自版本化 ProjectProcess；可新增或编辑任务节点。Workflow 执行、Event、Artifact 与 Usage 仍由 AI Lab canonical API 维护。</p>
    </section>
  );
}
