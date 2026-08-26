import React from "react";
import { createRoot } from "react-dom/client";
import { PlanCanvas } from "../../src/pages/ArchitectWorkbenchPage";

const plan = {
  id: "fixture-plan-v1",
  dsl: {
    name: "客户共创任务",
    nodes: [
      { id: "knowledge", node_type: "KNOWLEDGE_RETRIEVAL", name: "检索门禁系统相关知识", parameters: { agent_id: "knowledge", capability_status: "READY", execution_enabled: true } },
      { id: "requirements", node_type: "LLM_INFERENCE", name: "分析业务需求与 MVP 边界", parameters: { agent_id: "requirement-analyst", capability_status: "READY", execution_enabled: true } },
      { id: "architecture", node_type: "PROMPT_TRANSFORM", name: "设计系统架构与实施方案", parameters: { role_ids: ["solution-architect"], capability_status: "PLAN" } },
      { id: "gate", node_type: "FILTER_PASS", name: "执行反方风险评审", parameters: { decision_gate: "人工批准后继续", capability_status: "PLAN" } },
      { id: "deliverable", node_type: "OUTPUT_FORMAT", name: "汇总形成业务成果", parameters: { agent_id: "main-agent", capability_status: "UNCONNECTED", execution_enabled: false } },
    ],
    edges: [
      { source: "knowledge", target: "requirements" },
      { source: "requirements", target: "architecture" },
      { source: "architecture", target: "gate", condition: "review_ready" },
      { source: "gate", target: "deliverable", condition: "approved" },
    ],
  },
};

function Fixture() {
  return (
    <main className="architect-page" style={{ display: "flex" }}>
      <section className="sim-workflow-stage" style={{ flex: 1 }}>
        <header className="sim-workflow-header"><div><span className="eyebrow">WORKFLOW</span><h1>客户共创任务</h1><p>Hermes server plan</p></div><span className="truth-badge">CONTRACT</span></header>
        <PlanCanvas plan={plan} workflowId="" />
      </section>
    </main>
  );
}

createRoot(document.getElementById("root")).render(<Fixture />);
