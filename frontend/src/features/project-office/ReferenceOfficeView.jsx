import { useEffect, useMemo, useRef, useState } from "react";
import CharacterDesk from "./reference/CharacterDesk";
import "./reference/reference-office.css";
import "./ReferenceOfficeView.css";

const COLORS = ["#5dbe6e", "#e85555", "#9b7fea", "#4a9eed", "#f5c842", "#3dbbab"];
const SCREEN_TYPES = ["dashboard", "browsing", "typing", "code", "checklist", "analytics"];
const STATUS = {
  planned: ["planned", "已规划"], waiting: ["waiting", "待命中"], running: ["working", "进行中"],
  blocked: ["blocked", "已阻断"], failed: ["blocked", "失败"], done: ["done", "已完成"],
  succeeded: ["done", "已完成"], awaiting_review: ["tbd", "待复核"], reference: ["waiting", "参考节点"],
};

const text = (value, fallback = "未提供") => Array.isArray(value) ? (value.length ? value.map(String).join(" · ") : fallback) : (value || fallback);
const stateFor = (seat) => STATUS[seat.status] || ["waiting", seat.status || "待命中"];

function StatusPill({ tag, label }) {
  const color = tag === "working" ? "#5dbe6e" : tag === "blocked" ? "#ef4444" : tag === "tbd" ? "#f5c842" : tag === "done" ? "#818cf8" : "#9ca3af";
  return <span className="reference-status" style={{ background: `${color}1c`, color }}><i style={{ background: color }} />{label}</span>;
}

function DetailSheet({ seat, onClose }) {
  if (!seat) return null;
  const [tag, label] = stateFor(seat);
  return <>
    <div className="reference-sheet-backdrop" onClick={onClose} />
    <aside className="reference-sheet" aria-label={`${seat.name}员工详情`}>
      <div className="reference-sheet-handle" />
      <div className="reference-sheet-head"><div className="reference-sheet-avatar"><CharacterDesk color="#5dbe6e" state="selected" screenType="dashboard" /></div><div><small>员工详情</small><h2>{seat.name}</h2><p>{seat.businessRole || text(seat.roleIds)}</p></div><button type="button" onClick={onClose}>关闭</button></div>
      <div className="reference-sheet-grid"><div><small>状态</small><StatusPill tag={tag} label={label} /></div><div><small>节点ID</small><code>{seat.nodeId || seat.id}</code></div></div>
      <section><h3>输入</h3><p>{text(seat.input)}</p></section>
      <section><h3>预期输出</h3><p>{text(seat.expectedOutput)}</p></section>
      <section><h3>最新真实事件</h3><p>{seat.lastEvent?.message || seat.lastEvent?.event_type || "暂无映射事件"}</p></section>
      <section><h3>映射工件</h3><p>{seat.artifacts?.length ? seat.artifacts.map((item) => item.title || item.id).join(" · ") : "暂无明确来源工件"}</p></section>
    </aside>
  </>;
}

function Seat({ seat, index, selected, onClick, visible }) {
  const [tag, label] = stateFor(seat);
  const color = COLORS[index % COLORS.length];
  const active = tag === "working" ? "working" : tag === "blocked" ? "selected" : tag === "done" ? "done" : "sleeping";
  const event = seat.lastEvent;
  return <button className={`reference-seat ${visible ? "is-visible" : ""} ${selected ? "is-selected" : ""}`} type="button" onClick={onClick} aria-pressed={selected}>
    {event && <div className="reference-bubble"><span>{event.message || event.event_type || "服务端事件"}</span><small>{event.event_id || event.id || "event"}</small></div>}
    <div className="reference-character" style={{ filter: selected ? `drop-shadow(0 12px 32px ${color}55)` : `drop-shadow(0 4px 12px rgba(0,0,0,.13))` }}><CharacterDesk color={color} state={active} screenType={SCREEN_TYPES[index % SCREEN_TYPES.length]} /></div>
    <strong>{seat.name || `节点 ${index + 1}`}</strong>
    <small>{seat.businessRole || text(seat.roleIds, "服务端节点")}</small>
    <StatusPill tag={tag} label={label} />
  </button>;
}

export default function ReferenceOfficeView({ projection, onSwitchToWorkbench, error = "", busy = false }) {
  const [selectedId, setSelectedId] = useState("");
  const [visibleCount, setVisibleCount] = useState(0);
  const seats = projection.seats || [];
  const selected = seats.find((seat) => seat.id === selectedId) || null;
  const disconnected = Boolean(error) || projection.connectionState === "UNCONNECTED";
  useEffect(() => { setVisibleCount(0); const timer = setInterval(() => setVisibleCount((count) => Math.min(count + 1, seats.length)), 180); return () => clearInterval(timer); }, [seats.length]);
  useEffect(() => { if (selectedId && !seats.some((seat) => seat.id === selectedId)) setSelectedId(""); }, [seats, selectedId]);
  const truth = disconnected ? "UNCONNECTED" : ((busy || projection.connectionState === "SYNCING") ? "SYNCING" : projection.truthMode);
  return <div className="reference-office-shell">
    <header className="reference-office-header"><div className="reference-brand"><i /> <span>AI LAB PROJECT OFFICE</span></div><div className="reference-header-meta"><span>{projection.title || "服务端项目办公室"}</span><b>{truth}</b><em>{seats.length} nodes</em></div></header>
    <div className="reference-phasebar"><strong>{projection.stage || "项目席位"}</strong><span>{disconnected ? "UNCONNECTED · 已停止LIVE动效" : "服务端事实源 · 只读投影"}</span><button type="button" onClick={onSwitchToWorkbench}>回到工作台 →</button></div>
    {error && <div className="reference-error" role="alert">{error}</div>}
    <main className="reference-floor"><div className="reference-floor-label"><span>PROJECT FLOOR</span><small>{seats.length} 个服务端节点 · {projection.artifacts?.length || 0} 个工件</small></div><div className="reference-grid">{seats.map((seat, index) => <Seat key={seat.id} seat={seat} index={index} visible={index < visibleCount} selected={selected?.id === seat.id} onClick={() => setSelectedId((current) => current === seat.id ? "" : seat.id)} />)}</div><div className="reference-artifacts"><strong>工件交接</strong>{projection.artifacts?.length ? projection.artifacts.map((item) => <span key={item.id || item.title}>{item.title || item.id}</span>) : <span>尚无服务端工件</span>}</div></main>
    {selected && <DetailSheet seat={selected} onClose={() => setSelectedId("")} />}
  </div>;
}
