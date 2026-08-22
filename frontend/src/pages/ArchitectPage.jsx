import { useEffect, useMemo, useRef, useState } from "react";
import { ReactFlow } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { ArrowUpRight, Check, GitBranch, Lock, MessageSquare, RefreshCw } from "lucide-react";
import { useAuth } from "../auth/AuthContext";
import { platformApi } from "../services/platformApi";
import { assertRevisionAllowed, canStartWorkflow, diffPlanVersions, hasResultData, pollExecutionUntilTerminal, pollForNewPlan, projectPlanToCanvas, projectPlanToReactFlow, projectResultViews } from "../architectContract";
import "./ArchitectPage.css";

const truthLabel = (value) => value || "UNCONNECTED";

function PlanCanvas({ plan }) {
  const serverPlan = projectPlanToCanvas(plan);
  const { nodes, edges } = projectPlanToReactFlow({ dsl: serverPlan });
  return (
    <div className="architect-canvas" aria-label="server workflow plan canvas">
      <div className="architect-canvas__meta"><span>SERVER PLAN</span><span>{plan?.version ? `v${plan.version}` : "UNCONNECTED"}</span></div>
      {nodes.length ? <div style={{ height: "calc(100% - 24px)" }}><ReactFlow nodes={nodes} edges={edges} fitView nodesDraggable={false} nodesConnectable={false} elementsSelectable={true} panOnDrag zoomOnScroll /></div> : <div className="architect-empty"><GitBranch size={20} /><strong>No server plan yet</strong><span>UNCONNECTED · The canvas will populate after clarification and planning.</span></div>}
    </div>
  );
}

function ResultArea({ workflow, clarification, execution, executionEvents, artifacts }) {
  const views = projectResultViews({ requirement: clarification?.session?.confirmed_spec || null, evidence: executionEvents?.length ? executionEvents : execution?.nodes, gate: execution?.status === "awaiting_review" ? execution : null, artifact: artifacts?.[0] });
  return <aside className="architect-results" aria-label="results and evidence">
    <div className="architect-section-heading"><span>结果与证据</span><span className="truth-pill">{truthLabel(execution?.truth || "UNCONNECTED")}</span></div>
    {views.map((view) => <section className="result-card" key={view.type}><div className="result-card__heading"><span>{view.type === "requirement" ? "Requirement confirmation" : view.type === "evidence" ? "Evidence table" : view.type === "gate" ? "Decision gate" : "Artifact / result"}</span><ArrowUpRight size={15} /></div>{hasResultData(view.data) ? <pre>{JSON.stringify(view.data, null, 2)}</pre> : <p className="result-empty">UNCONNECTED · No server data available yet.</p>}</section>)}
    {clarification?.session?.phase && <p className="architect-footnote">Session: {clarification.session.phase}</p>}
  </aside>;
}

export default function ArchitectPage() {
  const { authSession, logout } = useAuth();
  const [workflows, setWorkflows] = useState([]);
  const [workflow, setWorkflow] = useState(null);
  const [clarification, setClarification] = useState(null);
  const [plan, setPlan] = useState(null);
  const [previousPlan, setPreviousPlan] = useState(null);
  const [execution, setExecution] = useState(null);
  const [executionEvents, setExecutionEvents] = useState([]);
  const [artifacts, setArtifacts] = useState([]);
  const [draft, setDraft] = useState("");
  const [revision, setRevision] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const activeWorkflowIdRef = useRef("");

  const resetWorkspace = () => {
    setWorkflow(null);
    setClarification(null);
    setPlan(null);
    setPreviousPlan(null);
    setExecution(null);
    setExecutionEvents([]);
    setArtifacts([]);
    setDraft("");
    setRevision("");
    setError("");
  };

  const resumePlan = async (workflowId) => {
    try {
      const nextPlan = await pollForNewPlan(workflowId, null, {
        getPlan: platformApi.getWorkflowPlan,
        getLifecycleEvents: platformApi.getLifecycleEvents,
      });
      if (activeWorkflowIdRef.current !== workflowId) return;
      setPlan(nextPlan);
      const refreshed = await platformApi.getWorkflow(workflowId);
      if (activeWorkflowIdRef.current === workflowId) setWorkflow(refreshed.workflow || refreshed);
    } catch (resumeError) {
      if (activeWorkflowIdRef.current === workflowId) setError(resumeError.message || "方案恢复失败");
    }
  };

  const resumeExecution = async (executionId, workflowId) => {
    try {
      const result = await pollExecutionUntilTerminal(executionId, {
        getExecution: platformApi.getExecution,
        getExecutionEvents: platformApi.getExecutionEvents,
        getExecutionArtifacts: platformApi.getExecutionArtifacts,
        onUpdate: ({ execution: nextExecution, events }) => {
          if (activeWorkflowIdRef.current !== workflowId) return;
          setExecution(nextExecution);
          setExecutionEvents(events);
        },
      });
      if (activeWorkflowIdRef.current !== workflowId) return;
      setExecution(result.execution);
      setExecutionEvents(result.events);
      setArtifacts(result.artifacts);
    } catch (resumeError) {
      if (activeWorkflowIdRef.current === workflowId) setError(resumeError.message || "执行恢复失败");
    }
  };

  const loadWorkflow = async (id) => {
    activeWorkflowIdRef.current = id || "";
    resetWorkspace();
    if (!id) return;
    setBusy(true);
    try {
      const planPromise = platformApi.getWorkflowPlan(id).catch((planError) => {
        if (planError?.status === 404) return null;
        throw planError;
      });
      const [nextWorkflow, nextClarification, nextPlan] = await Promise.all([
        platformApi.getWorkflow(id),
        platformApi.getClarification(id),
        planPromise,
      ]);
      if (activeWorkflowIdRef.current !== id) return;
      const loadedWorkflow = nextWorkflow.workflow || nextWorkflow;
      setWorkflow(loadedWorkflow);
      setClarification(nextClarification);
      setPlan(nextPlan);
      const latest = loadedWorkflow.latest_execution || null;
      if (latest) {
        const [fullExecution, events, nextArtifacts] = await Promise.all([
          platformApi.getExecution(latest.id),
          platformApi.getExecutionEvents(latest.id),
          platformApi.getExecutionArtifacts(latest.id),
        ]);
        if (activeWorkflowIdRef.current !== id) return;
        setExecution(fullExecution);
        setExecutionEvents(events);
        setArtifacts(nextArtifacts);
        if (["queued", "running"].includes(fullExecution.status)) void resumeExecution(fullExecution.id, id);
      }
      if (loadedWorkflow.status === "planning" && !nextPlan) void resumePlan(id);
    } catch (loadError) {
      if (activeWorkflowIdRef.current === id) setError(loadError.message || "无法连接服务端");
    } finally {
      if (activeWorkflowIdRef.current === id) setBusy(false);
    }
  };

  useEffect(() => { platformApi.listWorkflows().then((data) => { const rows = data.workflows || data || []; const architectRows = rows.filter((item) => item.clarification_session_id); setWorkflows(architectRows); if (architectRows[0]) loadWorkflow(architectRows[0].id); }).catch(() => setWorkflows([])); }, []);
  const messages = clarification?.messages || [];
  const latestPrompt = [...messages].reverse().find((item) => item.role === "assistant");
  const awaitingConfirmation = clarification?.session?.phase === "awaiting_requirement_confirmation";
  const diff = useMemo(() => previousPlan && plan ? diffPlanVersions(previousPlan, plan) : null, [previousPlan, plan]);

  const submitClarification = async (intent = null) => {
    if ((!intent && !draft.trim()) || !workflow) return;
    setBusy(true);
    setError("");
    try {
      await platformApi.answerClarification(workflow.id, draft.trim(), intent);
      setDraft("");
      const [nextWorkflow, nextClarification] = await Promise.all([
        platformApi.getWorkflow(workflow.id),
        platformApi.getClarification(workflow.id),
      ]);
      const refreshedWorkflow = nextWorkflow.workflow || nextWorkflow;
      setWorkflow(refreshedWorkflow);
      setClarification(nextClarification);
      if (refreshedWorkflow.status === "planning") {
        const firstPlan = await pollForNewPlan(workflow.id, null, {
          getPlan: platformApi.getWorkflowPlan,
          getLifecycleEvents: platformApi.getLifecycleEvents,
        });
        setPlan(firstPlan);
        await loadWorkflow(workflow.id);
      } else if (refreshedWorkflow.status === "awaiting_approval") {
        setPlan(await platformApi.getWorkflowPlan(workflow.id));
      }
    } catch (sendError) {
      setError(sendError.message || "澄清回复未完成");
    } finally {
      setBusy(false);
    }
  };
  const send = async (event) => { event.preventDefault(); await submitClarification(); };
  const retryClarification = async () => { if (!workflow || !["needs_attention", "clarifying_pending"].includes(workflow.status)) return; setBusy(true); setError(""); try { await platformApi.reopenClarification(workflow.id); await loadWorkflow(workflow.id); } catch (retryError) { setError(retryError.message || "澄清恢复失败"); } finally { setBusy(false); } };
  const revise = async (event) => { event.preventDefault(); if (!revision.trim() || !workflow) return; try { assertRevisionAllowed(execution); setBusy(true); setError(""); const oldPlan = plan; await platformApi.reviseWorkflow(workflow.id, revision.trim()); const nextPlan = await pollForNewPlan(workflow.id, oldPlan, { getPlan: platformApi.getWorkflowPlan, getLifecycleEvents: platformApi.getLifecycleEvents }); setPreviousPlan(oldPlan); setPlan(nextPlan); await loadWorkflow(workflow.id); setRevision(""); } catch (revisionError) { setError(revisionError.message || "方案修订未完成"); } finally { setBusy(false); } };
  const create = async (event) => { event.preventDefault(); if (!draft.trim()) return; setBusy(true); try { const result = await platformApi.createWorkflow({ title: "架构工作台任务", description: draft.trim(), desired_output: "服务端可审阅结果", clarification_mode: "dynamic" }); const createdWorkflow = result.workflow; setWorkflows((current) => [createdWorkflow, ...current.filter((item) => item.id !== createdWorkflow.id)]); setDraft(""); await loadWorkflow(createdWorkflow.id); } catch (createError) { setError(createError.message || "无法创建任务"); } finally { setBusy(false); } };
  const approve = async () => { if (!workflow || workflow.status !== "awaiting_approval") return; setBusy(true); try { await platformApi.approveWorkflowPlan(workflow.id); await loadWorkflow(workflow.id); } catch (approveError) { setError(approveError.message || "方案批准失败"); } finally { setBusy(false); } };
  const start = async () => { if (!workflow || !canStartWorkflow(workflow.status, execution)) return; const workflowId = workflow.id; setBusy(true); try { const started = await platformApi.startWorkflow(workflowId); const result = await pollExecutionUntilTerminal(started.id, { getExecution: platformApi.getExecution, getExecutionEvents: platformApi.getExecutionEvents, getExecutionArtifacts: platformApi.getExecutionArtifacts, onUpdate: ({ execution: nextExecution, events }) => { if (activeWorkflowIdRef.current !== workflowId) return; setExecution(nextExecution); setExecutionEvents(events); } }); if (activeWorkflowIdRef.current !== workflowId) return; setExecution(result.execution); setExecutionEvents(result.events); setArtifacts(result.artifacts); const refreshed = await platformApi.getWorkflow(workflowId); if (activeWorkflowIdRef.current === workflowId) setWorkflow(refreshed.workflow || refreshed); } catch (startError) { if (activeWorkflowIdRef.current === workflowId) setError(startError.message || "执行状态刷新失败"); } finally { if (activeWorkflowIdRef.current === workflowId) setBusy(false); } };

  return <main className="architect-page"><header className="architect-header"><div><div className="architect-kicker"><span className="quantum-mark" /> 架构工作台</div><h1>从需求到可审阅方案</h1><p>澄清约束，核对服务端计划，再批准真实执行。</p></div><div className="architect-header__actions"><span>{authSession?.user?.username || "account"}</span><button onClick={logout}>退出</button></div></header>
    <div className="architect-toolbar"><div className="workflow-picker"><label htmlFor="workflow-select">Workspace</label><select id="workflow-select" disabled={busy} value={workflow?.id || ""} onChange={(event) => loadWorkflow(event.target.value)}><option value="">+ 新建工作流</option>{workflows.map((item) => <option key={item.id} value={item.id}>{item.title}</option>)}</select></div><span className="truth-pill"><span className="status-dot" /> SERVER DATA · {workflow?.status || "UNCONNECTED"}</span></div>
    <div className="architect-grid"><section className="architect-conversation"><div className="architect-section-heading"><span>需求澄清</span><MessageSquare size={17} /></div><div className="conversation-copy"><span className="step-index">01</span><h2>还缺哪些条件？</h2><p>{workflow?.description || "先写下目标、用户和关键约束。"}</p></div><div className="message-stack">{messages.map((message) => <div className={`message message--${message.role}`} key={message.id}><span>{message.role === "assistant" ? "Hermes" : "你"}</span><p>{message.content || "UNCONNECTED · 服务端未返回问题。"}</p></div>)}{!messages.length && <div className="architect-empty"><Lock size={18} /><span>UNCONNECTED · 尚未选择服务端会话。</span></div>}</div><form onSubmit={workflow ? send : create} className="architect-composer"><label htmlFor="architect-response">回复</label><textarea id="architect-response" value={draft} onChange={(event) => setDraft(event.target.value)} placeholder={latestPrompt?.content || "补充目标、约束或验收证据…"} />{awaitingConfirmation ? <div><button disabled={busy} type="button" onClick={() => submitClarification("confirm")}><Check size={16} /> 确认并生成流程</button><button disabled={busy} type="button" onClick={() => submitClarification("revise")}>继续修改</button></div> : <button disabled={busy || ["needs_attention", "clarifying_pending"].includes(workflow?.status) || !draft.trim()} type="submit"><Check size={16} /> {workflow ? "提交回复" : "开始澄清"}</button>}</form>{["needs_attention", "clarifying_pending"].includes(workflow?.status) && <button className="retry-clarification" type="button" disabled={busy} onClick={retryClarification}>重新连接大架构师</button>}<form onSubmit={revise} className="revision-form"><label htmlFor="architect-revision">方案修订</label><div><input id="architect-revision" value={revision} onChange={(event) => setRevision(event.target.value)} placeholder="例如：交付前增加人工复核" /><button disabled={busy || !revision.trim() || ["queued", "running"].includes(execution?.status)} type="submit"><RefreshCw size={15} /> 请求修订</button></div></form></section><section className="architect-plan"><div className="architect-section-heading"><span>服务端计划</span><span className="canvas-note">只读 · 节点与连线来自服务端</span></div><PlanCanvas plan={plan} />{diff && <div className="change-set"><strong>变更集 · v{previousPlan.version} → v{plan.version}</strong><span>新增 {diff.added.length} · 删除 {diff.removed.length} · 修改 {diff.changed.length}</span><small>{diff.impact}</small></div>}<div className="plan-actions"><button disabled={busy || workflow?.status !== "awaiting_approval"} onClick={approve}>批准方案</button><button disabled={busy || !canStartWorkflow(workflow?.status, execution)} onClick={start}>开始执行</button></div></section><ResultArea workflow={workflow} clarification={clarification} execution={execution} executionEvents={executionEvents} artifacts={artifacts} /></div>{error && <p className="architect-error" role="alert">{error}</p>}</main>;
}
