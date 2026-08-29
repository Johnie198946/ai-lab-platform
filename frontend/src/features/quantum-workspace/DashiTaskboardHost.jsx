import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useAuth } from "../../auth/AuthContext";
import { platformApi } from "../../services/platformApi";
import "./DashiTaskboardHost.css";

const safeSlug = (value) => String(value || "qws").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 40) || "qws";
const taskMarker = (taskId) => `qws-${safeSlug(taskId)}`.slice(0, 64);

function resolveDashiTheme() {
  const explicitTheme = document.documentElement.dataset.theme;
  if (explicitTheme === "light" || explicitTheme === "dark") return explicitTheme;
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function addTaskboardUserHeaders(headers, user) {
  if (!user) return;
  headers.set("X-Taskboard-User-Id", safeSlug(user.user_id || user.username || "qws-user"));
  headers.set("X-Taskboard-User-Name", encodeURIComponent(user.username || "QWS 用户"));
  if (user.avatar_url) headers.set("X-Taskboard-User-Avatar", user.avatar_url);
}

async function dashiRequest(path, { method = "GET", body, user } = {}) {
  const headers = new Headers({ Accept: "application/json" });
  if (body !== undefined) headers.set("Content-Type", "application/json");
  addTaskboardUserHeaders(headers, user);
  const response = await fetch(`/taskboard${path}`, {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
    credentials: "same-origin",
  });
  const payload = response.status === 204 ? null : await response.json().catch(() => ({}));
  const detail = typeof payload?.detail === "string"
    ? payload.detail
    : Array.isArray(payload?.detail)
      ? payload.detail.map((item) => item?.msg || JSON.stringify(item)).join("；")
      : "";
  if (!response.ok) throw new Error(payload?.error?.message || payload?.message || detail || `Dashi API ${response.status}`);
  return payload;
}

const issueSummary = (issue) => issue ? {
  id: issue.id,
  identifier: issue.identifier || null,
  title: issue.title || "",
  status: issue.status || null,
  priority: issue.priority || null,
  assignee: issue.assignee || null,
  archived_at: issue.archivedAt || null,
} : null;

const issueFull = (issue) => issue ? {
  ...issueSummary(issue),
  description: issue.description || "",
  labels: issue.labels || [],
  development_context: issue.developmentContext || null,
  start_date: issue.startDate || null,
  due_date: issue.dueDate || null,
  recurrence: issue.recurrence || null,
  version: issue.version ?? null,
  updated_at: issue.updatedAt || null,
} : null;

function resolveCanonicalTask(dashiTask, qwsTasks) {
  const labels = new Set(dashiTask.labels || []);
  const markerMatches = (qwsTasks || []).filter((item) => labels.has(taskMarker(item.id)));
  if (markerMatches.length > 1) throw new Error("该卡片绑定了多个 QWS 任务，无法安全打开 AI Session。");
  const titleMatches = (qwsTasks || []).filter((item) => item.title?.trim() === dashiTask.title?.trim());
  const canonical = markerMatches[0] || (titleMatches.length === 1 ? titleMatches[0] : null);
  return {
    id: dashiTask.id,
    canonical_task_id: canonical?.id || null,
    title: dashiTask.title,
    summary: canonical?.summary || dashiTask.description || "",
    status: dashiTask.status,
    assignee_role: canonical?.assignee_role || dashiTask.assignee?.name || null,
    deliverables: canonical?.deliverables || [],
    stage_id: canonical?.stage_id || "taskboard-card",
    workflow_id: canonical?.workflow_id || null,
    binding_kind: "taskboard_card",
  };
}

function collectDirectChildren(rootTask, allTasks) {
  return (allTasks || [])
    .filter((candidate) => candidate.relations?.parent?.id === rootTask.id)
    .map((task) => ({ ...issueFull(task), depth: 1 }));
}

function buildCardContext({ project, dashiProjectId, dashiTask, qwsTask, allTasks, comments, attachments }) {
  const relations = dashiTask.relations || {};
  const tasksById = new Map((allTasks || []).map((item) => [item.id, item]));
  const fullRelation = (item) => issueFull(tasksById.get(item?.id) || item);
  const directChildren = collectDirectChildren(dashiTask, allTasks);
  const scopedTaskIds = new Set([
    dashiTask.id,
    relations.parent?.id,
    ...(relations.blockedBy || []).map((item) => item.id),
    ...(relations.blocks || []).map((item) => item.id),
    ...(relations.related || []).map((item) => item.id),
    ...directChildren.map((item) => item.id),
  ].filter(Boolean));
  const scopedTasks = (allTasks || []).filter((item) => scopedTaskIds.has(item.id));
  return {
    schema_version: 2,
    binding: {
      identity: { project_id: project.id, task_id: qwsTask.id, taskboard_task_id: dashiTask.id },
      default_scope: ["project_goal", "current_task", "acceptance_criteria", "direct_relations", "recent_comments"],
      comments_limit: 20,
    },
    session_registry: scopedTasks.map((item) => ({
      task_id: item.id,
      identifier: item.identifier || null,
      title: item.title || "未命名卡片",
      responsibility: item.description?.trim() || item.title || "未定义任务职责",
      status: item.status || null,
      card_version: item.version ?? null,
    })),
    project: {
      id: project.id,
      name: project.name,
      business_goal: project.goal || "",
      taskboard_project_id: dashiProjectId,
    },
    task: {
      qws_task_id: qwsTask.id,
      dashi_task_id: dashiTask.id,
      identifier: dashiTask.identifier || null,
      title: dashiTask.title || qwsTask.title,
      parent_issue: fullRelation(relations.parent),
      descriptions: [
        { id: "qws-summary", source: "qws_summary", content: qwsTask.summary || "" },
        { id: "taskboard-description", source: "taskboard_description", content: dashiTask.description || "" },
      ],
      sub_issues: directChildren,
      comments: (comments || []).slice(-20).map((comment) => ({
        id: comment.id,
        body: comment.body || "",
        author: { type: comment.authorType, id: comment.authorId, name: comment.authorName },
        attachments: (comment.attachments || []).map((attachment) => ({
          id: attachment.id,
          filename: attachment.filename,
          content_type: attachment.contentType,
          size: attachment.size,
        })),
        version: comment.version,
        created_at: comment.createdAt,
        updated_at: comment.updatedAt,
      })),
      attachments: (attachments || []).map((attachment) => ({
        id: attachment.id,
        filename: attachment.filename,
        content_type: attachment.contentType,
        size: attachment.size,
        kind: attachment.kind,
        created_at: attachment.createdAt,
      })),
      status: dashiTask.status,
      priority: dashiTask.priority,
      assignee: dashiTask.assignee || null,
      labels: dashiTask.labels || [],
      development_context: dashiTask.developmentContext || null,
      start_date: dashiTask.startDate || null,
      due_date: dashiTask.dueDate || null,
      recurrence: dashiTask.recurrence || null,
      related_issues: {
        blocked_by: (relations.blockedBy || []).map(fullRelation),
        blocks: (relations.blocks || []).map(fullRelation),
        related: (relations.related || []).map(fullRelation),
      },
      qws: {
        binding_kind: qwsTask.binding_kind || "canonical_task",
        canonical_task_id: qwsTask.canonical_task_id || null,
        stage_id: qwsTask.stage_id,
        workflow_id: qwsTask.workflow_id || null,
        status: qwsTask.status,
        assignee_role: qwsTask.assignee_role || null,
        deliverables: qwsTask.deliverables || [],
      },
      version: dashiTask.version,
      created_at: dashiTask.createdAt,
      updated_at: dashiTask.updatedAt,
    },
  };
}

export function DashiTaskboardHost({ project, onOpenTaskChat }) {
  const { authSession } = useAuth();
  const user = authSession?.user || {};
  const tenant = safeSlug(user.tenant_key || user.user_id || "default");
  const dashiProjectId = useMemo(() => `qws-${tenant}-${safeSlug(project.id)}`.slice(0, 64).replace(/-$/, ""), [project.id, tenant]);
  const iframeRef = useRef(null);
  const [state, setState] = useState("正在初始化 Dashi Taskboard…");
  const [error, setError] = useState("");
  const [ready, setReady] = useState(false);

  const ensureTaskboardSession = useCallback(async () => {
    const accessToken = authSession?.accessToken || "";
    const sessionResponse = await fetch("/taskboard/api/qws/session", {
      method: "POST",
      credentials: "same-origin",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
        ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
      },
      body: JSON.stringify({ project_id: project.id }),
    });
    if (!sessionResponse.ok) {
      const payload = await sessionResponse.json().catch(() => ({}));
      const message = payload?.error?.message || payload?.message || payload?.detail;
      throw new Error(typeof message === "string" && message.trim()
        ? `Dashi 项目同步失败：${message}`
        : `Dashi 项目同步失败（HTTP ${sessionResponse.status}）`);
    }
    const session = await sessionResponse.json();
    if (session.taskboard_project_id !== dashiProjectId) throw new Error("Dashi 返回了不一致的租户项目绑定");
    return session;
  }, [authSession?.accessToken, dashiProjectId, project.id]);

  useEffect(() => {
    let active = true;
    setReady(false);
    setError("");
    setState("正在同步 QWS 项目与 Dashi 数据…");
    ensureTaskboardSession()
      .then(() => { if (active) { setReady(true); setState(""); } })
      .catch((reason) => { if (active) setError(reason.message || "Dashi 初始化失败"); });
    return () => { active = false; };
  }, [ensureTaskboardSession]);

  const openArchitect = useCallback((workflowId) => {
    window.location.assign(`/architect?workflow_id=${encodeURIComponent(workflowId)}`);
  }, []);

  const loadTaskSession = useCallback(async (dashiTaskId) => {
    const [taskPayload, tasksPayload, commentsPayload, attachmentsPayload, latestProcess] = await Promise.all([
      dashiRequest(`/api/tasks/${encodeURIComponent(dashiTaskId)}`, { user }),
      dashiRequest(`/api/tasks?projectId=${encodeURIComponent(dashiProjectId)}&archived=false`, { user }),
      dashiRequest(`/api/tasks/${encodeURIComponent(dashiTaskId)}/comments`, { user }),
      dashiRequest(`/api/tasks/${encodeURIComponent(dashiTaskId)}/attachments`, { user }),
      platformApi.getProjectProcess(project.id),
    ]);
    const dashiTask = taskPayload.task;
    const qwsTask = resolveCanonicalTask(dashiTask, latestProcess.tasks || []);
    return {
      task: qwsTask,
      cardContext: buildCardContext({
        project,
        dashiProjectId,
        dashiTask,
        qwsTask,
        allTasks: tasksPayload.tasks || [],
        comments: commentsPayload.comments || [],
        attachments: attachmentsPayload.attachments || [],
      }),
    };
  }, [dashiProjectId, project, user]);

  useEffect(() => {
    const postTheme = () => {
      iframeRef.current?.contentWindow?.postMessage({ type: "taskboard:theme", theme: resolveDashiTheme() }, window.location.origin);
    };
    const mediaQuery = window.matchMedia?.("(prefers-color-scheme: dark)");
    const handleThemeChange = () => postTheme();
    mediaQuery?.addEventListener?.("change", handleThemeChange);
    const themeObserver = typeof MutationObserver === "undefined" ? null : new MutationObserver(handleThemeChange);
    themeObserver?.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    const receive = async (event) => {
      if (event.source !== iframeRef.current?.contentWindow || !event.data?.type) return;
      const frame = iframeRef.current.contentWindow;
      if (event.data.type === "taskboard:frame-awaiting-challenge") {
        frame.postMessage({ type: "taskboard:frame-challenge", payload: { challenge: crypto.randomUUID().replaceAll("-", "") } }, window.location.origin);
        return;
      }
      if (event.data.type === "taskboard:ready") {
        frame.postMessage({
          type: "taskboard:host-context",
          payload: {
            user: { type: "user", id: safeSlug(user.user_id || user.username || "qws-user"), name: user.username || "QWS 用户", avatarUrl: user.avatar_url || null },
            language: "zh",
            theme: resolveDashiTheme(),
            projectId: dashiProjectId,
            workspacePath: "/workspace",
            projects: [{ id: project.id, name: project.name, projectKind: "local", hostId: "local", workspacePath: "/workspace" }],
          },
        }, window.location.origin);
        postTheme();
        return;
      }
      if (event.data.type === "taskboard:open-external") {
        const url = event.data.payload?.url;
        if (typeof url === "string") window.open(url, "_blank", "noopener,noreferrer");
        return;
      }
      if (event.data.type === "taskboard:open-thread") {
        const workflowId = event.data.payload?.threadId;
        if (workflowId) openArchitect(workflowId);
        return;
      }
      if (event.data.type !== "taskboard:create-thread") return;
      const dashiTaskId = event.data.payload?.taskId;
      try {
        setState("正在打开任务 AI Session…");
        const session = await loadTaskSession(dashiTaskId);
        onOpenTaskChat?.({
          ...session,
          refreshCardContext: () => loadTaskSession(dashiTaskId),
        });
        frame.postMessage({ type: "taskboard:thread-prepared", payload: { taskId: dashiTaskId } }, window.location.origin);
        setState("");
      } catch (reason) {
        setState("");
        frame.postMessage({ type: "taskboard:thread-create-error", payload: { taskId: dashiTaskId, error: reason.message || "任务 AI Session 打开失败" } }, window.location.origin);
      }
    };
    window.addEventListener("message", receive);
    return () => {
      window.removeEventListener("message", receive);
      mediaQuery?.removeEventListener?.("change", handleThemeChange);
      themeObserver?.disconnect();
    };
  }, [dashiProjectId, loadTaskSession, onOpenTaskChat, openArchitect, project, user]);

  const src = `/taskboard/?host=qws&lang=zh&project=${encodeURIComponent(dashiProjectId)}`;
  return <section className="qw-dashi-host" aria-label="Dashi Taskboard">
    {(state || error) && <div className={`qw-dashi-status ${error ? "is-error" : ""}`}>{error || state}</div>}
    {ready && <iframe ref={iframeRef} title="Dashi Taskboard" src={src} allow="clipboard-read; clipboard-write" />}
  </section>;
}
