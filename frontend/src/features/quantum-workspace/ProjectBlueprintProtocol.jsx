import { Braces } from "lucide-react";
import { useEffect, useRef } from "react";

export function ProjectBlueprintProtocol({ protocol, complete = false, dispatchable = complete }) {
  const protocolRef = useRef(null);
  useEffect(() => {
    const element = protocolRef.current;
    if (!element || complete) return;
    element.scrollTo({ top: element.scrollHeight, behavior: "auto" });
  }, [protocol, complete]);
  if (!protocol) return null;
  return <section className={`qw-blueprint-protocol ${complete ? "complete" : "draft"}`} aria-label={complete ? "完整结构化协议" : "结构化协议草稿"}>
    <header>
      <span><Braces size={14} />结构化协议</span>
      <small>{complete ? (dispatchable ? "完整 · 可派发" : "协议完整 · 等待本轮确认") : "实时草稿 · 可能不完整"}</small>
    </header>
    <pre ref={protocolRef} aria-live="polite"><code>{protocol}</code></pre>
  </section>;
}