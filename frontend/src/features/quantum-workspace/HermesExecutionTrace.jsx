const PHASE_LABELS = {
  planning_context: "项目名称与描述已绑定，正在检查需求空白",
  blueprint_repair: "首轮未形成完整协议，正在执行一次受控补全",
  context: "正在同步会话上下文与权限",
  boot: "正在启动租户 Hermes",
  reasoning: "Hermes 正在理解需求",
  running: "Hermes 正在继续处理",
  replay: "正在读取本 Session 已有结果",
};

export const hermesExecutionStep = (event, labels = {}) => {
  if (event.type === "status") {
    if (event.phase === "delegate") return event.detail || "正在调用专属 Agent";
    return labels[event.phase] || PHASE_LABELS[event.phase] || event.detail || "AI 正在处理";
  }
  if (event.type === "triage_route") {
    return event.route_class === "PROFESSIONAL_TASK"
      ? labels.professional || "已识别为专业任务，租户技能可以参与"
      : labels.general || "已完成请求分类，将直接生成回答";
  }
  if (event.type === "capability_route") {
    const candidates = (event.skill_candidates || []).map((item) => item.name).filter(Boolean);
    if (candidates.length) return `候选技能：${candidates.join("、")}`;
    if ((event.selected_capabilities || []).includes("tenant_skills")) return "租户技能已开放，Hermes 正在判断是否需要调用";
    return "能力路由已完成，本轮无需调用技能";
  }
  if (event.type === "tool_start") return event.label || `正在调用 ${event.tool || "AI 能力"}`;
  if (event.type === "tool_complete") return `${event.tool || "AI 能力"} 已返回`;
  if (event.type === "agent_route") return `已连接 ${event.agent?.name || event.agent?.id || "Hermes Agent"}`;
  if (event.type === "clarify") return "发现关键信息缺口，等待你补充";
  if (event.type === "delta") return labels.generating || "Hermes 正在生成回答";
  return "";
};

export const createHermesExecution = (detail, startedAt = Date.now()) => ({
  startedAt,
  lastActivityAt: startedAt,
  currentStartedAt: startedAt,
  current: detail,
  elapsedMs: 0,
  steps: [{ signature: "local:start", detail, elapsedMs: 0 }],
});

export const updateHermesExecution = (message, event, labels = {}) => {
  const detail = hermesExecutionStep(event, labels);
  if (!detail) return message;
  const execution = message.execution || createHermesExecution(detail);
  const elapsedMs = Math.max(0, Date.now() - execution.startedAt);
  const activityAt = Date.now();
  const signature = `${event.type}:${event.phase || event.tool || event.reason_code || detail}`;
  const previous = execution.steps.at(-1);
  if (previous?.signature === signature) {
    return { ...message, execution: { ...execution, current: detail, elapsedMs, lastActivityAt: activityAt } };
  }
  return {
    ...message,
    execution: {
      ...execution,
      current: detail,
      elapsedMs,
      lastActivityAt: activityAt,
      currentStartedAt: activityAt,
      steps: [...execution.steps, { signature, detail, elapsedMs }].slice(-8),
    },
  };
};

const elapsedLabel = (milliseconds) => `${Math.max(0, Math.round((milliseconds || 0) / 1000))}s`;

export function HermesExecutionTrace({ execution, pending, waitingForClarification, clock, variant = "task" }) {
  if (!execution) return null;
  const elapsedMs = pending ? Math.max(0, clock - execution.startedAt) : execution.elapsedMs;
  const inactiveMs = pending ? Math.max(0, clock - (execution.lastActivityAt || execution.startedAt)) : 0;
  const currentMs = pending ? Math.max(0, clock - (execution.currentStartedAt || execution.startedAt)) : 0;
  let slowNotice = "";
  if (waitingForClarification) {
    slowNotice = "Hermes 已暂停执行，正在等待你的回答。";
  } else if (pending && inactiveMs >= 45000) {
    slowNotice = "最近 45 秒没有新的上游事件。若仍无活动，本轮会按保护策略结束并提供重试；已有事件后的总耗时不受 60 秒首活动时限限制。";
  } else if (pending && inactiveMs >= 15000) {
    slowNotice = variant === "planning"
      ? "Hermes 正在形成下一项澄清问题或完整蓝图；这是模型处理阶段，不是页面卡死。"
      : "模型响应较慢，系统会在首个输出、技能调用或澄清问题前最多等待 60 秒。";
  } else if (pending && inactiveMs >= 6000) {
    slowNotice = variant === "planning" ? "Hermes 正在评估需求缺口，可继续等待。" : "模型正在规划，可继续等待。";
  }
  return <details className="qw-execution-trace" open={pending || undefined}>
    <summary><span>{execution.current || "执行详情"}</span><time title="本轮总耗时">总计 {elapsedLabel(elapsedMs)}</time></summary>
    <ol>{execution.steps.map((step) => <li key={`${step.signature}-${step.elapsedMs}`}><time>{elapsedLabel(step.elapsedMs)}</time><span>{step.detail}</span></li>)}</ol>
    {pending && !waitingForClarification && <p className="qw-execution-current">当前阶段已持续 {elapsedLabel(currentMs)} · 最近活动距今 {elapsedLabel(inactiveMs)}</p>}
    {slowNotice && <p className="qw-execution-slow">{slowNotice}</p>}
  </details>;
}
