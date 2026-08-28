import { Bot, Send, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { platformApi } from "../../services/platformApi";
import { restoreTaskMessages } from "./taskChatMessages.js";

export function TaskChatDrawer({ project, process, task, cardContext, onClose }) {
  const [conversation, setConversation] = useState(null);
  const [contextSync, setContextSync] = useState(null);
  const [messages, setMessages] = useState([]);
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const messagesRef = useRef(null);

  useEffect(() => {
    let active = true;
    setConversation(null);
    setContextSync(null);
    setMessages([]);
    setError("");
    platformApi.openTaskConversation({
      project_id: project.id,
      task_id: task.id,
      workflow_id: task.workflow_id,
      agent_version: "hermes-current",
      card_context: cardContext,
    }).then(async (value) => {
      const history = await platformApi.listTaskMessages(value.id);
      if (active) {
        setConversation(value);
        setContextSync(value.context_sync || null);
        setMessages(restoreTaskMessages(history));
      }
    }).catch((reason) => active && setError(reason.message));
    return () => { active = false; };
  }, [cardContext, project.id, task.id, task.workflow_id]);

  useEffect(() => {
    messagesRef.current?.scrollTo({ top: messagesRef.current.scrollHeight });
  }, [messages]);

  const send = async (event) => {
    event.preventDefault();
    if (!question.trim() || !conversation || busy) return;
    const text = question.trim();
    const requestId = `qw-chat-${crypto.randomUUID()}`;
    setQuestion("");
    setBusy(true);
    setError("");
    setMessages((current) => [...current, { id: requestId, role: "user", content: text }, { id: `${requestId}-assistant`, role: "assistant", content: "", pending: true }]);
    try {
      const finalEvent = await platformApi.streamTaskMessage(conversation.id, { question: text, request_id: requestId }, (streamEvent) => {
        if (streamEvent.type === "delta" && streamEvent.content) {
          setMessages((current) => current.map((message) => message.id === `${requestId}-assistant` ? { ...message, content: `${message.content}${streamEvent.content}` } : message));
        }
        if (streamEvent.type === "done") {
          setMessages((current) => current.map((message) => message.id === `${requestId}-assistant` ? { ...message, content: streamEvent.answer || message.content, pending: false } : message));
        }
        if (streamEvent.type === "error") {
          const detail = streamEvent.detail || streamEvent.message || "Hermes 上游连接失败。";
          setMessages((current) => current.map((message) => message.id === `${requestId}-assistant` ? { ...message, content: detail, pending: false, failed: true } : message));
        }
      });
      if (finalEvent?.type === "error") return;
      const persisted = await platformApi.listTaskMessages(conversation.id);
      setMessages(restoreTaskMessages(persisted));
    } catch (reason) {
      setError(reason.message);
      setMessages((current) => current.map((message) => message.id === `${requestId}-assistant` ? { ...message, content: "流式连接失败，消息未被冒充为成功。", pending: false, failed: true } : message));
    } finally {
      setBusy(false);
    }
  };

  return (
    <aside className="qw-chat-drawer" aria-label={`${task.title} 任务对话`}>
      <header><div><span className="qw-eyebrow">AI Lab · Task Session</span><h3>{task.title}</h3></div><button type="button" onClick={onClose} aria-label="关闭任务对话"><X size={18} /></button></header>
      <div className="qw-binding"><span>task · {task.id.slice(-8)}</span><span>workflow · {task.workflow_id ? task.workflow_id.slice(-8) : "UNCONNECTED"}</span><span>revision · {process.process_revision}</span>{contextSync && <span>context v{contextSync.revision} · {contextSync.mode === "full" ? "首次全量" : contextSync.mode === "incremental" ? `增量 +${contextSync.changes_count}` : "已是最新"}</span>}</div>
      <div className="qw-chat-messages" ref={messagesRef} aria-live="polite">
        {!messages.length && <div className="qw-chat-empty"><Bot size={22} /><strong>卡片上下文已绑定到租户 Hermes Session</strong><span>首次同步完整卡片，后续仅传递增量；AI 只读，不会在前端创建或修改任务。</span></div>}
        {messages.map((message) => <article key={message.id} className={`qw-message ${message.role} ${message.failed ? "failed" : ""}`}><small>{message.role === "user" ? "你" : "AI Assistant"}</small><p>{message.content || (message.pending ? "正在读取真实任务上下文…" : "")}</p></article>)}
      </div>
      {error && <p className="qw-error compact">{error}</p>}
      <form className="qw-chat-form" onSubmit={send}><label className="qw-sr-only" htmlFor="qw-task-chat-question">围绕当前任务提问</label><textarea id="qw-task-chat-question" rows={2} value={question} onChange={(e) => setQuestion(e.target.value)} placeholder={conversation ? "围绕当前任务提问…" : "正在建立服务端绑定…"} disabled={!conversation || busy} /><button className="qw-button primary" aria-label="发送消息" disabled={!conversation || busy || !question.trim()}><Send size={16} /></button></form>
    </aside>
  );
}
