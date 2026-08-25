import { useMemo, useState } from "react";
import ReactMarkdown from "react-markdown";
import {
  ArrowRight,
  Bot,
  CheckCircle2,
  CircleDot,
  LogOut,
  Network,
  Play,
  ShieldCheck,
  Sparkles,
  Wrench,
} from "lucide-react";
import { useAuth } from "../auth/AuthContext";
import { platformApi } from "../services/platformApi";
import {
  agencyRunbooks,
  agencySource,
  buildAgencyPrompt,
} from "../data/agencyRunbooks";
import "./AgencyPortalPage.css";

const phaseOrder = ["概念", "计划", "开发", "验证", "发布", "生命周期"];

function eventLabel(event) {
  if (event.type === "tool_start") return `调用 ${event.tool || "AI Lab 能力"}`;
  if (event.type === "tool_complete") return `${event.tool || "能力"} 已返回`;
  if (event.type === "status") return event.detail || "Hermes 正在执行";
  if (event.type === "clarify") return event.question || "需要补充信息";
  if (event.type === "done") return "业务交付已生成";
  if (event.type === "error") return event.message || event.error || "执行失败";
  return event.message || event.detail || event.type;
}

export default function AgencyPortalPage() {
  const { authSession, logout } = useAuth();
  const [selectedId, setSelectedId] = useState(agencyRunbooks[0].id);
  const [brief, setBrief] = useState("");
  const [isRunning, setIsRunning] = useState(false);
  const [events, setEvents] = useState([]);
  const [answer, setAnswer] = useState("");
  const [error, setError] = useState("");
  const [sessionId, setSessionId] = useState(null);

  const selected = useMemo(
    () => agencyRunbooks.find((item) => item.id === selectedId) || agencyRunbooks[0],
    [selectedId],
  );

  const run = async () => {
    if (!brief.trim() || isRunning) return;
    setIsRunning(true);
    setEvents([]);
    setAnswer("");
    setError("");
    const prompt = buildAgencyPrompt(selected, brief);
    try {
      const nextSessionId = await platformApi.streamOrchestrationSession(
        prompt,
        sessionId,
        (event) => {
          setEvents((current) => [...current.slice(-39), event]);
          if (event.type === "done") {
            setAnswer(event.answer || event.reply || event.content || "");
          }
          if (event.type === "error") {
            setError(event.message || event.error || "Agency 执行失败");
          }
        },
      );
      setSessionId(nextSessionId || sessionId);
    } catch (runError) {
      setError(runError.message || "无法连接 Agency 执行服务");
    } finally {
      setIsRunning(false);
    }
  };

  return (
    <main className="agency-shell">
      <header className="agency-topbar">
        <div className="agency-brand">
          <div className="agency-brand-mark" aria-hidden="true"><Network size={21} /></div>
          <div>
            <strong>THE AGENCY · AI LAB</strong>
            <span>业务员工前台 / 能力执行中台</span>
          </div>
        </div>
        <div className="agency-account">
          <span>{authSession?.user?.username || authSession?.identifier || "访客"}</span>
          <button type="button" onClick={logout} aria-label="退出登录">
            <LogOut size={18} />
          </button>
        </div>
      </header>

      <section className="agency-hero">
        <div>
          <span className="agency-eyebrow"><Sparkles size={15} /> AI EMPLOYEE SERVICE DESK</span>
          <h1>选择一项业务实践，<br />让 AI 员工开始工作。</h1>
          <p>
            Agency Agents 负责业务角色与流程，Hermes 负责调度，AI Lab 提供知识、调研和执行能力。
          </p>
        </div>
        <div className="agency-trust-grid" aria-label="运行架构">
          <article><Bot size={20} /><strong>270</strong><span>可按需加载的专业员工</span></article>
          <article><Network size={20} /><strong>12</strong><span>001 业务实践 Runbook</span></article>
          <article><ShieldCheck size={20} /><strong>3 层</strong><span>业务、调度、能力边界</span></article>
        </div>
      </section>

      <nav className="agency-phase-nav" aria-label="IPD 阶段">
        {phaseOrder.map((phase) => (
          <a key={phase} href={`#phase-${phase}`}>{phase}</a>
        ))}
      </nav>

      <section className="agency-workspace">
        <div className="agency-catalog" aria-label="001 实践目录">
          {phaseOrder.map((phase) => (
            <section key={phase} id={`phase-${phase}`} className="agency-phase-group">
              <div className="agency-phase-heading">
                <span>{String(phaseOrder.indexOf(phase) + 1).padStart(2, "0")}</span>
                <h2>{phase}</h2>
              </div>
              <div className="agency-card-grid">
                {agencyRunbooks.filter((item) => item.phase === phase).map((item) => (
                  <button
                    type="button"
                    key={item.id}
                    className={`agency-runbook-card ${selectedId === item.id ? "is-selected" : ""}`}
                    onClick={() => setSelectedId(item.id)}
                    aria-pressed={selectedId === item.id}
                  >
                    <span className="agency-runbook-id">{item.id}</span>
                    <strong>{item.title}</strong>
                    <p>{item.summary}</p>
                    <span className="agency-card-action">查看员工与交付 <ArrowRight size={15} /></span>
                  </button>
                ))}
              </div>
            </section>
          ))}
        </div>

        <aside className="agency-run-panel" aria-label="业务启动面板">
          <div className="agency-panel-kicker">已选择 · {selected.phase}</div>
          <h2>{selected.id} {selected.title}</h2>
          <p className="agency-question">{selected.question}</p>

          <div className="agency-panel-section">
            <h3><Bot size={16} /> 员工团队</h3>
            <div className="agency-chip-list">
              {selected.agents.map((agent) => <span key={agent}>{agent}</span>)}
            </div>
          </div>

          <div className="agency-panel-section">
            <h3><Wrench size={16} /> AI Lab 能力</h3>
            <div className="agency-chip-list is-capability">
              {selected.capabilities.map((capability) => <span key={capability}>{capability}</span>)}
            </div>
          </div>

          <label className="agency-brief-label" htmlFor="agency-brief">告诉员工你的真实需求</label>
          <textarea
            id="agency-brief"
            value={brief}
            onChange={(event) => setBrief(event.target.value)}
            placeholder="例如：我们希望为制造企业建立一个能够降低非计划停机的 AI 运维方案，首期覆盖两条产线……"
            rows={7}
          />
          <button
            type="button"
            className="agency-run-button"
            onClick={run}
            disabled={!brief.trim() || isRunning}
          >
            {isRunning ? <CircleDot className="agency-spin" size={18} /> : <Play size={18} />}
            {isRunning ? "员工正在工作" : "启动这项业务"}
          </button>

          {(events.length > 0 || error) && (
            <section className="agency-live-panel" aria-live="polite">
              <h3>真实执行记录</h3>
              <ol>
                {events.map((event, index) => (
                  <li key={`${event.type}-${index}`}>
                    <CheckCircle2 size={14} />
                    <span>{eventLabel(event)}</span>
                  </li>
                ))}
              </ol>
              {error && <p className="agency-error" role="alert">{error}</p>}
            </section>
          )}
        </aside>
      </section>

      {answer && (
        <section className="agency-deliverable" aria-live="polite">
          <div className="agency-deliverable-heading">
            <span>DELIVERABLE</span>
            <h2>{selected.title} · 正式交付</h2>
          </div>
          <div className="agency-markdown"><ReactMarkdown>{answer}</ReactMarkdown></div>
        </section>
      )}

      <footer className="agency-footer">
        <span>Agency roster: {agencySource.repository} @ {agencySource.revision.slice(0, 7)}</span>
        <span>Execution: Hermes · Capability provider: AI Lab</span>
      </footer>
    </main>
  );
}
