import { useCallback, useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import {
  BarChart3,
  Database,
  File,
  FileText,
  FileType2,
  LoaderCircle,
  Network,
  Workflow,
  X,
} from "lucide-react";
import { platformApi } from "../../services/platformApi";
import { artifactPresentation, parseStructuredArtifact } from "./artifactPresentation";
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
const ICONS = { markdown: FileText, word: FileType2, chart: BarChart3, topology: Network, flowchart: Workflow, data: Database, file: File, image: File };

const text = (value, fallback = "未提供") => Array.isArray(value) ? (value.length ? value.map(String).join(" · ") : fallback) : (value || fallback);
const stateFor = (seat) => STATUS[seat.status] || ["waiting", seat.status || "待命中"];
const sourceNodeId = (artifact) => artifact?.metadata?.source_node_id || artifact?.metadata?.node_id || artifact?.metadata?.producer_node_id || "";
const artifactTime = (artifact) => {
  const value = artifact?.created_at || artifact?.metadata?.captured_at;
  return value && Number.isFinite(Date.parse(value)) ? new Date(value).toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" }) : "时间未提供";
};

function SafeMarkdown({ children }) {
  const components = {
    a: ({ href = "", ...props }) => <a href={href} target="_blank" rel="noreferrer noopener" {...props} />,
    img: ({ src = "", alt = "" }) => /^(data:image\/(?:png|jpeg);base64,|\/(?!\/))/.test(src) ? <img src={src} alt={alt} /> : <span className="reference-blocked-image">[外部图像未自动加载：{alt || "未命名"}]</span>,
  };
  return <ReactMarkdown components={components}>{children}</ReactMarkdown>;
}

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
  return <button className={`reference-seat reference-seat--${tag} ${visible ? "is-visible" : ""} ${selected ? "is-selected" : ""}`} type="button" onClick={onClick} aria-pressed={selected} data-agent-state={tag}>
    {event && <div className="reference-bubble"><span>{event.message || event.event_type || "服务端事件"}</span><small>{event.event_id || event.id || "event"}</small></div>}
    <div className="reference-character" style={{ filter: selected ? `drop-shadow(0 12px 32px ${color}55)` : "drop-shadow(0 4px 12px rgba(0,0,0,.13))" }}><CharacterDesk color={color} state={active} screenType={SCREEN_TYPES[index % SCREEN_TYPES.length]} /></div>
    <strong>{seat.name || `节点 ${index + 1}`}</strong>
    <small>{seat.businessRole || text(seat.roleIds, "服务端节点")}</small>
    <StatusPill tag={tag} label={label} />
    {seat.artifacts?.length > 0 && <span className="reference-output-chip">输出物 · {seat.artifacts.length}</span>}
  </button>;
}

function TransferLayer({ transfers = [] }) {
  if (!transfers.length) return null;
  const point = (index) => ({ x: 16.7 + (index % 3) * 33.3, y: index < 3 ? 25 : 75 });
  return <svg className="reference-transfer-layer" viewBox="0 0 100 100" preserveAspectRatio="none" aria-label="真实输出物流转">
    {transfers.map((transfer) => {
      const from = point(transfer.sourceIndex);
      const to = point(transfer.targetIndex);
      const path = `M ${from.x} ${from.y} L ${to.x} ${to.y}`;
      return <g className="reference-transfer" key={transfer.id}><path d={path} /><circle r="1.2"><title>{transfer.artifactTitle} → 下一个节点</title><animateMotion dur="1.8s" repeatCount="indefinite" path={path} /></circle></g>;
    })}
  </svg>;
}

function ChartPreview({ data, content }) {
  const labels = Array.isArray(data?.labels) ? data.labels.slice(0, 24).map(String) : [];
  const rawValues = Array.isArray(data?.values) ? data.values : Array.isArray(data?.series?.[0]?.data) ? data.series[0].data : [];
  const values = rawValues.slice(0, 24);
  const valid = values.length > 0 && values.every((value) => typeof value === "number" && Number.isFinite(value) && value >= 0);
  if (!valid) return <MissingStructure content={content} expected="最多 24 个非负有限数值（labels + values，或 series[0].data）" />;
  const max = Math.max(...values, 1);
  const width = 620;
  const step = width / values.length;
  return <div className="reference-structured-preview"><svg viewBox="0 0 660 310" role="img" aria-label="真实数据图表">
    <line x1="28" y1="270" x2="642" y2="270" />
    {values.map((value, index) => { const height = (value / max) * 210; const x = 34 + index * step; return <g key={`${labels[index] || index}-${index}`}><rect x={x} y={270 - height} width={Math.max(step - 18, 8)} height={height} /><text x={x + Math.max(step - 18, 8) / 2} y="292">{labels[index]?.slice(0, 8) || index + 1}</text><text className="reference-chart-value" x={x + Math.max(step - 18, 8) / 2} y={260 - height}>{value}</text></g>; })}
  </svg>{rawValues.length > 24 && <small>仅展示前 24 个数据点；源数据共 {rawValues.length} 个。</small>}</div>;
}

function DiagramPreview({ data, content, topology = false }) {
  const nodes = Array.isArray(data?.nodes) ? data.nodes.filter((node) => node && typeof node === "object" && !Array.isArray(node)).slice(0, 12) : [];
  const edges = Array.isArray(data?.edges) ? data.edges.filter((edge) => edge && typeof edge === "object" && !Array.isArray(edge)).slice(0, 80) : [];
  if (!nodes.length) return <MissingStructure content={content} expected="nodes + edges" />;
  const normalized = nodes.map((node, index) => ({ id: String(node.id ?? index), label: String(node.label || node.name || node.id || `节点 ${index + 1}`) }));
  const positions = new Map(normalized.map((node, index) => {
    if (topology) { const angle = (Math.PI * 2 * index) / normalized.length - Math.PI / 2; return [node.id, { x: 330 + Math.cos(angle) * 220, y: 170 + Math.sin(angle) * 105 }]; }
    const columns = Math.min(normalized.length, 4); return [node.id, { x: 90 + (index % columns) * 160, y: 90 + Math.floor(index / columns) * 130 }];
  }));
  return <div className="reference-structured-preview"><svg viewBox="0 0 660 340" role="img" aria-label={topology ? "真实拓扑图" : "真实流程图"}>
    {edges.map((edge, index) => { const from = positions.get(String(edge.source ?? edge.from)); const to = positions.get(String(edge.target ?? edge.to)); return from && to ? <line className="reference-diagram-edge" key={`${index}-${edge.source}`} x1={from.x} y1={from.y} x2={to.x} y2={to.y} /> : null; })}
    {normalized.map((node) => { const point = positions.get(node.id); return <g className="reference-diagram-node" key={node.id} transform={`translate(${point.x - 62} ${point.y - 25})`}><rect width="124" height="50" rx="12" /><text x="62" y="30">{node.label.slice(0, 12)}</text></g>; })}
  </svg>{data?.nodes?.length > 12 && <small>仅展示前 12 个节点；源数据共 {data.nodes.length} 个。</small>}</div>;
}

function MissingStructure({ content, expected }) {
  return <div className="reference-missing-structure"><strong>缺少可视化结构</strong><p>服务端内容未提供 {expected}，因此不生成伪图。</p>{content && <pre>{content}</pre>}</div>;
}

function WordTextPreview({ content }) {
  const paragraphs = (content || "").split(/\n{2,}/).map((item) => item.trim()).filter(Boolean);
  return <article className="reference-artifact-preview reference-artifact-preview--word"><div className="reference-word-page">{paragraphs.length ? paragraphs.map((paragraph, index) => <p key={`${index}-${paragraph.slice(0, 16)}`}>{paragraph}</p>) : <p>无可读取文本</p>}</div></article>;
}

function ArtifactPreview({ artifact, content }) {
  const presentation = artifactPresentation(artifact);
  const structured = parseStructuredArtifact(content);
  const candidateImage = content || artifact.source_url || "";
  const imageSource = /^(data:image\/(?:png|jpeg);base64,|\/(?!\/))/.test(candidateImage) ? candidateImage : "";
  if (presentation.type === "chart") return <ChartPreview data={structured} content={content} />;
  if (presentation.type === "topology") return <DiagramPreview data={structured} content={content} topology />;
  if (presentation.type === "flowchart") return <DiagramPreview data={structured} content={content} />;
  if (presentation.type === "word") return <WordTextPreview content={content} />;
  if (presentation.type === "markdown") return <article className="reference-artifact-preview reference-artifact-preview--markdown"><SafeMarkdown>{content || "无可读取内容"}</SafeMarkdown></article>;
  if (presentation.type === "image" && imageSource) return <div className="reference-artifact-image"><img src={imageSource} alt={artifact.title || "工件图像"} /></div>;
  return <pre className="reference-artifact-preview reference-artifact-preview--data">{content || "无可读取内容"}</pre>;
}

function ArtifactDialog({ artifact, executionId, sourceName, onClose }) {
  const [state, setState] = useState({ loading: true, content: "", error: "" });
  const dialogRef = useRef(null);
  const closeButtonRef = useRef(null);
  const presentation = artifactPresentation(artifact);
  const Icon = ICONS[presentation.type] || File;
  useEffect(() => {
    let active = true;
    const previousActive = document.activeElement;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    closeButtonRef.current?.focus();
    const onKeyDown = (event) => {
      if (event.key === "Escape") { onClose(); return; }
      if (event.key !== "Tab") return;
      const focusable = [...(dialogRef.current?.querySelectorAll("button:not([disabled]),a[href],[tabindex]:not([tabindex='-1'])") || [])];
      if (!focusable.length) { event.preventDefault(); return; }
      const first = focusable[0];
      const last = focusable.at(-1);
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    };
    window.addEventListener("keydown", onKeyDown);
    platformApi.getArtifactContent(executionId, artifact.id).then((payload) => {
      if (active) setState({ loading: false, content: payload?.content || "", error: "" });
    }).catch((nextError) => {
      if (active) setState({ loading: false, content: "", error: nextError.message || "无法读取工件内容" });
    });
    return () => {
      active = false;
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", onKeyDown);
      previousActive?.focus?.();
    };
  }, [artifact.id, executionId, onClose]);
  return <><div className="reference-artifact-backdrop" onClick={onClose} /><section ref={dialogRef} className="reference-artifact-dialog" role="dialog" aria-modal="true" aria-label={`${artifact.title || "工件"}内容预览`}>
    <header><div className={`reference-artifact-icon is-${presentation.tone}`}><Icon size={22} /></div><div><small>{presentation.label} · {sourceName || "来源节点未标注"}</small><h2>{artifact.title || artifact.id}</h2></div><button ref={closeButtonRef} type="button" onClick={onClose} aria-label="关闭工件预览"><X size={19} /></button></header>
    <div className="reference-artifact-meta"><span>真实 Artifact</span><code>{artifact.id}</code>{presentation.extension && <span>.{presentation.extension}</span>}<span>{artifact.mime_type || "MIME未提供"}</span><span>{artifactTime(artifact)}</span>{artifact.node_run_id && <code>{artifact.node_run_id}</code>}<code>{artifact.content_hash?.slice(0, 10) || "无哈希"}</code></div>
    <div className="reference-artifact-dialog__body">{state.loading ? <div className="reference-artifact-loading"><LoaderCircle size={22} />读取真实内容…</div> : state.error ? <div className="reference-artifact-load-error" role="alert">{state.error}</div> : <ArtifactPreview artifact={artifact} content={state.content} />}</div>
  </section></>;
}

function ArtifactGallery({ artifacts = [], seats = [], executionId, onOpen }) {
  const seatNames = new Map(seats.map((seat) => [seat.id, seat.name]));
  return <section className="reference-artifact-gallery" aria-label="项目交付物">
    <div className="reference-artifact-gallery__heading"><div><small>DELIVERABLES</small><strong>项目交付物</strong></div><span>{artifacts.length} 件真实工件</span></div>
    <div className="reference-artifact-gallery__track">{artifacts.length ? artifacts.map((artifact) => {
      const presentation = artifactPresentation(artifact);
      const Icon = ICONS[presentation.type] || File;
      const sourceName = seatNames.get(sourceNodeId(artifact)) || "来源节点未标注";
      return <button type="button" className={`reference-artifact-card is-${presentation.tone}`} key={artifact.id || artifact.title} onClick={() => onOpen(artifact)} disabled={!artifact.id || !executionId}>
        <span className="reference-artifact-card__visual"><Icon size={23} /><b>{presentation.label}</b></span><span className="reference-artifact-card__copy"><strong>{artifact.title || artifact.id}</strong><small>{sourceName} · {artifactTime(artifact)}</small></span><span className="reference-artifact-card__status">可审阅</span>
      </button>;
    }) : <div className="reference-artifact-empty"><FileText size={18} /><span>尚无服务端真实工件</span></div>}</div>
  </section>;
}

export default function ReferenceOfficeView({ projection, onSwitchToWorkbench, error = "", busy = false }) {
  const [selectedId, setSelectedId] = useState("");
  const [visibleCount, setVisibleCount] = useState(0);
  const [selectedArtifact, setSelectedArtifact] = useState(null);
  const seats = projection.seats || [];
  const selected = seats.find((seat) => seat.id === selectedId) || null;
  const disconnected = Boolean(error) || projection.connectionState === "UNCONNECTED";
  useEffect(() => { setVisibleCount(0); const timer = setInterval(() => setVisibleCount((count) => Math.min(count + 1, seats.length)), 180); return () => clearInterval(timer); }, [seats.length]);
  useEffect(() => { if (selectedId && !seats.some((seat) => seat.id === selectedId)) setSelectedId(""); }, [seats, selectedId]);
  useEffect(() => { if (selectedArtifact && !(projection.artifacts || []).some((item) => item.id === selectedArtifact.id)) setSelectedArtifact(null); }, [projection.artifacts, selectedArtifact]);
  const truth = disconnected ? "UNCONNECTED" : ((busy || projection.connectionState === "SYNCING") ? "SYNCING" : projection.truthMode);
  const sourceName = selectedArtifact ? seats.find((seat) => seat.id === sourceNodeId(selectedArtifact))?.name : "";
  const openArtifact = useCallback((artifact) => { setSelectedId(""); setSelectedArtifact(artifact); }, []);
  const closeArtifact = useCallback(() => setSelectedArtifact(null), []);
  return <div className="reference-office-shell">
    <header className="reference-office-header"><div className="reference-brand"><i /> <span>AI LAB PROJECT OFFICE</span></div><div className="reference-header-meta"><span>{projection.title || "服务端项目办公室"}</span><b>{truth}</b><em>{seats.length} nodes</em></div></header>
    <div className="reference-phasebar"><strong>{projection.stage || "项目席位"}</strong><span>{disconnected ? "UNCONNECTED · 已停止LIVE动效" : "服务端事实源 · 只读投影"}</span><button type="button" onClick={onSwitchToWorkbench}>回到工作台 →</button></div>
    {error && <div className="reference-error" role="alert">{error}</div>}
    <main className="reference-floor"><div className="reference-floor-label"><span>PROJECT FLOOR</span><small>{seats.length} 个服务端节点 · {projection.artifacts?.length || 0} 个工件</small></div><div className="reference-grid"><TransferLayer transfers={projection.transfers} />{seats.map((seat, index) => <Seat key={seat.id} seat={seat} index={index} visible={index < visibleCount} selected={selected?.id === seat.id} onClick={() => setSelectedId((current) => current === seat.id ? "" : seat.id)} />)}</div><ArtifactGallery artifacts={projection.artifacts} seats={seats} executionId={projection.executionId} onOpen={openArtifact} /></main>
    {selected && <DetailSheet seat={selected} onClose={() => setSelectedId("")} />}
    {selectedArtifact && <ArtifactDialog artifact={selectedArtifact} executionId={projection.executionId} sourceName={sourceName} onClose={closeArtifact} />}
  </div>;
}
