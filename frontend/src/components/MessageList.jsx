export function MessageList({ messages, isThinking }) {
  return (
    <div className="message-list">
      {messages.map((message, index) => (
        <article key={message.id} className={`message-bubble message-bubble--${message.role}`}>
          <div className="message-bubble__meta">
            <span className="message-bubble__role">{message.role === "assistant" ? "数字人" : "你"}</span>
            <span className="message-bubble__index">{String(index + 1).padStart(2, "0")}</span>
          </div>
          <p>{message.content}</p>
        </article>
      ))}

      {isThinking && (
        <article className="message-bubble message-bubble--assistant message-bubble--thinking">
          <div className="message-bubble__meta">
            <span className="message-bubble__role">数字人</span>
            <span className="message-bubble__index">SSE</span>
          </div>
          <div className="thinking-line">
            <span className="thinking-dot" />
            <span className="thinking-dot" />
            <span className="thinking-dot" />
          </div>
          <p>正在调用 ai-lab-platform，并按协议生成 6 个可协同角色与关键页面壳体…</p>
        </article>
      )}
    </div>
  );
}
