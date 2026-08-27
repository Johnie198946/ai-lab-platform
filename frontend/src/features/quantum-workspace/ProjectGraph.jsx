import { Background, Controls, MiniMap, ReactFlow } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { layoutProjectGraph } from "./quantumProjection";

export function ProjectGraph({ graph }) {
  const projected = layoutProjectGraph(graph);
  const nodes = projected.nodes.map((node) => ({
    ...node,
    className: `qw-flow-node ${node.availability === "UNAVAILABLE" || node.status === "UNCONNECTED" ? "unconnected" : ""}`,
  }));
  return (
    <section className="qw-graph">
      <div className="qw-graph-head"><div><span className="qw-eyebrow">Project graph studio</span><h2>{graph.view_type === "workflow" ? "Workflow 视图" : "AI Resource 视图"}</h2></div><span className={`qw-chip ${graph.source_status === "UNCONNECTED" ? "warning" : ""}`}>{graph.source_status}</span></div>
      <div className="qw-graph-canvas">
        <ReactFlow nodes={nodes} edges={projected.edges} nodesDraggable={false} nodesConnectable={false} elementsSelectable fitView minZoom={0.35} maxZoom={1.5}>
          <Background color="#d9dde5" gap={20} size={1} />
          <MiniMap pannable zoomable nodeColor={(node) => node.className?.includes("unconnected") ? "#d97706" : "#2f6fed"} />
          <Controls showInteractive={false} />
        </ReactFlow>
      </div>
      <p className="qw-note">此视图是 ProjectProcess 的只读投影。Workflow 执行、Execution、Event、Artifact 与 Usage 仍由 AI Lab canonical API 维护。</p>
    </section>
  );
}
