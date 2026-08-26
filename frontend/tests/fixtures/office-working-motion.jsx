import React from "react";
import { createRoot } from "react-dom/client";
import CharacterDesk from "../../src/features/project-office/reference/CharacterDesk";
import "../../src/features/project-office/reference/reference-office.css";
import "../../src/features/project-office/ReferenceOfficeView.css";

const examples = [
  ["working", "运行中：持续工作动效", "#5dbe6e", "code"],
  ["sleeping", "等待中：静态休息", "#9b7fea", "typing"],
  ["done", "已完成：稳定完成态", "#4a9eed", "analytics"],
];

createRoot(document.getElementById("root")).render(examples.map(([state, label, color, screenType]) => (
  <article key={state} data-fixture-state={state}>
    <div className="fixture-character"><CharacterDesk color={color} state={state} screenType={screenType} /></div>
    <strong>{label}</strong>
  </article>
)));
