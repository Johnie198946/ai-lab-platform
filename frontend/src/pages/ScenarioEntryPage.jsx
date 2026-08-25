import { useState } from "react";
import { ArrowRight, Bot, CheckCircle2, FileText, Loader2, LogOut, Play, Radio, ShieldCheck } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { platformApi } from "../services/platformApi";
import "./ScenarioEntryPage.css";

const SCENARIO = {
  id: "001-product-development",
  title: "001 产品开发",
  subtitle: "AI服务器产品从需求到概念评审",
  description: "预制一条可审阅的 IPD 产品开发链路。启动后由 AI Lab 调用现有 Hermes Runtime 执行，前端只展示真实状态、事件和交付物。",
  stages: ["需求洞察", "概念定义", "方案设计", "合规评审"],
  agents: [
    ["需求分析 Agent", "主责"],
    ["市场洞察 Agent", "协同"],
    ["产品规划 Agent", "协同"],
    ["架构设计 Agent", "评审"],
    ["合规评审 Agent", "门禁"],
  ],
  deliverables: ["客户需求矩阵", "产品定位建议", "技术约束清单", "概念阶段评审结论"],
};

const WORKFLOW_DESCRIPTION = `这是预制场景「001 产品开发」。请按 IPD 概念阶段执行 AI 服务器产品开发任务：先分析客户需求和市场信号，形成需求矩阵；再完成产品定位与关键取舍；补充技术架构约束；最后进行合规与概念阶段评审。参与角色包括需求分析 Agent、市场洞察 Agent、产品规划 Agent、架构设计 Agent、合规评审 Agent。输出客户需求矩阵、产品定位建议、技术约束清单和概念阶段评审结论。该任务必须使用现有 AI Lab/Hermes Runtime 执行，不创建第二套 Runtime。`;

export default function ScenarioEntryPage() {
  const { authSession, logout } = useAuth();
  const navigate = useNavigate();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const startScenario = async () => {
    setBusy(true);
    setError("");
    try {
      const result = await platformApi.createWorkflow({
        title: SCENARIO.title,
        description: WORKFLOW_DESCRIPTION,
        desired_output: SCENARIO.deliverables.join("、"),
        clarification_mode: "compatibility",
      });
      const workflowId = result?.workflow?.id;
      if (!workflowId) throw new Error("服务端没有返回工作流 ID");
      navigate(`/architect?scenario=${SCENARIO.id}&workflow=${encodeURIComponent(workflowId)}`);
    } catch (nextError) {
      setError(nextError.message || "无法创建 001 产品开发任务");
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="scenario-entry-page">
      <header className="scenario-topbar">
        <div className="scenario-brand"><span className="scenario-mark" /><strong>AI Lab</strong><span>业务场景工作台</span></div>
        <div className="scenario-account"><span className="live-pill"><Radio size={12} /> Hermes Runtime 已接入</span><span>{authSession?.user?.username || "account"}</span><button type="button" onClick={logout} aria-label="退出"><LogOut size={16} /></button></div>
      </header>

      <section className="scenario-hero">
        <div className="scenario-kicker">预制场景 · IPD 产品开发</div>
        <h1>选择一个业务场景，查看它如何被执行。</h1>
        <p>这里不是自由搭建 Workflow 的编辑器，而是已经配置好的业务过程工作台。当前先提供 001 产品开发，后续可以继续增加场景。</p>
      </section>

      <section className="scenario-grid" aria-label="预制业务场景">
        <article className="scenario-card scenario-card--featured">
          <div className="scenario-card-head"><div><span className="scenario-code">SCENARIO / 001</span><h2>{SCENARIO.title}</h2><p>{SCENARIO.subtitle}</p></div><span className="demo-badge">LIVE EXECUTION</span></div>
          <p className="scenario-description">{SCENARIO.description}</p>
          <div className="stage-strip">{SCENARIO.stages.map((stage, index) => <div className="stage-chip" key={stage}><span>{String(index + 1).padStart(2, "0")}</span>{stage}</div>)}</div>
          <div className="scenario-columns">
            <div><h3><Bot size={15} /> Agent 分工</h3><ul>{SCENARIO.agents.map(([name, role]) => <li key={name}><span>{name}</span><em>{role}</em></li>)}</ul></div>
            <div><h3><FileText size={15} /> 预期交付物</h3><ul>{SCENARIO.deliverables.map((item) => <li key={item}><CheckCircle2 size={14} /><span>{item}</span></li>)}</ul></div>
          </div>
          <div className="scenario-card-foot"><div className="truth-note"><ShieldCheck size={15} /><span>执行事件和交付物来自 AI Lab / Hermes；不在前端伪造。</span></div><button className="scenario-start" type="button" onClick={startScenario} disabled={busy}>{busy ? <Loader2 size={16} className="spin" /> : <Play size={16} />}{busy ? "正在创建任务…" : "进入 001 产品开发"}<ArrowRight size={16} /></button></div>
          {error && <p className="scenario-error" role="alert">{error}</p>}
        </article>

        <aside className="scenario-side-note"><span className="side-note-label">工作台边界</span><h3>展示层与执行层分离</h3><p>场景、IPD 阶段、任务和交付物由 AI Lab 管理；Agent 调用、工具执行和真实事件由现有 Hermes Runtime 完成。</p><div className="boundary-row"><span>前端工作台</span><b>展示</b></div><div className="boundary-row"><span>AI Lab</span><b>业务状态</b></div><div className="boundary-row"><span>Hermes</span><b>真实执行</b></div></aside>
      </section>
    </main>
  );
}
