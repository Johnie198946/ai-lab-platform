import { Check } from "lucide-react";
import { composeClarificationResponse, isOtherClarificationChoice, normalizedClarificationChoice } from "./hermesClarification.js";

export function HermesClarificationCard({
  clarification,
  busy,
  responseText,
  onResponseTextChange,
  selections,
  onSelectionsChange,
  onSubmit,
  idPrefix = "hermes-clarification",
  continuationLabel = "回答后，Hermes 会继续处理。",
  clock = Date.now(),
}) {
  if (!clarification) return null;
  const questionId = `${idPrefix}-question`;
  const responseId = `${idPrefix}-response`;
  const choices = (clarification.choices || []).map(normalizedClarificationChoice);
  const otherSelected = choices.some((choice) => selections.includes(choice.value) && isOtherClarificationChoice(choice));
  const composedResponse = composeClarificationResponse(choices, selections, responseText);
  const remainingSeconds = clarification.expiresAt
    ? Math.max(0, Math.ceil((clarification.expiresAt - clock) / 1000))
    : null;
  const remainingLabel = remainingSeconds === null
    ? ""
    : `${Math.floor(remainingSeconds / 60)}:${String(remainingSeconds % 60).padStart(2, "0")}`;
  return <section className="qw-clarification" aria-live="assertive" aria-labelledby={questionId}>
    <div><small>AI 需要补充信息{remainingLabel && <time> · 剩余 {remainingLabel}</time>}</small><strong id={questionId}>{clarification.question}</strong><span>{continuationLabel}</span></div>
    {!!choices.length && <div className="qw-clarification-choices">{choices.map((choice) => {
      const selected = selections.includes(choice.value);
      return <button type="button" key={choice.value} aria-pressed={selected} disabled={busy} onClick={() => {
        if (clarification.multi_select) {
          onSelectionsChange(selected ? selections.filter((value) => value !== choice.value) : [...selections, choice.value]);
        } else if (isOtherClarificationChoice(choice)) {
          onSelectionsChange([choice.value]);
        } else {
          onSelectionsChange([choice.value]);
        }
      }}>{selected && <Check size={13} />}{choice.label}</button>;
    })}</div>}
    <form onSubmit={(event) => { event.preventDefault(); onSubmit(composedResponse); }}><label htmlFor={responseId}>{otherSelected ? "请补充具体信息" : choices.length ? "补充回答（也可以完全自行输入）" : "你的回答"}</label><textarea id={responseId} rows={3} value={responseText} onChange={(event) => onResponseTextChange(event.target.value)} disabled={busy} autoFocus aria-describedby={`${responseId}-hint`} placeholder={choices.length ? "可选择上方建议，也可以在这里直接输入你的答案" : "请输入你的答案"} /><span id={`${responseId}-hint`} className="qw-clarification-hint">选项仅作辅助；你输入的内容会与已选信息一起交给 Hermes 继续收敛。</span><button type="submit" className="qw-button primary" disabled={busy || !composedResponse}>{busy ? "提交中…" : "提交并继续"}</button></form>
  </section>;
}
