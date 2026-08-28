import React from "react";
import ReactDOM from "react-dom/client";
import { AIResourceWorkbench, DEFAULT_SCENARIO_TWIN } from "../features/quantum-workspace/AIResourceWorkbench";
import "../index.css";
import "../features/quantum-workspace/quantumWorkspace.css";

const plan = {
  source_status: "AI_PROPOSED",
  scenario: { name: "企业智能服务平台", goal: "面向内部员工和客户提供知识问答、任务协同与智能决策服务。" },
  systems: [
    { id: "portal", name: "客户服务门户", role: "多渠道用户入口与权限控制", deployment: "容器", replicas: 3 },
    { id: "agent", name: "Agent 编排平台", role: "任务拆解、工具调用与流程调度", deployment: "Kubernetes", replicas: 4 },
    { id: "knowledge", name: "企业知识中台", role: "知识检索、本体与证据治理", deployment: "容器", replicas: 3 },
  ],
  infrastructure: {
    ecs: { count: 8, v_cpu: 32, memory_gb: 128 },
    storage: { system_disk_gb: 200, data_disk_gb: 4096, object_storage_gb: 20480 },
    hyperconverged_nodes: { count: 4, profile: "高性能超融合节点" },
    gpu: { model: "企业级推理 GPU", count: 16, memory_gb: 32 },
    network: { bandwidth_mbps: 10000 },
  },
  runtime: {
    microservices: 18, containers: 42, queues: 6,
    agents: { count: 12, concurrency: 80 },
    inference: { replicas: 6, service: "统一推理网关", provider: "xFusion Token Factory", model: "企业大模型服务" },
    ontology: "客户、产品、合同、知识、任务和组织权限的统一企业本体",
  },
  sla: { p95_latency_ms: 1500, throughput_rps: 120, availability: "99.95%", target_monthly_cost_cny: 180000, acceleration: "连续批处理、KV Cache、量化与弹性推理副本" },
  token_factory: { status: "PLANNED", product_mapping: "Token Factory 企业推理资源池", token_peak_per_minute: 82000, monthly_token_estimate: 840000000, capacity_unit: "2 个推理容量单元", evidence: "以并发、Token 峰值和 P95 目标进行容量规划" },
  topology: { nodes: [], edges: [] },
  assumptions: ["首期覆盖 2,000 名内部用户", "业务峰值集中在工作日 09:00–18:00", "最终规格需通过 PoC 压测确认"],
};

const resourceData = {
  plan,
  monitoring: { source_status: "UNCONNECTED", active_executions: 0, total_executions: 0, average_progress: 0, tokens_used: 0, estimated_cost_usd: 0, executions: [] },
};

function Prototype() {
  const generateDataset = async ({ simulatorId, rowCount, seed }) => {
    const base = DEFAULT_SCENARIO_TWIN.datasets[0];
    const dataset = { ...base, id: `dataset-${simulatorId}-${seed}`, simulator_id: simulatorId, row_count: rowCount, seed, generated_at: new Date().toISOString(), sample_rows: base.sample_rows.map((row, index) => ({ ...row, order_id: `SIM-SO-${String(seed).slice(-4)}-${String(index + 1).padStart(3, "0")}` })) };
    return { dataset, plan: { ...plan, scenario_twin: { ...DEFAULT_SCENARIO_TWIN, datasets: [dataset] } } };
  };
  return <div className="qw-app"><AIResourceWorkbench resourceData={resourceData} onRecommend={async () => ({ plan })} onSave={async () => ({ plan })} onGenerateDataset={generateDataset} onAskContext={async ({ contextTitle, question }) => ({ answer: `「${contextTitle}」已附加到问题中。针对“${question}”，建议先核对场景证据和真实性边界，再调整方案；所有模拟数据都应保留 seed、Schema、质量结果与 lineage。` })} /></div>;
}

ReactDOM.createRoot(document.getElementById("root")).render(<React.StrictMode><Prototype /></React.StrictMode>);
