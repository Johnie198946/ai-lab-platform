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

      <textarea
        value={input}
        onChange={(event) => onChange(event.target.value)}
        onKeyDown={onKeyDown}
        placeholder="例如：请帮我打造一个 AI 智能体编排平台，并协同完成营销与销售。"
        rows={3}
      />

      <div className="composer__actions">
        <span>⌘ / Ctrl + Enter 发送</span>
        <button type="button" onClick={onSubmit} disabled={isThinking}>
          {isThinking ? "编排中..." : "开始编排"}
        </button>
      </div>
    </div>
  );
}
