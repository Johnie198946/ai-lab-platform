const BLUEPRINT_FENCE = /```project_blueprint\b/i;
const GENERIC_JSON_FENCE = /```(?:json)?\s*\n/i;

const isBlueprintShape = (value) => value && typeof value === "object" && !Array.isArray(value)
  && Array.isArray(value.stages) && Array.isArray(value.tasks);

const parseBlueprintCandidate = (payload) => {
  try {
    const value = JSON.parse(payload.trim());
    return isBlueprintShape(value) ? value : null;
  } catch {
    return null;
  }
};

const locateBlueprintPayload = (source) => {
  for (const fence of [BLUEPRINT_FENCE, GENERIC_JSON_FENCE]) {
    fence.lastIndex = 0;
    const match = fence.exec(source);
    if (!match) continue;
    const payloadStart = match.index + match[0].length;
    const payloadEnd = source.indexOf("```", payloadStart);
    if (payloadEnd < 0) return { match, payloadStart, payloadEnd, blueprint: null, partial: true };
    const blueprint = parseBlueprintCandidate(source.slice(payloadStart, payloadEnd));
    if (blueprint || fence === BLUEPRINT_FENCE) return { match, payloadStart, payloadEnd, blueprint, partial: false };
  }
  const objectStart = source.indexOf("{");
  const objectEnd = source.lastIndexOf("}");
  if (objectStart >= 0 && objectEnd > objectStart) {
    const blueprint = parseBlueprintCandidate(source.slice(objectStart, objectEnd + 1));
    if (blueprint) return { match: { index: objectStart }, payloadStart: objectStart, payloadEnd: objectEnd + 1, blueprint, partial: false };
  }
  return null;
};

const uniqueText = (values = []) => [...new Set(values.map((value) => String(value || "").trim()).filter(Boolean))];

export const extractProjectBlueprint = (content = "") => {
  const source = String(content || "");
  return locateBlueprintPayload(source)?.blueprint || null;
};

export const extractProjectBlueprintProtocol = (content = "") => {
  const source = String(content || "");
  const located = locateBlueprintPayload(source);
  if (located) {
    const payloadEnd = located.payloadEnd >= 0 ? located.payloadEnd : source.length;
    const payload = source.slice(located.payloadStart, payloadEnd).trim();
    if (!payload) return null;
    return {
      payload: located.blueprint ? JSON.stringify(located.blueprint, null, 2) : payload,
      complete: Boolean(located.blueprint),
    };
  }

  const objectStart = source.search(/\{\s*"(?:schema_version|project_goal|stages|tasks)"\s*:/i);
  if (objectStart < 0) return null;
  const payload = source.slice(objectStart).trim();
  return payload ? { payload, complete: false } : null;
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
  const located = locateBlueprintPayload(source);
  if (!located) {
    const likelyBareBlueprint = pending && source.search(/\{\s*"(?:project_goal|stages|tasks)"\s*:/i);
    if (likelyBareBlueprint >= 0) {
      return source.slice(0, likelyBareBlueprint).trim() || "项目蓝图正在整理中，结构化协议草稿见下方。";
    }
    return source.trim();
  }

  const naturalReply = source.slice(0, located.match.index).trim();
  const blueprint = located.blueprint;
  if (blueprint) return [naturalReply, summarizeProjectBlueprint(blueprint)].filter(Boolean).join("\n\n");
  if (naturalReply) return naturalReply;
  return pending ? "项目蓝图正在整理中，结构化协议草稿见下方。" : "项目蓝图已返回，结构化协议见下方。";
};

export const projectPlanningNaturalReply = (content = "") => {
  const source = String(content || "");
  const located = locateBlueprintPayload(source);
  return (located ? source.slice(0, located.match.index) : source).trim();
};
