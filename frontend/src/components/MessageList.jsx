export function MessageList({ messages, isThinking }) {
  return (
    <div className="message-list">
      {messages.map((message) => (
        <article key={message.id} className={`message-bubble message-bubble--${message.role}`}>
          <span className="message-bubble__role">{message.role === "assistant" ? "AI" : "你"}</span>
          <p>{message.content}</p>
        </article>
      ))}

      {isThinking && (
        <article className="message-bubble message-bubble--assistant message-bubble--thinking">
          <span className="message-bubble__role">AI</span>
          <div className="thinking-line">
            <span className="thinking-dot" />
            <span className="thinking-dot" />
            <span className="thinking-dot" />
          </div>
          <p>正在调用 ai-lab-platform，并生成一支可协同的角色团队…</p>
        </article>
      )}
    </div>
  );
}
