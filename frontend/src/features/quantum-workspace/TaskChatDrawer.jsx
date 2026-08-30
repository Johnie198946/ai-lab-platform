import { Bot, Check, RefreshCw, Send, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { platformApi } from "../../services/platformApi";
import { HermesClarificationCard } from "./HermesClarificationCard";
import { createHermesExecution, HermesExecutionTrace, updateHermesExecution } from "./HermesExecutionTrace";
import { restoreTaskMessages } from "./taskChatMessages.js";

const visibleAssistantContent = (content) => String(content || "").replace(/```task_backfill\s*\n[\s\S]*?\n```/gi, "").trim();

const FIELD_LABELS = {
  title: "议题标题",
  description: "描述",
  status: "状态",
  priority: "优先级",
  labels: "标签",
  assigneeTarget: "负责人",
  developmentContext: "开发上下文",
  startDate: "开始日期",
  dueDate: "截止日期",
  recurrence: "重复",
  appendComment: "评论",
};

const VALUE_LABELS = {
  backlog: "待规划", todo: "待处理", in_progress: "进行中", in_review: "待评审",
  blocked: "已阻塞", done: "已完成", canceled: "已取消",
  none: "无优先级", urgent: "紧急", high: "高", medium: "中", low: "低",
  "current-user": "当前用户", "codex-agent": "AI Lab AI 员工",
};

const RELATION_LABELS = {
  parent: "父议题", sub_issue: "子议题", blocks: "阻塞", blocked_by: "阻塞于", related: "相关议题",
};

const displayValue = (field, value) => {
  if (value == null) return "清空";
  if (VALUE_LABELS[value]) return VALUE_LABELS[value];
  if (field === "labels") return value.length ? value.join("、") : "清空全部标签";
  if (field === "developmentContext") return value.type === "worktree" ? `${value.path}${value.branch ? ` · ${value.branch}` : ""}` : value.branch;
  if (field === "recurrence") return `每 ${value.interval} ${value.unit}`;
  return String(value);
};

function BackfillChangeList({ changes }) {
  const rows = Object.entries(changes || {})
    .filter(([field]) => !["createIssues", "addAttachments", "relationChanges"].includes(field))
    .map(([field, value]) => ({ key: field, label: FIELD_LABELS[field] || field, value: displayValue(field, value) }));
  for (const [index, issue] of (changes?.createIssues || []).entries()) {
    rows.push({ key: `issue-${index}`, label: `新增${RELATION_LABELS[issue.relation] || "议题"}`, value: issue.title });
  }
  for (const [index, attachment] of (changes?.addAttachments || []).entries()) {
    rows.push({ key: `attachment-${index}`, label: "添加附件", value: attachment.filename });
  }
  for (const action of ["remove", "add"]) {
    for (const [index, relation] of (changes?.relationChanges?.[action] || []).entries()) {
      rows.push({ key: `${action}-${index}`, label: `${action === "add" ? "添加" : "移除"}${RELATION_LABELS[relation.type]}`, value: relation.target_task_id });
    }
  }
  return <div className="qw-backfill-fields">{rows.map((row) => <div key={row.key}><span>{row.label}</span><p>{row.value}</p></div>)}</div>;
}

function TaskGovernancePanel({ project, task, onResolved }) {
  const review = (task?.challenge_reviews || []).find((item) => item.status === "OPEN");
  const options = review?.decision_brief?.options || review?.alternatives || [];
  const [selectedOptionId, setSelectedOptionId] = useState(options[0]?.id || "");
  const [rationale, setRationale] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [duplicateCandidates, setDuplicateCandidates] = useState([]);
  const [mergePreview, setMergePreview] = useState(null);
  const [fieldChoices, setFieldChoices] = useState({});
  const [manifestNote, setManifestNote] = useState("");
  const projection = task?.relation_projection;

  useEffect(() => {
    setSelectedOptionId(options[0]?.id || "");
    setRationale("");
    setError("");
  }, [review?.id]);

  const resolveReview = async () => {
    const option = options.find((item) => item.id === selectedOptionId);
    if (!review || !option || !rationale.trim()) return;
    setBusy(true);
    setError("");
    try {
      await platformApi.resolveProjectTaskChallenge(project.id, task.canonical_task_id, review.id, {
        request_id: `ui-${crypto.randomUUID()}`,
        expected_revision: task.process_revision,
        expected_task_revision: task.task_revision,
        selected_option_id: option.id,
        resolution: option.resolution,
        rationale: rationale.trim(),
      });
      await onResolved?.();
    } catch (reason) {
      setError(reason.message || "决策提交失败");
    } finally {
      setBusy(false);
    }
  };

  const checkDuplicates = async () => {
    setBusy(true);
    setError("");
    try {
      const result = await platformApi.checkProjectTaskDuplicates(project.id, {
        task_id: task.canonical_task_id, title: task.title, summary: task.summary || task.title,
        acceptance_criteria: task.acceptance_criteria || [], deliverables: task.deliverables || [],
        assignee_role: task.assignee_role, due_date: task.due_date, labels: task.labels || [], trigger: "CREATE",
      });
      setDuplicateCandidates(result.candidates || []);
    } catch (reason) {
      setError(reason.message || "重复检查失败");
    } finally { setBusy(false); }
  };

  const previewMerge = async (candidate) => {
    setBusy(true);
    setError("");
    try {
      const result = await platformApi.createProjectTaskMergePreview(project.id, task.canonical_task_id, {
        request_id: `ui-${crypto.randomUUID()}`, expected_revision: task.process_revision,
        secondary_task_id: candidate.target_task_id, expected_primary_revision: task.task_revision,
        expected_secondary_revision: candidate.target_task_revision,
      });
      const preview = { ...result.merge, process_revision: result.process_revision };
      setMergePreview(preview);
      setFieldChoices(Object.fromEntries((preview.conflicts || []).map((item) => [item.field, "primary"])));
    } catch (reason) {
      setError(reason.message || "合并预览失败");
    } finally { setBusy(false); }
  };

  const applyMerge = async () => {
    if (!mergePreview || mergePreview.blockers?.length) return;
    setBusy(true);
    setError("");
    try {
      await platformApi.applyProjectTaskMerge(project.id, mergePreview.id, {
        request_id: `ui-${crypto.randomUUID()}`, expected_revision: mergePreview.process_revision,
        field_choices: fieldChoices,
      });
      setMergePreview(null);
      setDuplicateCandidates([]);
      await onResolved?.();
    } catch (reason) {
      setError(reason.message || "合并失败");
    } finally { setBusy(false); }
  };

  const decideManifest = async (decision) => {
    if (task.delivery_manifest?.status !== "READY" || !manifestNote.trim()) return;
    setBusy(true);
    setError("");
    try {
      await platformApi.decideProjectTaskDeliveryManifest(
        project.id, task.canonical_task_id, task.delivery_manifest.id,
        { expected_revision: task.process_revision, decision, note: manifestNote.trim() },
      );
      await onResolved?.();
    } catch (reason) {
      setError(reason.message || "验收决策失败");
    } finally { setBusy(false); }
  };

  if (!review && !projection && !task?.delivery_manifest) return null;
  return (
    <section className="qw-task-governance" aria-label="任务治理">
      <div><strong>治理状态</strong><span>{task.canonical_status || "—"}</span></div>
      {projection && <div><span>关系真源：QWS</span><span>Taskboard 投影：{projection.status === "ALIGNED" ? "一致" : projection.status === "DRIFT" ? "存在漂移" : "待校验"}</span></div>}
      {task.delivery_manifest && <div><span>交付清单</span><span>{task.delivery_manifest.status}</span></div>}
      {task.delivery_manifest?.status === "READY" && <div className="qw-task-decision">
        <textarea value={manifestNote} onChange={(event) => setManifestNote(event.target.value)} placeholder="填写验收意见（必填）" rows={2} disabled={busy} />
        <div><button type="button" onClick={() => decideManifest("REWORK")} disabled={busy || !manifestNote.trim()}>退回返工</button><button type="button" onClick={() => decideManifest("ACCEPT")} disabled={busy || !manifestNote.trim()}>验收通过</button></div>
      </div>}
      <div className="qw-task-duplicate">
        <button type="button" onClick={checkDuplicates} disabled={busy}>检查重复任务</button>
        {duplicateCandidates.map((candidate) => <button type="button" key={candidate.target_task_id} onClick={() => previewMerge(candidate)} disabled={busy}>{candidate.target_title} · {(candidate.score * 100).toFixed(0)}%</button>)}
      </div>
      {mergePreview && <div className="qw-task-decision">
        <strong>字段级合并预览</strong>
        {(mergePreview.conflicts || []).map((conflict) => <label key={conflict.field}>{conflict.field}<select value={fieldChoices[conflict.field] || "primary"} onChange={(event) => setFieldChoices((current) => ({ ...current, [conflict.field]: event.target.value }))}>{conflict.allowed_choices.map((choice) => <option key={choice} value={choice}>{choice === "primary" ? "保留当前任务" : choice === "secondary" ? "使用来源任务" : "合并两边"}</option>)}</select></label>)}
        {mergePreview.blockers?.length > 0 && <p className="qw-error">存在活跃执行租约，暂不能合并。</p>}
        <button type="button" onClick={applyMerge} disabled={busy || mergePreview.blockers?.length}>确认合并</button>
      </div>}
      {review && (
        <div className="qw-task-decision">
          <strong>{review.decision_brief?.question || review.question || "需要你的决策"}</strong>
          <select value={selectedOptionId} onChange={(event) => setSelectedOptionId(event.target.value)} disabled={busy}>
            {options.map((option) => <option key={option.id} value={option.id}>{option.label} · 代价：{option.cost}</option>)}
          </select>
          <textarea value={rationale} onChange={(event) => setRationale(event.target.value)} placeholder="填写决策理由（必填）" rows={2} disabled={busy} />
          <button type="button" onClick={resolveReview} disabled={busy || !selectedOptionId || !rationale.trim()}>{busy ? "提交中…" : "确认决策"}</button>
          {error && <p className="qw-error">{error}</p>}
        </div>
      )}
    </section>
  );
}

export function TaskChatDrawer({ project, process, task, cardContext, refreshCardContext, onClose }) {
  const [conversation, setConversation] = useState(null);
  const [contextSync, setContextSync] = useState(null);
  const [currentCardContext, setCurrentCardContext] = useState(cardContext);
  const [governanceTask, setGovernanceTask] = useState(task);
  const [messages, setMessages] = useState([]);
  const [proposals, setProposals] = useState([]);
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const [proposalBusy, setProposalBusy] = useState("");
  const [clarification, setClarification] = useState(null);
  const [clarificationBusy, setClarificationBusy] = useState(false);
  const [clarificationText, setClarificationText] = useState("");
  const [clarificationSelections, setClarificationSelections] = useState([]);
  const [contextRefreshing, setContextRefreshing] = useState(false);
  const [error, setError] = useState("");
  const [clock, setClock] = useState(Date.now());
  const messagesRef = useRef(null);
  const aiEmployee = conversation?.binding?.ai_employee || null;
  const assistantLabel = aiEmployee
    ? `${aiEmployee.display_name} · AI 员工`
    : "AI Lab AI 员工";

  useEffect(() => {
    let active = true;
    setConversation(null);
    setContextSync(null);
    setCurrentCardContext(cardContext);
    setMessages([]);
    setProposals([]);
    setClarification(null);
    setError("");
    platformApi.openTaskConversation({
      project_id: project.id,
      task_id: task.id,
      workflow_id: task.workflow_id,
      agent_version: "hermes-current",
      card_context: cardContext,
    }).then(async (value) => {
      const [history, backfills] = await Promise.all([
        platformApi.listTaskMessages(value.id),
        platformApi.listTaskBackfillProposals(value.id),
      ]);
      if (active) {
        setConversation(value);
        setContextSync(value.context_sync || null);
        setMessages(restoreTaskMessages(history));
        setProposals(backfills || []);
      }
    }).catch((reason) => active && setError(reason.message));
    return () => { active = false; };
  }, [cardContext, project.id, task.id, task.workflow_id]);

  useEffect(() => {
    messagesRef.current?.scrollTo({ top: messagesRef.current.scrollHeight });
  }, [messages]);

  useEffect(() => {
    if (!busy) return undefined;
    const timer = window.setInterval(() => setClock(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [busy]);

  const send = async (event) => {
    event.preventDefault();
    if (!question.trim() || !conversation || busy) return;
    const text = question.trim();
    const requestId = `qw-chat-${crypto.randomUUID()}`;
    setQuestion("");
    setBusy(true);
    setError("");
    try {
      const activeConversation = conversation;
      const startedAt = Date.now();
      setClock(startedAt);
      setMessages((current) => [...current, { id: requestId, role: "user", content: text }, { id: `${requestId}-assistant`, role: "assistant", content: "", pending: true, execution: createHermesExecution("正在同步卡片增量", startedAt) }]);
      const finalEvent = await platformApi.streamTaskMessage(activeConversation.id, { question: text, request_id: requestId }, (streamEvent) => {
        setMessages((current) => current.map((message) => message.id === `${requestId}-assistant` ? updateHermesExecution(message, streamEvent, { context: "正在同步卡片上下文与权限", reasoning: "Hermes 正在理解任务", professional: "已识别为任务操作，租户技能可以参与" }) : message));
        if (streamEvent.type === "delta" && streamEvent.content) {
          setMessages((current) => current.map((message) => message.id === `${requestId}-assistant` ? { ...message, content: `${message.content}${streamEvent.content}` } : message));
        }
        if (streamEvent.type === "done") {
          setClarification(null);
          setMessages((current) => current.map((message) => message.id === `${requestId}-assistant` ? { ...message, content: streamEvent.answer || message.content, pending: false, execution: { ...message.execution, current: "回答已完成", elapsedMs: Date.now() - message.execution.startedAt } } : message));
        }
        if (streamEvent.type === "error") {
          setClarification(null);
          const detail = streamEvent.detail || streamEvent.message || "Hermes 上游连接失败。";
          setMessages((current) => current.map((message) => message.id === `${requestId}-assistant` ? { ...message, content: detail, pending: false, failed: true } : message));
        }
        if (streamEvent.type === "clarify") {
          setClarification({ ...streamEvent, sessionId: activeConversation.session_id || activeConversation.binding?.session_id, messageId: `${requestId}-assistant` });
          setClarificationText("");
          setClarificationSelections([]);
          setMessages((current) => current.map((message) => message.id === `${requestId}-assistant` ? { ...message, waitingForClarification: true, execution: { ...message.execution, current: "等待你补充信息" } } : message));
        }
        if (streamEvent.type === "clarify_expired") {
          setClarification(null);
          setError("澄清问题已过期，请重新发送任务要求。");
        }
      });
      if (finalEvent?.type === "error") return;
      const persisted = await platformApi.listTaskMessages(activeConversation.id);
      setMessages((current) => {
        const execution = current.find((message) => message.id === `${requestId}-assistant`)?.execution;
        return restoreTaskMessages(persisted).map((message) => message.role === "assistant" && message.request_id === requestId ? { ...message, execution } : message);
      });
      const proposal = await platformApi.materializeTaskBackfillProposal(activeConversation.id, requestId);
      if (proposal) setProposals((current) => [...current.filter((item) => item.id !== proposal.id), proposal]);
    } catch (reason) {
      setError(reason.message);
      setMessages((current) => current.map((message) => message.id === `${requestId}-assistant` ? { ...message, content: "流式连接失败，消息未被冒充为成功。", pending: false, failed: true } : message));
    } finally {
      setBusy(false);
    }
  };

  const refreshContext = async () => {
    if (!refreshCardContext || contextRefreshing || busy) return;
    setContextRefreshing(true);
    setError("");
    try {
      const refreshed = await refreshCardContext();
      const activeConversation = await platformApi.openTaskConversation({
        project_id: project.id,
        task_id: refreshed.task.id,
        workflow_id: refreshed.task.workflow_id,
        agent_version: "hermes-current",
        card_context: refreshed.cardContext,
      });
      setCurrentCardContext(refreshed.cardContext);
      setGovernanceTask(refreshed.task);
      setConversation(activeConversation);
      setContextSync(activeConversation.context_sync || null);
    } catch (reason) {
      setError(reason.message);
    } finally {
      setContextRefreshing(false);
    }
  };

  const submitClarification = async (explicitResponse) => {
    if (!clarification || clarificationBusy) return;
    const response = explicitResponse || clarificationSelections.join("；") || clarificationText.trim();
    if (!response) return;
    setClarificationBusy(true);
    setError("");
    try {
      const result = await platformApi.submitTaskClarification({
        session_id: clarification.sessionId,
        response,
        clarify_id: clarification.clarify_id,
      });
      if (!result?.ok) throw new Error(result?.state === "expired" ? "澄清问题已过期，请重新提问。" : "澄清答案未被 Hermes 接受。");
      const messageId = clarification.messageId;
      setClarification(null);
      setMessages((current) => current.map((message) => message.id === messageId ? { ...message, waitingForClarification: false, execution: { ...message.execution, current: "已收到补充，继续整理回填方案" } } : message));
    } catch (reason) {
      setError(reason.message);
    } finally {
      setClarificationBusy(false);
    }
  };

  const applyProposal = async (proposal) => {
    if (!conversation || proposalBusy || !refreshCardContext) return;
    if (!window.confirm("确认按预览逐项更新本卡片、创建或关联议题及附件，并把超出职责的内容投递给对应卡片 Session？")) return;
    setProposalBusy(proposal.id);
    setError("");
    try {
      const applied = await platformApi.applyTaskBackfillProposal(conversation.id, proposal.id);
      const refreshed = await refreshCardContext();
      setCurrentCardContext(refreshed.cardContext);
      setGovernanceTask(refreshed.task);
      const completed = await platformApi.completeTaskBackfillProposal(conversation.id, proposal.id, refreshed.cardContext, applied.applied_evidence);
      setContextSync(completed.context_sync || contextSync);
      setProposals((current) => current.map((item) => item.id === proposal.id ? completed : item));
    } catch (reason) {
      setError(reason.status === 409
        ? "卡片已被其他操作更新，请重新生成回填方案。"
        : `${reason.message} 请检查后再次点击“确认回填”重试。`);
    } finally {
      setProposalBusy("");
    }
  };

  const discardProposal = async (proposal) => {
    if (!conversation || proposalBusy) return;
    setProposalBusy(proposal.id);
    try {
      const discarded = await platformApi.discardTaskBackfillProposal(conversation.id, proposal.id);
      setProposals((current) => current.map((item) => item.id === proposal.id ? discarded : item));
    } catch (reason) {
      setError(reason.message);
    } finally {
      setProposalBusy("");
    }
  };

  return (
    <aside className="qw-chat-drawer" aria-label={`${task.title} 任务对话`}>
      <header><div><span className="qw-eyebrow">AI Lab · AI 员工 Session</span><h3>{task.title}</h3></div><div className="qw-chat-header-actions"><button type="button" disabled={!refreshCardContext || contextRefreshing || busy} onClick={refreshContext} aria-label="刷新任务上下文" title="仅在卡片内容变化后刷新"><RefreshCw size={16} />{contextRefreshing ? "同步中" : "刷新上下文"}</button><button type="button" onClick={onClose} aria-label="关闭任务对话"><X size={18} /></button></div></header>
      <div className="qw-binding">{aiEmployee && <span>{aiEmployee.display_name} · AI 员工 · {aiEmployee.job_title}</span>}<span>task · {task.id.slice(-8)}</span><span>card v{currentCardContext?.task?.version ?? "-"}</span><span>workflow · {task.workflow_id ? task.workflow_id.slice(-8) : "UNCONNECTED"}</span><span>revision · {process.process_revision}</span>{contextSync && <span>context v{contextSync.revision} · {contextSync.mode === "full" ? "首次全量" : contextSync.mode === "incremental" ? `增量 +${contextSync.changes_count}` : "已是最新"}</span>}</div>
      <TaskGovernancePanel project={project} task={governanceTask} onResolved={refreshContext} />
      <div className="qw-chat-messages" ref={messagesRef} aria-live="polite">
        {!messages.length && <div className="qw-chat-empty"><Bot size={22} /><strong>项目、当前任务和直接依赖已绑定</strong><span>上下文按 revision/hash 留痕；连续交流复用快照，卡片变化后再点“刷新上下文”。要求 AI 回填时会先生成方案，确认后才写入。</span></div>}
        {messages.map((message) => {
          return <article key={message.id} className={`qw-message ${message.role} ${message.failed ? "failed" : ""}`}><small>{message.role === "user" ? "你" : assistantLabel}</small>{message.role === "assistant" && <HermesExecutionTrace execution={message.execution} pending={message.pending} waitingForClarification={message.waitingForClarification} clock={clock} />}<p>{message.role === "assistant" ? visibleAssistantContent(message.content) || (message.waitingForClarification ? "请先回答下方问题，AI 会把结论整理到正确字段。" : message.pending ? "正在处理当前任务…" : "") : message.content}</p></article>;
        })}
        <HermesClarificationCard clarification={clarification} busy={clarificationBusy} responseText={clarificationText} onResponseTextChange={setClarificationText} selections={clarificationSelections} onSelectionsChange={setClarificationSelections} onSubmit={submitClarification} idPrefix="qw-task-clarification" continuationLabel="回答后将继续生成字段级回填方案。" />
        {proposals.map((proposal) => <section key={proposal.id} className={`qw-backfill-proposal ${proposal.status}`}>
          <div><small>AI 回填方案 · {proposal.status === "proposed" ? "待确认" : proposal.status === "applied" ? "已回填" : "已放弃"}</small><strong>{proposal.summary}</strong></div>
          {Object.keys(proposal.self_changes || {}).length > 0 && <div className="qw-backfill-scope"><span>将写入本卡片</span><BackfillChangeList changes={proposal.self_changes} /></div>}
          {(proposal.routed_items || []).map((item) => <div key={`${item.target_task_id}-${item.content}`} className="qw-backfill-route"><span>投递给 {item.target_title || item.target_task_id}</span><p>{item.content}</p></div>)}
          {proposal.status === "proposed" && <div className="qw-backfill-actions"><button type="button" onClick={() => discardProposal(proposal)} disabled={proposalBusy === proposal.id}>放弃</button><button type="button" className="qw-button primary" onClick={() => applyProposal(proposal)} disabled={proposalBusy === proposal.id}><Check size={14} />确认回填</button></div>}
        </section>)}
      </div>
      {error && <p className="qw-error compact" role="alert">{error}</p>}
      <form className="qw-chat-form" onSubmit={send}><label className="qw-sr-only" htmlFor="qw-task-chat-question">围绕当前任务提问</label><textarea id="qw-task-chat-question" rows={2} value={question} onChange={(e) => setQuestion(e.target.value)} placeholder={conversation ? "围绕当前任务提问；如需写入，请明确说“生成回填方案”…" : "正在建立服务端绑定…"} disabled={!conversation || busy} /><button className="qw-button primary" aria-label="发送消息" disabled={!conversation || busy || !question.trim()}><Send size={16} /></button></form>
    </aside>
  );
}
