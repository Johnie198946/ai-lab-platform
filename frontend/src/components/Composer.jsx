export function Composer({
  input,
  isThinking,
  submitError,
  onChange,
  onKeyDown,
  onSubmit,
}) {
  return (
    <div className="composer">
      {submitError && <div className="integration-banner integration-banner--error">{submitError}</div>}

      <div className="composer__promptline">
        <span className="signal-pill">产品上市</span>
        <span className="signal-pill">营销全链路</span>
        <span className="signal-pill">6 角色协同</span>
      </div>

      <textarea
        value={input}
        onChange={(event) => onChange(event.target.value)}
        onKeyDown={onKeyDown}
        placeholder="例如：为 FusionOne AI 23.8.0 新品上市生成 6 角色协同方案，覆盖市场洞察、开发、营销和销售交付。"
        rows={4}
      />

      <div className="composer__actions">
        <span>支持 `⌘ / Ctrl + Enter` 快速发送</span>
        <button type="button" onClick={onSubmit} disabled={isThinking}>
          {isThinking ? "角色编排中..." : "生成 6 角色"}
        </button>
      </div>
    </div>
  );
}
