import { Check, ClipboardList, Sparkles, X } from "lucide-react";
import { useState } from "react";
import { platformApi } from "../../services/platformApi";

export function BusinessIntakePanel({ project, process, onApplied }) {
  const [open, setOpen] = useState(!process?.process_instance_id);
  const [draft, setDraft] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [form, setForm] = useState({
    business_goal: project?.goal ?? "",
    customers_and_scenarios: "",
    product_scope: "",
    product_form: "software",
    innovation_level: "new_product",
    tailoring_level: "standard",
    requirements_and_evidence: "",
    desired_deliverables: "产品包、架构基线、验证报告",
    target_finish_at: "",
  });
  const update = (key, value) => setForm((current) => ({ ...current, [key]: value }));

  const generate = async (event) => {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const intake = await platformApi.createBusinessIntake(project.id, {
        request_id: `ui-intake-${crypto.randomUUID()}`,
        ...form,
        desired_deliverables: form.desired_deliverables.split(/[、,，]/).map((item) => item.trim()).filter(Boolean),
        target_finish_at: `${form.target_finish_at}T00:00:00Z`,
      });
      const result = await platformApi.generateProcessDraft(project.id, {
        request_id: `ui-draft-${crypto.randomUUID()}`,
        business_intake_id: intake.id,
        process_template_id: "ipd-product-development",
        process_template_version: "1.0.0",
        catalog_revision: "catalog-current",
      });
      setDraft(result);
    } catch (reason) {
      setError(reason.message);
    } finally {
      setBusy(false);
    }
  };

  const apply = async () => {
    setBusy(true);
    setError("");
    try {
      await platformApi.applyProcessDraft(project.id, draft.id, {
        request_id: `ui-apply-${crypto.randomUUID()}`,
        expected_revision: process?.process_revision ?? 0,
        draft_revision: draft.revision,
      });
      setOpen(false);
      setDraft(null);
      await onApplied();
    } catch (reason) {
      setError(reason.message);
    } finally {
      setBusy(false);
    }
  };

  if (!open) return <button className="qw-intake-trigger" onClick={() => setOpen(true)}><ClipboardList size={17} /><span><strong>Business Intake</strong><small>生成新的流程草案</small></span></button>;
  return (
    <aside className="qw-intake-panel">
      <div className="qw-panel-title"><div><span className="qw-eyebrow">Review first</span><h3>Business Intake</h3></div>{process?.process_instance_id && <button onClick={() => setOpen(false)} aria-label="关闭"><X size={17} /></button>}</div>
      {!draft ? (
        <form onSubmit={generate} className="qw-intake-form">
          <label>业务目标<textarea rows={3} value={form.business_goal} onChange={(e) => update("business_goal", e.target.value)} required /></label>
          <label>客户与场景<textarea rows={2} value={form.customers_and_scenarios} onChange={(e) => update("customers_and_scenarios", e.target.value)} required /></label>
          <label>产品范围<input value={form.product_scope} onChange={(e) => update("product_scope", e.target.value)} placeholder="全新产品 / 重大升级" required /></label>
          <div className="qw-form-row"><label>产品形态<select value={form.product_form} onChange={(e) => update("product_form", e.target.value)}><option value="software">软件</option><option value="hardware">硬件</option><option value="integrated">软硬一体</option><option value="service">服务 / 解决方案</option></select></label><label>创新程度<select value={form.innovation_level} onChange={(e) => update("innovation_level", e.target.value)}><option value="new_product">全新产品</option><option value="major_upgrade">重大升级</option><option value="routine_update">常规迭代</option></select></label></div>
          <label>裁剪级别<select value={form.tailoring_level} onChange={(e) => update("tailoring_level", e.target.value)}><option value="full">完整</option><option value="standard">标准</option><option value="lite">轻量</option></select></label>
          <label>需求与证据<textarea rows={3} value={form.requirements_and_evidence} onChange={(e) => update("requirements_and_evidence", e.target.value)} required /></label>
          <label>期望交付物<input value={form.desired_deliverables} onChange={(e) => update("desired_deliverables", e.target.value)} required /></label>
          <label>目标完成日期<input type="date" value={form.target_finish_at} onChange={(e) => update("target_finish_at", e.target.value)} required /></label>
          {error && <p className="qw-error">{error}</p>}
          <button className="qw-button primary wide" disabled={busy}><Sparkles size={15} />{busy ? "生成中…" : "生成 ProcessDraft"}</button>
        </form>
      ) : (
        <div className="qw-draft-review">
          <span className="qw-chip warning">AI_PROPOSED · 待人工复核</span>
          <h4>IPD v{draft.process.template_version}</h4>
          <div className="qw-review-stats"><span><strong>{draft.process.stages.length}</strong>阶段</span><span><strong>{draft.process.gates.length}</strong>TR/DCP</span><span><strong>{draft.process.tasks.length}</strong>任务</span></div>
          <ol>{draft.process.stages.map((stage) => <li key={stage.id}><span>{stage.name}</span><small>{draft.process.gates.filter((gate) => gate.stage_id === stage.id).map((gate) => gate.name).join(" · ") || "无 Gate"}</small></li>)}</ol>
          <p className="qw-note">Agent 候选当前均为 UNAVAILABLE；应用草案不会自动执行 Workflow，也不会代签 DCP。</p>
          {error && <p className="qw-error">{error}</p>}
          <div className="qw-actions"><button className="qw-button ghost" onClick={() => setDraft(null)}>返回修改</button><button className="qw-button primary" onClick={apply} disabled={busy}><Check size={15} />{busy ? "应用中…" : "确认并实例化"}</button></div>
        </div>
      )}
    </aside>
  );
}
