import {
  Activity,
  ArrowRight,
  BadgeCheck,
  BarChart3,
  Bot,
  Boxes,
  BrainCircuit,
  Braces,
  Cable,
  Check,
  ChevronRight,
  CircleCheckBig,
  CircleDollarSign,
  CloudCog,
  Code2,
  Cpu,
  Database,
  FileJson,
  FlaskConical,
  Gauge,
  GitFork,
  HardDrive,
  Eye,
  Layers3,
  MessageCircle,
  Play,
  Plus,
  Radio,
  RefreshCw,
  Save,
  Send,
  Server,
  ShieldCheck,
  Sparkles,
  Timer,
  Table2,
  Trash2,
  TrendingDown,
  Unplug,
  Users,
  WalletCards,
  Waypoints,
  Workflow,
  X,
  Zap,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Background, Controls, MiniMap, ReactFlow } from "@xyflow/react";
import "@xyflow/react/dist/style.css";

const TABS = [
  ["configuration", "资源配置", CloudCog],
  ["topology", "架构与拓扑", GitFork],
  ["monitoring", "运行监控", Activity],
];

const TOKEN_FACTORY_ADVANTAGES = [
  { icon: Layers3, title: "全栈一体化", detail: "算力、存储、网络与推理服务统一规划，减少多厂商拼装复杂度。" },
  { icon: Gauge, title: "高效推理", detail: "面向 Token 吞吐、并发与时延目标进行资源池和推理链路优化。" },
  { icon: ShieldCheck, title: "私有化可信交付", detail: "支持数据留域、资源隔离与企业级可用性设计。" },
  { icon: TrendingDown, title: "全生命周期 TCO", detail: "从容量规划到运行监控持续校准，避免闲置与峰值资源浪费。" },
];

export const DEFAULT_SCENARIO_TWIN = {
  level: "L2 状态化仿真",
  fidelity: { data: 82, interface: 76, workflow: 90, exception: 65 },
  actors: ["客户经理", "财务审批人", "交付经理", "最终客户"],
  steps: ["客户申请", "资料校验", "信用审批", "订单创建", "库存分配", "履约开票"],
  subagents: [
    { name: "场景编排 Agent", role: "控制步骤、分支和任务交接", tools: "流程状态 · 事件总线" },
    { name: "财务审批 Agent", role: "执行信用、账期和风险判断", tools: "CRM · 信用规则" },
    { name: "交付 Agent", role: "处理库存、拆单和交付决策", tools: "库存 API · ERP" },
  ],
  systems: [
    { id: "erp-order-simulator", name: "ERP 订单模拟器", truth: "SIMULATED", detail: "订单、审批、发票状态机", interfaces: 6, methodology: { scenario_scope: "承接信用审批后的订单创建、库存分配、履约与开票；不模拟与本场景无关的 ERP 总账。", module_reuse: "销售订单、库存预留、应收开票三个最小业务切片", data_strategy: "从用户字段字典提取客户、SKU、价格、账期；缺失字段按约束生成合成值并记录 lineage。", state_machine: ["DRAFT", "CREDIT_APPROVED", "ALLOCATED", "PARTIAL", "SHIPPED", "INVOICED"], agent_design: { agent: "ERP 行为模拟 Agent", objective: "依据场景事件驱动订单状态迁移并返回可解释结果", inputs: ["客户信用结论", "订单行", "库存快照", "异常参数"], tools: ["订单状态机", "规则引擎", "Mock API", "合成数据仓"], memory: "仅保存当前 run 的订单状态和证据链", guardrails: ["禁止访问生产 ERP", "禁止生成未定义状态", "迁移必须输出 rule_id"] }, validation: ["主链路六步可重放", "接口契约通过率 ≥ 95%", "缺货/超信用/重复开票可复现"] }, contracts: [{ method: "POST", path: "/orders", purpose: "创建订单" }, { method: "POST", path: "/orders/{id}/allocate", purpose: "库存预留" }, { method: "POST", path: "/orders/{id}/invoice", purpose: "模拟开票" }] },
    { id: "crm-sandbox", name: "CRM 测试环境", truth: "SANDBOX", detail: "客户、联系人和历史交易", interfaces: 4, methodology: { scenario_scope: "支撑资料校验与信用审批步骤的客户上下文查询。", module_reuse: "客户主数据与交易历史", data_strategy: "优先使用脱敏样本，无样本时生成分层客户画像。", state_machine: ["ACTIVE", "REVIEW", "BLOCKED"], agent_design: { agent: "CRM 数据代理", objective: "返回与场景一致的客户上下文", inputs: ["customer_id"], tools: ["Sandbox API", "字段映射"], memory: "只读会话缓存", guardrails: ["PII 默认脱敏"] }, validation: ["字段覆盖率 ≥ 90%", "查询结果可追溯"] }, contracts: [{ method: "GET", path: "/customers/{id}", purpose: "查询客户" }] },
    { id: "inventory-mock", name: "库存 Mock API", truth: "SIMULATED", detail: "锁库、扣减、补货与异常", interfaces: 5, methodology: { scenario_scope: "模拟库存分配、缺货和跨仓调拨。", module_reuse: "库存可用量与预留", data_strategy: "按 SKU/仓库/批次生成库存快照并注入缺货概率。", state_machine: ["AVAILABLE", "RESERVED", "SHORTAGE", "TRANSFER_PENDING", "DEDUCTED"], agent_design: { agent: "库存行为模拟 Agent", objective: "按规则返回库存动作与异常", inputs: ["sku", "quantity", "warehouse"], tools: ["库存状态机", "异常注入器"], memory: "run 级库存快照", guardrails: ["库存不得小于零"] }, validation: ["锁库与释放守恒", "缺货分支可重复"] }, contracts: [{ method: "POST", path: "/inventory/reserve", purpose: "预留库存" }] },
    { id: "synthetic-business-data", name: "合成业务数据", truth: "SYNTHETIC", detail: "客户、商品、订单与异常样本", interfaces: 8, methodology: { scenario_scope: "为全部模拟器提供一致的实体与异常样本。", module_reuse: "业务实体生成与关联约束", data_strategy: "Schema 约束 + 分布参数 + 固定种子；不复制真实 PII。", state_machine: ["DRAFT", "GENERATED", "VALIDATED", "PUBLISHED"], agent_design: { agent: "合成数据设计 Agent", objective: "生成满足关系和分布约束的可重放数据", inputs: ["字段字典", "约束", "规模", "seed"], tools: ["Schema 生成器", "质量校验器"], memory: "数据集 manifest", guardrails: ["禁止产生真实 PII"] }, validation: ["Schema 通过率 100%", "主外键完整率 100%", "PII 扫描通过"] }, contracts: [{ method: "POST", path: "/datasets/generate", purpose: "生成数据集" }] },
  ],
  datasets: [{ id: "dataset-erp-order-simulator-20260828", simulator_id: "erp-order-simulator", name: "ERP 订单模拟器 · 销售订单样本", truth: "SYNTHETIC", status: "VALIDATED", row_count: 1000, seed: 20260828, generated_at: "2026-08-28T04:00:00Z", schema: [{ name: "order_id", type: "string", description: "模拟订单编号" }, { name: "customer_id", type: "string", description: "合成客户标识" }, { name: "sku", type: "string", description: "合成商品编码" }, { name: "quantity", type: "integer", description: "订购数量" }, { name: "state", type: "enum", description: "订单状态" }, { name: "rule_id", type: "string", description: "状态迁移证据" }], sample_rows: [{ order_id: "SIM-SO-0828-001", customer_id: "SYN-C-2048", sku: "SKU-431", quantity: "8", state: "ALLOCATED", rule_id: "ERP-R-04" }, { order_id: "SIM-SO-0828-002", customer_id: "SYN-C-7319", sku: "SKU-118", quantity: "16", state: "PARTIAL", rule_id: "ERP-R-09" }, { order_id: "SIM-SO-0828-003", customer_id: "SYN-C-5521", sku: "SKU-906", quantity: "3", state: "INVOICED", rule_id: "ERP-R-11" }], quality: { schema_validity: 100, referential_integrity: 100, pii_safety: 100, scenario_coverage: 84 }, lineage: "由 ERP 模拟方法论、场景步骤和 seed=20260828 确定性生成；未读取生产数据。" }],
};

const DEFAULT_MODEL_REGISTRY = {
  models: [
    { id: "model-online-general", name: "企业通用大模型", delivery_mode: "ONLINE", provider: "AI Lab Provider Router", version: "provider-managed", stage: "PRODUCTION", capabilities: ["chat", "tool_calling", "structured_output"], context_window: 128000, endpoint: "统一推理网关 / online", runtime: "Provider API", hardware: "Provider managed", linked_agents: ["场景编排 Agent", "财务审批 Agent"], linked_datasets: ["ERP 订单模拟器 · 销售订单样本"], evaluation: { scenario_pass_rate: 94, p95_latency_ms: 1420, cost_per_million_tokens: 18.6 }, truth: "CONNECTED" },
    { id: "model-offline-private", name: "企业私有推理模型", delivery_mode: "OFFLINE", provider: "AI Lab Model Runtime", version: "v1.3-int4", stage: "STAGING", capabilities: ["chat", "rag", "function_calling"], context_window: 32768, endpoint: "Token Factory 私有推理池", artifact_uri: "s3://model-registry/private-model/v1.3-int4", runtime: "vLLM-compatible", quantization: "INT4", hardware: "16 × 企业级推理 GPU", linked_agents: ["交付 Agent"], linked_datasets: ["业务异常评测集"], evaluation: { scenario_pass_rate: 88, p95_latency_ms: 980, cost_per_million_tokens: 6.4 }, truth: "PLANNED" },
  ],
  policy: { promotion_gate: "评测通过 + 安全审查 + 容量压测", fallback: "online → offline private → rule-based degraded mode" },
};

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

function ContextChatButton({ onClick, label = "询问 AI" }) {
  return <button type="button" className="qw-context-chat-button" onClick={onClick}><MessageCircle size={14} />{label}</button>;
}

function Section({ icon: Icon, title, description, children, action, onChat, className = "" }) {
  return (
    <section className={`qw-resource-card ${className}`}>
      <header>
        <div><i><Icon size={16} /></i><span><h3>{title}</h3><p>{description}</p></span></div>
        {(action || onChat) && <div className="qw-card-actions">{action}{onChat && <ContextChatButton onClick={onChat} />}</div>}
      </header>
      {children}
    </section>
  );
}

function ResourceContextChat({ context, onClose, onAsk }) {
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const [messages, setMessages] = useState([{ role: "assistant", content: `已附加「${context.title}」的当前配置、真实性标签与方案假设。你可以直接问选型依据、风险或调整建议。` }]);
  const suggestions = context.suggestions || ["为什么这样设计？", "有哪些风险和假设？", "如何降低成本？"];
  const submit = async (value = question) => {
    const nextQuestion = value.trim();
    if (!nextQuestion || busy) return;
    setMessages((current) => [...current, { role: "user", content: nextQuestion }]);
    setQuestion(""); setBusy(true);
    try {
      const result = await onAsk({ contextId: context.id, contextTitle: context.title, question: nextQuestion });
      setMessages((current) => [...current, { role: "assistant", content: result.answer }]);
    } catch (reason) {
      setMessages((current) => [...current, { role: "error", content: reason.message || "AI 暂时无法回答，请稍后重试。" }]);
    } finally { setBusy(false); }
  };
  return (
    <aside className="qw-resource-chat" aria-label={`${context.title}上下文问答`}>
      <header><div><span className="qw-prototype-label">CONTEXT COPILOT</span><h3>{context.title}</h3><p>自动携带当前卡片配置，不会直接修改或部署资源。</p></div><button type="button" aria-label="关闭上下文问答" onClick={onClose}><X size={17} /></button></header>
      <div className="qw-chat-context"><span><Code2 size={13} />已附加上下文</span><strong>{context.summary}</strong><small>PLAN SNAPSHOT · {context.truth || "USER_CONFIGURED"}</small></div>
      <div className="qw-resource-chat-messages">{messages.map((message, index) => <article key={`${message.role}-${index}`} className={message.role}><span>{message.role === "user" ? "你" : message.role === "error" ? "!" : <Sparkles size={13} />}</span><p>{message.content}</p></article>)}{busy && <article className="assistant loading"><span><RefreshCw className="spin" size={13} /></span><p>正在结合卡片上下文分析…</p></article>}</div>
      <div className="qw-chat-suggestions">{suggestions.map((item) => <button type="button" key={item} onClick={() => submit(item)}>{item}</button>)}</div>
      <form className="qw-resource-chat-form" onSubmit={(event) => { event.preventDefault(); submit(); }}><textarea aria-label="向 AI 询问当前卡片" rows="3" value={question} onChange={(event) => setQuestion(event.target.value)} placeholder={`询问${context.title}的设计依据、风险或修改建议…`} /><button type="submit" aria-label="发送问题" disabled={busy || !question.trim()}><Send size={15} /></button></form>
    </aside>
  );
}

function TokenFactoryValue({ draft, onChat }) {
  const mapping = draft.token_factory || {};
  return (
    <section className="qw-token-value qw-resource-card">
      <div className="qw-token-value-lead">
        <div className="qw-token-value-head"><span className="qw-token-brand"><Zap size={14} />xFusion Token Factory</span><ContextChatButton label="咨询方案" onClick={onChat} /></div>
        <h3>把资源清单升级为可交付的 AI 推理产线</h3>
        <p>不是额外增加一套配置，而是用一体化产品能力承接当前场景的算力、推理、运维与成本目标。</p>
        <div className="qw-token-fit">
          <span><small>当前负载</small><strong>{displayValue(mapping.token_peak_per_minute, " Token/min")}</strong></span>
          <ArrowRight size={16} />
          <span><small>推荐形态</small><strong>{mapping.product_mapping || "待方案确认"}</strong></span>
          <ArrowRight size={16} />
          <span><small>交付方式</small><strong>一体化资源池</strong></span>
        </div>
        <small className="qw-token-disclaimer">方案推介 · 具体规格与收益以压测和商务方案为准</small>
      </div>
      <div className="qw-token-benefits">
        {TOKEN_FACTORY_ADVANTAGES.map(({ icon: Icon, title, detail }) => (
          <article key={title}><i><Icon size={15} /></i><div><strong>{title}</strong><p>{detail}</p></div></article>
        ))}
      </div>
    </section>
  );
}

function TruthBadge({ value }) {
  return <span className={`qw-truth-badge truth-${value.toLowerCase()}`}>{value}</span>;
}

function ScenarioTwinBlueprint({ draft, onChat }) {
  const twin = draft.scenario_twin || DEFAULT_SCENARIO_TWIN;
  const fidelity = Object.values(twin.fidelity);
  const averageFidelity = Math.round(fidelity.reduce((sum, value) => sum + value, 0) / fidelity.length);
  return (
    <section className="qw-twin-blueprint qw-resource-card">
      <header className="qw-twin-blueprint-head">
        <div><i><FlaskConical size={16} /></i><span><small>SCENARIO ENVIRONMENT TWIN</small><h3>用户业务环境还原</h3><p>不复刻完整业务系统，只构建当前需求所需的角色、流程、数据、接口和异常。</p></span></div>
        <div className="qw-card-actions"><span className="qw-twin-level"><strong>{twin.level}</strong><small>建议还原等级</small></span><ContextChatButton onClick={onChat} /></div>
      </header>
      <div className="qw-twin-overview">
        <div className="qw-twin-score" style={{ "--twin-score": `${averageFidelity}%` }}><div><strong>{averageFidelity}</strong><small>综合还原度</small></div></div>
        <div className="qw-twin-fidelity">
          {[["数据", twin.fidelity.data], ["接口", twin.fidelity.interface], ["流程", twin.fidelity.workflow], ["异常", twin.fidelity.exception]].map(([label, value]) => <article key={label}><span><strong>{label}还原</strong><em>{value}%</em></span><div><i style={{ width: `${value}%` }} /></div></article>)}
        </div>
        <div className="qw-twin-scope"><span><Users size={14} /><strong>{twin.actors.length}</strong><small>业务角色</small></span><span><Bot size={14} /><strong>{twin.subagents.length}</strong><small>Subagent</small></span><span><Database size={14} /><strong>{twin.systems.length}</strong><small>环境组件</small></span><span><Cable size={14} /><strong>{twin.systems.reduce((sum, system) => sum + system.interfaces, 0)}</strong><small>接口契约</small></span></div>
      </div>
      <div className="qw-twin-journey">
        <span>业务场景路径</span><ol>{twin.steps.map((step, index) => <li key={step}><i>{String(index + 1).padStart(2, "0")}</i><strong>{step}</strong>{index < twin.steps.length - 1 && <ArrowRight size={13} />}</li>)}</ol>
      </div>
    </section>
  );
}

function SubagentPanel({ draft, onChat }) {
  const twin = draft.scenario_twin || DEFAULT_SCENARIO_TWIN;
  return (
    <Section icon={Bot} title="场景 Subagent" description="Agent 只承担判断、规划和协作；确定性系统行为交给模拟服务。" action={<span className="qw-plan-count">{twin.subagents.length} PLANNED</span>} onChat={onChat}>
      <div className="qw-subagent-list">{twin.subagents.map((agent, index) => <article key={agent.name}><span>{String(index + 1).padStart(2, "0")}</span><i><Bot size={15} /></i><div><strong>{agent.name}</strong><p>{agent.role}</p><small>{agent.tools}</small></div></article>)}</div>
    </Section>
  );
}

function SimulationEnvironmentPanel({ draft, onChat, onGenerateDataset, onOpenDatasets }) {
  const twin = draft.scenario_twin || DEFAULT_SCENARIO_TWIN;
  const [selectedId, setSelectedId] = useState(twin.systems[0]?.id);
  const [detailTab, setDetailTab] = useState("method");
  const [rowCount, setRowCount] = useState(1000);
  const [seed, setSeed] = useState(20260828);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const selected = twin.systems.find((system) => system.id === selectedId) || twin.systems[0];
  const dataset = twin.datasets?.find((item) => item.simulator_id === selected?.id) || twin.datasets?.[0];
  const method = selected?.methodology || {};
  const agent = method.agent_design || {};
  const generate = async () => {
    setBusy(true); setError("");
    try { await onGenerateDataset({ simulatorId: selected.id, rowCount, seed }); setDetailTab("data"); }
    catch (reason) { setError(reason.message || "模拟数据生成失败"); }
    finally { setBusy(false); }
  };
  return (
    <Section className="qw-simulation-card" icon={Waypoints} title="数据源、接口与模拟环境" description="用最小可运行切片还原业务系统；方法、Agent、接口、数据和验收证据均可下钻。" onChat={onChat}>
      <div className="qw-simulator-list">{twin.systems.map((system) => <article key={system.name} className={selected?.id === system.id ? "selected" : ""}><i>{system.truth === "SYNTHETIC" ? <FileJson size={15} /> : system.truth === "SANDBOX" ? <Cable size={15} /> : <Braces size={15} />}</i><div><strong>{system.name}</strong><p>{system.detail}</p><small>{system.interfaces} 个接口 / 数据契约</small></div><TruthBadge value={system.truth} /><button type="button" onClick={() => { setSelectedId(system.id); setDetailTab("method"); }}><Eye size={13} />查看设计</button></article>)}</div>
      {selected && <div className="qw-simulation-detail">
        <header><div><span className="qw-prototype-label">SIMULATION SPEC</span><h4>{selected.name}</h4><p>{method.scenario_scope}</p></div><div className="qw-detail-tabs"><button type="button" className={detailTab === "method" ? "active" : ""} onClick={() => setDetailTab("method")}><Waypoints size={13} />模拟方法</button><button type="button" className={detailTab === "data" ? "active" : ""} onClick={() => setDetailTab("data")}><Table2 size={13} />模拟数据{dataset && <em>{dataset.row_count}</em>}</button></div></header>
        {detailTab === "method" ? <div className="qw-methodology-grid">
          <div className="qw-method-steps">
            {[['01','需求映射',method.scenario_scope],['02','模块取用',method.module_reuse],['03','数据策略',method.data_strategy]].map(([index,title,detail]) => <article key={title}><span>{index}</span><div><strong>{title}</strong><p>{detail}</p></div></article>)}
            <article><span>04</span><div><strong>状态机</strong><div className="qw-state-machine">{(method.state_machine || []).map((state, index) => <span key={state}>{state}{index < method.state_machine.length - 1 && <ChevronRight size={11} />}</span>)}</div></div></article>
          </div>
          <div className="qw-agent-spec"><header><i><Bot size={15} /></i><span><small>AGENT DESIGN</small><strong>{agent.agent}</strong></span><TruthBadge value="PLANNED" /></header><p>{agent.objective}</p><dl><div><dt>输入</dt><dd>{(agent.inputs || []).join(' · ')}</dd></div><div><dt>工具</dt><dd>{(agent.tools || []).join(' · ')}</dd></div><div><dt>记忆</dt><dd>{agent.memory}</dd></div><div><dt>护栏</dt><dd>{(agent.guardrails || []).join('；')}</dd></div></dl></div>
          <div className="qw-contract-spec"><header><strong>接口契约</strong><small>{selected.interfaces} 个规划接口</small></header>{(selected.contracts || []).map((contract) => <article key={`${contract.method}-${contract.path}`}><em>{contract.method}</em><code>{contract.path}</code><span>{contract.purpose}</span></article>)}</div>
          <div className="qw-validation-spec"><header><CircleCheckBig size={14} /><strong>验收规则</strong></header>{(method.validation || []).map((item) => <p key={item}><Check size={12} />{item}</p>)}</div>
        </div> : <div className="qw-dataset-workbench">
          <div className="qw-dataset-controls"><div><span className="qw-prototype-label">SYNTHETIC DATA GENERATOR</span><strong>生成可查看、可重放、可校验的业务数据</strong><small>固定 seed 可得到相同结果；生成记录包含 Schema、质量和 lineage。</small></div><label>数据量<input type="number" min="1" max="1000000" value={rowCount} onChange={(event) => setRowCount(Number(event.target.value))} /></label><label>Seed<input type="number" min="1" value={seed} onChange={(event) => setSeed(Number(event.target.value))} /></label><button type="button" disabled={busy} onClick={generate}>{busy ? <RefreshCw className="spin" size={14} /> : <Sparkles size={14} />}生成数据</button></div>
          {error && <p className="qw-dataset-error">{error}</p>}
          {dataset ? <><div className="qw-dataset-manifest"><span><TruthBadge value={dataset.truth || "SYNTHETIC"} /><strong>{dataset.name}</strong><small>{dataset.row_count.toLocaleString()} 行 · seed {dataset.seed} · {dataset.status}</small></span><div>{Object.entries(dataset.quality || {}).map(([key, value]) => <span key={key}><strong>{value}%</strong><small>{key.replaceAll('_',' ')}</small></span>)}</div><p>{dataset.lineage}</p></div><div className="qw-dataset-table-wrap"><table><thead><tr>{(dataset.schema || []).map((field) => <th key={field.name}><span>{field.name}</span><small>{field.type}</small></th>)}</tr></thead><tbody>{(dataset.sample_rows || []).map((row, index) => <tr key={index}>{dataset.schema.map((field) => <td key={field.name}>{row[field.name]}</td>)}</tr>)}</tbody></table></div><footer className="qw-dataset-footer"><span><Table2 size={13} />当前显示 {dataset.sample_rows?.length || 0} 条样例 / 共 {dataset.row_count.toLocaleString()} 条</span><div><button type="button"><FileJson size={13} />导出 manifest</button><button type="button" className="primary" onClick={onOpenDatasets}><Database size={13} />进入数据集工作区</button></div></footer></> : <div className="qw-dataset-empty"><Database size={22} /><strong>尚未生成数据集</strong><p>设置数据量和 Seed 后生成；数据会保存到当前资源方案 revision。</p></div>}
        </div>}
      </div>}
    </Section>
  );
}

function DatasetWorkspace({ draft, onBack, onGenerateDataset, openChat }) {
  const twin = draft.scenario_twin || DEFAULT_SCENARIO_TWIN;
  const datasets = twin.datasets?.length ? twin.datasets : DEFAULT_SCENARIO_TWIN.datasets;
  const [selectedId, setSelectedId] = useState(datasets[0]?.id);
  const [view, setView] = useState("data");
  const [filter, setFilter] = useState("");
  const selected = datasets.find((item) => item.id === selectedId) || datasets[0];
  const simulator = twin.systems.find((item) => item.id === selected?.simulator_id);
  const rows = (selected?.sample_rows || []).filter((row) => !filter || Object.values(row).some((value) => String(value).toLowerCase().includes(filter.toLowerCase())));
  return <div className="qw-dataset-studio">
    <header className="qw-dataset-studio-head"><div><button type="button" onClick={onBack}>← 返回资源配置</button><span className="qw-prototype-label">DATASET STUDIO</span><h3>模拟数据集工作区</h3><p>Schema、版本、质量、血缘和使用关系统一管理；大体量数据落对象存储或表引擎。</p></div><div><ContextChatButton onClick={() => openChat("datasets", "模拟数据集", "数据集 Schema、质量、版本、血缘和任务用途", ["这个数据集是否覆盖当前场景？", "如何设计训练/评测切分？"])} /><button type="button" className="qw-button primary" onClick={() => onGenerateDataset({ simulatorId: selected?.simulator_id || twin.systems[0]?.id, rowCount: selected?.row_count || 1000, seed: (selected?.seed || 1) + 1 })}><Sparkles size={14} />生成新版本</button></div></header>
    <div className="qw-dataset-studio-layout"><aside className="qw-dataset-catalog"><label><Database size={14} /><input aria-label="搜索数据集" placeholder="搜索数据集…" value={filter} onChange={(event) => setFilter(event.target.value)} /></label><small>PROJECT DATASETS · {datasets.length}</small>{datasets.map((item) => <button type="button" key={item.id} className={item.id === selected?.id ? "active" : ""} onClick={() => setSelectedId(item.id)}><i><Table2 size={15} /></i><span><strong>{item.name}</strong><small>{item.row_count.toLocaleString()} rows · v{item.version || 1}</small></span><TruthBadge value={item.truth || "SYNTHETIC"} /></button>)}</aside>
      {selected && <main className="qw-dataset-detail"><header><div><span><TruthBadge value={selected.truth || "SYNTHETIC"} /><em>{selected.status}</em></span><h3>{selected.name}</h3><p>{simulator?.methodology?.data_strategy || selected.lineage}</p></div><div className="qw-dataset-kpis"><span><strong>{selected.row_count.toLocaleString()}</strong><small>Rows</small></span><span><strong>{selected.schema?.length || 0}</strong><small>Columns</small></span><span><strong>{selected.seed}</strong><small>Seed</small></span><span><strong>{Math.round(Object.values(selected.quality || {}).reduce((a,b) => a + b, 0) / Math.max(1, Object.keys(selected.quality || {}).length))}%</strong><small>Quality</small></span></div></header><nav>{[["data","数据预览"],["schema","Schema"],["profile","质量画像"],["versions","版本"],["lineage","血缘与用途"]].map(([id,label]) => <button type="button" key={id} className={view === id ? "active" : ""} onClick={() => setView(id)}>{label}</button>)}</nav>
        {view === "data" && <section className="qw-dataset-sheet"><div><input placeholder="过滤当前样例…" value={filter} onChange={(event) => setFilter(event.target.value)} /><span>只读预览 · 显示 {rows.length} / {selected.row_count.toLocaleString()}</span></div><div><table><thead><tr><th>#</th>{selected.schema.map((field) => <th key={field.name}><strong>{field.name}</strong><small>{field.type}</small></th>)}</tr></thead><tbody>{rows.map((row,index) => <tr key={index}><td>{index + 1}</td>{selected.schema.map((field) => <td key={field.name}>{row[field.name]}</td>)}</tr>)}</tbody></table></div></section>}
        {view === "schema" && <section className="qw-dataset-schema-list">{selected.schema.map((field,index) => <article key={field.name}><span>{String(index + 1).padStart(2,"0")}</span><strong>{field.name}</strong><code>{field.type}</code><p>{field.description}</p><em>{index === 0 ? "PRIMARY" : "NULLABLE"}</em></article>)}</section>}
        {view === "profile" && <section className="qw-dataset-profile">{Object.entries(selected.quality || {}).map(([key,value]) => <article key={key}><span><strong>{key.replaceAll("_"," ")}</strong><em>{value}%</em></span><div><i style={{width:`${value}%`}} /></div><small>{value >= 95 ? "通过发布门槛" : "建议补充异常与边界样本"}</small></article>)}</section>}
        {view === "versions" && <section className="qw-version-list"><article><i><BadgeCheck size={16} /></i><span><strong>v{selected.version || 1} · 当前版本</strong><small>{selected.generated_at || "原型样例"} · digest {(selected.digest || "preview-20260828").slice(0,12)}</small></span><TruthBadge value="VALIDATED" /></article><article><i><GitFork size={16} /></i><span><strong>不可变版本策略</strong><small>每次生成创建新 version；Schema、质量、seed、对象 URI 与 checksum 一同固化。</small></span></article></section>}
        {view === "lineage" && <section className="qw-dataset-lineage"><div><strong>生成血缘</strong><p>{selected.lineage}</p><code>{simulator?.name || "场景模拟器"} → deterministic generator → dataset v{selected.version || 1}</code></div><div><strong>消费关系</strong><ul><li>ERP 行为模拟 Agent · simulation input</li><li>模型评测流水线 · evaluation dataset</li><li>方案拓扑节点 · dataset binding</li></ul></div></section>}
      </main>}
    </div>
  </div>;
}

function ModelRegistryPanel({ draft, onChat }) {
  const registry = draft.model_registry || DEFAULT_MODEL_REGISTRY;
  const [mode, setMode] = useState("ONLINE");
  const models = registry.models.filter((item) => item.delivery_mode === mode);
  return <Section className="qw-model-registry" icon={BrainCircuit} title="大模型仓库" description="统一管理线上 Provider 模型与线下私有模型的版本、部署、评测、数据和 Agent 绑定。" action={<div className="qw-model-mode"><button type="button" className={mode === "ONLINE" ? "active" : ""} onClick={() => setMode("ONLINE")}>线上模型</button><button type="button" className={mode === "OFFLINE" ? "active" : ""} onClick={() => setMode("OFFLINE")}>线下模型</button></div>} onChat={onChat}><div className="qw-model-policy"><span><ShieldCheck size={14} /><strong>准入门槛</strong>{registry.policy?.promotion_gate}</span><span><GitFork size={14} /><strong>降级链路</strong>{registry.policy?.fallback}</span></div><div className="qw-model-list">{models.map((model) => <article key={model.id}><header><div><i><BrainCircuit size={16} /></i><span><small>{model.delivery_mode} · {model.provider}</small><strong>{model.name}</strong></span></div><TruthBadge value={model.truth} /></header><div className="qw-model-version"><span><small>版本 / 阶段</small><strong>{model.version} · {model.stage}</strong></span><span><small>Runtime</small><strong>{model.runtime}</strong></span><span><small>Serving</small><strong>{model.endpoint}</strong></span><span><small>硬件 / 交付</small><strong>{model.hardware}</strong></span></div><div className="qw-model-capabilities">{model.capabilities.map((item) => <em key={item}>{item}</em>)}</div><div className="qw-model-eval"><span><strong>{model.evaluation?.scenario_pass_rate}%</strong><small>场景通过率</small></span><span><strong>{model.evaluation?.p95_latency_ms} ms</strong><small>P95</small></span><span><strong>{model.evaluation?.cost_per_million_tokens}</strong><small>百万 Token 成本</small></span></div><footer><span><Bot size={13} />{model.linked_agents?.join(" · ") || "未绑定 Agent"}</span><span><Database size={13} />{model.linked_datasets?.join(" · ") || "未绑定数据集"}</span></footer></article>)}</div></Section>;
}

function ConfigurationPanel({ draft, update, updateSystem, addSystem, removeSystem, openChat, onGenerateDataset, onOpenDatasets }) {
  const infrastructure = draft.infrastructure;
  const runtime = draft.runtime;
  return (
    <div className="qw-resource-config-grid">
      <ScenarioTwinBlueprint draft={draft} onChat={() => openChat("scenario", "场景与环境还原", "业务目标、角色、步骤和四类还原度", ["这个场景为什么建议 L2 仿真？", "还缺哪些业务证据？"])} />
      <SubagentPanel draft={draft} onChat={() => openChat("scenario-twin", "场景 Subagent", "Subagent 分工、工具、记忆和安全护栏", ["Agent 为什么这样拆分？", "哪些行为不应该交给 Agent？"])} />
      <SimulationEnvironmentPanel draft={draft} onGenerateDataset={onGenerateDataset} onOpenDatasets={onOpenDatasets} onChat={() => openChat("simulation", "数据源、接口与模拟环境", "模拟方法、接口契约、Agent 设计、数据集和验收规则", ["ERP 模拟器如何映射当前场景？", "模拟数据与真实数据差多少？"])} />
      <Section icon={Workflow} title="场景与系统拆解" description="把用户需求还原为可部署的系统边界、职责和副本策略。" action={<button type="button" className="qw-resource-inline-action" onClick={addSystem}><Plus size={14} />新增系统</button>} onChat={() => openChat("systems", "场景与系统拆解", "业务系统边界、职责、部署方式与副本策略", ["系统边界是否合理？", "哪些系统可以合并？"])}>
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

      <Section icon={Server} title="计算、存储与网络" description="ECS、超融合节点、GPU、磁盘、对象存储和带宽统一配置。" onChat={() => openChat("infrastructure", "计算、存储与网络", "ECS、存储、超融合、GPU 和网络容量", ["这个容量是怎么估算的？", "如何降低基础设施成本？"])}>
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

      <Section icon={BrainCircuit} title="AI 运行时与本体" description="微服务、容器、队列、Agent、模型和推理服务的运行边界。" onChat={() => openChat("runtime", "AI 运行时与本体", "微服务、Agent、推理服务、模型和本体配置", ["模型和推理服务为什么这样选？", "本体还需要哪些实体关系？"])}>
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

      <ModelRegistryPanel draft={draft} onChat={() => openChat("model-registry", "大模型仓库", "线上/线下模型、版本、评测、Serving 与 Agent/数据集绑定", ["什么场景必须使用线下模型？", "模型如何晋级到生产阶段？"])} />

      <Section icon={Gauge} title="SLA、加速与成本约束" description="用可验收指标约束资源选型，所有建议值都需要压测确认。" onChat={() => openChat("sla", "SLA、加速与成本约束", "P95、吞吐、可用性、预算和推理加速要求", ["SLA 是否现实？", "怎样平衡时延和成本？"])}>
        <div className="qw-resource-fields four">
          <Field label="P95 时延" type="number" suffix="ms" value={draft.sla.p95_latency_ms} onChange={(value) => update(["sla", "p95_latency_ms"], value)} />
          <Field label="吞吐" type="number" step="0.1" suffix="RPS" value={draft.sla.throughput_rps} onChange={(value) => update(["sla", "throughput_rps"], value)} />
          <Field label="可用性" value={draft.sla.availability} onChange={(value) => update(["sla", "availability"], value)} />
          <Field label="月成本上限" type="number" suffix="CNY" value={draft.sla.target_monthly_cost_cny} onChange={(value) => update(["sla", "target_monthly_cost_cny"], value)} />
        </div>
        <Field label="加速要求" value={draft.sla.acceleration} onChange={(value) => update(["sla", "acceleration"], value)} hint="例如量化、连续批处理、KV Cache、张量并行或推测解码。" />
      </Section>

      <TokenFactoryValue draft={draft} onChat={() => openChat("token-factory", "Token Factory 方案", "当前负载到 Token Factory 产品形态的建议映射", ["Token Factory 的价值在哪里？", "这个映射需要哪些压测证据？"])} />
    </div>
  );
}

function TopologyPanel({ plan, onUpdateNode, openChat }) {
  const [viewMode, setViewMode] = useState("logical");
  const [selectedNodeId, setSelectedNodeId] = useState(null);
  const projected = useMemo(() => {
    const twin = plan.scenario_twin || DEFAULT_SCENARIO_TWIN;
    const infra = plan.infrastructure;
    const runtime = plan.runtime;
    let sourceNodes;
    let sourceEdges;
    if (viewMode === "deployment") {
      sourceNodes = [
        { id: "deploy-edge", label: "访问入口 · WAF / API Gateway", type: "gateway", position: { x: 300, y: 20 }, config: { deployment: "双可用区入口", resource_binding: `${displayValue(infra.network.bandwidth_mbps, " Mbps")}`, metrics: ["request_rate", "p95_rtt", "error_rate"] } },
        { id: "deploy-zone-a", label: "可用区 A · 主业务集群", type: "zone", position: { x: 70, y: 125 }, config: { deployment: "Kubernetes / AZ-A", resource_binding: `${displayValue(infra.ecs.count)} ECS · ${displayValue(runtime.containers)} 容器`, replicas: Math.ceil((runtime.inference.replicas || 2) / 2), metrics: ["cluster_health", "pod_restarts"] } },
        { id: "deploy-zone-b", label: "可用区 B · 容灾集群", type: "zone", position: { x: 530, y: 125 }, config: { deployment: "Kubernetes / AZ-B", resource_binding: `${displayValue(infra.hyperconverged_nodes.count)} HCI 节点`, replicas: Math.floor((runtime.inference.replicas || 2) / 2), metrics: ["cluster_health", "failover_readiness"] } },
        { id: "deploy-agent-a", label: `Agent Runtime A · ${displayValue(runtime.agents.concurrency)} 并发`, type: "runtime", position: { x: 25, y: 240 }, config: { deployment: "AZ-A / autoscaling", resource_binding: "ECS 工作负载", cpu: infra.ecs.v_cpu, memory_gb: infra.ecs.memory_gb, metrics: ["active_agents", "tool_success_rate", "turn_latency"] } },
        { id: "deploy-agent-b", label: "Agent Runtime B · standby", type: "runtime", position: { x: 485, y: 240 }, config: { deployment: "AZ-B / warm standby", resource_binding: "HCI 工作负载", metrics: ["active_agents", "failover_time"] } },
        { id: "deploy-inference", label: `${runtime.inference.service} · ${displayValue(runtime.inference.replicas)} 副本`, type: "inference", position: { x: 255, y: 340 }, config: { deployment: "Token Factory 推理池", resource_binding: `${displayValue(infra.gpu.count)} × ${infra.gpu.model}`, model_binding: runtime.inference.model, replicas: runtime.inference.replicas, gpu: infra.gpu.count, metrics: ["ttft", "tpot", "tokens_per_second", "gpu_utilization"] } },
        { id: "deploy-storage", label: `数据与对象存储 · ${displayValue(infra.storage.object_storage_gb, " GB")}`, type: "storage", position: { x: 25, y: 455 }, config: { deployment: "跨区复制", resource_binding: `${displayValue(infra.storage.data_disk_gb, " GB")} 数据盘`, metrics: ["capacity_used", "iops", "replication_lag"] } },
        { id: "deploy-model-registry", label: `模型仓库 · ${(plan.model_registry || DEFAULT_MODEL_REGISTRY).models.length} 个版本`, type: "model", position: { x: 255, y: 455 }, config: { deployment: "模型控制平面", model_binding: runtime.inference.model, metrics: ["serving_health", "model_drift", "promotion_status"] } },
        { id: "deploy-observability", label: "统一可观测与审计", type: "telemetry", position: { x: 485, y: 455 }, config: { deployment: "OpenTelemetry / Metrics", resource_binding: "全部拓扑节点", metrics: ["logs", "metrics", "traces", "cost"] } },
      ];
      sourceEdges = [["deploy-edge","deploy-zone-a","主路由"],["deploy-edge","deploy-zone-b","容灾路由"],["deploy-zone-a","deploy-agent-a","调度"],["deploy-zone-b","deploy-agent-b","调度"],["deploy-agent-a","deploy-inference","推理请求"],["deploy-agent-b","deploy-inference","故障切换"],["deploy-storage","deploy-inference","RAG / 数据"],["deploy-model-registry","deploy-inference","模型版本"],["deploy-inference","deploy-observability","遥测"],["deploy-zone-a","deploy-observability","集群指标"],["deploy-zone-b","deploy-observability","集群指标"]].map(([source,target,label],index)=>({id:`deploy-edge-${index}`,source,target,label}));
    } else if (viewMode === "dataflow") {
      sourceNodes = [
        { id: "flow-source", label: "用户数据源 · SANDBOX / 脱敏", type: "source", position: { x: 20, y: 35 }, config: { truth_status: "SANDBOX", dataset_binding: "用户字段字典 / 脱敏样本", metrics: ["freshness", "schema_drift"] } },
        { id: "flow-contract", label: "接口与 Schema 契约", type: "contract", position: { x: 255, y: 35 }, config: { deployment: "Contract Registry", resource_binding: `${twin.systems.reduce((sum,item)=>sum+item.interfaces,0)} 个接口`, metrics: ["contract_pass_rate", "breaking_changes"] } },
        { id: "flow-synthetic", label: `合成数据集 · ${(twin.datasets || []).reduce((sum,item)=>sum+(item.row_count||0),0).toLocaleString()} 行`, type: "synthetic", position: { x: 490, y: 35 }, config: { truth_status: "SYNTHETIC", dataset_binding: twin.datasets?.[0]?.name || "待生成数据集", metrics: ["quality_score", "pii_safety", "scenario_coverage"] } },
        { id: "flow-simulator", label: "业务模拟器 · 状态与异常事件", type: "simulated", position: { x: 135, y: 175 }, config: { deployment: `${twin.systems.length} 个模拟组件`, dataset_binding: twin.datasets?.[0]?.name, metrics: ["event_rate", "state_transition_errors"] } },
        { id: "flow-orchestrator", label: "场景编排 Agent · 上下文组装", type: "runtime", position: { x: 380, y: 175 }, config: { deployment: "Agent Runtime", model_binding: runtime.inference.model, dataset_binding: twin.datasets?.[0]?.name, metrics: ["context_tokens", "tool_success_rate"] } },
        { id: "flow-retrieval", label: "本体 / RAG 检索上下文", type: "storage", position: { x: 20, y: 315 }, config: { deployment: "向量与本体服务", resource_binding: runtime.ontology, metrics: ["retrieval_latency", "recall", "evidence_coverage"] } },
        { id: "flow-inference", label: `${runtime.inference.model} · 推理`, type: "inference", position: { x: 255, y: 315 }, config: { deployment: runtime.inference.service, model_binding: runtime.inference.model, resource_binding: `${displayValue(infra.gpu.count)} GPU`, metrics: ["ttft", "tpot", "tokens_per_second"] } },
        { id: "flow-tools", label: "Mock API / Tool 调用", type: "contract", position: { x: 490, y: 315 }, config: { deployment: "受控 Tool Gateway", resource_binding: `${twin.systems.reduce((sum,item)=>sum+item.interfaces,0)} 个契约`, metrics: ["tool_latency", "tool_error_rate"] } },
        { id: "flow-output", label: "业务响应、证据与回放记录", type: "output", position: { x: 255, y: 465 }, config: { deployment: "结果与证据仓", resource_binding: "对象存储 / Execution", metrics: ["scenario_pass_rate", "evidence_completeness", "cost"] } },
      ];
      sourceEdges = [["flow-source","flow-contract","字段映射"],["flow-contract","flow-synthetic","约束生成"],["flow-synthetic","flow-simulator","样本输入"],["flow-simulator","flow-orchestrator","业务事件"],["flow-orchestrator","flow-retrieval","检索请求"],["flow-retrieval","flow-inference","证据上下文"],["flow-orchestrator","flow-inference","Prompt / Context"],["flow-inference","flow-tools","Tool Call"],["flow-tools","flow-orchestrator","Tool Result"],["flow-inference","flow-output","Token Stream"],["flow-orchestrator","flow-output","决策证据"]].map(([source,target,label],index)=>({id:`flow-edge-${index}`,source,target,label}));
    } else {
      sourceNodes = plan.topology?.nodes?.length ? plan.topology.nodes : [
      { id: "scene", label: plan.scenario?.name || "业务场景", type: "scenario", position: { x: 285, y: 20 } },
      { id: "orchestrator", label: twin.subagents[0]?.name || "场景编排 Agent", type: "agent", position: { x: 285, y: 115 } },
      { id: "finance-agent", label: twin.subagents[1]?.name || "财务审批 Agent", type: "agent", position: { x: 55, y: 220 } },
      { id: "delivery-agent", label: twin.subagents[2]?.name || "交付 Agent", type: "agent", position: { x: 515, y: 220 } },
      { id: "erp-simulator", label: `${twin.systems[0]?.name || "ERP 模拟器"} · SIMULATED`, type: "simulated", position: { x: 25, y: 330 } },
      { id: "crm-sandbox", label: `${twin.systems[1]?.name || "CRM 测试环境"} · SANDBOX`, type: "sandbox", position: { x: 255, y: 330 } },
      { id: "inventory-mock", label: `${twin.systems[2]?.name || "库存 Mock API"} · SIMULATED`, type: "simulated", position: { x: 485, y: 330 } },
      { id: "synthetic-data", label: `${twin.systems[3]?.name || "合成业务数据"} · SYNTHETIC`, type: "synthetic", position: { x: 255, y: 430 } },
      { id: "token-factory", label: "xFusion Token Factory · PLANNED", type: "factory", position: { x: 145, y: 530 } },
      { id: "resource-pool", label: "GPU · HCI · 存储资源池 · PLANNED", type: "resource", position: { x: 405, y: 530 } },
      ];
      sourceEdges = plan.topology?.edges?.length ? plan.topology.edges : [
      ["scene", "orchestrator"], ["orchestrator", "finance-agent"], ["orchestrator", "delivery-agent"],
      ["finance-agent", "erp-simulator"], ["finance-agent", "crm-sandbox"], ["delivery-agent", "erp-simulator"], ["delivery-agent", "inventory-mock"],
      ["erp-simulator", "synthetic-data"], ["crm-sandbox", "synthetic-data"], ["inventory-mock", "synthetic-data"],
      ["synthetic-data", "token-factory"], ["token-factory", "resource-pool"],
      ].map(([source, target], index) => ({ id: `edge-${index}`, source, target }));
    }
    const nodes = sourceNodes.map((node, index) => {
      const { type: visualType, ...nodeData } = node;
      return {
        ...nodeData,
        position: node.position || { x: 70 + (index % 3) * 250, y: 55 + Math.floor(index / 3) * 132 },
        data: { label: node.label, visualType, config: { ...(node.config || {}), ...(plan.topology?.node_configs?.[node.id] || {}) } },
        className: `qw-resource-flow-node type-${visualType || "service"}`,
      };
    });
    return { nodes, edges: sourceEdges.map((edge) => ({ ...edge, type: "smoothstep", animated: viewMode === "dataflow", labelStyle: { fontSize: 9, fill: "#526078" }, style: { strokeWidth: viewMode === "dataflow" ? 1.8 : 1.3 } })) };
  }, [plan, viewMode]);
  const selectedNode = projected.nodes.find((item) => item.id === selectedNodeId) || projected.nodes[0];
  const selectedConfig = selectedNode?.data?.config || {};
  const updateSelected = (key, value) => selectedNode && onUpdateNode(selectedNode.id, key, value);
  const viewMeta = {
    logical: { eyebrow: "SOLUTION BLUEPRINT", title: "业务到算力的端到端架构", note: "逻辑视图 · 展示职责和依赖，不代表资源已经部署", canvas: "业务孪生与资源方案拓扑", detail: "角色、Subagent、模拟环境、推理服务与基础设施的逻辑依赖", legend: [["scenario","业务"],["runtime","Agent"],["simulated","模拟"],["sandbox","Sandbox"],["factory","Token Factory"]] },
    deployment: { eyebrow: "DEPLOYMENT BLUEPRINT", title: "跨可用区部署拓扑", note: "部署规划 · 资源数量实时引用资源配置", canvas: "入口、集群、推理池、存储与可观测落位", detail: "主备可用区、Agent Runtime、推理服务、GPU/HCI、模型仓库与遥测依赖", legend: [["gateway","入口"],["zone","可用区"],["runtime","Runtime"],["inference","推理"],["storage","存储"],["telemetry","遥测"]] },
    dataflow: { eyebrow: "DATA FLOW", title: "场景数据与推理流", note: "动态流向 · 箭头表示数据、事件、上下文或证据的方向", canvas: "从数据源到业务输出的全链路数据流", detail: "字段契约、合成数据、模拟事件、RAG、Prompt、Tool Call、Token 与证据回写", legend: [["source","数据源"],["contract","契约"],["synthetic","合成"],["runtime","Agent"],["inference","推理"],["output","输出"]] },
  }[viewMode];
  return (
    <div className="qw-topology-prototype">
      <div className="qw-prototype-toolbar">
        <div><span className="qw-prototype-label">{viewMeta.eyebrow}</span><strong>{viewMeta.title}</strong><small>{viewMeta.note}</small></div>
        <div className="qw-topology-filters">{[["logical","逻辑架构"],["deployment","部署拓扑"],["dataflow","数据流"]].map(([id,label]) => <button type="button" key={id} className={viewMode === id ? "active" : ""} aria-pressed={viewMode === id} onClick={() => { setViewMode(id); setSelectedNodeId(null); }}>{label}</button>)}</div>
      </div>
      <div className="qw-topology-layout">
        <div className="qw-resource-topology">
          <div className="qw-resource-topology-head"><span><strong>{viewMeta.canvas}</strong><small>{viewMeta.detail}</small></span><div>{viewMeta.legend.map(([tone,label]) => <span key={tone}><i className={tone} />{label}</span>)}</div></div>
          <div className="qw-resource-flow">
            <ReactFlow key={viewMode} nodes={projected.nodes} edges={projected.edges} nodesDraggable={false} nodesConnectable={false} onNodeClick={(_, node) => setSelectedNodeId(node.id)} fitView minZoom={0.35} maxZoom={1.5}>
              <Background color="#dfe4ec" gap={20} size={1} />
              <MiniMap pannable zoomable nodeColor={(node) => node.className?.includes("factory") ? "#6d4aff" : node.className?.includes("scenario") ? "#2f6fed" : node.className?.includes("runtime") ? "#10a8a0" : "#76839a"} />
              <Controls showInteractive={false} />
            </ReactFlow>
          </div>
        </div>
        <aside className="qw-topology-value">
          <div className="qw-topology-view-summary"><span>{viewMeta.eyebrow}</span><strong>{projected.nodes.length} 节点 · {projected.edges.length} 连接</strong><small>{viewMeta.detail}</small></div>
          <section className="qw-node-inspector"><header><span><small>NODE CONFIGURATION</small><strong>{selectedNode?.data.label}</strong></span><ContextChatButton label="问这个节点" onClick={() => openChat("topology-node", selectedNode?.data.label || "拓扑节点", "节点配置、资源/模型/数据绑定与遥测指标", ["这个节点需要哪些资源？", "它如何与前面配置联动？"])} /></header><div className="qw-node-truth"><TruthBadge value={selectedConfig.truth_status || "PLANNED"} /><span>{selectedNode?.data.visualType || "service"}</span></div><div className="qw-node-fields"><Field label="部署方式" value={selectedConfig.deployment} onChange={(value) => updateSelected("deployment", value)} /><Field label="资源绑定" value={selectedConfig.resource_binding} onChange={(value) => updateSelected("resource_binding", value)} hint="例如 GPU 资源池 / ECS 工作负载" /><Field label="模型绑定" value={selectedConfig.model_binding} onChange={(value) => updateSelected("model_binding", value)} /><Field label="数据集绑定" value={selectedConfig.dataset_binding} onChange={(value) => updateSelected("dataset_binding", value)} /><Field label="副本" type="number" value={selectedConfig.replicas} onChange={(value) => updateSelected("replicas", value)} /><Field label="CPU" type="number" value={selectedConfig.cpu} onChange={(value) => updateSelected("cpu", value)} /><Field label="内存" type="number" suffix="GB" value={selectedConfig.memory_gb} onChange={(value) => updateSelected("memory_gb", value)} /><Field label="GPU" type="number" value={selectedConfig.gpu} onChange={(value) => updateSelected("gpu", value)} /><Field label="监控指标" value={(selectedConfig.metrics || []).join(", ")} onChange={(value) => updateSelected("metrics", value.split(",").map((item) => item.trim()).filter(Boolean))} hint="配置后自动进入运行监控矩阵" /></div><p><strong>联动规则：</strong>节点绑定引用资源配置、模型版本与数据集版本；保存后，容量和遥测范围随方案 revision 一起更新。</p></section>
          <span className="qw-token-brand"><Zap size={14} />WHY TOKEN FACTORY</span>
          <h3>让架构更简单，交付更确定</h3>
          <p>Token Factory 位于推理服务与基础资源之间，把多层技术组件收敛为企业级 AI 资源产线。</p>
          <div className="qw-topology-proof">
            {TOKEN_FACTORY_ADVANTAGES.map(({ icon: Icon, title, detail }, index) => <article key={title}><span>0{index + 1}</span><i><Icon size={15} /></i><div><strong>{title}</strong><p>{detail}</p></div></article>)}
          </div>
          <div className="qw-topology-callout"><BadgeCheck size={17} /><span><strong>面向当前方案的推荐理由</strong><small>{displayValue(plan.runtime.agents.concurrency)} Agent 并发 · {displayValue(plan.infrastructure.gpu.count)} 张 GPU · {displayValue(plan.sla.p95_latency_ms, "ms P95")}</small></span></div>
        </aside>
      </div>
    </div>
  );
}

function MonitoringPanel({ monitoring, plan, openChat }) {
  const connected = monitoring.source_status === "LIVE";
  const preview = connected ? monitoring : {
    active_executions: 18, total_executions: 126, average_progress: 76, tokens_used: 2_840_000, estimated_cost_usd: 186.42,
    executions: [
      { id: "exec-product-copilot", workflow_id: "智能产品助理", status: "running", provider: "Token Factory", model: "企业推理服务", progress: 82, tokens_used: 684200, estimated_cost_usd: 41.38 },
      { id: "exec-knowledge-agent", workflow_id: "知识检索 Agent", status: "running", provider: "Token Factory", model: "RAG 推理集群", progress: 64, tokens_used: 512840, estimated_cost_usd: 32.17 },
      { id: "exec-evaluation", workflow_id: "模型评测流水线", status: "queued", provider: "统一推理网关", model: "待调度", progress: 18, tokens_used: 89420, estimated_cost_usd: 5.41 },
    ],
  };
  const utilization = [
    ["GPU 利用率", 78, "12 / 16 卡活跃", "purple"], ["显存占用", 64, "326 / 512 GB", "blue"],
    ["CPU 利用率", 46, "118 / 256 vCPU", "green"], ["对象存储", 38, "7.6 / 20 TB", "amber"],
  ];
  const tokenTrend = [34, 42, 38, 55, 61, 58, 72, 68, 79, 74, 88, 82];
  const scenarioTrace = [
    ["00:00", "客户提交业务申请", "success", "合成客户数据 #C-2048"],
    ["00:03", "场景编排 Agent 创建任务", "success", "拆分为信用、库存和履约三个子任务"],
    ["00:08", "CRM Sandbox 返回客户资料", "success", "接口 GET /customers/C-2048"],
    ["00:12", "财务审批 Agent 完成信用判断", "success", "信用等级 A · 账期 30 天"],
    ["00:17", "ERP 模拟器创建订单", "success", "订单 SO-20260828-091"],
    ["00:21", "库存不足，进入异常分支", "warning", "交付 Agent 正在评估拆单策略"],
  ];
  const inventory = monitoring.resource_inventory?.length ? monitoring.resource_inventory : [
    { key: "ecs", category: "计算", label: "ECS", configured: `${displayValue(plan.infrastructure.ecs.count)} 台 / ${displayValue(plan.infrastructure.ecs.v_cpu)} vCPU / ${displayValue(plan.infrastructure.ecs.memory_gb, " GB")}`, metrics: ["CPU", "内存", "实例健康"] },
    { key: "hci", category: "计算", label: "超融合节点", configured: `${displayValue(plan.infrastructure.hyperconverged_nodes.count)} 节点 · ${plan.infrastructure.hyperconverged_nodes.profile}`, metrics: ["节点健康", "CPU", "存储时延"] },
    { key: "gpu", category: "加速", label: "GPU", configured: `${displayValue(plan.infrastructure.gpu.count)} × ${plan.infrastructure.gpu.model} / ${displayValue(plan.infrastructure.gpu.memory_gb, " GB")}`, metrics: ["利用率", "显存", "温度", "功耗"] },
    { key: "storage", category: "存储", label: "块与对象存储", configured: `系统 ${displayValue(plan.infrastructure.storage.system_disk_gb, " GB")} · 数据 ${displayValue(plan.infrastructure.storage.data_disk_gb, " GB")} · 对象 ${displayValue(plan.infrastructure.storage.object_storage_gb, " GB")}`, metrics: ["容量", "IOPS", "吞吐", "时延"] },
    { key: "network", category: "网络", label: "业务带宽", configured: displayValue(plan.infrastructure.network.bandwidth_mbps, " Mbps"), metrics: ["带宽", "丢包", "P95 RTT"] },
    { key: "runtime", category: "AI Runtime", label: "服务与队列", configured: `${displayValue(plan.runtime.microservices)} 微服务 · ${displayValue(plan.runtime.containers)} 容器 · ${displayValue(plan.runtime.queues)} 队列`, metrics: ["副本健康", "请求率", "队列深度", "错误率"] },
    { key: "agents", category: "AI Runtime", label: "Agent", configured: `${displayValue(plan.runtime.agents.count)} 个 · 并发 ${displayValue(plan.runtime.agents.concurrency)}`, metrics: ["活跃数", "工具成功率", "轮次时延", "Token"] },
    { key: "inference", category: "模型", label: "推理服务", configured: `${plan.runtime.inference.service} · ${plan.runtime.inference.model} · ${displayValue(plan.runtime.inference.replicas)} 副本`, metrics: ["TTFT", "TPOT", "Token/s", "错误率"] },
    { key: "datasets", category: "数据", label: "模拟数据集", configured: `${plan.scenario_twin?.datasets?.length || 0} 个 · ${(plan.scenario_twin?.datasets || []).reduce((sum,item) => sum + (item.row_count || 0),0).toLocaleString()} 行`, metrics: ["质量", "新鲜度", "生成失败"] },
    { key: "models", category: "模型", label: "模型仓库", configured: `${(plan.model_registry || DEFAULT_MODEL_REGISTRY).models.length} 个版本`, metrics: ["场景通过率", "Serving 健康", "漂移", "成本"] },
  ];
  return (
    <div className="qw-resource-monitor">
      <div className="qw-monitor-head"><div><span className="qw-prototype-label">SCENARIO & RESOURCE OBSERVABILITY</span><strong>业务仿真与资源运行态势</strong><small>从业务步骤、Subagent 和模拟接口下钻到 GPU、Token、时延与成本</small></div><span className={`qw-monitor-mode ${connected ? "live" : "demo"}`}><Radio size={13} />{connected ? "LIVE DATA" : "DEMO · 原型数据"}</span></div>
      <div className="qw-simulation-observability">
        <section className="qw-scenario-trace">
          <header><span><strong>业务仿真轨迹</strong><small>场景 #SIM-20260828-014 · L2 状态化仿真</small></span><span className="qw-running-state"><Play size={12} />RUNNING</span></header>
          <ol>{scenarioTrace.map(([time, title, status, detail]) => <li key={time}><time>{time}</time><i className={status}>{status === "success" ? <CircleCheckBig size={13} /> : <Activity size={13} />}</i><div><strong>{title}</strong><small>{detail}</small></div></li>)}</ol>
        </section>
        <section className="qw-fidelity-observability">
          <header><span><strong>场景验证与还原度</strong><small>业务正确性与环境相似度</small></span><FlaskConical size={16} /></header>
          <div className="qw-fidelity-kpis"><span><strong>94%</strong><small>场景成功率</small></span><span><strong>82%</strong><small>综合还原度</small></span><span><strong>12 / 15</strong><small>接口覆盖</small></span><span><strong>7 / 10</strong><small>异常覆盖</small></span></div>
          <div className="qw-fidelity-matrix"><article><span>流程一致性<em>90%</em></span><div><i style={{ width: "90%" }} /></div></article><article><span>数据相似度<em>82%</em></span><div><i style={{ width: "82%" }} /></div></article><article><span>接口契约<em>76%</em></span><div><i style={{ width: "76%" }} /></div></article><article><span>异常行为<em>65%</em></span><div><i style={{ width: "65%" }} /></div></article></div>
          <div className="qw-fidelity-insight"><Sparkles size={14} /><span><strong>AI 观察</strong><small>库存异常分支覆盖不足，建议补充跨仓调拨和延迟交付两个测试场景。</small></span></div>
        </section>
      </div>
      <div className="qw-monitor-section-title"><span><strong>技术资源监控</strong><small>保留原有资源、模型、Token 和成本观测能力</small></span></div>
      <section className="qw-monitor-inventory"><header><span><strong>配置对齐监控矩阵</strong><small>由当前资源方案与任务绑定动态生成，不使用固定监控模板</small></span><ContextChatButton onClick={() => openChat("monitoring", "运行监控", "按资源配置、拓扑绑定和任务执行动态生成的监控矩阵", ["当前方案还缺哪些监控指标？", "怎样设置告警阈值？"])} label="指标建议" /></header><div>{inventory.map((item) => <article key={item.key}><span className="qw-inventory-category">{item.category}</span><div><strong>{item.label}</strong><small>{item.configured}</small></div><p>{item.metrics.map((metric) => <em key={metric}>{metric.replaceAll("_", " ")}</em>)}</p><span className={`qw-inventory-source ${connected ? "live" : "planned"}`}>{connected ? "LIVE" : "PLANNED"}</span></article>)}</div></section>
      <div className="qw-resource-metrics compact">
        <Metric icon={Activity} label="活跃执行" value={preview.active_executions} detail={`${preview.total_executions} 次可观测执行`} tone="green" />
        <Metric icon={Gauge} label="平均进度" value={`${preview.average_progress}%`} detail="任务平均完成度" />
        <Metric icon={BrainCircuit} label="Token 用量" value={preview.tokens_used.toLocaleString()} detail="今日推理累计" tone="purple" />
        <Metric icon={CircleDollarSign} label="推理成本" value={`$${preview.estimated_cost_usd.toFixed(2)}`} detail="当日成本估算" tone="amber" />
      </div>
      <div className="qw-monitor-grid">
        <section className="qw-monitor-card qw-monitor-usage"><header><span><strong>资源池利用率</strong><small>基础资源当前负载</small></span><Server size={16} /></header><div>{utilization.map(([label, value, detail, tone]) => <article key={label}><span><strong>{label}</strong><small>{detail}</small></span><div className={`qw-util-bar ${tone}`}><i style={{ width: `${value}%` }} /></div><em>{value}%</em></article>)}</div></section>
        <section className="qw-monitor-card qw-monitor-token"><header><span><strong>Token 吞吐趋势</strong><small>最近 60 分钟 · Token/min</small></span><BarChart3 size={16} /></header><div className="qw-token-chart">{tokenTrend.map((value, index) => <i key={`${value}-${index}`} style={{ height: `${value}%` }}><span>{value}k</span></i>)}</div><footer><span><strong>82k</strong><small>当前吞吐</small></span><span><strong>1.42s</strong><small>P95 时延</small></span><span><strong>6</strong><small>排队任务</small></span></footer></section>
        <section className="qw-monitor-card qw-monitor-health"><header><span><strong>Token Factory 集群</strong><small>推理资源池健康概览</small></span><BadgeCheck size={16} /></header><div className="qw-health-ring"><div><strong>96</strong><small>健康评分</small></div></div><ul><li><span><Database size={13} />推理节点</span><strong>8 / 8</strong></li><li><span><Timer size={13} />调度延迟</span><strong>38 ms</strong></li><li><span><WalletCards size={13} />容量余量</span><strong>22%</strong></li></ul></section>
      </div>
      {!connected && <div className="qw-monitor-demo-note"><Unplug size={14} /><span><strong>当前展示原型数据</strong><small>接入 canonical Execution、节点遥测与 Token Factory 指标后自动切换为实时监控。</small></span></div>}
      {Boolean(preview.executions.length) && (
        <div className="qw-resource-executions">
          <div className="qw-resource-table-row header"><span>Execution</span><span>状态</span><span>Provider / Model</span><span>进度</span><span>Token</span><span>成本</span></div>
          {preview.executions.map((execution) => <div className="qw-resource-table-row" key={execution.id}>
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

export function AIResourceWorkbench({ resourceData, onRecommend, onSave, onGenerateDataset, onAskContext }) {
  const [activeTab, setActiveTab] = useState("configuration");
  const [configurationView, setConfigurationView] = useState("main");
  const [draft, setDraft] = useState(() => clone(resourceData.plan));
  const [constraints, setConstraints] = useState("");
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [chatContext, setChatContext] = useState(null);
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
  const updateTopologyNode = (nodeId, key, value) => setDraft((current) => {
    const next = clone(current);
    next.topology = next.topology || { nodes: [], edges: [] };
    next.topology.node_configs = next.topology.node_configs || {};
    next.topology.node_configs[nodeId] = { ...(next.topology.node_configs[nodeId] || {}), [key]: value };
    return next;
  });
  const openChat = (id, title, summary, suggestions) => setChatContext({ id, title, summary, suggestions, truth: draft.source_status });
  const generateDataset = async (request) => {
    if (!onGenerateDataset) throw new Error("模拟数据生成接口尚未连接");
    const result = await onGenerateDataset(request);
    if (result?.plan) setDraft(clone(result.plan));
    return result;
  };
  const askContext = onAskContext || (async ({ contextTitle, question }) => ({ answer: `基于「${contextTitle}」当前方案：${question}。原型回答会同时核对场景、真实性标签、容量假设和验收指标；接入 Hermes 后将返回完整依据与修改建议。` }));

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
  const scenarioTwin = draft.scenario_twin || DEFAULT_SCENARIO_TWIN;
  return (
    <section className="qw-resource-workbench">
      <header className="qw-resource-head">
        <div><span className="qw-eyebrow">AI infrastructure planning & operations</span><h2>AI Resource 工作台</h2><p>从用户场景生成 Subagent、模拟数据与接口，再推导系统、算力、模型和 Token Factory 方案。</p></div>
        <div className="qw-resource-actions">
          <span className={`qw-chip ${draft.source_status === "UNCONFIGURED" ? "warning" : ""}`}>{draft.source_status}</span>
          <button type="button" className="qw-button" disabled={Boolean(busy)} onClick={() => runAction("save", () => onSave(draft), "资源配置已保存并生成新 revision。")}>{busy === "save" ? <Activity className="spin" size={14} /> : <Save size={14} />}保存配置</button>
          <button type="button" className="qw-button primary" disabled={Boolean(busy)} onClick={() => runAction("recommend", () => onRecommend(constraints), "Hermes 已生成资源建议，请核对假设后保存。")}>{busy === "recommend" ? <Activity className="spin" size={14} /> : <Sparkles size={14} />}AI 一键推荐</button>
        </div>
      </header>
      <div className="qw-resource-ai-bar"><Sparkles size={15} /><label><span>补充约束（可选）</span><input value={constraints} onChange={(event) => setConstraints(event.target.value)} placeholder="例如：私有化部署、成本优先、P95 < 2 秒、国产 GPU…" /></label><small>推荐结果标记为 AI_PROPOSED，不会自动部署资源。</small></div>
      {(error || notice) && <div className={`qw-resource-feedback ${error ? "error" : "success"}`}>{error ? <Unplug size={15} /> : <Check size={15} />}<span>{error || notice}</span></div>}
      <div className="qw-resource-metrics">
        <Metric icon={Workflow} label="系统 / 环境" value={`${draft.systems.length} + ${scenarioTwin.systems.length}`} detail={`${draft.systems.length} 个业务系统 · ${scenarioTwin.systems.length} 个仿真组件`} />
        <Metric icon={Cpu} label="计算" value={`${displayValue(infra.ecs.count)} ECS`} detail={`${displayValue(infra.ecs.v_cpu)} vCPU · ${displayValue(infra.ecs.memory_gb, "GB")}`} tone="green" />
        <Metric icon={BrainCircuit} label="GPU / 模型" value={`${displayValue(infra.gpu.count)} × ${infra.gpu.model}`} detail={draft.runtime.inference.model} tone="purple" />
        <Metric icon={Gauge} label="SLA" value={displayValue(draft.sla.p95_latency_ms, "ms")} detail={`P95 · ${draft.sla.availability}`} tone="amber" />
        <Metric icon={Zap} label="Token Factory 适配" value="方案推荐" detail={draft.token_factory.product_mapping || "一体化推理资源池"} tone="red" />
      </div>
      <nav className="qw-resource-tabs" aria-label="AI Resource 工作台视图">
        {TABS.map(([id, label, Icon]) => <button type="button" key={id} className={activeTab === id ? "active" : ""} aria-pressed={activeTab === id} onClick={() => { setActiveTab(id); if (id !== "configuration") setConfigurationView("main"); }}><Icon size={15} />{label}</button>)}
      </nav>
      <div className="qw-resource-body">
        {activeTab === "configuration" && configurationView === "main" && <ConfigurationPanel draft={draft} update={update} updateSystem={updateSystem} addSystem={addSystem} removeSystem={removeSystem} openChat={openChat} onGenerateDataset={generateDataset} onOpenDatasets={() => setConfigurationView("datasets")} />}
        {activeTab === "configuration" && configurationView === "datasets" && <DatasetWorkspace draft={draft} onBack={() => setConfigurationView("main")} onGenerateDataset={generateDataset} openChat={openChat} />}
        {activeTab === "topology" && <TopologyPanel plan={draft} onUpdateNode={updateTopologyNode} openChat={openChat} />}
        {activeTab === "monitoring" && <MonitoringPanel monitoring={resourceData.monitoring} plan={draft} openChat={openChat} />}
      </div>
      <footer className="qw-resource-assumptions"><strong>方案假设</strong><div>{draft.assumptions.map((item, index) => <span key={`${item}-${index}`}>{index + 1}. {item}</span>)}</div><small>资源变更仍需人工确认；未连接的监控与 Token Factory 数据不会显示为 LIVE。</small></footer>
      {chatContext && <ResourceContextChat context={chatContext} onClose={() => setChatContext(null)} onAsk={askContext} />}
    </section>
  );
}
