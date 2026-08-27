import { useEffect, useMemo, useRef, useState } from "react";
import { ReactFlow, applyNodeChanges } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { Check, ChevronDown, GitBranch, LogOut, Play, Plus, RefreshCw } from "lucide-react";
import { useAuth } from "../auth/AuthContext";
import { isShowroomAccount } from "../auth/entryRoute";
import { platformApi } from "../services/platformApi";
import {
  architectSearchWithView,
  architectViewFromSearch,
  architectWorkflowForContext,
  canStartWorkflow,
  customerDemandIdFromSearch,
  pollExecutionUntilTerminal,
  pollForNewPlan,
  projectPlanToCanvas,
  projectPlanToReactFlow,
  projectOfficeProjection,
  showroomSessionIdFromSearch,
  shouldFetchWorkflowPlan,
} from "../architectContract";
import { canonicalPlanToSimLike, simLikeToCanonicalPlan } from "../architectCanvasAdapter";
import ProjectOfficeView from "../features/project-office/ProjectOfficeView";
import "./ArchitectWorkbenchPage.css";

const STATUS_COPY = {
  draft: ["需求输入", "把目标、用户和验收标准讲清楚。"],
  clarifying: ["需求确认", "Hermes 正在补齐影响方案的关键条件。"],
  awaiting_requirement_confirmation: ["需求确认", "确认后才会生成流程，不会自动执行。"],
  planning: ["流程生成", "服务端正在编译已批准的流程合同。"],
  awaiting_approval: ["流程确认", "只读检查角色、交付件和 Gate，再批准。"],
  agent_ready: ["等待执行", "专属 AI 员工已就绪，启动后由 Hermes 真实运行。"],
  ready: ["等待执行", "专属 AI 员工已就绪，启动后由 Hermes 真实运行。"],
  running: ["真实执行", "只展示安全执行摘要、工具、证据和资源。"],
  queued: ["执行排队", "同一命令只会映射到一个 Hermes Run。"],
  awaiting_review: ["成果复核", "先核对证据与 Gate，再决定是否采用。"],
  completed: ["已完成", "成果、证据和资源账单已经归档。"],
  failed: ["需要处理", "执行失败，保留真实错误和已生成证据。"],
};

const listValue = (value) => (Array.isArray(value) ? value : []);

function PlanCanvas({ plan, workflowId, onSaved }) {
  const [simulation, setSimulation] = useState(false);
  const [saveError, setSaveError] = useState("");
  const [saving, setSaving] = useState(false);
  const [historyVersions, setHistoryVersions] = useState([]);
  const [selectedHistoryId, setSelectedHistoryId] = useState("");
  const [rollbackError, setRollbackError] = useState("");
  const [rollingBack, setRollingBack] = useState(false);
  const serverPlan = useMemo(() => projectPlanToCanvas(plan), [plan]);
  const simulationView = useMemo(
    () => canonicalPlanToSimLike(serverPlan),
    [serverPlan],
  );
  const [simulationNodes, setSimulationNodes] = useState(simulationView.nodes);
  useEffect(() => {
    setSimulation(false);
    setSimulationNodes(simulationView.nodes);
  }, [simulationView.nodes]);
  const { nodes: serverNodes, edges: serverEdges } = projectPlanToReactFlow({ dsl: serverPlan });
  const nodes = simulation ? simulationNodes : serverNodes;
  const edges = simulation ? simulationView.edges : serverEdges;
  useEffect(() => {
    if (!workflowId) return undefined;
    let active = true;
    platformApi.listWorkflowPlanVersions(workflowId)
      .then((versions) => {
        if (active) setHistoryVersions(Array.isArray(versions) ? versions : []);
      })
      .catch(() => {
        if (active) setHistoryVersions([]);
      });
    return () => { active = false; };
  }, [workflowId, plan?.id]);
  const saveSimulation = async () => {
    if (!simulation || saving || !workflowId || !plan?.content_hash || !plan?.activation_revision) return;
    setSaving(true);
    setSaveError("");
    try {
      const editedDsl = simLikeToCanonicalPlan({ nodes: simulationNodes, edges: simulationView.edges });
      const nextPlan = await platformApi.patchWorkflowPlan(workflowId, {
        dsl: { ...plan.dsl, ...editedDsl },
        deliverable: plan.deliverable,
        allow_network: plan.allow_network,
        max_tokens: plan.max_tokens,
        knowledge_scope: plan.knowledge_scope || [],
        expected_hash: plan.content_hash,
        expected_revision: plan.activation_revision,
        request_id: `canvas-${globalThis.crypto?.randomUUID?.() || Date.now()}`,
      });
      onSaved?.(nextPlan);
      setSimulation(false);
    } catch (nextError) {
      setSaveError(nextError.message || "保存失败，当前本地编辑仍保留。");
    } finally {
      setSaving(false);
    }
  };
  const rollbackSelected = async () => {
    if (!selectedHistoryId || rollingBack || !workflowId || !plan?.content_hash || !plan?.activation_revision) return;
    setRollingBack(true);
    setRollbackError("");
    try {
      const nextPlan = await platformApi.rollbackWorkflowPlan(workflowId, {
        source_plan_id: selectedHistoryId,
        expected_hash: plan.content_hash,
        expected_revision: plan.activation_revision,
        request_id: `rollback-${globalThis.crypto?.randomUUID?.() || Date.now()}`,
      });
      onSaved?.(nextPlan);
      setSelectedHistoryId("");
    } catch (nextError) {
      setRollbackError(nextError.message || "回滚失败，当前计划保持不变。");
    } finally {
      setRollingBack(false);
    }
  };
  const toggleSimulation = () => {
    setSimulation((current) => !current);
    setSimulationNodes(simulationView.nodes);
  };
  return (
    <div className="plan-canvas" aria-label="server workflow plan canvas">
      <div className="plan-canvas__toolbar">
        <span>{simulation ? "SIMULATION · 本地编辑，不会保存或执行" : "SERVER PLAN · 只读"}</span>
        <button type="button" onClick={toggleSimulation} aria-pressed={simulation}>
          {simulation ? "退出 SIMULATION" : "进入 SIMULATION 编辑"}
        </button>
        {simulation ? <button type="button" onClick={saveSimulation} disabled={saving}>{saving ? "保存中…" : "保存 SIMULATION 编辑"}</button> : null}
        {saveError ? <span role="alert">{saveError}</span> : null}
        {historyVersions.length > 1 ? <>
          <select aria-label="历史 Plan 版本" value={selectedHistoryId} onChange={(event) => setSelectedHistoryId(event.target.value)}>
            <option value="">选择历史版本</option>
            {historyVersions.filter((version) => version.id !== plan?.id).map((version) => <option key={version.id} value={version.id}>v{version.version} · {version.id}</option>)}
          </select>
          <button type="button" onClick={rollbackSelected} disabled={!selectedHistoryId || rollingBack}>{rollingBack ? "回滚中…" : "从历史版本回滚"}</button>
          {rollbackError ? <span role="alert">{rollbackError}</span> : null}
        </> : null}
      </div>
      {nodes.length ? (
        <ReactFlow
          nodes={nodes}
          edges={edges}
          fitView
          nodesDraggable={simulation}
          nodesConnectable={false}
          elementsSelectable={true}
          onNodesChange={(changes) => {
            if (simulation) setSimulationNodes((current) => applyNodeChanges(changes, current));
          }}
          panOnDrag
          zoomOnScroll
        />
      ) : (
        <div className="empty-state"><GitBranch size={18} /> 暂无服务端流程</div>
      )}
    </div>
  );
}

function DetailDrawer({ title, count, children }) {
  return (
    <details className="detail-drawer">
      <summary>{title}<span>{count}</span><ChevronDown size={15} /></summary>
      <div className="detail-drawer__body">{children}</div>
    </details>
  );
}

export default function ArchitectPage() {
  const { isAuthenticated, authSession, logout } = useAuth();
  const defaultArchitectView = isShowroomAccount(authSession?.user) ? "office" : "workbench";
  const [architectView, setArchitectView] = useState(() => architectViewFromSearch(window.location.search, defaultArchitectView));
  const showroomSessionId = useMemo(() => showroomSessionIdFromSearch(window.location.search), []);
  const customerDemandId = useMemo(() => customerDemandIdFromSearch(window.location.search), []);
  const [workflows, setWorkflows] = useState([]);
  const [workflow, setWorkflow] = useState(null);
  const [clarification, setClarification] = useState(null);
  const [plan, setPlan] = useState(null);
  const [execution, setExecution] = useState(null);
  const [executionEvents, setExecutionEvents] = useState([]);
  const [artifacts, setArtifacts] = useState([]);
  const [explainContext, setExplainContext] = useState(null);
  const [evidenceReport, setEvidenceReport] = useState(null);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [connectionState, setConnectionState] = useState("SYNCING");
  const activeWorkflowIdRef = useRef("");

  const planDsl = plan?.dsl || plan || null;
  const messages = clarification?.messages || [];
  const phase = clarification?.session?.phase || "";
  const executionStatus = execution?.status || "";
  const statusKey = executionStatus || phase || workflow?.status || "draft";
  const [stageTitle, stageReason] = STATUS_COPY[statusKey] || ["任务进行中", "按当前服务端状态继续。"];
  const planNodes = listValue(planDsl?.nodes);
  const executionNodes = listValue(execution?.nodes);
  const currentNode = executionNodes.find((node) => node.status === "running") || executionNodes.find((node) => node.status === "pending");
  const awaitingConfirmation = phase === "awaiting_requirement_confirmation";
  const recentEvents = listValue(executionEvents).slice(-6);
  const toolEvents = listValue(executionEvents).filter((event) => ["tool_start", "tool_complete", "skill_load", "agent_spawn"].includes(event.event_type || event.type));
  const tokenTotal = Number(execution?.input_tokens || 0) + Number(execution?.output_tokens || 0) + Number(execution?.reasoning_tokens || 0);
  const officeProjection = useMemo(
    () => projectOfficeProjection({ workflow, plan, execution, events: executionEvents, artifacts, connectionState }),
    [workflow, plan, execution, executionEvents, artifacts, connectionState],
  );

  const switchArchitectView = (view) => {
    const search = architectSearchWithView(window.location.search, view);
    window.history.replaceState(window.history.state, "", `${window.location.pathname}${search}${window.location.hash}`);
    setArchitectView(view);
  };

  const resumeExecution = async (executionId, workflowId) => {
    try {
      const result = await pollExecutionUntilTerminal(executionId, {
        getExecution: platformApi.getExecution,
        getExecutionEvents: platformApi.getExecutionEvents,
        getExecutionArtifacts: platformApi.getExecutionArtifacts,
        onUpdate: ({ execution: nextExecution, events }) => {
          if (activeWorkflowIdRef.current !== workflowId) return;
          setConnectionState("CONNECTED");
          setExecution(nextExecution);
          setExecutionEvents(events);
        },
      });
      if (activeWorkflowIdRef.current !== workflowId) return;
      setConnectionState("CONNECTED");
      setExecution(result.execution);
      setExecutionEvents(result.events);
      setArtifacts(result.artifacts);
    } catch (nextError) {
      if (activeWorkflowIdRef.current === workflowId) {
        setConnectionState("UNCONNECTED");
        setError(nextError.message || "执行状态读取失败");
      }
    }
  };

  const loadWorkflow = async (id) => {
    activeWorkflowIdRef.current = id || "";
    setWorkflow(null);
    setClarification(null);
    setPlan(null);
    setExecution(null);
    setExecutionEvents([]);
    setArtifacts([]);
    setExplainContext(null);
    setEvidenceReport(null);
    setError("");
    if (!id) return;
    setConnectionState("SYNCING");
    setBusy(true);
    try {
      const [workflowData, clarificationData] = await Promise.all([
        platformApi.getWorkflow(id),
        platformApi.getClarification(id),
      ]);
      if (activeWorkflowIdRef.current !== id) return;
      const loaded = workflowData.workflow || workflowData;
      let planData = null;
      if (shouldFetchWorkflowPlan(loaded, clarificationData)) {
        planData = await platformApi.getWorkflowPlan(id).catch((nextError) => nextError?.status === 404 ? null : Promise.reject(nextError));
      }
      setConnectionState("CONNECTED");
      setWorkflow(loaded);
      setClarification(clarificationData);
      setPlan(planData);
      if (!planData && (loaded.status === "planning" || loaded.active_plan_id)) {
        const nextPlan = await pollForNewPlan(id, null, {
          getPlan: platformApi.getWorkflowPlan,
          getLifecycleEvents: platformApi.getLifecycleEvents,
        });
        if (activeWorkflowIdRef.current === id) setPlan(nextPlan);
      }
      const latest = loaded.latest_execution;
      if (latest?.id) {
        const [fullExecution, events, nextArtifacts, nextExplain, nextReport] = await Promise.all([
          platformApi.getExecution(latest.id),
          platformApi.getExecutionEvents(latest.id),
          platformApi.getExecutionArtifacts(latest.id),
          platformApi.getExecutionExplainContext(latest.id).catch(() => null),
          platformApi.getExecutionEvidenceReport(latest.id).catch(() => null),
        ]);
        if (activeWorkflowIdRef.current !== id) return;
        setExecution(fullExecution);
        setExecutionEvents(events);
        setArtifacts(nextArtifacts);
        setExplainContext(nextExplain);
        setEvidenceReport(nextReport);
        if (["queued", "running"].includes(fullExecution.status)) void resumeExecution(fullExecution.id, id);
      }
    } catch (nextError) {
      if (activeWorkflowIdRef.current === id) {
        setConnectionState("UNCONNECTED");
        setError(nextError.message || "无法读取工作台");
      }
    } finally {
      if (activeWorkflowIdRef.current === id) setBusy(false);
    }
  };

  useEffect(() => {
    platformApi.listWorkflows().then((data) => {
      const rows = data.workflows || data || [];
      const architectRows = rows.filter((item) => item.clarification_session_id);
      setWorkflows(architectRows);
      setConnectionState("CONNECTED");
      const selected = architectWorkflowForContext(architectRows, { customerDemandId, showroomSessionId });
      if (selected) loadWorkflow(selected.id);
    }).catch((nextError) => {
      setWorkflows([]);
      setConnectionState("UNCONNECTED");
      setError(nextError.message || "无法读取任务列表");
    });
  }, []);

  const create = async (event) => {
    event.preventDefault();
    if (!draft.trim()) return;
    setBusy(true);
    setError("");
    try {
      const result = await platformApi.createWorkflow({
        title: "客户共创任务",
        description: draft.trim(),
        desired_output: "可审阅业务成果",
        clarification_mode: "dynamic",
        ...(showroomSessionId ? { showroom_session_id: showroomSessionId } : {}),
        ...(customerDemandId ? { customer_demand_id: customerDemandId } : {}),
      });
      const created = result.workflow;
      setWorkflows((current) => [created, ...current.filter((item) => item.id !== created.id)]);
      setDraft("");
      await loadWorkflow(created.id);
    } catch (nextError) {
      setError(nextError.message || "无法创建任务");
    } finally {
      setBusy(false);
    }
  };

  const submitClarification = async (intent = null) => {
    if (!workflow || (!intent && !draft.trim())) return;
    setBusy(true);
    setError("");
    try {
      await platformApi.answerClarification(workflow.id, draft.trim(), intent);
      setDraft("");
      await loadWorkflow(workflow.id);
    } catch (nextError) {
      setError(nextError.status === 409 ? "上一条回复正在处理，请稍候刷新状态。" : (nextError.message || "需求回复失败"));
    } finally {
      setBusy(false);
    }
  };
  const send = async (event) => { event.preventDefault(); await submitClarification(); };

  const approve = async () => {
    setBusy(true);
    try {
      await platformApi.approveWorkflowPlan(workflow.id);
      await loadWorkflow(workflow.id);
    } catch (nextError) {
      setError(nextError.message || "流程批准失败");
    } finally {
      setBusy(false);
    }
  };

  const start = async () => {
    if (!canStartWorkflow(workflow?.status, execution)) return;
    const workflowId = workflow.id;
    setBusy(true);
    setError("");
    try {
      const started = await platformApi.startWorkflow(workflowId);
      setExecution(started);
      await resumeExecution(started.id, workflowId);
    } catch (nextError) {
      setError(nextError.message || "Hermes执行启动失败");
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="architect-page">
      <header className="architect-topbar">
        <div className="brand-lockup"><span className="quantum-mark" /><strong>AI Lab</strong><span>共创工作台</span></div>
        <div className="topbar-actions"><div className="architect-view-toggle" aria-label="Architect 视图"><button type="button" className={architectView === "office" ? "is-active" : ""} aria-pressed={architectView === "office"} onClick={() => switchArchitectView("office")}>Office</button><button type="button" className={architectView === "workbench" ? "is-active" : ""} aria-pressed={architectView === "workbench"} onClick={() => switchArchitectView("workbench")}>Workbench</button></div><span className="connection-state">{isAuthenticated ? "已登录" : "未登录"}</span><span>{authSession?.user?.username || "account"}</span><button type="button" onClick={logout} aria-label="退出"><LogOut size={16} /></button></div>
      </header>

      {architectView === "office" ? <ProjectOfficeView projection={officeProjection} error={error} busy={busy} onSwitchToWorkbench={() => switchArchitectView("workbench")} /> : <div className="workbench-layout">
        <aside className="workbench-nav">
          <button className="new-task" type="button" onClick={() => loadWorkflow("")}><Plus size={16} />新任务</button>
          <label htmlFor="workflow-select">当前任务</label>
          <select id="workflow-select" disabled={busy} value={workflow?.id || ""} onChange={(event) => loadWorkflow(event.target.value)}>
            <option value="">未命名任务</option>
            {workflows.map((item) => <option key={item.id} value={item.id}>{item.title}</option>)}
          </select>
          <ol className="stage-list">
            {["需求确认", "流程与 AI 员工", "真实执行", "成果复核"].map((label, index) => <li className={index <= (["draft", "clarifying"].includes(statusKey) ? 0 : plan ? execution ? 3 : 1 : 0) ? "is-active" : ""} key={label}><span>{index + 1}</span>{label}</li>)}
          </ol>
        </aside>

        <section className="workbench-main">
          {showroomSessionId && <div className="context-strip"><span>已续接来访上下文</span><code>{showroomSessionId}</code></div>}
          {customerDemandId && <div className="context-strip"><span>已续接确认需求</span><code>{customerDemandId}</code></div>}
          <div className="focus-heading"><div><span className="eyebrow">当前步骤</span><h1>{stageTitle}</h1><p>{stageReason}</p></div><span className={`status-chip status-chip--${executionStatus || workflow?.status || "draft"}`}>{busy ? "处理中" : executionStatus || workflow?.status || "待开始"}</span></div>
          {error && <div className="error-banner">{error}</div>}

          {!plan && !execution && (
            <section className="focus-card">
              {workflow && <div className="goal-summary"><span>客户目标</span><p>{workflow.description}</p></div>}
              <div className="conversation-list">
                {messages.slice(-4).map((message) => <div className={`conversation-row conversation-row--${message.role}`} key={message.id}><span>{message.role === "assistant" ? "Hermes" : "你"}</span><p>{message.content}</p></div>)}
              </div>
              <form onSubmit={workflow ? send : create} className="primary-composer">
                <label htmlFor="architect-response">{workflow ? "补充关键信息" : "你希望解决什么问题？"}</label>
                <textarea id="architect-response" value={draft} onChange={(event) => setDraft(event.target.value)} placeholder="说清目标即可，Hermes 会自然追问缺失条件。" />
                {awaitingConfirmation ? <div className="composer-actions"><button className="primary-action" disabled={busy} type="button" onClick={() => submitClarification("confirm")}><Check size={16} />确认并生成流程</button><button className="secondary-action" disabled={busy} type="button" onClick={() => submitClarification("revise")}>继续修改</button></div> : <button className="primary-action" disabled={busy || !draft.trim()} type="submit"><Check size={16} />{workflow ? "提交回复" : "开始澄清"}</button>}
              </form>
            </section>
          )}

          {plan && !execution && (
            <section className="focus-card">
              <div className="process-summary"><div><span>推荐流程</span><h2>{planDsl?.name || "服务端流程"}</h2><p>{planDsl?.process_contract_id ? `已绑定合同 ${planDsl.process_contract_id}` : "服务端安全计划"}</p></div><span className="truth-badge">{planDsl?.process_contract_digest ? "CONTRACT" : "PLAN"}</span></div>
              <div className="node-list">{planNodes.map((node, index) => <article className={node.parameters?.execution_enabled ? "node-card node-card--live" : "node-card"} key={node.id}><span className="node-index">{String(index + 1).padStart(2, "0")}</span><div><strong>{node.name}</strong><p>{listValue(node.parameters?.role_ids).join(" · ") || node.parameters?.agent_id}</p><small>{node.parameters?.decision_gate || "无自动决策"}</small></div><span>{node.parameters?.execution_enabled ? "可执行" : "参考"}</span></article>)}</div>
              <details className="plan-detail"><summary>查看完整流程图与通过标准<ChevronDown size={16} /></summary><PlanCanvas plan={plan} workflowId={workflow?.id} onSaved={(nextPlan) => setPlan(nextPlan)} /></details>
              <div className="approval-row"><p>批准只允许合同中已激活的节点执行。</p><button className="primary-action" type="button" disabled={busy || workflow?.status !== "awaiting_approval"} onClick={approve}><Check size={16} />批准并构建 AI 员工</button>{canStartWorkflow(workflow?.status, execution) && <button className="primary-action" type="button" disabled={busy} onClick={start}><Play size={16} />启动真实执行</button>}</div>
            </section>
          )}

          {execution && (
            <section className="focus-card">
              <div className="execution-focus"><span>当前任务</span><h2>{currentNode?.name || (executionStatus === "awaiting_review" ? "成果等待复核" : "Hermes 执行")}</h2><p>{currentNode?.agent_id ? `AI 员工：${currentNode.agent_id}` : "由 Hermes 唯一运行时执行"}</p><progress max="100" value={execution.progress || 0} /></div>
              <div className="event-list">{recentEvents.map((event, index) => <div key={event.id || event.event_id || index}><span className="event-dot" /><div><strong>{event.message || event.event_type}</strong><small>{event.payload?.category || event.event_type}</small></div></div>)}</div>
              {artifacts[0] && <article className="latest-output"><span>当前输出</span><h3>{artifacts[0].title || "Hermes成果"}</h3><pre>{artifacts[0].content || artifacts[0].preview || ""}</pre></article>}
            </section>
          )}

          {(plan || execution) && <div className="detail-stack">
            <DetailDrawer title="证据" count={recentEvents.length}>{recentEvents.length ? recentEvents.map((event, index) => <p key={event.id || index}>{event.message || event.event_type}</p>) : <p>尚无运行证据。</p>}</DetailDrawer>
            <DetailDrawer title="工具与 Skill" count={toolEvents.length}>{toolEvents.length ? toolEvents.map((event, index) => <p key={event.id || index}>{event.payload?.tool || event.event_type} · {event.payload?.status || "done"}</p>) : <p>尚未调用工具。</p>}</DetailDrawer>
            <DetailDrawer title="工件" count={artifacts.length}>{artifacts.length ? artifacts.map((artifact) => <p key={artifact.id}>{artifact.title}</p>) : <p>尚无工件。</p>}</DetailDrawer>
            <DetailDrawer title="Evidence-bound 报告" count={evidenceReport?.claims?.length || 0}>{evidenceReport ? <div className="evidence-report"><strong>结论与证据</strong>{evidenceReport.claims.map((claim) => <p key={claim.claim_id}><span className={`claim-status claim-status--${claim.status.toLowerCase()}`}>{claim.status}</span>{claim.statement}</p>)}<strong>Token Factory 建议</strong><p>{evidenceReport.token_factory_recommendation?.recommendation}</p><small>{evidenceReport.token_factory_recommendation?.status}</small></div> : <p>执行后生成确定性报告。</p>}</DetailDrawer>
            <DetailDrawer title="Token 与资源" count={tokenTotal}><dl><div><dt>输入</dt><dd>{execution?.input_tokens || 0}</dd></div><div><dt>输出</dt><dd>{execution?.output_tokens || 0}</dd></div><div><dt>推理</dt><dd>{execution?.reasoning_tokens || 0}</dd></div><div><dt>估算费用</dt><dd>${Number(execution?.estimated_cost_usd || 0).toFixed(4)}</dd></div></dl></DetailDrawer>
          </div>}
        </section>

        <aside className="explain-panel"><span className="eyebrow">解释 AI</span><h2>为什么是这一步？</h2><p>{explainContext?.why_this_step || stageReason}</p>{explainContext && <small>Snapshot {explainContext.snapshot_id.slice(0, 10)}</small>}<div><strong>系统不会做什么</strong><ul><li>不展示隐藏思维链</li><li>不绕过人工批准</li><li>不把参考流程标成 LIVE</li></ul></div><button type="button" onClick={() => workflow && loadWorkflow(workflow.id)} disabled={busy}><RefreshCw size={15} />刷新真实状态</button></aside>
      </div>}
    </main>
  );
}
