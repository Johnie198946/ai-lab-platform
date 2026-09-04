import { useCallback, useEffect, useState } from "react";
import { platformApi } from "../services/platformApi";
import "./AgentPage.css";

const EMPTY_DRAFT = {
  name: "",
  mission: "",
  sources: [],
  schedule: "0 18 * * *",
  actions: ["collect", "ingest", "compile", "notify"],
  channel: "inapp",
  skills: ["data-source-monitoring", "wiki-ingester"],
};

const SCHEDULE_PRESETS = [
  { label: "每日 18:00(默认)", value: "0 18 * * *" },
  { label: "每日 09:00", value: "0 9 * * *" },
  { label: "每日 08:00", value: "0 8 * * *" },
  { label: "每周一 09:00", value: "0 9 * * 1" },
  { label: "每 2 小时", value: "0 */2 * * *" },
];

export function AgentPage() {
  const [goal, setGoal] = useState("");
  const [draft, setDraft] = useState(null);
  const [isParsing, setIsParsing] = useState(false);
  const [agents, setAgents] = useState([]);
  const [templates, setTemplates] = useState([]);
  const [notifications, setNotifications] = useState({ items: [], unread: 0 });
  const [showNotifications, setShowNotifications] = useState(false);
  const [error, setError] = useState("");

  const refreshAgents = useCallback(async () => {
    try {
      const data = await platformApi.listAgents();
      setAgents(data.agents ?? []);
    } catch (e) {
      setError(e.message);
    }
  }, []);

  const refreshNotifications = useCallback(async () => {
    try {
      const data = await platformApi.listNotifications({ limit: 30 });
      setNotifications(data);
    } catch (e) {
      /* 通知中心加载失败不阻塞页面 */
    }
  }, []);

  useEffect(() => {
    refreshAgents();
    refreshNotifications();
    platformApi.listAgentTemplates().then(setTemplates).catch(() => {});
    const timer = setInterval(refreshNotifications, 30000);
    return () => clearInterval(timer);
  }, [refreshAgents, refreshNotifications]);

  const handleParse = async () => {
    if (!goal.trim() || isParsing) return;
    setError("");
    setIsParsing(true);
    try {
      const result = await platformApi.draftAgent(goal.trim());
      if (result.ok) {
        setDraft({ ...EMPTY_DRAFT, ...result.draft, _goal: goal.trim() });
      } else {
        setError(result.error || "解析失败");
      }
    } catch (e) {
      setError(e.message);
    } finally {
      setIsParsing(false);
    }
  };

  const handleConfirm = async () => {
    if (!draft) return;
    setError("");
    try {
      const payload = {
        name: draft.name,
        mission: draft.mission,
        sources: draft.sources ?? [],
        schedule: draft.schedule,
        actions: draft.actions ?? ["collect", "ingest", "compile", "notify"],
        channel: draft.channel ?? "inapp",
        skills: draft.skills ?? ["data-source-monitoring", "wiki-ingester"],
      };
      const created = await platformApi.createAgent(payload);
      setDraft(null);
      setGoal("");
      await refreshAgents();
      alert(`✅ Agent「${created.name}」已创建并接管调度\n下次运行: ${created.next_run_at ?? "待调度"}`);
    } catch (e) {
      setError(e.message);
    }
  };

  const handleTemplate = async (key) => {
    setError("");
    try {
      const created = await platformApi.instantiateAgentTemplate(key, {
        name: "",
        mission: goal.trim() || "使用模板默认任务",
      });
      setGoal("");
      await refreshAgents();
      alert(`✅ 模板 Agent「${created.name}」已创建\n下次运行: ${created.next_run_at ?? "待调度"}`);
    } catch (e) {
      setError(e.message);
    }
  };

  const handleToggle = async (agent) => {
    try {
      await platformApi.updateAgent(agent.id, {
        status: agent.status === "active" ? "paused" : "active",
      });
      await refreshAgents();
    } catch (e) {
      setError(e.message);
    }
  };

  const handleDelete = async (agent) => {
    if (!window.confirm(`确认删除 Agent「${agent.name}」?`)) return;
    try {
      await platformApi.deleteAgent(agent.id);
      await refreshAgents();
    } catch (e) {
      setError(e.message);
    }
  };

  const handleReadAll = async () => {
    await platformApi.markAllNotificationsRead();
    refreshNotifications();
  };

  const handleRead = async (id) => {
    await platformApi.markNotificationRead(id);
    refreshNotifications();
  };

  const fmtTime = (iso) => {
    if (!iso) return "—";
    const d = new Date(iso);
    const p = (n) => String(n).padStart(2, "0");
    return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
  };

  return (
    <main className="agent-shell">
      <header className="agent-topbar">
        <span className="agent-brand">AI Lab · 子 Agent 工厂</span>
        <div className="agent-topbar-actions">
          <button
            className="agent-bell"
            onClick={() => setShowNotifications((v) => !v)}
            title="站内通知"
          >
            🔔
            {notifications.unread > 0 && (
              <span className="agent-bell-badge">{notifications.unread}</span>
            )}
          </button>
        </div>
      </header>

      {showNotifications && (
        <section className="agent-notif-panel">
          <div className="agent-notif-head">
            <strong>站内通知</strong>
            <button onClick={handleReadAll}>全部已读</button>
          </div>
          {notifications.items.length === 0 && <p className="agent-notif-empty">暂无通知</p>}
          {notifications.items.map((n) => (
            <div
              key={n.id}
              className={`agent-notif-item ${n.read ? "" : "is-unread"}`}
              onClick={() => !n.read && handleRead(n.id)}
            >
              <div className="agent-notif-title">
                {n.title}
                {!n.read && <span className="agent-notif-dot">●</span>}
              </div>
              <div className="agent-notif-time">{fmtTime(n.created_at)}</div>
              {n.content && (
                <pre className="agent-notif-content">{n.content.slice(0, 600)}</pre>
              )}
            </div>
          ))}
        </section>
      )}

      <section className="agent-create-card">
        <h2>一句话创建子 Agent</h2>
        <p className="agent-create-hint">
          例如:「帮我做一个 agent 跟踪中国政府政策,每日 18:00 汇报」
        </p>
        <div className="agent-create-row">
          <textarea
            value={goal}
            onChange={(e) => setGoal(e.target.value)}
            placeholder="描述你想创建的 Agent:研究什么 / 跟踪哪些信源 / 多久汇报一次..."
            rows={3}
          />
          <button className="agent-btn agent-btn-primary" onClick={handleParse} disabled={isParsing || !goal.trim()}>
            {isParsing ? "解析中..." : "生成配置卡"}
          </button>
        </div>
        {error && <p className="agent-error">{error}</p>}

        {draft && (
          <div className="agent-confirm-card">
            <h3>确认 Agent 配置</h3>
            <label className="agent-field">
              <span>名称</span>
              <input value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} />
            </label>
            <label className="agent-field">
              <span>任务</span>
              <textarea value={draft.mission} rows={2} onChange={(e) => setDraft({ ...draft, mission: e.target.value })} />
            </label>
            <label className="agent-field">
              <span>频率</span>
              <select value={draft.schedule} onChange={(e) => setDraft({ ...draft, schedule: e.target.value })}>
                {SCHEDULE_PRESETS.map((p) => (
                  <option key={p.value} value={p.value}>{p.label}</option>
                ))}
              </select>
            </label>
            <label className="agent-field">
              <span>汇报通道</span>
              <select value={draft.channel} onChange={(e) => setDraft({ ...draft, channel: e.target.value })}>
                <option value="inapp">站内通知</option>
                <option value="inapp,feishu">站内 + 飞书(后续)</option>
              </select>
            </label>
            <div className="agent-field">
              <span>信源({draft.sources?.length ?? 0})</span>
              <div className="agent-source-list">
                {(draft.sources ?? []).slice(0, 8).map((s, i) => (
                  <span key={i} className="agent-source-chip">
                    {s.name} · {s.kind}
                  </span>
                ))}
                {(draft.sources?.length ?? 0) > 8 && (
                  <span className="agent-source-chip">+{(draft.sources?.length ?? 0) - 8}</span>
                )}
              </div>
            </div>
            <div className="agent-confirm-actions">
              <button className="agent-btn" onClick={() => setDraft(null)}>取消</button>
              <button className="agent-btn agent-btn-primary" onClick={handleConfirm}>确认创建</button>
            </div>
          </div>
        )}
      </section>

      {templates.length > 0 && (
        <section className="agent-templates">
          <h3>模板库(一键创建)</h3>
          <div className="agent-template-grid">
            {templates.map((t) => (
              <button key={t.key} className="agent-template-card" onClick={() => handleTemplate(t.key)}>
                <strong>{t.name}</strong>
                <span>{t.mission.slice(0, 40)}...</span>
                <em>{t.schedule} · {t.source_count} 信源</em>
              </button>
            ))}
          </div>
        </section>
      )}

      <section className="agent-list">
        <h3>我的 Agents({agents.length})</h3>
        {agents.length === 0 && <p className="agent-empty">还没有 Agent,用上面一句话创建一个。</p>}
        {agents.map((a) => (
          <div key={a.id} className="agent-row">
            <div className="agent-row-main">
              <strong>{a.name}</strong>
              <span className={`agent-status agent-status--${a.status}`}>
                {a.status === "active" ? "运行中" : a.status === "paused" ? "已暂停" : a.status}
              </span>
              {a.last_status && (
                <span className={`agent-last agent-last--${a.last_status}`}>
                  {a.last_status === "ok" ? "✓ 上次成功" : a.last_status === "error" ? "✗ 上次失败" : a.last_status}
                </span>
              )}
              <p className="agent-mission">{a.mission}</p>
              <div className="agent-meta">
                频率 {a.schedule} · 下次 {fmtTime(a.next_run_at)} · 上次 {fmtTime(a.last_run_at)}
                {a.sources?.length > 0 && ` · ${a.sources.length} 信源`}
              </div>
            </div>
            <div className="agent-row-actions">
              <button className="agent-btn" onClick={() => handleToggle(a)}>
                {a.status === "active" ? "暂停" : "恢复"}
              </button>
              <button className="agent-btn agent-btn-danger" onClick={() => handleDelete(a)}>删除</button>
            </div>
          </div>
        ))}
      </section>
    </main>
  );
}

export default AgentPage;
