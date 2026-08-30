const safeSlug = (value) => String(value || "qws").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 40) || "qws";

export const qwsTaskMarker = (taskId) => `qws-${safeSlug(taskId)}`.slice(0, 64);

const reverseType = (type) => ({ parent: "child", child: "parent", blocks: "blocked_by", blocked_by: "blocks" }[type] || type);

function qwsIdForDashiTask(task, qwsTasks) {
  const labels = new Set(task?.labels || []);
  const matches = (qwsTasks || []).filter((candidate) => labels.has(qwsTaskMarker(candidate.id)));
  return matches.length === 1 ? matches[0].id : null;
}

function relationRows(dashiTask, allTasks) {
  const relations = dashiTask?.relations || {};
  const tasksById = new Map((allTasks || []).map((task) => [task.id, task]));
  const rows = [];
  const push = (type, item) => {
    const task = tasksById.get(item?.id) || item;
    if (task?.id) rows.push({ type, task });
  };
  push("parent", relations.parent);
  for (const item of relations.blockedBy || []) push("blocked_by", item);
  for (const item of relations.blocks || []) push("blocks", item);
  for (const item of relations.related || []) push("related", item);
  for (const task of allTasks || []) {
    if (task.relations?.parent?.id === dashiTask?.id) push("child", task);
  }
  return rows;
}

export function buildTaskboardRelationProjection({ digest, dashiTask, allTasks, qwsTasks }) {
  const canonicalEntries = digest?.entries || [];
  const canonicalKeys = new Set(canonicalEntries
    .filter((entry) => !entry.restricted && entry.effective_task_id)
    .map((entry) => `${entry.relation_type}:${entry.effective_task_id}`));
  const projectionKeys = new Set();
  let unmappedCount = 0;
  for (const row of relationRows(dashiTask, allTasks)) {
    const qwsTaskId = qwsIdForDashiTask(row.task, qwsTasks);
    if (!qwsTaskId) {
      unmappedCount += 1;
      continue;
    }
    projectionKeys.add(`${row.type}:${qwsTaskId}`);
  }
  const missingInTaskboard = [...canonicalKeys].filter((key) => !projectionKeys.has(key));
  const extraInTaskboard = [...projectionKeys].filter((key) => !canonicalKeys.has(key));
  const verifiable = digest?.canonical_source === "QWS_PROCESS_SNAPSHOT";
  return {
    canonical_source: digest?.canonical_source || null,
    canonical_hash: digest?.source_hash || null,
    taskboard_mode: digest?.projection_contract?.taskboard_mode || "READ_ONLY_CONSUMER_REQUIRED",
    status: !verifiable ? "UNVERIFIABLE" : (!missingInTaskboard.length && !extraInTaskboard.length && !unmappedCount ? "ALIGNED" : "DRIFT"),
    missing_in_taskboard: missingInTaskboard,
    extra_in_taskboard: extraInTaskboard,
    unmapped_taskboard_relations: unmappedCount,
    canonical_entries: canonicalEntries,
  };
}

export function groupCanonicalRelations(entries) {
  const grouped = { parent: [], child: [], blocked_by: [], blocks: [], related: [] };
  for (const entry of entries || []) {
    const type = grouped[entry.relation_type] ? entry.relation_type : "related";
    grouped[type].push(entry);
  }
  return grouped;
}

export { reverseType };
