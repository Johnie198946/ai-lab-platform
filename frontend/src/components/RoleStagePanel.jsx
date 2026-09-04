function OutputSection({ section }) {
  if (section.type === "text") {
    return (
      <article className="protocol-section-card">
        <div className="protocol-section-card__header">
          <span className="section-label">Text</span>
          <h4>{section.title}</h4>
        </div>
        <p>{section.content}</p>
      </article>
    );
  }

  if (section.type === "cards") {
    return (
      <article className="protocol-section-card">
        <div className="protocol-section-card__header">
          <span className="section-label">Cards</span>
          <h4>{section.title}</h4>
        </div>
        <div className="protocol-card-grid">
          {section.items.map((item) => (
            <div key={item.title} className="protocol-mini-card">
              <strong>{item.title}</strong>
              <p>{item.body}</p>
            </div>
          ))}
        </div>
      </article>
    );
  }

  if (section.type === "table") {
    return (
      <article className="protocol-section-card">
        <div className="protocol-section-card__header">
          <span className="section-label">Table</span>
          <h4>{section.title}</h4>
        </div>
        <div className="protocol-table-wrap">
          <table className="protocol-table">
            <thead>
              <tr>
                {section.columns.map((column) => (
                  <th key={column}>{column}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {section.rows.map((row) => (
                <tr key={row.join("-")}>
                  {row.map((cell) => (
                    <td key={cell}>{cell}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </article>
    );
  }

  if (section.type === "chart") {
    return (
      <article className="protocol-section-card">
        <div className="protocol-section-card__header">
          <span className="section-label">Chart</span>
          <h4>{section.title}</h4>
        </div>
        <div className="protocol-chart-list">
          {section.items.map((item) => (
            <div key={item.label} className="protocol-chart-row">
              <div className="protocol-chart-row__meta">
                <span>{item.label}</span>
                <strong>{item.value}%</strong>
              </div>
              <div className="protocol-chart-row__track">
                <span style={{ width: `${item.value}%` }} />
              </div>
            </div>
          ))}
        </div>
      </article>
    );
  }

  return null;
}

function StreamBlock({ stream }) {
  if (stream.type === "progress") {
    return (
      <article className="protocol-stream">
        <div className="protocol-stream__header">
          <div>
            <span className="section-label">{stream.hint}</span>
            <h4>{stream.title}</h4>
          </div>
        </div>
        <div className="protocol-stream-list">
          {stream.items.map((item) => (
            <div key={item.label} className="protocol-stream-item">
              <div className="protocol-stream-item__meta">
                <strong>{item.label}</strong>
                <span>{item.meta}</span>
              </div>
              <div className="protocol-stream-item__track">
                <span style={{ width: `${item.progress}%` }} />
              </div>
              <em>{item.progress}%</em>
            </div>
          ))}
        </div>
      </article>
    );
  }

  if (stream.type === "pipeline") {
    return (
      <article className="protocol-stream">
        <div className="protocol-stream__header">
          <div>
            <span className="section-label">{stream.hint}</span>
            <h4>{stream.title}</h4>
          </div>
        </div>
        <div className="protocol-pipeline">
          {stream.items.map((item) => (
            <div
              key={item.label}
              className={`protocol-pipeline__node protocol-pipeline__node--${item.state}`}
            >
              <span className="protocol-pipeline__dot" />
              <strong>{item.label}</strong>
            </div>
          ))}
        </div>
      </article>
    );
  }

  if (stream.type === "decision") {
    return (
      <article className="protocol-stream">
        <div className="protocol-stream__header">
          <div>
            <span className="section-label">{stream.hint}</span>
            <h4>{stream.title}</h4>
          </div>
        </div>
        <div className="protocol-decision-card">
          <strong>{stream.decision.title}</strong>
          <p>{stream.decision.message}</p>
          <button type="button" className="protocol-action protocol-action--ghost">
            {stream.decision.cta}
          </button>
        </div>
      </article>
    );
  }

  if (stream.type === "cards") {
    return (
      <article className="protocol-stream">
        <div className="protocol-stream__header">
          <div>
            <span className="section-label">{stream.hint}</span>
            <h4>{stream.title}</h4>
          </div>
        </div>
        <div className="protocol-card-grid">
          {stream.items.map((item) => (
            <div key={item.title} className="protocol-mini-card">
              <strong>{item.title}</strong>
              <p>{item.body}</p>
            </div>
          ))}
        </div>
      </article>
    );
  }

  return null;
}

export function RoleStagePanel({ role }) {
  // Simplified: no longer uses hardcoded protocolShells
  const shell = {
    stage: "等待上游输入",
    status: "待触发",
    emphasis: "等待前序角色完成后进入当前阶段",
    summary: "当前角色暂不展示关键流程页壳体。你仍然可以编辑角色职责、技能和名字。",
    metrics: [
      { label: "当前模式", value: "待机" },
      { label: "依赖关系", value: "上游完成后唤起" },
      { label: "输出形态", value: "JSON + Word" },
    ],
    streams: [],
    sections: [
      {
        title: "统一协议",
        type: "text",
        content: "角色页面遵循统一规律：过程使用 SSE 流驱动，结果使用 JSON 渲染，下载使用 Word 链接承接。",
      },
    ],
    actions: [{ label: "继续编辑当前角色", kind: "primary" }],
    focus: role?.focus || "",
  };

  return (
    <section className="protocol-shell">
      <div className="protocol-shell__header">
        <div>
          <div className="eyebrow">
            <span className="eyebrow__dot" />
            {shell.stage}
          </div>
          <h3>{role ? `${role.title} 关键角色页` : "关键角色页"}</h3>
          <p>{shell.summary}</p>
        </div>
        <div className="protocol-shell__meta">
          <span className="signal-pill">{shell.status}</span>
          <span className="signal-pill">{shell.emphasis}</span>
          {shell.focus ? <span className="signal-pill">{shell.focus}</span> : null}
        </div>
      </div>

      <div className="protocol-metrics">
        {shell.metrics.map((metric) => (
          <div key={metric.label} className="status-card">
            <span className="status-card__label">{metric.label}</span>
            <strong>{metric.value}</strong>
          </div>
        ))}
      </div>

      <div className="protocol-layout">
        <div className="protocol-layout__streams">
          <div className="protocol-layout__title">
            <span className="section-label">Process</span>
            <h4>过程动效区</h4>
          </div>
          <div className="protocol-stream-grid">
            {shell.streams.map((stream) => (
              <StreamBlock key={stream.title} stream={stream} />
            ))}
          </div>
        </div>

        <div className="protocol-layout__results">
          <div className="protocol-layout__title">
            <span className="section-label">Result</span>
            <h4>结果渲染区</h4>
          </div>
          <div className="protocol-results">
            {shell.sections.map((section) => (
              <OutputSection key={section.title} section={section} />
            ))}
          </div>
        </div>
      </div>

      <div className="protocol-actions">
        {shell.actions.map((action) =>
          action.kind === "link" ? (
            <a
              key={action.label}
              className="protocol-action"
              href={action.href}
              download
            >
              {action.label}
            </a>
          ) : (
            <button
              key={action.label}
              type="button"
              className={`protocol-action ${
                action.kind === "secondary" ? "protocol-action--ghost" : ""
              }`}
            >
              {action.label}
            </button>
          ),
        )}
      </div>
    </section>
  );
}
