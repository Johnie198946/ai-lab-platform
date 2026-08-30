export const normalizedClarificationChoice = (choice) => typeof choice === "string"
  ? { label: choice, value: choice }
  : { label: choice?.label || choice?.value || "选项", value: choice?.value || choice?.label || "" };

export const isOtherClarificationChoice = (choice) => /^(other|其他|其它|自定义)(?:\s*[（(].*[）)])?$/i.test(
  String(choice?.value || choice?.label || choice || "").trim(),
);

export const composeClarificationResponse = (choices, selections, responseText) => {
  const selected = (selections || []).map((value) => choices.find((choice) => choice.value === value)).filter(Boolean);
  const regular = selected.filter((choice) => !isOtherClarificationChoice(choice)).map((choice) => choice.label);
  const includesOther = selected.some(isOtherClarificationChoice);
  const detail = String(responseText || "").trim();
  return [
    ...regular,
    ...(detail ? [`${includesOther ? "其他" : regular.length ? "补充" : "回答"}：${detail}`] : []),
  ].join("；");
};
