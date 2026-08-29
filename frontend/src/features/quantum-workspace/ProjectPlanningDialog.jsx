import { Bot, Send, Sparkles, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { platformApi } from "../../services/platformApi";
import { HermesClarificationCard } from "./HermesClarificationCard";

const planningContext = (project) => ({
  schema_version: 1,
  project: { id: project.id, name: project.name, business_goal: project.goal, desired_outputs: project.desired_outputs || [] },
  task: {
    dashi_task_id: "project-intake",
    qws_task_id: "project-intake",
    title: "项目需求收敛与派发",
    descriptions: [{ source: "project_goal", content: project.goal }],
    status: "in_progress",
    assignee: { id: "main_agent", name: "Hermes main_agent", type: "agent" },
    qws: { binding_kind: "project_planning", stage_id: "project-planning", deliverables: project.desired_outputs || [] },
  },
});

const visibleAnswer = (content = "") => content.replace(/```project_blueprint[\s\S]*?```/gi, "").trim();

export function ProjectPlanningDialog({ template, initialProject, onClose, onChanged }) {
  const [project, setProject] = useState(initialProject || null);
  const [name, setName] = useState(initialProject?.name || "");
  const [goal, setGoal] = useState(initialProject?.goal || "");
  const [conversation, setConversation] = useState(null);
  const [messages, setMessages] = useState([]);
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [blueprintRequestId, setBlueprintRequestId] = useState("");
  const [clarification, setClarification] = useState(null);
  const [clarificationBusy, setClarificationBusy] = useState(false);
  const [clarificationText, setClarificationText] = useState("");
  const [clarificationSelections, setClarificationSelections] = useState([]);
  const messagesRef = useRef(null);

  useEffect(() => {
    if (!project) return undefined;
    let active = true;
    platformApi.openTaskConversation({ project_id: project.id, task_id: "project-intake", workflow_id: null, agent_version: "hermes-project-planning-v1", card_context: planningContext(project) })
      .then(async (value) => {
        const history = await platformApi.listTaskMessages(value.id);
        if (!active) return;
        const visibleHistory = history.filter((item) => item.role !== "system");
        setConversation(value);
        setMessages(visibleHistory);
        const latest = [...history].reverse().find((item) => item.role === "assistant" && /```project_blueprint/i.test(item.content));
        setBlueprintRequestId(latest?.request_id || "");
        if (!history.length) {
          void runStream(value, {
            text: "Assess the project context supplied by the application.",
            requestId: `project-intake-${project.id}`,
            trigger: "project_created",
            showUser: false,
          });
        }
      }).catch((reason) => active && setError(reason.message));
    return () => { active = false; };
  }, [project?.id]);

  useEffect(() => { messagesRef.current?.scrollTo({ top: messagesRef.current.scrollHeight }); }, [messages]);

  const create = async (event) => {
    event.preventDefault(); setBusy(true); setError("");
    try {
      const result = await platformApi.instantiateProject(template.id, { request_id: `ui-project-${crypto.randomUUID()}`, name, goal, desired_outputs: template.deliverables, inputs: {}, truth_mode: "PLANNED", resource_overrides: {} });
      setProject({ id: result.project_id, name, goal, desired_outputs: template.deliverables, process_revision: 0 });
      await onChanged?.();
    } catch (reason) { setError(reason.message); } finally { setBusy(false); }
  };

  const runStream = async (activeConversation, { text, requestId, trigger = "user", showUser = true }) => {
    setBusy(true); setError(""); setClarification(null);
    setMessages((current) => [...current, ...(showUser ? [{ id: requestId, request_id: requestId, role: "user", content: text }] : []), { id: `${requestId}-assistant`, request_id: requestId, role: "assistant", content: "", pending: true }]);
    try {
      await platformApi.streamTaskMessage(activeConversation.id, { question: text, request_id: requestId, trigger }, (eventValue) => {
        if (eventValue.type === "delta" && eventValue.content) setMessages((current) => current.map((item) => item.id === `${requestId}-assistant` ? { ...item, content: `${item.content}${eventValue.content}` } : item));
        if (eventValue.type === "done") {
          const answer = eventValue.answer || "";
          setClarification(null);
          setMessages((current) => current.map((item) => item.id === `${requestId}-assistant` ? { ...item, content: answer || item.content, pending: false, waitingForClarification: false } : item));
          if (/```project_blueprint/i.test(answer)) setBlueprintRequestId(requestId);
        }
        if (eventValue.type === "clarify") {
          setClarification({ ...eventValue, sessionId: activeConversation.session_id || activeConversation.binding?.session_id, messageId: `${requestId}-assistant` });
          setClarificationText("");
          setClarificationSelections([]);
          setMessages((current) => current.map((item) => item.id === `${requestId}-assistant` ? { ...item, waitingForClarification: true } : item));
        }
        if (eventValue.type === "clarify_expired") {
          setClarification(null);
          setError("澄清问题已过期，请重新发送需求。");
        }
      });
    } catch (reason) {
      setError(reason.message);
      setMessages((current) => current.map((item) => item.id === `${requestId}-assistant` ? { ...item, pending: false, failed: true, content: item.content || "Hermes 连接失败" } : item));
    } finally { setBusy(false); }
  };

  const send = async (event, forcedQuestion = "") => {
    event?.preventDefault();
    const text = forcedQuestion || question.trim();
    if (!text || !conversation || busy) return;
    setQuestion("");
    await runStream(conversation, { text, requestId: `project-plan-${crypto.randomUUID()}` });
  };

  const submitClarification = async (explicitResponse) => {
    if (!clarification || clarificationBusy) return;
    const response = explicitResponse || clarificationSelections.join("；") || clarificationText.trim();
    if (!response) return;
    setClarificationBusy(true); setError("");
    try {
      const result = await platformApi.submitTaskClarification({ session_id: clarification.sessionId, response, clarify_id: clarification.clarify_id });
      if (!result?.ok) throw new Error(result?.state === "expired" ? "澄清问题已过期，请重新发送需求。" : "澄清答案未被 Hermes 接受。");
      const messageId = clarification.messageId;
      setClarification(null);
      setMessages((current) => current.map((item) => item.id === messageId ? { ...item, waitingForClarification: false } : item));
    } catch (reason) { setError(reason.message); }
    finally { setClarificationBusy(false); }
  };

  const dispatch = async () => {
    if (!blueprintRequestId || !conversation || busy) return;
    if (!window.confirm("确认按当前蓝图一次性建立动态流程、任务卡片、AI 员工、甘特数据和项目文档？")) return;
    setBusy(true); setError("");
    try {
      await platformApi.dispatchProjectBlueprint(project.id, { conversation_id: conversation.id, assistant_request_id: blueprintRequestId, expected_revision: project.process_revision || 0 });
      await onChanged?.();
      window.location.assign(`/projects/${project.id}/taskboard`);
    } catch (reason) { setError(reason.message); setBusy(false); }
  };

  return <div className="qw-modal qw-planning-modal" role="dialog" aria-modal="true" aria-labelledby="project-planning-title"><section className="qw-planning-card">
    <header><div><span className="qw-eyebrow">Hermes · Project planning session</span><h2 id="project-planning-title">{project ? project.name : "创建项目"}</h2></div><button type="button" onClick={onClose} aria-label="关闭"><X size={18} /></button></header>
    {!project ? <form className="qw-planning-seed" onSubmit={create}><div><Sparkles size={20} /><strong>先给 Hermes 一个起点</strong><p>创建草稿后进入持续对话，流程节点不会由前端写死。</p></div><label>项目名称<input value={name} onChange={(event) => setName(event.target.value)} required maxLength={160} autoFocus /></label><label>初始业务目标<textarea value={goal} onChange={(event) => setGoal(event.target.value)} required rows={5} maxLength={4000} /></label>{error && <p className="qw-error" role="alert">{error}</p>}<button className="qw-button primary wide" disabled={busy}>{busy ? "创建会话中…" : "创建并开始需求收敛"}</button></form> : <>
      <div className="qw-planning-context"><span>草稿项目</span><span>Hermes main_agent</span><span>revision {project.process_revision || 0}</span><span>{blueprintRequestId ? "蓝图待确认" : "需求收敛中"}</span></div>
      <div className="qw-planning-messages" ref={messagesRef} aria-live="polite">{!messages.length && <div className="qw-chat-empty"><Bot size={24} /><strong>正在把项目名称与描述交给 Hermes</strong><span>Hermes 会先判断信息是否足够；不足时直接提出一个关键问题，足够时生成可确认蓝图。</span></div>}{messages.map((message) => <article key={message.id} className={`qw-message ${message.role} ${message.failed ? "failed" : ""}`}><small>{message.role === "user" ? "你" : "Hermes · AI Lab"}</small><p>{message.role === "assistant" ? visibleAnswer(message.content) || (message.waitingForClarification ? "请回答下方问题，Hermes 会继续评估。" : message.pending ? "正在检查需求完整度…" : "蓝图已生成，请确认派发。") : message.content}</p></article>)}<HermesClarificationCard clarification={clarification} busy={clarificationBusy} responseText={clarificationText} onResponseTextChange={setClarificationText} selections={clarificationSelections} onSelectionsChange={setClarificationSelections} onSubmit={submitClarification} idPrefix="qw-project-clarification" continuationLabel="回答后，Hermes 会继续检查需求；信息足够时自动生成蓝图。" /></div>
      {error && <p className="qw-error compact" role="alert">{error}</p>}
      <form className="qw-planning-composer" onSubmit={send}><label className="qw-sr-only" htmlFor="project-planning-question">项目需求</label><textarea id="project-planning-question" rows={3} value={question} onChange={(event) => setQuestion(event.target.value)} placeholder={clarification ? "请先回答上方澄清问题…" : "补充目标、范围、角色、日期、验收或依赖…"} disabled={!conversation || busy || !!clarification} /><button className="qw-button primary" aria-label="发送" disabled={!conversation || busy || !!clarification || !question.trim()}><Send size={16} /></button></form>
      <footer><button type="button" className="qw-button subtle" disabled={!conversation || busy} onClick={() => send(null, "请检查目前仍缺少哪些关键信息；若信息已足够，请生成可供我确认派发的完整项目蓝图。")}>检查并生成蓝图</button><button type="button" className="qw-button primary" disabled={!blueprintRequestId || busy} onClick={dispatch}>{busy ? "正在派发…" : "确认并派发项目"}</button></footer>
    </>}
  </section></div>;
}
