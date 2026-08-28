import {
  Activity,
  Boxes,
  BrainCircuit,
  Check,
  CircleDollarSign,
  CloudCog,
  Cpu,
  Gauge,
  GitFork,
  HardDrive,
  Network,
  Plus,
  Save,
  Server,
  Sparkles,
  Trash2,
  Unplug,
  Workflow,
  Zap,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Background, Controls, MiniMap, ReactFlow } from "@xyflow/react";
import "@xyflow/react/dist/style.css";

const TABS = [
  ["configuration", "资源配置", CloudCog],
  ["topology", "架构与拓扑", GitFork],
  ["monitoring", "运行监控", Activity],
  ["token-factory", "Token Factory", Zap],
];

const numberValue = (value) => value ?? "";
const displayValue = (value, suffix = "") => value === null || value === undefined || value === "" ? "待配置" : `${value}${suffix}`;
const clone = (value) => JSON.parse(JSON.stringify(value));

function Field({ label, value, onChange, type = "text", suffix, min = 0, step = 1, hint }) {
  return (
    <label className="qw-resource-field">
      <span>{label}</span>
      <div>
        <input
          type={type}
          min={type === "number" ? min : undefined}
          step={type === "number" ? step : undefined}
          inputMode={type === "number" ? "numeric" : undefined}
          value={type === "number" ? numberValue(value) : value ?? ""}
          onChange={(event) => onChange(type === "number" ? (event.target.value === "" ? null : Number(event.target.value)) : event.target.value)}
        />
        {suffix && <em>{suffix}</em>}
      </div>
      {hint && <small>{hint}</small>}
    </label>
  );
}

function Metric({ icon: Icon, label, value, detail, tone = "blue" }) {
  return (
    <div className={`qw-resource-metric ${tone}`}>
      <i><Icon size={16} /></i>
      <span>{label}<strong>{value}</strong><small>{detail}</small></span>
    </div>
  );
}

function Section({ icon: Icon, title, description, children, action }) {
  return (
    <section className="qw-resource-card">
      <header>
        <div><i><Icon size={16} /></i><span><h3>{title}</h3><p>{description}</p></span></div>
        {action}
      </header>
      {children}
    </section>
  );
}

function ConfigurationPanel({ draft, update, updateSystem, addSystem, removeSystem }) {
  const infrastructure = draft.infrastructure;
  const runtime = draft.runtime;
  return (
    <div className="qw-resource-config-grid">
      <Section icon={Workflow} title="场景与系统拆解" description="把用户需求还原为可部署的系统边界、职责和副本策略。" action={<button type="button" className="qw-resource-inline-action" onClick={addSystem}><Plus size={14} />新增系统</button>}>
        <div className="qw-resource-scenario"><span>用户场景</span><strong>{draft.scenario?.name}</strong><p>{draft.scenario?.goal}</p></div>
        <div className="qw-resource-system-list">
          {draft.systems.map((system, index) => (
            <div className="qw-resource-system-row" key={system.id || index}>
              <Field label="系统名称" value={system.name} onChange={(value) => updateSystem(index, "name", value)} />
              <Field label="系统职责" value={system.role} onChange={(value) => updateSystem(index, "role", value)} />
              <Field label="部署方式" value={system.deployment} onChange={(value) => updateSystem(index, "deployment", value)} />
              <Field label="副本" type="number" value={system.replicas} onChange={(value) => updateSystem(index, "replicas", value)} />
              <button type="button" aria-label={`删除${system.name || "系统"}`} className="qw-resource-delete" onClick={() => removeSystem(index)}><Trash2 size={14} /></button>
            </div>
          ))}
        </div>
      </Section>

      <Section icon={Server} title="计算、存储与网络" description="ECS、超融合节点、GPU、磁盘、对象存储和带宽统一配置。">
        <div className="qw-resource-fieldset"><h4><Cpu size={14} />ECS</h4><div>
          <Field label="实例数" type="number" value={infrastructure.ecs.count} onChange={(value) => update(["infrastructure", "ecs", "count"], value)} />
          <Field label="单实例 vCPU" type="number" value={infrastructure.ecs.v_cpu} onChange={(value) => update(["infrastructure", "ecs", "v_cpu"], value)} />
          <Field label="单实例内存" type="number" suffix="GB" value={infrastructure.ecs.memory_gb} onChange={(value) => update(["infrastructure", "ecs", "memory_gb"], value)} />
        </div></div>
        <div className="qw-resource-fieldset"><h4><HardDrive size={14} />存储</h4><div>
          <Field label="系统盘" type="number" suffix="GB" value={infrastructure.storage.system_disk_gb} onChange={(value) => update(["infrastructure", "storage", "system_disk_gb"], value)} />
          <Field label="数据盘" type="number" suffix="GB" value={infrastructure.storage.data_disk_gb} onChange={(value) => update(["infrastructure", "storage", "data_disk_gb"], value)} />
          <Field label="对象存储" type="number" suffix="GB" value={infrastructure.storage.object_storage_gb} onChange={(value) => update(["infrastructure", "storage", "object_storage_gb"], value)} />
        </div></div>
        <div className="qw-resource-fieldset"><h4><Boxes size={14} />超融合与 GPU</h4><div>
          <Field label="超融合节点" type="number" value={infrastructure.hyperconverged_nodes.count} onChange={(value) => update(["infrastructure", "hyperconverged_nodes", "count"], value)} />
          <Field label="节点规格" value={infrastructure.hyperconverged_nodes.profile} onChange={(value) => update(["infrastructure", "hyperconverged_nodes", "profile"], value)} />
          <Field label="GPU 型号" value={infrastructure.gpu.model} onChange={(value) => update(["infrastructure", "gpu", "model"], value)} />
          <Field label="GPU 数量" type="number" value={infrastructure.gpu.count} onChange={(value) => update(["infrastructure", "gpu", "count"], value)} />
          <Field label="单卡显存" type="number" suffix="GB" value={infrastructure.gpu.memory_gb} onChange={(value) => update(["infrastructure", "gpu", "memory_gb"], value)} />
          <Field label="带宽" type="number" suffix="Mbps" value={infrastructure.network.bandwidth_mbps} onChange={(value) => update(["infrastructure", "network", "bandwidth_mbps"], value)} />
        </div></div>
      </Section>

      <Section icon={BrainCircuit} title="AI 运行时与本体" description="微服务、容器、队列、Agent、模型和推理服务的运行边界。">
        <div className="qw-resource-fields four">
          <Field label="微服务" type="number" value={runtime.microservices} onChange={(value) => update(["runtime", "microservices"], value)} />
          <Field label="容器" type="number" value={runtime.containers} onChange={(value) => update(["runtime", "containers"], value)} />
          <Field label="队列" type="number" value={runtime.queues} onChange={(value) => update(["runtime", "queues"], value)} />
          <Field label="Agent 数" type="number" value={runtime.agents.count} onChange={(value) => update(["runtime", "agents", "count"], value)} />
          <Field label="Agent 并发" type="number" value={runtime.agents.concurrency} onChange={(value) => update(["runtime", "agents", "concurrency"], value)} />
          <Field label="推理副本" type="number" value={runtime.inference.replicas} onChange={(value) => update(["runtime", "inference", "replicas"], value)} />
          <Field label="推理服务" value={runtime.inference.service} onChange={(value) => update(["runtime", "inference", "service"], value)} />
          <Field label="模型提供方" value={runtime.inference.provider} onChange={(value) => update(["runtime", "inference", "provider"], value)} />
          <Field label="模型" value={runtime.inference.model} onChange={(value) => update(["runtime", "inference", "model"], value)} />
        </div>
        <Field label="本体建模" value={runtime.ontology} onChange={(value) => update(["runtime", "ontology"], value)} hint="描述核心实体、关系、权限边界与知识更新机制。" />
      </Section>

      <Section icon={Gauge} title="SLA、加速与成本约束" description="用可验收指标约束资源选型，所有建议值都需要压测确认。">
        <div className="qw-resource-fields four">
          <Field label="P95 时延" type="number" suffix="ms" value={draft.sla.p95_latency_ms} onChange={(value) => update(["sla", "p95_latency_ms"], value)} />
          <Field label="吞吐" type="number" step="0.1" suffix="RPS" value={draft.sla.throughput_rps} onChange={(value) => update(["sla", "throughput_rps"], value)} />
          <Field label="可用性" value={draft.sla.availability} onChange={(value) => update(["sla", "availability"], value)} />
          <Field label="月成本上限" type="number" suffix="CNY" value={draft.sla.target_monthly_cost_cny} onChange={(value) => update(["sla", "target_monthly_cost_cny"], value)} />
        </div>
        <Field label="加速要求" value={draft.sla.acceleration} onChange={(value) => update(["sla", "acceleration"], value)} hint="例如量化、连续批处理、KV Cache、张量并行或推测解码。" />
      </Section>
    </div>
  );
}

function TopologyPanel({ plan }) {
  const projected = useMemo(() => {
    const nodes = (plan.topology?.nodes || []).map((node, index) => ({
      ...node,
      position: { x: 70 + (index % 4) * 280, y: 70 + Math.floor(index / 4) * 150 },
      data: { label: node.label },
      className: `qw-resource-flow-node type-${node.type || "service"}`,
    }));
    return { nodes, edges: (plan.topology?.edges || []).map((edge) => ({ ...edge, type: "smoothstep", animated: false })) };
  }, [plan.topology]);
  if (!projected.nodes.length) return <div className="qw-resource-empty"><GitFork size={26} /><strong>尚未生成拓扑</strong><p>运行 AI 推荐，或先配置系统与运行时资源。</p></div>;
  return (
    <div className="qw-resource-topology">
      <div className="qw-resource-topology-head"><span><strong>逻辑架构与部署拓扑</strong><small>当前为规划投影，不代表资源已经部署。</small></span><div><i className="scenario" />场景<i className="system" />系统<i className="runtime" />运行时</div></div>
      <div className="qw-resource-flow">
        <ReactFlow nodes={projected.nodes} edges={projected.edges} nodesDraggable={false} nodesConnectable={false} fitView minZoom={0.35} maxZoom={1.5}>
          <Background color="#dfe4ec" gap={20} size={1} />
          <MiniMap pannable zoomable nodeColor={(node) => node.className?.includes("scenario") ? "#2f6fed" : node.className?.includes("runtime") ? "#10a8a0" : "#76839a"} />
          <Controls showInteractive={false} />
        </ReactFlow>
      </div>
    </div>
  );
}

function MonitoringPanel({ monitoring }) {
  const connected = monitoring.source_status === "LIVE";
  return (
    <div className="qw-resource-monitor">
      <div className="qw-resource-metrics compact">
        <Metric icon={Activity} label="活跃执行" value={monitoring.active_executions} detail={`${monitoring.total_executions} 次可观测执行`} tone="green" />
        <Metric icon={Gauge} label="平均进度" value={`${monitoring.average_progress}%`} detail="来自 canonical Execution" />
        <Metric icon={BrainCircuit} label="Token 用量" value={monitoring.tokens_used.toLocaleString()} detail="已记录执行累计" tone="purple" />
        <Metric icon={CircleDollarSign} label="推理成本" value={`$${monitoring.estimated_cost_usd.toFixed(4)}`} detail="平台已记录估算" tone="amber" />
      </div>
      {!connected ? <div className="qw-resource-empty"><Unplug size={26} /><strong>尚无可监控的真实执行</strong><p>任务绑定 Workflow 并产生 canonical Execution 后，这里才会显示真实资源与用量指标。</p></div> : (
        <div className="qw-resource-executions">
          <div className="qw-resource-table-row header"><span>Execution</span><span>状态</span><span>Provider / Model</span><span>进度</span><span>Token</span><span>成本</span></div>
          {monitoring.executions.map((execution) => <div className="qw-resource-table-row" key={execution.id}>
            <span><strong>{execution.id}</strong><small>{execution.workflow_id}</small></span>
            <span><i className={`status ${execution.status}`} />{execution.status}</span>
            <span>{execution.provider || "未记录"}<small>{execution.model || "未记录模型"}</small></span>
            <span>{execution.progress}%</span><span>{execution.tokens_used.toLocaleString()}</span><span>${execution.estimated_cost_usd.toFixed(4)}</span>
          </div>)}
        </div>
      )}
    </div>
  );
}

function TokenFactoryPanel({ draft, update }) {
  const mapping = draft.token_factory;
  return (
    <div className="qw-token-factory-layout">
      <Section icon={Zap} title="超聚变 Token Factory 映射" description="把场景负载、Token 峰值、GPU 推理能力和产品容量单元建立可审计映射。">
        <div className="qw-token-status"><span><i /><strong>接口未连接</strong><small>当前映射为规划建议，不是 Token Factory 产品接口或报价结果。</small></span><button type="button" className="qw-button" disabled><Unplug size={14} />等待产品接口</button></div>
        <div className="qw-resource-fields three">
          <Field label="建议产品映射" value={mapping.product_mapping} onChange={(value) => update(["token_factory", "product_mapping"], value)} />
          <Field label="Token 峰值" type="number" suffix="/分钟" value={mapping.token_peak_per_minute} onChange={(value) => update(["token_factory", "token_peak_per_minute"], value)} />
          <Field label="月 Token 估算" type="number" value={mapping.monthly_token_estimate} onChange={(value) => update(["token_factory", "monthly_token_estimate"], value)} />
          <Field label="容量单元" value={mapping.capacity_unit} onChange={(value) => update(["token_factory", "capacity_unit"], value)} />
        </div>
        <Field label="选型证据与限制" value={mapping.evidence} onChange={(value) => update(["token_factory", "evidence"], value)} />
      </Section>
      <Section icon={Network} title="对应关系" description="从业务工作负载逐层换算到 Token Factory 容量。">
        <ol className="qw-token-chain">
          <li><span>01</span><div><strong>业务场景</strong><p>{draft.scenario?.goal}</p></div></li>
          <li><span>02</span><div><strong>Agent 与并发</strong><p>{displayValue(draft.runtime.agents.count)} 个 Agent · {displayValue(draft.runtime.agents.concurrency)} 并发</p></div></li>
          <li><span>03</span><div><strong>推理负载</strong><p>{displayValue(mapping.token_peak_per_minute, " Token/分钟")} · {draft.runtime.inference.model}</p></div></li>
          <li><span>04</span><div><strong>算力与容量</strong><p>{displayValue(draft.infrastructure.gpu.count)} × {draft.infrastructure.gpu.model} · {mapping.capacity_unit}</p></div></li>
          <li><span>05</span><div><strong>Token Factory 产品</strong><p>{mapping.product_mapping}</p></div></li>
        </ol>
      </Section>
    </div>
  );
}

export function AIResourceWorkbench({ resourceData, onRecommend, onSave }) {
  const [activeTab, setActiveTab] = useState("configuration");
  const [draft, setDraft] = useState(() => clone(resourceData.plan));
  const [constraints, setConstraints] = useState("");
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  useEffect(() => setDraft(clone(resourceData.plan)), [resourceData.plan]);

  const update = (path, value) => setDraft((current) => {
    const next = clone(current);
    let target = next;
    path.slice(0, -1).forEach((key) => { target = target[key]; });
    target[path.at(-1)] = value;
    return next;
  });
  const updateSystem = (index, key, value) => setDraft((current) => {
    const next = clone(current); next.systems[index][key] = value; return next;
  });
  const addSystem = () => setDraft((current) => ({ ...current, systems: [...current.systems, { id: `system-${Date.now()}`, name: "新系统", role: "", deployment: "容器", replicas: 1 }] }));
  const removeSystem = (index) => setDraft((current) => ({ ...current, systems: current.systems.filter((_, itemIndex) => itemIndex !== index) }));

  const runAction = async (kind, action, success) => {
    setBusy(kind); setError(""); setNotice("");
    try {
      const result = await action();
      setDraft(clone(result.plan));
      setNotice(success);
    } catch (reason) {
      setError(reason.message || "操作失败，请稍后重试");
    } finally { setBusy(""); }
  };
  const infra = draft.infrastructure;
  return (
    <section className="qw-resource-workbench">
      <header className="qw-resource-head">
        <div><span className="qw-eyebrow">AI infrastructure planning & operations</span><h2>AI Resource 工作台</h2><p>从用户场景生成系统、算力、模型与 Token Factory 映射，并用真实执行数据持续校验。</p></div>
        <div className="qw-resource-actions">
          <span className={`qw-chip ${draft.source_status === "UNCONFIGURED" ? "warning" : ""}`}>{draft.source_status}</span>
          <button type="button" className="qw-button" disabled={Boolean(busy)} onClick={() => runAction("save", () => onSave(draft), "资源配置已保存并生成新 revision。")}>{busy === "save" ? <Activity className="spin" size={14} /> : <Save size={14} />}保存配置</button>
          <button type="button" className="qw-button primary" disabled={Boolean(busy)} onClick={() => runAction("recommend", () => onRecommend(constraints), "Hermes 已生成资源建议，请核对假设后保存。")}>{busy === "recommend" ? <Activity className="spin" size={14} /> : <Sparkles size={14} />}AI 一键推荐</button>
        </div>
      </header>
      <div className="qw-resource-ai-bar"><Sparkles size={15} /><label><span>补充约束（可选）</span><input value={constraints} onChange={(event) => setConstraints(event.target.value)} placeholder="例如：私有化部署、成本优先、P95 < 2 秒、国产 GPU…" /></label><small>推荐结果标记为 AI_PROPOSED，不会自动部署资源。</small></div>
      {(error || notice) && <div className={`qw-resource-feedback ${error ? "error" : "success"}`}>{error ? <Unplug size={15} /> : <Check size={15} />}<span>{error || notice}</span></div>}
      <div className="qw-resource-metrics">
        <Metric icon={Workflow} label="系统" value={draft.systems.length} detail={`${displayValue(draft.runtime.microservices)} 个微服务`} />
        <Metric icon={Cpu} label="计算" value={`${displayValue(infra.ecs.count)} ECS`} detail={`${displayValue(infra.ecs.v_cpu)} vCPU · ${displayValue(infra.ecs.memory_gb, "GB")}`} tone="green" />
        <Metric icon={BrainCircuit} label="GPU / 模型" value={`${displayValue(infra.gpu.count)} × ${infra.gpu.model}`} detail={draft.runtime.inference.model} tone="purple" />
        <Metric icon={Gauge} label="SLA" value={displayValue(draft.sla.p95_latency_ms, "ms")} detail={`P95 · ${draft.sla.availability}`} tone="amber" />
        <Metric icon={Zap} label="Token Factory" value={draft.token_factory.status} detail={draft.token_factory.product_mapping} tone="red" />
      </div>
      <nav className="qw-resource-tabs" aria-label="AI Resource 工作台视图">
        {TABS.map(([id, label, Icon]) => <button type="button" key={id} className={activeTab === id ? "active" : ""} aria-pressed={activeTab === id} onClick={() => setActiveTab(id)}><Icon size={15} />{label}</button>)}
      </nav>
      <div className="qw-resource-body">
        {activeTab === "configuration" && <ConfigurationPanel draft={draft} update={update} updateSystem={updateSystem} addSystem={addSystem} removeSystem={removeSystem} />}
        {activeTab === "topology" && <TopologyPanel plan={draft} />}
        {activeTab === "monitoring" && <MonitoringPanel monitoring={resourceData.monitoring} />}
        {activeTab === "token-factory" && <TokenFactoryPanel draft={draft} update={update} />}
      </div>
      <footer className="qw-resource-assumptions"><strong>方案假设</strong><div>{draft.assumptions.map((item, index) => <span key={`${item}-${index}`}>{index + 1}. {item}</span>)}</div><small>资源变更仍需人工确认；未连接的监控与 Token Factory 数据不会显示为 LIVE。</small></footer>
    </section>
  );
}
