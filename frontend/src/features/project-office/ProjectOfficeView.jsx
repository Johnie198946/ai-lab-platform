import { useEffect, useState } from "react";
import { ArrowRight, BriefcaseBusiness, FileText, Monitor, UserRound } from "lucide-react";
import "./ProjectOfficeView.css";
import ReferenceOfficeView from "./ReferenceOfficeView";

const listText = (values) => values.length ? values.map(String).join(" · ") : "未提供";

const STATUS_LABEL = {
  UNCONNECTED: "未连接",
  reference: "参考节点",
  waiting: "等待中",
  planned: "已规划",
  running: "执行中",
  blocked: "已阻断",
  failed: "失败",
  done: "已完成",
  succeeded: "已成功",
  cancelled: "已取消",
  awaiting_review: "等待复核",
};

function EventBubble({ event }) {
  if (!event) return null;
  return (
    <div className="office-event-bubble" aria-label="最新真实事件">
      <span>{event.message || event.event_type || event.type}</span>
      <small>{event.event_id || event.id}</small>
    </div>
  );
}

function EmployeeConsole({ seat, truthOverride = "" }) {
  if (!seat) {
    return <aside className="office-console office-console--empty"><UserRound size={20} /><p>选择一个席位查看服务端详情。</p></aside>;
  }
  return (
    <aside className="office-console" aria-live="polite" aria-label={`${seat.name} 员工详情`}>
      <div className="office-console__heading">
        <div className="office-console__portrait"><UserRound size={22} /></div>
        <div><span>员工详情</span><h2>{seat.name}</h2></div>
        <span className={`office-truth office-truth--${(truthOverride || seat.truthState.status).toLowerCase()}`}>{truthOverride || seat.truthState.status}</span>
      </div>
      <dl className="office-console__facts">
        <div><dt>业务角色</dt><dd>{seat.businessRole || listText(seat.roleIds)}</dd></div>
        {seat.runtimeAgentId && <div><dt>Runtime ID</dt><dd><code>{seat.runtimeAgentId}</code></dd></div>}
        <div><dt>节点状态</dt><dd>{STATUS_LABEL[seat.status] || seat.status}</dd></div>
      </dl>
      <section><h3>输入</h3><p>{listText(seat.input)}</p></section>
      <section><h3>预期输出</h3><p>{listText(seat.expectedOutput)}</p></section>
      <section><h3>最新事件</h3><p>{seat.lastEvent?.message || seat.lastEvent?.event_type || seat.lastEvent?.type || "暂无映射事件"}</p></section>
      <section><h3>映射工件</h3>{seat.artifacts.length ? <ul>{seat.artifacts.map((artifact) => <li key={artifact.id || artifact.title}><FileText size={14} />{artifact.title || artifact.id}</li>)}</ul> : <p>暂无明确来源工件</p>}</section>
    </aside>
  );
}

function LegacyProjectOfficeView({ projection, onSwitchToWorkbench, error = "", busy = false }) {
  const [selectedId, setSelectedId] = useState(projection.seats[0]?.id || "");
  const selectedSeat = projection.seats.find((seat) => seat.id === selectedId) || projection.seats[0] || null;
  const disconnected = Boolean(error) || projection.connectionState === "UNCONNECTED";
  const effectiveTruth = disconnected ? "UNCONNECTED" : projection.truthMode;
  const headerTruth = (busy || projection.connectionState === "SYNCING") && !disconnected ? "SYNCING" : effectiveTruth;

  useEffect(() => {
    if (!projection.seats.some((seat) => seat.id === selectedId)) setSelectedId(projection.seats[0]?.id || "");
  }, [projection.seats, selectedId]);

  return (
    <section className={`project-office${disconnected ? " is-unconnected" : ""}`} aria-label="AI Project Office 只读视图">
      <header className="office-header">
        <div><span className="office-kicker">Office View · 只读</span><h1>{projection.title}</h1><p>当前阶段：<strong>{projection.stage}</strong> <span className={`office-header-truth office-truth--${headerTruth.toLowerCase()}`}>{headerTruth}</span></p></div>
        <button className="office-switch" type="button" onClick={onSwitchToWorkbench}>切换到工作台 <ArrowRight size={17} /></button>
      </header>

      {disconnected && <div className="office-connection-error" role="alert"><strong>UNCONNECTED</strong><span>{error || "状态源尚未建立连接"}</span><small>已停止 LIVE 动效；请切换到工作台重试。</small></div>}

      <div className="office-layout">
        <div className="office-floor">
          <div className="office-floor__label"><BriefcaseBusiness size={17} /><span>项目席位</span><small>{projection.seats.length} 个服务端节点</small></div>
          {projection.seats.length ? (
            <div className="office-stage">
              {projection.seats.map((seat) => (
                <button
                  className={`office-seat office-seat--${seat.status}${selectedSeat?.id === seat.id ? " is-selected" : ""}`}
                  type="button"
                  key={seat.id}
                  onClick={() => setSelectedId(seat.id)}
                  aria-label={`查看 ${seat.name} 员工详情，状态 ${STATUS_LABEL[seat.status] || seat.status}`}
                  aria-pressed={selectedSeat?.id === seat.id}
                >
                  <EventBubble event={seat.lastEvent} />
                  <div className="office-desk">
                    <span className="office-monitor"><Monitor size={21} /></span>
                    <span className="office-employee"><UserRound size={22} /></span>
                  </div>
                  <span className="office-seat__name">{seat.name}</span>
                  <span className="office-seat__role">{seat.businessRole || listText(seat.roleIds)}</span>
                  <span className="office-seat__status"><i aria-hidden="true" />{STATUS_LABEL[seat.status] || seat.status}</span>
                  <span className={`office-truth office-truth--${(disconnected ? "UNCONNECTED" : seat.truthState.status).toLowerCase()}`}>{disconnected ? "UNCONNECTED" : seat.truthState.status}</span>
                </button>
              ))}
            </div>
          ) : <div className="office-empty">当前任务还没有服务端计划节点。</div>}

          <section className="office-artifact-shelf" aria-label="工件交接带">
            <div><FileText size={18} /><strong>工件交接</strong><span>{projection.artifacts.length}</span></div>
            <ul>{projection.artifacts.length ? projection.artifacts.map((artifact) => <li key={artifact.id || artifact.title}><FileText size={14} /><span>{artifact.title || artifact.id}</span><small>{artifact.kind || artifact.source_kind || "artifact"}</small></li>) : <li className="office-artifact-shelf__empty">尚无服务端工件</li>}</ul>
          </section>
        </div>
        <EmployeeConsole seat={selectedSeat} truthOverride={disconnected ? "UNCONNECTED" : ""} />
      </div>
    </section>
  );
}

export default function ProjectOfficeView(props) {
  return <ReferenceOfficeView {...props} />;
}
