import { Check } from "lucide-react";

const normalizedChoice = (choice) => typeof choice === "string"
  ? { label: choice, value: choice }
  : { label: choice?.label || choice?.value || "选项", value: choice?.value || choice?.label || "" };

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
  const choices = (clarification.choices || []).map(normalizedChoice);
  return <section className="qw-clarification" aria-live="assertive" aria-labelledby={questionId}>
    <div><small>AI 需要补充信息</small><strong id={questionId}>{clarification.question}</strong><span>{continuationLabel}</span></div>
    {!!choices.length && <div className="qw-clarification-choices">{choices.map((choice) => {
      const selected = selections.includes(choice.value);
      return <button type="button" key={choice.value} aria-pressed={selected} disabled={busy} onClick={() => clarification.multi_select ? onSelectionsChange(selected ? selections.filter((value) => value !== choice.value) : [...selections, choice.value]) : onSubmit(choice.value)}>{selected && <Check size={13} />}{choice.label}</button>;
    })}</div>}
    {clarification.multi_select && <button type="button" className="qw-button primary qw-clarification-submit" disabled={busy || !selections.length} onClick={() => onSubmit()}>提交所选答案</button>}
    {!choices.length && <form onSubmit={(event) => { event.preventDefault(); onSubmit(); }}><label htmlFor={responseId}>你的回答</label><textarea id={responseId} rows={3} value={responseText} onChange={(event) => onResponseTextChange(event.target.value)} disabled={busy} autoFocus /><button type="submit" className="qw-button primary" disabled={busy || !responseText.trim()}>{busy ? "提交中…" : "继续"}</button></form>}
  </section>;
}
