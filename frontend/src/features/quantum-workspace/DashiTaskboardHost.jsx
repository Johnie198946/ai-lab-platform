import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useAuth } from "../../auth/AuthContext";
import { platformApi } from "../../services/platformApi";
import { buildTaskboardRelationProjection, groupCanonicalRelations, qwsTaskMarker } from "./relationProjection.js";
import { ProjectDocuments } from "./ProjectDocuments";
import "./DashiTaskboardHost.css";

const safeSlug = (value) => String(value || "qws").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 40) || "qws";

const isReviewTask = (task) => /审核|验收|评审|复核|review|acceptance/i.test([
  task?.title,
  task?.assignee_role,
  task?.assignee?.name,
  ...(task?.labels || []),
].filter(Boolean).join(" "));

const batchAutoInstruction = (task) => isReviewTask(task)
  ? `立即执行审核任务《${task.title}》。先确认所有 blockedBy 上游任务已完成；系统会在依赖完成前保持本卡在待办队列。审核时逐项检查每个上游任务的交付物和验收标准，并在 routes 中按 session_directory 的精确 target_task_id 为每个被审核任务写入明确评论：通过项写依据，不通过项写问题、整改方案和复核条件。若存在必须由用户决定且无法自动消除的分歧，将本卡 status 设为 in_review（等你确认）；若全部可自动验收则设为 done；若客观阻塞则设为 blocked。appendComment 必须写审核纪要、结论和剩余风险，最终只输出一个合法 task_backfill。`
  : `立即全自动执行任务《${task.title}》，持续工作到完成或确认存在无法自行消除的阻塞。不要等待人工确认，也不要只给建议。优先使用项目知识与安全公开网络工具完成事实核查和交付。执行结束后必须输出 task_backfill：将状态设为 done、in_review 或 blocked；只有确需用户决策时才使用 in_review；appendComment 写明执行日志、纪要、问题、根因、已采取的解决方案、验证结果和剩余风险；每项实质性交付成果必须写入 addAttachments，不能只写在评论里。`;


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

async function dashiTextRequest(path) {
  const response = await fetch(`/taskboard${path}`, { credentials: "same-origin" });
  if (!response.ok) throw new Error(`Dashi content API ${response.status}`);
  return response.text();
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


function resolveCanonicalTask(dashiTask, qwsTasks) {
  const labels = new Set(dashiTask.labels || []);
  const markerMatches = (qwsTasks || []).filter((item) => labels.has(qwsTaskMarker(item.id)));
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
    acceptance_criteria: canonical?.acceptance_criteria || [],
    labels: canonical?.labels || dashiTask.labels || [],
    due_date: canonical?.due_date || dashiTask.dueDate || null,
    stage_id: canonical?.stage_id || "taskboard-card",
    workflow_id: canonical?.workflow_id || null,
    canonical_status: canonical?.status || null,
    task_revision: canonical?.task_revision || 1,
    challenge_reviews: canonical?.challenge_reviews || [],
    delivery_manifest: canonical?.delivery_manifest || null,
    binding_kind: "taskboard_card",
  };
}


function buildCardContext({ project, dashiProjectId, dashiTask, qwsTask, comments, attachments, relationProjection, reviewInputs = [] }) {
  const canonicalRelations = groupCanonicalRelations(relationProjection.canonical_entries);
  return {
    schema_version: 2,
    binding: {
      identity: { project_id: project.id, task_id: qwsTask.id, taskboard_task_id: dashiTask.id },
      default_scope: ["project_goal", "current_task", "acceptance_criteria", "direct_relations", "recent_comments"],
      comments_limit: 20,
    },
    session_registry: [{
      task_id: dashiTask.id,
      identifier: dashiTask.identifier || null,
      title: dashiTask.title || "未命名卡片",
      responsibility: dashiTask.description?.trim() || dashiTask.title || "未定义任务职责",
      status: dashiTask.status || null,
      card_version: dashiTask.version ?? null,
    }],
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
      parent_issue: null,
      descriptions: [
        { id: "qws-summary", source: "qws_summary", content: qwsTask.summary || "" },
        { id: "taskboard-description", source: "taskboard_description", content: dashiTask.description || "" },
      ],
      sub_issues: [],
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
      review_inputs: reviewInputs,
      status: dashiTask.status,
      priority: dashiTask.priority,
      assignee: dashiTask.assignee || null,
      labels: dashiTask.labels || [],
      development_context: dashiTask.developmentContext || null,
      start_date: dashiTask.startDate || null,
      due_date: dashiTask.dueDate || null,
      recurrence: dashiTask.recurrence || null,
      related_issues: canonicalRelations,
      relation_projection: relationProjection,
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

export function DashiTaskboardHost({ project, onOpenTaskChat, onRevisionChange }) {
  const { authSession } = useAuth();
  const user = authSession?.user || {};
  const tenant = safeSlug(user.tenant_key || user.user_id || "default");
  const dashiProjectId = useMemo(() => `qws-${tenant}-${safeSlug(project.id)}`.slice(0, 64).replace(/-$/, ""), [project.id, tenant]);
  const iframeRef = useRef(null);
  const [state, setState] = useState("正在初始化 Dashi Taskboard…");
  const [error, setError] = useState("");
  const [ready, setReady] = useState(false);
  const [activeView, setActiveView] = useState("issues");

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
    const qwsTasks = latestProcess.tasks || [];
    const qwsTask = resolveCanonicalTask(dashiTask, qwsTasks);
    if (!qwsTask.canonical_task_id) throw new Error("该 Taskboard 卡片尚未绑定 QWS canonical task，不能建立执行上下文。");
    const [relationDigest, manifests] = await Promise.all([
      platformApi.getProjectTaskRelationDigest(project.id, qwsTask.canonical_task_id),
      platformApi.getProjectTaskDeliveryManifests(project.id, qwsTask.canonical_task_id),
    ]);
    const relationProjection = buildTaskboardRelationProjection({
      digest: relationDigest,
      dashiTask,
      allTasks: tasksPayload.tasks || [],
      qwsTasks,
    });
    const reviewTask = isReviewTask({ ...qwsTask, assignee: dashiTask.assignee });
    const tasksById = new Map((tasksPayload.tasks || []).map((item) => [item.id, item]));
    const reviewTargets = reviewTask ? (dashiTask.relations?.blockedBy || []) : [];
    const reviewInputs = await Promise.all(reviewTargets.map(async (target) => {
      const targetTask = tasksById.get(target.id) || target;
      const [targetComments, targetAttachments] = await Promise.all([
        dashiRequest(`/api/tasks/${encodeURIComponent(target.id)}/comments`, { user }),
        dashiRequest(`/api/tasks/${encodeURIComponent(target.id)}/attachments`, { user }),
      ]);
      const attachments = await Promise.all((targetAttachments.attachments || []).slice(0, 6).map(async (attachment) => {
        const readable = String(attachment.contentType || "").startsWith("text/")
          || /\.(md|markdown|txt|json|yaml|yml|csv|log)$/i.test(attachment.filename || "");
        const content = readable
          ? await dashiTextRequest(`/api/attachments/${encodeURIComponent(attachment.id)}/content`).catch(() => "")
          : "";
        return {
          id: attachment.id,
          filename: attachment.filename,
          content_type: attachment.contentType,
          content: content.slice(0, 20_000),
        };
      }));
      return {
        task_id: targetTask.id,
        identifier: targetTask.identifier || null,
        title: targetTask.title || "",
        description: targetTask.description || "",
        status: targetTask.status || null,
        comments: (targetComments.comments || []).slice(-20).map((comment) => ({
          body: comment.body || "",
          author_name: comment.authorName || "",
          created_at: comment.createdAt,
        })),
        attachments,
      };
    }));
    return {
      task: {
        ...qwsTask,
        process_revision: latestProcess.process_revision || project.process_revision || 1,
        delivery_manifest: manifests.find((item) => item.status === "READY") || manifests.at(-1) || null,
        relation_projection: relationProjection,
      },
      cardContext: buildCardContext({
        project,
        dashiProjectId,
        dashiTask,
        qwsTask,
        comments: commentsPayload.comments || [],
        attachments: attachmentsPayload.attachments || [],
        relationProjection,
        reviewInputs,
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
      if (event.data.type === "taskboard:view-change") {
        setActiveView(event.data.payload?.view || "issues");
        return;
      }
      if (event.data.type === "taskboard:run-task") {
        const dashiTaskId = event.data.payload?.taskId;
        setError("");
        setState("正在启动此任务…");
        try {
          const session = await loadTaskSession(dashiTaskId);
          const conversation = await platformApi.openTaskConversation({
            project_id: project.id,
            task_id: session.task.id,
            workflow_id: session.task.workflow_id,
            agent_version: "hermes-current",
            card_context: session.cardContext,
          });
          await platformApi.startTaskAutoExecution(conversation.id, {
            instruction: batchAutoInstruction(session.task),
            request_id: `qw-single-${crypto.randomUUID()}`,
          });
          setState(`任务《${session.task.title}》已开始执行，可在卡片中查看实时进度`);
          frame.postMessage({ type: "taskboard:task-started", payload: { taskId: dashiTaskId } }, window.location.origin);
          window.setTimeout(() => setState(""), 5000);
        } catch (reason) {
          setError(reason.message || "任务启动失败");
        }
        return;
      }
      if (event.data.type === "taskboard:run-project-todos") {
        setError("");
        setState("正在启动全部待办任务…");
        try {
          const tasksPayload = await dashiRequest(
            `/api/tasks?projectId=${encodeURIComponent(dashiProjectId)}&archived=false`,
            { user },
          );
          const todoTasks = (tasksPayload.tasks || []).filter((item) =>
            item.status === "backlog" && !item.archivedAt,
          );
          const readyTasks = todoTasks.filter((item) => (item.relations?.blockedBy || []).every((blocker) => blocker.status === "done"));
          const queued = todoTasks.length - readyTasks.length;
          const results = await Promise.allSettled(readyTasks.map(async (item) => {
            let lastError;
            for (let attempt = 0; attempt < 3; attempt += 1) {
              try {
                const session = await loadTaskSession(item.id);
                const conversation = await platformApi.openTaskConversation({
                  project_id: project.id,
                  task_id: session.task.id,
                  workflow_id: session.task.workflow_id,
                  agent_version: "hermes-current",
                  card_context: session.cardContext,
                });
                return await platformApi.startTaskAutoExecution(conversation.id, {
                  instruction: batchAutoInstruction(item),
                  request_id: `qw-batch-${crypto.randomUUID()}`,
                });
              } catch (reason) {
                lastError = reason;
                if (attempt < 2) {
                  await new Promise((resolve) => window.setTimeout(resolve, 400 * (attempt + 1)));
                }
              }
            }
            throw lastError || new Error(`任务《${item.title}》启动失败`);
          }));
          const started = results.filter((result) => result.status === "fulfilled").length;
          const failed = results.length - started;
          setState(`已启动 ${started} 个依赖就绪任务${queued ? `，${queued} 个前向依赖任务留在待办队列` : ""}${failed ? `，${failed} 个启动失败` : ""}`);
          frame.postMessage({
            type: "taskboard:project-todos-started",
            payload: { total: todoTasks.length, started, queued, failed },
          }, window.location.origin);
          window.setTimeout(() => setState(""), 8000);
        } catch (reason) {
          setError(reason.message || "批量启动待办任务失败");
        }
        return;
      }
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
      if (event.data.type === "taskboard:open-project-automation") return;
      if (event.data.type !== "taskboard:create-thread") return;
      const dashiTaskId = event.data.payload?.taskId;
      try {
        setState("正在打开任务 AI Session…");
        const session = await loadTaskSession(dashiTaskId);
        onOpenTaskChat?.({
          ...session,
          autoInstruction: `${event.data.payload?.instruction || "执行当前任务。"}\n\n立即全自动执行当前任务，持续工作到完成或确认存在无法自行消除的阻塞。不要等待人工确认，也不要只给建议。执行过程中保留可读日志；结束时自动更新卡片状态、负责人和必要字段，在卡片评论中写明执行纪要、发现的问题、根因、已采取的解决方案、验证结果和剩余风险。若缺少关键外部信息，先尝试可用工具和项目上下文；仍无法解决时将卡片标为 blocked，并在评论中写清问题与可执行解决方案。最终必须输出 task_backfill 块，包含 appendComment，并将 status 设置为 done 或 blocked；每项实质性交付成果必须写入 addAttachments，不能只写在评论里。`,
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
    {(state || error) && <div className={`qw-dashi-status ${error ? "is-error" : ""}`} role="status"><i aria-hidden="true" />{error || state}</div>}
    {ready && <iframe ref={iframeRef} title="Dashi Taskboard" src={src} allow="clipboard-read; clipboard-write" />}
    {ready && activeView === "readme" && <div className="qw-dashi-project-documents" aria-label="项目文档工作区">
      <ProjectDocuments projectId={project.id} onRevisionChange={onRevisionChange} />
    </div>}
  </section>;
}
