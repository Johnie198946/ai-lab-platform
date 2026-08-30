import { CheckCircle2, FileText, GitBranch, RefreshCw, Users } from "lucide-react";
import { ProjectBlueprintProtocol } from "./ProjectBlueprintProtocol";

const unique = (values = []) => [...new Set(values.map((value) => String(value || "").trim()).filter(Boolean))];

export function ProjectBlueprintReview({ blueprint, version, current = false, dispatchable = false }) {
  const stages = Array.isArray(blueprint?.stages) ? blueprint.stages : [];
  const tasks = Array.isArray(blueprint?.tasks) ? blueprint.tasks : [];
  const documents = Array.isArray(blueprint?.documents) ? blueprint.documents : [];
  const roles = unique(tasks.map((task) => task?.role));
  const acceptance = unique([
    ...stages.flatMap((stage) => stage?.acceptance_criteria || []),
    ...tasks.flatMap((task) => task?.acceptance_criteria || []),
  ]);
  return <section className={`qw-blueprint-review ${current ? "current" : "superseded"}`} aria-label={`需求收敛单 v${version}`}>
    <header>
      <div><span>需求收敛单</span><strong>v{version}</strong></div>
      <small>{current ? "当前待确认版本" : "已由后续版本替代"}</small>
    </header>
    {blueprint.project_goal && <div className="qw-blueprint-goal"><span>项目目标</span><p>{blueprint.project_goal}</p></div>}
    <div className="qw-blueprint-facts">
      <span><GitBranch size={14} />{stages.length} 个阶段</span>
      <span><CheckCircle2 size={14} />{tasks.length} 项任务</span>
      <span><Users size={14} />{roles.length} 类角色</span>
      <span><FileText size={14} />{documents.length} 份文档</span>
    </div>
    <ol className="qw-blueprint-stages">{stages.map((stage, index) => {
      const stageTasks = tasks.filter((task) => task?.stage_key === stage?.key);
      return <li key={stage?.key || index}>
        <span>{String(index + 1).padStart(2, "0")}</span>
        <div><strong>{stage?.name || stage?.key}</strong>{stage?.goal && <p>{stage.goal}</p>}<small>{stageTasks.map((task) => task?.title).filter(Boolean).join(" · ") || "该阶段尚无任务"}</small></div>
      </li>;
    })}</ol>
    {!!acceptance.length && <details><summary>查看关键验收标准（{acceptance.length}）</summary><ul>{acceptance.slice(0, 12).map((item) => <li key={item}>{item}</li>)}</ul></details>}
    <ProjectBlueprintProtocol protocol={JSON.stringify(blueprint, null, 2)} complete dispatchable={dispatchable} />
    {current && <p className="qw-blueprint-revise"><RefreshCw size={13} />不符合预期时，直接在下方粘贴你的流程或补充要求；Hermes 会基于 v{version} 合并修订并生成 v{version + 1}。</p>}
  </section>;
}
