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
}) {
  if (!clarification) return null;
  const questionId = `${idPrefix}-question`;
  const responseId = `${idPrefix}-response`;
  const choices = (clarification.choices || []).map(normalizedClarificationChoice);
  const otherSelected = choices.some((choice) => selections.includes(choice.value) && isOtherClarificationChoice(choice));
  const showFreeText = !choices.length || otherSelected;
  const composedResponse = composeClarificationResponse(choices, selections, responseText);
  return <section className="qw-clarification" aria-live="assertive" aria-labelledby={questionId}>
    <div><small>AI 需要补充信息</small><strong id={questionId}>{clarification.question}</strong><span>{continuationLabel}</span></div>
    {!!choices.length && <div className="qw-clarification-choices">{choices.map((choice) => {
      const selected = selections.includes(choice.value);
      return <button type="button" key={choice.value} aria-pressed={selected} disabled={busy} onClick={() => {
        if (clarification.multi_select) {
          onSelectionsChange(selected ? selections.filter((value) => value !== choice.value) : [...selections, choice.value]);
        } else if (isOtherClarificationChoice(choice)) {
          onSelectionsChange([choice.value]);
        } else {
          onSelectionsChange([choice.value]);
          onSubmit(choice.label);
        }
      }}>{selected && <Check size={13} />}{choice.label}</button>;
    })}</div>}
    {clarification.multi_select && !otherSelected && <button type="button" className="qw-button primary qw-clarification-submit" disabled={busy || !selections.length} onClick={() => onSubmit(composeClarificationResponse(choices, selections, responseText))}>提交所选答案</button>}
    {showFreeText && <form onSubmit={(event) => { event.preventDefault(); onSubmit(choices.length ? composedResponse : responseText.trim()); }}><label htmlFor={responseId}>{otherSelected ? "请补充具体信息" : "你的回答"}</label><textarea id={responseId} rows={3} value={responseText} onChange={(event) => onResponseTextChange(event.target.value)} disabled={busy} autoFocus aria-describedby={`${responseId}-hint`} /><span id={`${responseId}-hint`} className="qw-clarification-hint">这段内容会原样交给 Hermes，并与已选信息一起继续收敛。</span><button type="submit" className="qw-button primary" disabled={busy || !responseText.trim()}>{busy ? "提交中…" : "提交并继续"}</button></form>}
  </section>;
}
