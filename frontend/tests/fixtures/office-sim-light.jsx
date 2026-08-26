import React from "react";
import { createRoot } from "react-dom/client";
import ReferenceOfficeView from "../../src/features/project-office/ReferenceOfficeView";

const seats = [
  ["research", "检索门禁系统相关知识", "知识研究员", "done", "已完成权威资料检索"],
  ["analysis", "分析业务需求与 MVP 边界", "需求分析师", "running", "正在收敛核心业务边界"],
  ["architecture", "设计系统架构与实施方案", "系统架构师", "waiting", null],
  ["review", "执行反方风险评审", "风险评审专家", "done", "已提交风险复核意见"],
  ["summary", "汇总形成业务成果", "项目协调员", "running", "正在合并成员交付物"],
  ["quality", "质量与范围门禁", "质量负责人", "awaiting_review", "等待负责人确认范围"],
  ["delivery", "输出可审阅业务成果", "交付负责人", "waiting", null],
].map(([id, name, businessRole, status, message], index) => ({
  id, nodeId: id, name, businessRole, status, roleIds: [businessRole], input: ["客户共创任务"], expectedOutput: ["可审阅成果"],
  lastEvent: message ? { event_id: `evt-${index + 1}`, message } : null,
  artifacts: index % 2 === 0 ? [{ id: `artifact-${index}`, title: `${name}成果` }] : [],
}));

const projection = {
  title: "客户共创任务",
  stage: "方案设计与评审",
  truthMode: "LIVE",
  connectionState: "CONNECTED",
  executionId: "fixture-execution",
  seats,
  transfers: [
    { id: "t1", sourceIndex: 0, targetIndex: 1, artifactTitle: "门禁领域证据包" },
    { id: "t2", sourceIndex: 1, targetIndex: 4, artifactTitle: "MVP 边界说明" },
  ],
  artifacts: seats.flatMap((seat) => seat.artifacts.map((artifact) => ({ ...artifact, metadata: { source_node_id: seat.id }, relative_path: `${artifact.id}.md`, created_at: "2026-08-26T08:00:00Z" }))),
};

const plan = {
  id: "fixture-office-plan-v1",
  content_hash: "fixture-hash",
  activation_revision: 1,
  dsl: {
    name: projection.title,
    nodes: seats.map((seat, index) => ({
      id: seat.id,
      node_type: index === 5 ? "FILTER_PASS" : index === 6 ? "OUTPUT_FORMAT" : "LLM_INFERENCE",
      name: seat.name,
      parameters: { agent_id: seat.businessRole, capability_status: "READY", execution_enabled: true },
    })),
    edges: [
      { source: "research", target: "analysis" },
      { source: "analysis", target: "architecture" },
      { source: "architecture", target: "review" },
      { source: "review", target: "summary" },
      { source: "summary", target: "quality" },
      { source: "quality", target: "delivery", condition: "approved" },
    ],
  },
};

const executionNodes = seats.map((seat) => ({ node_id: seat.id, status: seat.status }));

createRoot(document.getElementById("root")).render(<ReferenceOfficeView projection={projection} plan={plan} workflowId="" executionNodes={executionNodes} canEditCanvas={false} onSwitchToWorkbench={() => {}} />);
