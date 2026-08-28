import { Bot, Check, Send, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { platformApi } from "../../services/platformApi";
import { restoreTaskMessages } from "./taskChatMessages.js";

const visibleAssistantContent = (content) => String(content || "").replace(/```task_backfill\s*\n[\s\S]*?\n```/gi, "").trim();

const executionStep = (event) => {
  if (event.type === "status") {
    const phaseLabels = {
      context: "正在同步卡片上下文与权限",
      boot: "正在启动租户 Hermes",
      reasoning: "Hermes 正在理解任务",
      delegate: event.detail || "正在调用专属 Agent",
    };
    return phaseLabels[event.phase] || event.detail || "AI 正在处理";
  }
  if (event.type === "triage_route") {
    return event.route_class === "PROFESSIONAL_TASK"
      ? "已识别为任务操作，租户技能可以参与"
      : "该问题可直接回答，未启用任务技能";
  }
  if (event.type === "capability_route") {
    const candidates = (event.skill_candidates || []).map((item) => item.name).filter(Boolean);
    if (candidates.length) return `候选技能：${candidates.join("、")}`;
    if ((event.selected_capabilities || []).includes("tenant_skills")) return "租户技能已开放，正在选择是否调用";
    return "本轮未选择技能能力";
  }
  if (event.type === "tool_start") return event.label || `正在调用 ${event.tool || "AI 能力"}`;
  if (event.type === "tool_complete") return `${event.tool || "AI 能力"} 已返回`;
  if (event.type === "agent_route") return `已连接 ${event.agent?.name || event.agent?.id || "Hermes Agent"}`;
  return "";
};

const updateExecution = (message, event) => {
  const detail = executionStep(event);
  if (!detail) return message;
  const execution = message.execution || { startedAt: Date.now(), steps: [] };
  const elapsedMs = Math.max(0, Date.now() - execution.startedAt);
  const signature = `${event.type}:${event.phase || event.tool || event.reason_code || detail}`;
  const previous = execution.steps.at(-1);
  if (previous?.signature === signature) {
    return { ...message, execution: { ...execution, current: detail, elapsedMs } };
  }
  return {
    ...message,
    execution: {
      ...execution,
      current: detail,
      elapsedMs,
      steps: [...execution.steps, { signature, detail, elapsedMs }].slice(-8),
    },
  };
};

const elapsedLabel = (milliseconds) => `${Math.max(0, Math.round((milliseconds || 0) / 1000))}s`;

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
  "current-user": "当前用户", "codex-agent": "Codex Agent",
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

const clarificationChoice = (choice) => typeof choice === "string"
  ? { label: choice, value: choice }
  : { label: choice?.label || choice?.value || "选项", value: choice?.value || choice?.label || "" };

export function TaskChatDrawer({ project, process, task, cardContext, refreshCardContext, onClose }) {
  const [conversation, setConversation] = useState(null);
  const [contextSync, setContextSync] = useState(null);
  const [currentCardContext, setCurrentCardContext] = useState(cardContext);
  const [messages, setMessages] = useState([]);
  const [proposals, setProposals] = useState([]);
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const [proposalBusy, setProposalBusy] = useState("");
  const [clarification, setClarification] = useState(null);
  const [clarificationBusy, setClarificationBusy] = useState(false);
  const [clarificationText, setClarificationText] = useState("");
  const [clarificationSelections, setClarificationSelections] = useState([]);
  const [error, setError] = useState("");
  const [clock, setClock] = useState(Date.now());
  const messagesRef = useRef(null);

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
      let activeConversation = conversation;
      if (refreshCardContext) {
        const refreshed = await refreshCardContext();
        setCurrentCardContext(refreshed.cardContext);
        activeConversation = await platformApi.openTaskConversation({
          project_id: project.id,
          task_id: refreshed.task.id,
          workflow_id: refreshed.task.workflow_id,
          agent_version: "hermes-current",
          card_context: refreshed.cardContext,
        });
        setConversation(activeConversation);
        setContextSync(activeConversation.context_sync || null);
      }
      const startedAt = Date.now();
      setClock(startedAt);
      setMessages((current) => [...current, { id: requestId, role: "user", content: text }, { id: `${requestId}-assistant`, role: "assistant", content: "", pending: true, execution: { startedAt, current: "正在同步卡片增量", elapsedMs: 0, steps: [{ signature: "local:context", detail: "正在同步卡片增量", elapsedMs: 0 }] } }]);
      const finalEvent = await platformApi.streamTaskMessage(activeConversation.id, { question: text, request_id: requestId }, (streamEvent) => {
        setMessages((current) => current.map((message) => message.id === `${requestId}-assistant` ? updateExecution(message, streamEvent) : message));
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
          setClarification({ ...streamEvent, sessionId: activeConversation.session_id, messageId: `${requestId}-assistant` });
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
      const completed = await platformApi.completeTaskBackfillProposal(conversation.id, proposal.id, refreshed.cardContext, applied.applied_evidence);
      setContextSync(completed.context_sync || contextSync);
      setProposals((current) => current.map((item) => item.id === proposal.id ? completed : item));
    } catch (reason) {
      setError(reason.status === 409 ? "卡片已被其他操作更新，请重新生成回填方案。" : reason.message);
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
      <header><div><span className="qw-eyebrow">AI Lab · Task Session</span><h3>{task.title}</h3></div><button type="button" onClick={onClose} aria-label="关闭任务对话"><X size={18} /></button></header>
      <div className="qw-binding"><span>task · {task.id.slice(-8)}</span><span>card v{currentCardContext?.task?.version ?? "-"}</span><span>workflow · {task.workflow_id ? task.workflow_id.slice(-8) : "UNCONNECTED"}</span><span>revision · {process.process_revision}</span>{contextSync && <span>context v{contextSync.revision} · {contextSync.mode === "full" ? "首次全量" : contextSync.mode === "incremental" ? `增量 +${contextSync.changes_count}` : "已是最新"}</span>}</div>
      <div className="qw-chat-messages" ref={messagesRef} aria-live="polite">
        {!messages.length && <div className="qw-chat-empty"><Bot size={22} /><strong>卡片上下文已绑定到租户 Hermes Session</strong><span>首次同步完整卡片，之后每次发言前只同步增量；要求 AI 回填时会先生成方案，确认后才写入。</span></div>}
        {messages.map((message) => {
          const elapsedMs = message.execution ? (message.pending ? clock - message.execution.startedAt : message.execution.elapsedMs) : 0;
          const slowNotice = message.waitingForClarification ? "Hermes 已暂停执行，正在等待你的回答。" : message.pending && elapsedMs >= 20000 ? "模型响应较慢，系统会在首个输出、技能调用或澄清问题前最多等待 60 秒。" : message.pending && elapsedMs >= 8000 ? "模型正在规划，可继续等待。" : "";
          return <article key={message.id} className={`qw-message ${message.role} ${message.failed ? "failed" : ""}`}><small>{message.role === "user" ? "你" : "AI Assistant"}</small>{message.role === "assistant" && message.execution && <details className="qw-execution-trace" open={message.pending || undefined}><summary><span>{message.execution.current || "执行详情"}</span><time>{elapsedLabel(elapsedMs)}</time></summary><ol>{message.execution.steps.map((step) => <li key={`${step.signature}-${step.elapsedMs}`}><time>{elapsedLabel(step.elapsedMs)}</time><span>{step.detail}</span></li>)}</ol>{slowNotice && <p className="qw-execution-slow">{slowNotice}</p>}</details>}<p>{message.role === "assistant" ? visibleAssistantContent(message.content) || (message.waitingForClarification ? "请先回答下方问题，AI 会把结论整理到正确字段。" : message.pending ? "正在处理当前任务…" : "") : message.content}</p></article>;
        })}
        {clarification && <section className="qw-clarification" aria-live="assertive" aria-labelledby="qw-clarification-question">
          <div><small>AI 需要补充信息</small><strong id="qw-clarification-question">{clarification.question}</strong><span>回答后将继续生成字段级回填方案。</span></div>
          {!!clarification.choices?.length && <div className="qw-clarification-choices">{clarification.choices.map(clarificationChoice).map((choice) => {
            const selected = clarificationSelections.includes(choice.value);
            return <button type="button" key={choice.value} aria-pressed={selected} disabled={clarificationBusy} onClick={() => clarification.multi_select ? setClarificationSelections((current) => selected ? current.filter((value) => value !== choice.value) : [...current, choice.value]) : submitClarification(choice.value)}>{selected && <Check size={13} />}{choice.label}</button>;
          })}</div>}
          {clarification.multi_select && <button type="button" className="qw-button primary qw-clarification-submit" disabled={clarificationBusy || !clarificationSelections.length} onClick={() => submitClarification()}>提交所选答案</button>}
          {!clarification.choices?.length && <form onSubmit={(event) => { event.preventDefault(); void submitClarification(); }}><label htmlFor="qw-clarification-response">你的回答</label><textarea id="qw-clarification-response" rows={3} value={clarificationText} onChange={(event) => setClarificationText(event.target.value)} disabled={clarificationBusy} autoFocus /><button type="submit" className="qw-button primary" disabled={clarificationBusy || !clarificationText.trim()}>{clarificationBusy ? "提交中…" : "继续"}</button></form>}
        </section>}
        {proposals.map((proposal) => <section key={proposal.id} className={`qw-backfill-proposal ${proposal.status}`}>
          <div><small>AI 回填方案 · {proposal.status === "proposed" ? "待确认" : proposal.status === "applied" ? "已回填" : "已放弃"}</small><strong>{proposal.summary}</strong></div>
          {Object.keys(proposal.self_changes || {}).length > 0 && <div className="qw-backfill-scope"><span>将写入本卡片</span><BackfillChangeList changes={proposal.self_changes} /></div>}
          {(proposal.routed_items || []).map((item) => <div key={`${item.target_task_id}-${item.content}`} className="qw-backfill-route"><span>投递给 {item.target_title || item.target_task_id}</span><p>{item.content}</p></div>)}
          {proposal.status === "proposed" && <div className="qw-backfill-actions"><button type="button" onClick={() => discardProposal(proposal)} disabled={proposalBusy === proposal.id}>放弃</button><button type="button" className="qw-button primary" onClick={() => applyProposal(proposal)} disabled={proposalBusy === proposal.id}><Check size={14} />确认回填</button></div>}
        </section>)}
      </div>
      {error && <p className="qw-error compact">{error}</p>}
      <form className="qw-chat-form" onSubmit={send}><label className="qw-sr-only" htmlFor="qw-task-chat-question">围绕当前任务提问</label><textarea id="qw-task-chat-question" rows={2} value={question} onChange={(e) => setQuestion(e.target.value)} placeholder={conversation ? "围绕当前任务提问；如需写入，请明确说“生成回填方案”…" : "正在建立服务端绑定…"} disabled={!conversation || busy} /><button className="qw-button primary" aria-label="发送消息" disabled={!conversation || busy || !question.trim()}><Send size={16} /></button></form>
    </aside>
  );
}
