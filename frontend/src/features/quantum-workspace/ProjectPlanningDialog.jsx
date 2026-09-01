import { Bot, Send, Sparkles, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import { platformApi } from "../../services/platformApi";
import { HermesClarificationCard } from "./HermesClarificationCard";
import { createHermesExecution, HermesExecutionTrace, updateHermesExecution } from "./HermesExecutionTrace";
import { ProjectBlueprintReview } from "./ProjectBlueprintReview";
import { ProjectBlueprintProtocol } from "./ProjectBlueprintProtocol";
import { extractProjectBlueprint, extractProjectBlueprintProtocol, projectPlanningNaturalReply, projectPlanningVisibleAnswer } from "./projectBlueprintPresentation.js";

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

export function ProjectPlanningDialog({ template, initialProject, onClose, onChanged }) {
  const [project, setProject] = useState(initialProject || null);
  const [name, setName] = useState(initialProject?.name || "");
  const [goal, setGoal] = useState(initialProject?.goal || "");
  const [conversation, setConversation] = useState(null);
  const [messages, setMessages] = useState([]);
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [planningNotice, setPlanningNotice] = useState("");
  const [blueprintRequestId, setBlueprintRequestId] = useState("");
  const [resumeNeeded, setResumeNeeded] = useState(false);
  const [clarification, setClarification] = useState(null);
  const [clarificationBusy, setClarificationBusy] = useState(false);
  const [clarificationText, setClarificationText] = useState("");
  const [clarificationSelections, setClarificationSelections] = useState([]);
  const [clock, setClock] = useState(Date.now());
  const messagesRef = useRef(null);
  const blueprintMessages = messages.filter((item) => item.role === "assistant" && extractProjectBlueprint(item.content));
  const latestBlueprintMessage = blueprintMessages.at(-1);
  const latestBlueprintVersion = blueprintMessages.length;
  const [reviewBlueprint, setReviewBlueprint] = useState(null);

  useEffect(() => {
    const generated = latestBlueprintMessage ? extractProjectBlueprint(latestBlueprintMessage.content) : null;
    setReviewBlueprint(generated ? structuredClone(generated) : null);
  }, [latestBlueprintMessage?.id]);

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
        const latest = [...history].reverse().find((item) => item.role === "assistant" && extractProjectBlueprint(item.content));
        setBlueprintRequestId(latest?.request_id || "");
        setResumeNeeded(history.length > 0 && !latest);
        if (!history.length) {
          void runStream(value, {
            text: "基于该项目背景，能收敛并完成全部项目字段时直接生成；否则持续向用户澄清至需求收敛。",
            requestId: `project-intake-${project.id}`,
            trigger: "project_created",
            showUser: false,
          });
        }
      }).catch((reason) => active && setError(reason.message));
    return () => { active = false; };
  }, [project?.id]);

  useEffect(() => {
    if (!messages.some((item) => item.role === "assistant" && item.pending)) return;
    messagesRef.current?.scrollTo({ top: messagesRef.current.scrollHeight });
  }, [messages]);

  useEffect(() => {
    if (!busy) return undefined;
    const timer = window.setInterval(() => setClock(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [busy]);

  const create = async (event) => {
    event.preventDefault(); setBusy(true); setError("");
    try {
      const result = await platformApi.instantiateProject(template.id, { request_id: `ui-project-${crypto.randomUUID()}`, name, goal, desired_outputs: template.deliverables, inputs: {}, truth_mode: "PLANNED", resource_overrides: {} });
      setProject({ id: result.project_id, name, goal, desired_outputs: template.deliverables, process_revision: 0 });
      await onChanged?.();
    } catch (reason) { setError(reason.message); } finally { setBusy(false); }
  };

  const runStream = async (activeConversation, { text, requestId, trigger = "user", showUser = true }) => {
    setBusy(true); setError(""); setPlanningNotice(""); setClarification(null); setResumeNeeded(false);
    const startedAt = Date.now();
    setClock(startedAt);
    setMessages((current) => [...current, ...(showUser ? [{ id: requestId, request_id: requestId, role: "user", content: text }] : []), { id: `${requestId}-assistant`, request_id: requestId, role: "assistant", content: "", pending: true, execution: createHermesExecution("正在把项目背景交给 Hermes", startedAt) }]);
    try {
      await platformApi.streamTaskMessage(activeConversation.id, { question: text, request_id: requestId, trigger }, (eventValue) => {
        setMessages((current) => current.map((item) => item.id === `${requestId}-assistant` ? updateHermesExecution(item, eventValue, { professional: "已识别为项目规划任务，正在匹配可用技能", generating: "Hermes 正在生成澄清问题或项目蓝图" }) : item));
        if (eventValue.type === "delta" && eventValue.content) setMessages((current) => current.map((item) => item.id === `${requestId}-assistant` ? { ...item, content: `${item.content}${eventValue.content}` } : item));
        if (eventValue.type === "done") {
          const answer = eventValue.answer || "";
          setClarification(null);
          setPlanningNotice("");
          setMessages((current) => current.map((item) => item.id === `${requestId}-assistant` ? { ...item, content: answer || item.content, pending: false, waitingForClarification: false, execution: { ...item.execution, current: "本轮处理完成", elapsedMs: Date.now() - item.execution.startedAt } } : item));
          if (extractProjectBlueprint(answer)) setBlueprintRequestId(requestId);
          else setResumeNeeded(true);
        }
        if (eventValue.type === "planning_incomplete") {
          const detail = eventValue.detail || "Hermes 本轮没有返回可验证的完整项目蓝图。";
          const answer = eventValue.answer || "";
          setClarification(null);
          setBlueprintRequestId("");
          setResumeNeeded(true);
          setPlanningNotice(detail);
          setMessages((current) => current.map((item) => item.id === `${requestId}-assistant` ? {
            ...item,
            content: answer || item.content || detail,
            pending: false,
            incomplete: true,
            waitingForClarification: false,
            execution: { ...item.execution, current: "蓝图未通过完整性校验", elapsedMs: Date.now() - item.execution.startedAt },
          } : item));
        }
        if (eventValue.type === "error") {
          const detail = eventValue.detail || eventValue.message || "Hermes 上游连接失败。";
          setMessages((current) => current.map((item) => item.id === `${requestId}-assistant` ? { ...item, content: detail, pending: false, failed: true, execution: { ...item.execution, current: "本轮处理失败", elapsedMs: Date.now() - item.execution.startedAt } } : item));
          setError(`${detail} 请重试本轮 AI 生成。`);
          setResumeNeeded(true);
        }
        if (eventValue.type === "clarify") {
          setClarification({ ...eventValue, sessionId: activeConversation.session_id || activeConversation.binding?.session_id, messageId: `${requestId}-assistant` });
          setClarificationText("");
          setClarificationSelections([]);
          setMessages((current) => current.map((item) => item.id === `${requestId}-assistant` ? { ...item, waitingForClarification: true, execution: { ...item.execution, current: "等待你补充关键信息" } } : item));
        }
        if (eventValue.type === "clarify_expired") {
          setClarification(null);
          setError("澄清问题已过期，请重新发送需求。");
        }
      });
    } catch (reason) {
      setError(reason.message);
      setResumeNeeded(true);
      setMessages((current) => current.map((item) => item.id === `${requestId}-assistant` ? { ...item, pending: false, failed: true, content: item.content || "Hermes 连接失败" } : item));
    } finally { setBusy(false); }
  };

  const send = async (event, forcedQuestion = "") => {
    event?.preventDefault();
    const text = forcedQuestion || question.trim();
    if (!text || !conversation || busy) return;
    setQuestion("");
    if (latestBlueprintVersion) setBlueprintRequestId("");
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
      setMessages((current) => current.map((item) => item.id === messageId ? { ...item, waitingForClarification: false, execution: { ...item.execution, current: "已收到补充，Hermes 继续收敛需求" } } : item));
    } catch (reason) { setError(reason.message); }
    finally { setClarificationBusy(false); }
  };

  const dispatch = async () => {
    if (!blueprintRequestId || !conversation || busy) return;
    if (!window.confirm("确认派发？系统将严格按你在当前页面保存后的需求确认单建立任务、角色、AI 员工、排期和项目文档，不会回用修改前的 AI 旧稿。")) return;
    setBusy(true); setError("");
    try {
      await platformApi.dispatchProjectBlueprint(project.id, { conversation_id: conversation.id, assistant_request_id: blueprintRequestId, expected_revision: project.process_revision || 0, blueprint: reviewBlueprint });
      await onChanged?.();
      window.location.assign(`/projects/${project.id}/taskboard`);
    } catch (reason) { setError(reason.message); setBusy(false); }
  };

  return <div className="qw-modal qw-planning-modal" role="dialog" aria-modal="true" aria-labelledby="project-planning-title"><section className="qw-planning-card">
    <header><div><span className="qw-eyebrow">Hermes · Project planning session</span><h2 id="project-planning-title">{project ? project.name : "创建项目"}</h2></div><button type="button" onClick={onClose} aria-label="关闭"><X size={18} /></button></header>
    {!project ? <form className="qw-planning-seed" onSubmit={create}><div><Sparkles size={20} /><strong>先给 Hermes 一个起点</strong><p>创建草稿后进入持续对话，流程节点不会由前端写死。</p></div><label>项目名称<input value={name} onChange={(event) => setName(event.target.value)} required maxLength={160} autoFocus /></label><label>初始业务目标<textarea value={goal} onChange={(event) => setGoal(event.target.value)} required rows={5} maxLength={4000} /></label>{error && <p className="qw-error" role="alert">{error}</p>}<button className="qw-button primary wide" disabled={busy}>{busy ? "创建会话中…" : "创建并开始需求收敛"}</button></form> : <>
      <div className="qw-planning-context"><span>草稿项目</span><span>Hermes main_agent</span><span>revision {project.process_revision || 0}</span><span>{blueprintRequestId ? `收敛单 v${latestBlueprintVersion} 待确认` : "需求收敛中"}</span></div>
      <div className="qw-planning-messages" ref={messagesRef} aria-live="polite">{!messages.length && <div className="qw-chat-empty"><Bot size={24} /><strong>{resumeNeeded ? "上次 AI 生成尚未完成" : "正在把项目名称与描述交给 Hermes"}</strong><span>{resumeNeeded ? "点击下方“继续 AI 生成”，Hermes 会沿用本 Session 的项目背景继续收敛。" : "Hermes 会先判断信息是否足够；不足时直接提出一个关键问题，足够时生成可确认蓝图。"}</span></div>}{messages.map((message) => {
        const blueprint = message.role === "assistant" ? extractProjectBlueprint(message.content) : null;
        const blueprintIndex = blueprint ? blueprintMessages.findIndex((item) => item.id === message.id) : -1;
        const protocol = message.role === "assistant" ? extractProjectBlueprintProtocol(message.content) : null;
        const visibleAnswer = message.role === "assistant"
          ? (blueprint ? projectPlanningNaturalReply(message.content) : projectPlanningVisibleAnswer(message.content, { pending: message.pending }))
          : message.content;
        const renderedAnswer = visibleAnswer || (message.waitingForClarification ? "请回答下方问题，Hermes 会继续评估。" : message.pending ? "正在检查需求完整度…" : message.failed ? "本轮未完成，请按提示重试。" : message.incomplete ? "本轮没有形成可验证蓝图，请补充信息或重试。" : "蓝图已生成，请确认派发。");
        const isCurrentBlueprint = message.id === latestBlueprintMessage?.id;
        return <article key={message.id} className={`qw-message ${message.role} ${message.failed ? "failed" : message.incomplete ? "incomplete" : ""}`}><small>{message.role === "user" ? "你" : "Hermes · AI Lab"}</small>{message.role === "assistant" && <HermesExecutionTrace execution={message.execution} pending={message.pending} waitingForClarification={message.waitingForClarification} clock={clock} variant="planning" />}{message.role === "assistant" ? <div className="qw-message-markdown"><ReactMarkdown>{renderedAnswer}</ReactMarkdown></div> : <p>{renderedAnswer}</p>}{protocol && !blueprint && <ProjectBlueprintProtocol protocol={protocol.payload} complete={protocol.complete} dispatchable={false} />}{blueprint && <ProjectBlueprintReview blueprint={isCurrentBlueprint && reviewBlueprint ? reviewBlueprint : blueprint} onChange={isCurrentBlueprint ? setReviewBlueprint : undefined} version={blueprintIndex + 1} current={isCurrentBlueprint} dispatchable={message.request_id === blueprintRequestId} />}</article>;
      })}<HermesClarificationCard clarification={clarification} busy={clarificationBusy} responseText={clarificationText} onResponseTextChange={setClarificationText} selections={clarificationSelections} onSelectionsChange={setClarificationSelections} onSubmit={submitClarification} idPrefix="qw-project-clarification" continuationLabel="回答后，Hermes 会继续检查需求；信息足够时自动生成蓝图。" /></div>
      {error && <p className="qw-error compact" role="alert">{error}</p>}
      {planningNotice && <p className="qw-planning-notice" role="status">{planningNotice}</p>}
      <form className="qw-planning-composer" onSubmit={send}><label className="qw-sr-only" htmlFor="project-planning-question">项目需求</label><textarea id="project-planning-question" rows={3} value={question} onChange={(event) => setQuestion(event.target.value)} placeholder={clarification ? "请先回答上方澄清问题…" : latestBlueprintVersion ? `继续补充或修订收敛单 v${latestBlueprintVersion}，也可以直接粘贴你的流程…` : "补充目标、范围、角色、日期、验收或依赖…"} disabled={!conversation || busy || !!clarification} /><button className="qw-button primary" aria-label="发送" disabled={!conversation || busy || !!clarification || !question.trim()}><Send size={16} /></button></form>
      <footer><button type="button" className="qw-button subtle" disabled={!conversation || busy} onClick={() => send(null, "基于当前项目名称、描述和既有对话，判断能否收敛需求并完成全部字段：能则直接生成完整项目蓝图；不能则继续向我提出最关键的问题，直至需求收敛。")}>{resumeNeeded ? "继续 AI 生成" : blueprintRequestId ? "重新检查蓝图" : "检查并生成蓝图"}</button><button type="button" className="qw-button primary" disabled={!blueprintRequestId || busy} onClick={dispatch}>{busy ? "正在派发…" : "确认并派发项目"}</button></footer>
    </>}
  </section></div>;
}
