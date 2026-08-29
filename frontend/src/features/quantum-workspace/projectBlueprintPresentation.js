const BLUEPRINT_FENCE = /```project_blueprint\b/i;

const uniqueText = (values = []) => [...new Set(values.map((value) => String(value || "").trim()).filter(Boolean))];

export const extractProjectBlueprint = (content = "") => {
  const source = String(content || "");
  const match = BLUEPRINT_FENCE.exec(source);
  if (!match) return null;
  const payloadStart = match.index + match[0].length;
  const payloadEnd = source.indexOf("```", payloadStart);
  if (payloadEnd < 0) return null;
  try {
    const blueprint = JSON.parse(source.slice(payloadStart, payloadEnd).trim());
    return blueprint && typeof blueprint === "object" && !Array.isArray(blueprint) ? blueprint : null;
  } catch {
    return null;
  }
};

export const summarizeProjectBlueprint = (blueprint) => {
  if (!blueprint) return "";
  const stages = Array.isArray(blueprint.stages) ? blueprint.stages : [];
  const tasks = Array.isArray(blueprint.tasks) ? blueprint.tasks : [];
  const documents = Array.isArray(blueprint.documents) ? blueprint.documents : [];
  const stageNames = uniqueText(stages.map((stage) => stage?.name || stage?.key));
  const roles = uniqueText(tasks.map((task) => task?.role));
  const deliverables = uniqueText(tasks.flatMap((task) => Array.isArray(task?.deliverables) ? task.deliverables : []));
  const documentTitles = uniqueText(documents.map((document) => document?.title));
  const acceptanceCriteria = uniqueText(stages.flatMap((stage) => Array.isArray(stage?.acceptance_criteria) ? stage.acceptance_criteria : []));
  const lines = [`项目蓝图已经整理完成，共 ${stages.length} 个阶段、${tasks.length} 项任务${documents.length ? `和 ${documents.length} 份项目文档` : ""}。`];

  if (blueprint.project_goal) lines.push(`项目目标：${String(blueprint.project_goal).trim()}`);
  if (stageNames.length) lines.push(`执行流程：${stageNames.join(" → ")}。`);
  const stageTaskLines = stages.map((stage, index) => {
    const stageKey = stage?.key;
    const taskTitles = uniqueText(tasks.filter((task) => task?.stage_key === stageKey).map((task) => task?.title));
    return taskTitles.length ? `${index + 1}. ${stage?.name || stageKey}：${taskTitles.join("、")}。` : "";
  }).filter(Boolean);
  if (stageTaskLines.length) lines.push(`阶段安排：\n${stageTaskLines.join("\n")}`);
  if (roles.length) lines.push(`计划由${roles.join("、")}等角色协作完成。`);
  if (acceptanceCriteria.length) lines.push(`关键验收：${acceptanceCriteria.slice(0, 6).join("；")}${acceptanceCriteria.length > 6 ? "等" : ""}。`);
  if (deliverables.length) lines.push(`主要交付物：${deliverables.slice(0, 6).join("、")}${deliverables.length > 6 ? "等" : ""}。`);
  if (documentTitles.length) lines.push(`同步生成文档：${documentTitles.slice(0, 6).join("、")}${documentTitles.length > 6 ? "等" : ""}。`);
  lines.push("详细任务、验收标准和依赖关系已经保存在蓝图中，确认后即可派发。");
  return lines.join("\n");
};

export const projectPlanningVisibleAnswer = (content = "", { pending = false } = {}) => {
  const source = String(content || "");
  const match = BLUEPRINT_FENCE.exec(source);
  if (!match) return source.trim();

  const naturalReply = source.slice(0, match.index).trim();
  const blueprint = extractProjectBlueprint(source);
  if (blueprint) return [naturalReply, summarizeProjectBlueprint(blueprint)].filter(Boolean).join("\n\n");
  if (naturalReply) return naturalReply;
  return pending ? "项目蓝图正在整理中，结构化协议已隐藏。" : "项目蓝图已返回，正在整理为可读摘要。";
};
