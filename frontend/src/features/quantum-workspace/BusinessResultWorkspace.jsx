import { useEffect, useMemo, useRef, useState } from "react";
import { platformApi } from "../../services/platformApi";

const RESULT_STATES = {
  loading: "正在读取可核验运行记录",
  empty: "当前 Workflow 还没有可查看的真实执行记录",
  error: "暂时无法读取运行结果",
  unauthorized: "你没有查看此执行结果的权限",
  running: "真实执行仍在进行，目前只能确认已记录到的步骤",
  unsupported: "暂无可核验仿真来源",
  awaiting_review: "真实执行已形成待复核材料，业务判断尚未完成",
  completed: "已形成可供业务复核的结果与证据",
};

const TRUTH_COPY = {
  LIVE: "真实执行中",
  REPLAY: "已记录的真实执行",
  UNCONNECTED: "暂无可核验结果",
};

function displayState(execution, summary) {
  if (!execution) return "empty";
  if (String(execution.status).toLowerCase() === "simulation") return "unsupported";
  if (summary?.truth_mode === "UNCONNECTED") return "unsupported";
  if (execution.status === "running") return "running";
  if (execution.status === "awaiting_review") return "awaiting_review";
  return "completed";
}

function StatePanel({ state, message }) {
  return <section className={`qw-result-state is-${state}`} role="status" aria-live="polite" aria-atomic="true">
    <strong>{RESULT_STATES[state]}</strong>
    {message && <p>{message}</p>}
  </section>;
}

function ClaimList({ items, empty }) {
  if (!items?.length) return <p className="qw-result-muted">{empty}</p>;
  return <ul className="qw-result-claims">{items.map((item, index) =>
    <li key={`${item.text}-${index}`}><span>{item.text}</span><small>{item.support_status === "SUPPORTED" ? "有记录支持" : "证据不足"}</small></li>
  )}</ul>;
}

function TextList({ items, empty }) {
  if (!items?.length) return <p className="qw-result-muted">{empty}</p>;
  return <ul className="qw-result-text-list">{items.map((item, index) => <li key={`${item}-${index}`}>{item}</li>)}</ul>;
}

export function BusinessResultWorkspace({ projectId }) {
  const [catalog, setCatalog] = useState(null);
  const [workflowId, setWorkflowId] = useState("");
  const [executionId, setExecutionId] = useState("");
  const [summary, setSummary] = useState(null);
  const [state, setState] = useState("loading");
  const [message, setMessage] = useState("");
  const requestSerialRef = useRef(0);

  useEffect(() => {
    const controller = new AbortController();
    const serial = ++requestSerialRef.current;
    setState("loading");
    setSummary(null);
    platformApi.listProjectWorkflowExecutions(projectId, { signal: controller.signal })
      .then((result) => {
        if (serial !== requestSerialRef.current) return;
        const workflows = result?.workflows || [];
        setCatalog(result);
        const initialWorkflow = workflows[0];
        setWorkflowId(initialWorkflow?.id || "");
        setExecutionId(initialWorkflow?.executions?.[0]?.id || "");
        if (!initialWorkflow?.executions?.length) setState("empty");
      })
      .catch((reason) => {
        if (controller.signal.aborted || serial !== requestSerialRef.current) return;
        setSummary(null);
        setCatalog(null);
        setState([401, 403].includes(reason.status) ? "unauthorized" : "error");
        setMessage([401, 403].includes(reason.status) ? "请联系项目管理员确认项目读取权限。" : "未据此生成结论，请稍后再试。" );
      });
    return () => controller.abort();
  }, [projectId]);

  const workflows = catalog?.workflows || [];
  const selectedWorkflow = workflows.find((item) => item.id === workflowId) || null;
  const executions = selectedWorkflow?.executions || [];
  const selectedExecution = executions.find((item) => item.id === executionId) || null;

  useEffect(() => {
    if (!executionId) return;
    const controller = new AbortController();
    const serial = ++requestSerialRef.current;
    setState("loading");
    setMessage("");
    setSummary(null);
    platformApi.getProjectBusinessResultSummary(projectId, executionId, { signal: controller.signal })
      .then((result) => {
        if (serial !== requestSerialRef.current) return;
        setSummary(result);
        setState(displayState(selectedExecution, result));
      })
      .catch((reason) => {
        if (controller.signal.aborted || serial !== requestSerialRef.current) return;
        setSummary(null);
        const unauthorized = [401, 403].includes(reason.status);
        setState(unauthorized ? "unauthorized" : "error");
        setMessage(unauthorized ? "请联系项目管理员确认项目读取权限。" : "未据此生成结论，请稍后再试。");
      });
    return () => controller.abort();
  }, [executionId, projectId, selectedExecution]);

  const truth = summary?.truth_mode || "UNCONNECTED";
  const evidence = summary?.evidence || [];
  const executionLabel = useMemo(() => {
    const index = executions.findIndex((item) => item.id === executionId);
    return index >= 0 ? `执行 ${index + 1}` : "未选择执行";
  }, [executionId, executions]);

  const chooseWorkflow = (event) => {
    const nextId = event.target.value;
    const nextWorkflow = workflows.find((item) => item.id === nextId);
    setWorkflowId(nextId);
    setExecutionId(nextWorkflow?.executions?.[0]?.id || "");
    setSummary(null);
    if (!nextWorkflow?.executions?.length) setState("empty");
  };

  return <main className="qw-result-workspace" id="business-result-main">
    <header className="qw-result-head">
      <div><span className="qw-eyebrow">Business Result Workspace</span><h2>运行与结果</h2><p>只读查看当前项目已绑定 Workflow 的可核验执行记录。</p></div>
      <span className={`qw-result-truth is-${truth.toLowerCase()}`}>{truth}<small>{TRUTH_COPY[truth]}</small></span>
    </header>

    <section className="qw-result-context" aria-label="执行上下文">
      <label><span>Workflow</span><select value={workflowId} onChange={chooseWorkflow} disabled={!workflows.length}>
        {!workflows.length && <option value="">暂无项目绑定 Workflow</option>}
        {workflows.map((item) => <option key={item.id} value={item.id}>{item.title}</option>)}
      </select></label>
      <label><span>Execution</span><select value={executionId} onChange={(event) => setExecutionId(event.target.value)} disabled={!executions.length}>
        {!executions.length && <option value="">暂无执行记录</option>}
        {executions.map((item, index) => <option key={item.id} value={item.id}>执行 {index + 1} · {item.status}</option>)}
      </select></label>
      <div><span>当前记录</span><strong>{selectedWorkflow?.title || "未选择 Workflow"}</strong><small>{executionLabel}</small></div>
    </section>

    {state === "loading" && <StatePanel state="loading" />}
    {state === "empty" && <StatePanel state="empty" message="产生真实执行记录后，可在这里按 Workflow 与 Execution 明确切换查看。" />}
    {state === "error" && <StatePanel state="error" message={message} />}
    {state === "unauthorized" && <StatePanel state="unauthorized" message={message} />}
    {state === "unsupported" && <StatePanel state="unsupported" message="UNCONNECTED · 暂无可核验结果" />}

    {summary && !["loading", "error", "unauthorized"].includes(state) && <div className="qw-result-body" aria-live="polite">
      <section className="qw-result-conclusion"><span>一句话结论</span><h3>{summary.one_sentence_conclusion?.text}</h3><small>{summary.one_sentence_conclusion?.support_status === "SUPPORTED" ? "由当前直接记录支持" : "需要更多证据"}</small></section>
      <div className="qw-result-grid">
        <section><h3>发生了什么</h3><ClaimList items={summary.what_happened} empty="尚无执行记录。" /></section>
        <section><h3>业务影响</h3><ClaimList items={summary.business_impact} empty="业务影响尚无法判断。" /></section>
        <section><h3>风险与限制</h3><TextList items={summary.risks_and_limitations} empty="当前没有新增风险记录。" /></section>
        <section><h3>下一步</h3><TextList items={(summary.recommended_next_steps || []).slice(0, 3)} empty="暂无建议。" /></section>
      </div>
      <section className="qw-result-evidence"><header><div><h3>直接证据</h3><p>仅展示本次 Execution 查询得到的持久记录。</p></div><span>{evidence.length} 条</span></header>
        {evidence.length ? <ol>{evidence.map((item) => <li key={item.evidence_id}><div><strong>{item.title}</strong><p>{item.text}</p></div><small>{item.kind} · {item.verification_status}</small></li>)}</ol> : <p className="qw-result-muted">尚无可核验直接证据。</p>}
      </section>
      <details className="qw-result-technical"><summary>技术记录</summary><dl>
        {Object.entries(summary.technical_facts_ref || {}).map(([key, value]) => <div key={key}><dt>{key}</dt><dd>{typeof value === "object" ? JSON.stringify(value) : String(value ?? "—")}</dd></div>)}
        <div><dt>source_digest</dt><dd>{summary.source_digest}</dd></div>
        <div><dt>summary_id</dt><dd>{summary.summary_id}</dd></div>
      </dl></details>
    </div>}
  </main>;
}
