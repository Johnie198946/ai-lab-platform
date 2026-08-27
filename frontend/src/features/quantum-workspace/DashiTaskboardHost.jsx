import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useAuth } from "../../auth/AuthContext";
import { platformApi } from "../../services/platformApi";
import "./DashiTaskboardHost.css";

const statusToDashi = {
  TODO: "todo",
  IN_PROGRESS: "in_progress",
  BLOCKED: "blocked",
  PAUSED: "backlog",
  DONE: "done",
};

const safeSlug = (value) => String(value || "qws").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 40) || "qws";
const taskMarker = (taskId) => `qws-${safeSlug(taskId)}`.slice(0, 64);

async function dashiRequest(path, { method = "GET", body, user } = {}) {
  const headers = new Headers({ Accept: "application/json" });
  if (body !== undefined) headers.set("Content-Type", "application/json");
  if (user) {
    headers.set("X-Taskboard-User-Id", safeSlug(user.user_id || user.username || "qws-user"));
    headers.set("X-Taskboard-User-Name", encodeURIComponent(user.username || "QWS 用户"));
    if (user.avatar_url) headers.set("X-Taskboard-User-Avatar", user.avatar_url);
  }
  const response = await fetch(`/taskboard${path}`, {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
    credentials: "same-origin",
  });
  const payload = response.status === 204 ? null : await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload?.error?.message || payload?.message || `Dashi API ${response.status}`);
  return payload;
}

export function DashiTaskboardHost({ project, process, onProcessChanged }) {
  const { authSession } = useAuth();
  const user = authSession?.user || {};
  const tenant = safeSlug(user.tenant_key || user.user_id || "default");
  const dashiProjectId = useMemo(() => `qws-${tenant}-${safeSlug(project.id)}`.slice(0, 64).replace(/-$/, ""), [project.id, tenant]);
  const iframeRef = useRef(null);
  const [state, setState] = useState("正在初始化 Dashi Taskboard…");
  const [error, setError] = useState("");
  const [ready, setReady] = useState(false);

  const ensureProjectAndTasks = useCallback(async () => {
    const accessToken = authSession?.accessToken || "";
    const sessionResponse = await fetch("/taskboard/api/qws/session", {
      method: "POST",
      credentials: "same-origin",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
        ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
      },
      body: "{}",
    });
    if (!sessionResponse.ok) throw new Error("Dashi 无法验证 AI Lab 登录会话");
    const projectsPayload = await dashiRequest("/api/projects", { user });
    let boardProject = (projectsPayload.projects || []).find((item) => item.id === dashiProjectId);
    if (!boardProject) {
      const created = await dashiRequest("/api/projects", {
        method: "POST",
        user,
        body: { id: dashiProjectId, name: project.name, workspacePath: "/workspace" },
      });
      boardProject = created.project;
    }
    const tasksPayload = await dashiRequest(`/api/tasks?projectId=${encodeURIComponent(dashiProjectId)}&archived=false`, { user });
    const existingMarkers = new Set((tasksPayload.tasks || []).flatMap((item) => item.labels || []));
    for (const task of process.tasks || []) {
      const marker = taskMarker(task.id);
      if (existingMarkers.has(marker)) continue;
      const stage = (process.stages || []).find((item) => item.id === task.stage_id);
      await dashiRequest("/api/tasks", {
        method: "POST",
        user,
        body: {
          projectId: dashiProjectId,
          title: task.title,
          description: [task.summary, stage?.name ? `QWS 阶段：${stage.name}` : "", ...(task.deliverables || []).map((item) => `交付物：${item}`)].filter(Boolean).join("\n\n"),
          status: statusToDashi[task.status] || "backlog",
          priority: "none",
          labels: [marker],
          assigneeTarget: "current-user",
          developmentContext: null,
          startDate: task.start_date || null,
          dueDate: task.due_date || null,
          recurrence: null,
        },
      });
    }
    return boardProject;
  }, [authSession?.accessToken, dashiProjectId, process.stages, process.tasks, project.name, user]);

  useEffect(() => {
    let active = true;
    setReady(false);
    setError("");
    setState("正在同步 QWS 项目与 Dashi 数据…");
    ensureProjectAndTasks()
      .then(() => { if (active) { setReady(true); setState(""); } })
      .catch((reason) => { if (active) setError(reason.message || "Dashi 初始化失败"); });
    return () => { active = false; };
  }, [ensureProjectAndTasks]);

  const openArchitect = useCallback((workflowId) => {
    window.location.assign(`/architect?workflow_id=${encodeURIComponent(workflowId)}`);
  }, []);

  useEffect(() => {
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
            theme: document.documentElement.dataset.theme === "light" ? "light" : "dark",
            projectId: dashiProjectId,
            workspacePath: "/workspace",
            projects: [{ id: project.id, name: project.name, projectKind: "local", hostId: "local", workspacePath: "/workspace" }],
          },
        }, window.location.origin);
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
        setState("正在创建 AI Lab 工作流并绑定任务…");
        const dashiTask = (await dashiRequest(`/api/tasks/${encodeURIComponent(dashiTaskId)}`, { user })).task;
        const marker = (dashiTask.labels || []).find((label) => label.startsWith("qws-"));
        let latestProcess = await platformApi.getProjectProcess(project.id);
        let qwsTask = (latestProcess.tasks || []).find((item) => taskMarker(item.id) === marker);
        if (!qwsTask) {
          const createdTask = await platformApi.createProjectTask(project.id, {
            expected_revision: latestProcess.process_revision,
            stage_id: latestProcess.stages?.[0]?.id,
            title: dashiTask.title,
            summary: dashiTask.description || dashiTask.title,
            deliverables: [],
          });
          qwsTask = createdTask.task || createdTask;
          latestProcess = await platformApi.getProjectProcess(project.id);
        }
        let workflowId = qwsTask.workflow_id;
        if (!workflowId) {
          const created = await platformApi.createWorkflow({
            title: dashiTask.title,
            description: dashiTask.description || dashiTask.title,
            desired_output: "可审阅、可验证的业务成果",
            clarification_mode: "dynamic",
          });
          workflowId = (created.workflow || created).id;
          latestProcess = await platformApi.getProjectProcess(project.id);
          await platformApi.bindProjectTaskWorkflow(project.id, qwsTask.id, {
            expected_revision: latestProcess.process_revision,
            workflow_id: workflowId,
          });
        }
        const freshDashiTask = (await dashiRequest(`/api/tasks/${encodeURIComponent(dashiTaskId)}`, { user })).task;
        await dashiRequest(`/api/tasks/${encodeURIComponent(dashiTaskId)}`, {
          method: "PATCH",
          user,
          body: {
            version: freshDashiTask.version,
            description: freshDashiTask.description,
            threadId: workflowId,
            threadBinding: { threadId: workflowId, codexProjectId: project.id, codexProjectKind: "local", codexHostId: "local", workspacePath: "/workspace" },
          },
        });
        frame.postMessage({ type: "taskboard:thread-prepared", payload: { taskId: dashiTaskId, threadId: workflowId } }, window.location.origin);
        setState("");
        await onProcessChanged?.();
        openArchitect(workflowId);
      } catch (reason) {
        setState("");
        frame.postMessage({ type: "taskboard:thread-create-error", payload: { taskId: dashiTaskId, error: reason.message || "AI Lab 工作流创建失败" } }, window.location.origin);
      }
    };
    window.addEventListener("message", receive);
    return () => window.removeEventListener("message", receive);
  }, [dashiProjectId, onProcessChanged, openArchitect, project.id, project.name, user]);

  const src = `/taskboard/?host=workbuddy&lang=zh&project=${encodeURIComponent(dashiProjectId)}`;
  return <section className="qw-dashi-host" aria-label="Dashi Taskboard">
    {(state || error) && <div className={`qw-dashi-status ${error ? "is-error" : ""}`}>{error || state}</div>}
    {ready && <iframe ref={iframeRef} title="Dashi Taskboard" src={src} allow="clipboard-read; clipboard-write" />}
  </section>;
}
