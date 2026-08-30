import { getAuthAccessToken } from "../auth/storage";
import { API_TOKEN, REQUEST_TIMEOUT_MS, buildApiUrl, buildAuthUrl } from "../config/env";
import { parseSseFrame, splitSseFrames } from "./sseFrames";

export class PlatformApiError extends Error {
  constructor(message, options = {}) {
    super(message);
    this.name = "PlatformApiError";
    this.status = options.status ?? 0;
    this.detail = options.detail ?? "";
  }
}

const parseErrorMessage = async (response) => {
  try {
    const payload = await response.json();
    if (typeof payload?.detail === "string" && payload.detail.trim()) {
      return payload.detail.trim();
    }
  } catch {}
  return response.statusText || "请求失败";
};

const extractAccessToken = (payload) =>
  [
    payload?.access_token,
    payload?.token,
    payload?.data?.access_token,
    payload?.data?.token,
  ].find((value) => typeof value === "string" && value.trim()) ?? "";

const request = async (path, options = {}) => {
  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);

  try {
    const headers = new Headers(options.headers ?? {});
    headers.set("Accept", "application/json");
    if (options.body !== undefined) {
      headers.set("Content-Type", "application/json");
    }
    let accessToken = API_TOKEN;
    if (!options.skipSessionAuth) {
      accessToken = getAuthAccessToken() || accessToken;
    }
    if (options.accessToken !== undefined) {
      accessToken = options.accessToken;
    }
    if (accessToken && !options.skipAuth) {
      headers.set("Authorization", `Bearer ${accessToken}`);
    }

    const response = await fetch(options.url ?? buildApiUrl(path), {
      method: options.method ?? "GET",
      headers,
      body: typeof options.body === "string" ? options.body : (options.body === undefined ? undefined : JSON.stringify(options.body)),
      signal: controller.signal,
    });

    if (!response.ok) {
      throw new PlatformApiError(await parseErrorMessage(response), {
        status: response.status,
      });
    }

    if (response.status === 204) {
      return null;
    }
    return response.json();
  } catch (error) {
    if (error instanceof PlatformApiError) {
      throw error;
    }
    if (error.name === "AbortError") {
      throw new PlatformApiError("请求超时，请检查后端服务是否可用。");
    }
    throw new PlatformApiError(error.message || "无法连接 ai-lab-platform。");
  } finally {
    window.clearTimeout(timeoutId);
  }
};

const streamRequest = async (path, body, onEvent) => {
  const headers = new Headers({ Accept: "text/event-stream", "Content-Type": "application/json" });
  const accessToken = getAuthAccessToken() || API_TOKEN;
  if (accessToken) headers.set("Authorization", `Bearer ${accessToken}`);
  const response = await fetch(buildApiUrl(path), {
    method: "POST",
    headers,
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    throw new PlatformApiError(await parseErrorMessage(response), { status: response.status });
  }
  if (!response.body) throw new PlatformApiError("浏览器未返回流式响应体。");
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let finalEvent = null;
  const dispatchFrames = (frames) => {
    for (const frame of frames) {
      const event = parseSseFrame(frame);
      if (!event) continue;
      finalEvent = event;
      onEvent?.(event);
    }
  };
  while (true) {
    const { value, done } = await reader.read();
    buffer += decoder.decode(value ?? new Uint8Array(), { stream: !done });
    const parsed = splitSseFrames(buffer, done);
    buffer = parsed.remainder;
    dispatchFrames(parsed.frames);
    if (done) break;
  }
  return finalEvent;
};

export const platformApi = {
  getHealth() {
    return request("/health");
  },
  login({ identifier, password }) {
    return request("", {
      method: "POST",
      url: buildAuthUrl("/api/v1/auth/login"),
      body: { identifier, password },
      skipAuth: true,
      skipSessionAuth: true,
    });
  },
  async authenticate({ identifier, password }) {
    const payload = await this.login({ identifier, password });
    const accessToken = extractAccessToken(payload);
    if (!accessToken) {
      throw new PlatformApiError("登录成功，但未返回 access token。");
    }
    return accessToken;
  },
  getAuthCapabilities() {
    return request("/api/v1/auth/capabilities", {
      skipAuth: true,
      skipSessionAuth: true,
    });
  },
  sendPhoneCode({ phone }) {
    return request("/api/v1/auth/phone/send-code", {
      method: "POST",
      body: { phone },
      skipAuth: true,
      skipSessionAuth: true,
    });
  },
  async authenticatePhone({ phone, code }) {
    const payload = await request("/api/v1/auth/phone/login", {
      method: "POST",
      body: { phone, code },
      skipAuth: true,
      skipSessionAuth: true,
    });
    const accessToken = extractAccessToken(payload);
    if (!accessToken) {
      throw new PlatformApiError("手机登录成功，但未返回 access token。");
    }
    return accessToken;
  },
  startOAuth({ provider, client = "web" }) {
    return request(`/api/v1/auth/oauth/${encodeURIComponent(provider)}/start?client=${encodeURIComponent(client)}`, {
      skipAuth: true,
      skipSessionAuth: true,
    });
  },
  async completeOAuth({ ticket }) {
    const payload = await request("/api/v1/auth/oauth/complete", {
      method: "POST",
      body: { ticket },
      skipAuth: true,
      skipSessionAuth: true,
    });
    const accessToken = extractAccessToken(payload);
    if (!accessToken) {
      throw new PlatformApiError("第三方登录成功，但未返回 access token。");
    }
    return accessToken;
  },
  getMe(options = {}) {
    return request("/api/v1/me", {
      accessToken: options.accessToken,
      skipSessionAuth: options.skipSessionAuth,
    });
  },
  createOrchestrationSession(goal, sessionId = null) {
    return request("/api/orchestration/sessions", {
      method: "POST",
      body: sessionId ? { goal, session_id: sessionId } : { goal },
    });
  },
  createOrchestrationSessionStream(goal, sessionId = null) {
    return request("/api/orchestration/sessions", {
      method: "POST",
      body: sessionId ? { goal, session_id: sessionId, stream: true } : { goal, stream: true },
    });
  },
  async streamOrchestrationSession(goal, sessionId = null, onEvent = () => {}) {
    const accessToken = getAuthAccessToken() || API_TOKEN;
    const headers = new Headers({
      Accept: "text/event-stream",
      "Content-Type": "application/json",
    });
    if (accessToken) {
      headers.set("Authorization", `Bearer ${accessToken}`);
    }
    const response = await fetch(buildApiUrl("/api/orchestration/sessions"), {
      method: "POST",
      headers,
      body: JSON.stringify(sessionId
        ? { goal, session_id: sessionId, stream: true, surface: "agency" }
        : { goal, stream: true, surface: "agency" }),
    });
    if (!response.ok || !response.body) {
      throw new PlatformApiError(await parseErrorMessage(response), {
        status: response.status,
      });
    }
    const resolvedSessionId = response.headers.get("X-Session-ID") || sessionId;
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    while (true) {
      const { value, done } = await reader.read();
      buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
      const lines = buffer.split(/\r?\n/);
      buffer = lines.pop() || "";
      for (const line of lines) {
        if (!line.startsWith("data:")) continue;
        try {
          onEvent(JSON.parse(line.slice(5).trim()));
        } catch {
          onEvent({ type: "status", detail: line.slice(5).trim() });
        }
      }
      if (done) break;
    }
    return resolvedSessionId;
  },
  chat(question) {
    return request("/api/chat", {
      method: "POST",
      body: { question },
    });
  },
  getOrchestrationSession(sessionId) {
    return request(`/api/orchestration/sessions/${sessionId}`);
  },
  updateRole(sessionId, roleId, role) {
    return request(`/api/orchestration/sessions/${sessionId}/roles/${roleId}`, {
      method: "PUT",
      body: {
        name: role.name,
        summary: role.summary,
        responsibility: role.responsibility,
        skills: role.skills,
      },
    });
  },
  generateRoleWorkflow(sessionId, roleId, goal, dataRequirements) {
    return request("/api/orchestration/workflow", {
      method: "POST",
      body: {
        session_id: sessionId,
        role_id: roleId,
        goal: goal,
        data_requirements: dataRequirements
      },
    });
  },
  // ===== Agent 管理（子 Agent 纯净沙箱）=====
  draftAgent(goal) {
    return request("/api/agents/draft", {
      method: "POST",
      body: { goal },
    });
  },
  createAgent(payload) {
    return request("/api/agents", {
      method: "POST",
      body: payload,
    });
  },
  listAgents() {
    return request("/api/agents");
  },
  updateAgent(agentId, payload) {
    return request(`/api/agents/${agentId}`, {
      method: "PATCH",
      body: payload,
    });
  },
  deleteAgent(agentId) {
    return request(`/api/agents/${agentId}`, {
      method: "DELETE",
    });
  },
  listAgentTemplates() {
    return request("/api/agents/templates");
  },
  instantiateAgentTemplate(templateKey, mission) {
    return request(`/api/agents/templates/${templateKey}/instantiate`, {
      method: "POST",
      body: { mission },
    });
  },
  listNotifications() {
    return request("/api/notifications");
  },
  markNotificationRead(notificationId) {
    return request(`/api/notifications/${notificationId}/read`, {
      method: "POST",
    });
  },
  markAllNotificationsRead() {
    return request("/api/notifications/read-all", {
      method: "POST",
    });
  },
  listWorkflows() {
    return request("/api/v1/workflows");
  },
  createWorkflow(payload) {
    return request("/api/v1/workflows", { method: "POST", body: payload });
  },
  getWorkflow(workflowId) {
    return request(`/api/v1/workflows/${workflowId}`);
  },
  getClarification(workflowId) {
    return request(`/api/v1/workflows/${workflowId}/clarification`);
  },
  answerClarification(workflowId, response, intent = null) {
    return request(`/api/v1/workflows/${workflowId}/clarification/respond`, { method: "POST", body: { response, intent } });
  },
  reopenClarification(workflowId) {
    return request(`/api/v1/workflows/${workflowId}/clarification/reopen`, { method: "POST", body: {} });
  },
  getWorkflowPlan(workflowId) {
    return request(`/api/v1/workflows/${workflowId}/plan`);
  },
  listWorkflowPlanVersions(workflowId) {
    return request(`/api/v1/workflows/${workflowId}/plan/versions`);
  },
  patchWorkflowPlan(workflowId, payload) {
    return request(`/api/v1/workflows/${workflowId}/plan`, { method: "PATCH", body: payload });
  },
  rollbackWorkflowPlan(workflowId, payload) {
    return request(`/api/v1/workflows/${workflowId}/plan/rollback`, { method: "POST", body: payload });
  },
  reviseWorkflow(workflowId, instruction) {
    return request(`/api/v1/workflows/${workflowId}/replan`, { method: "POST", body: { instruction } });
  },
  getLifecycleEvents(workflowId, after = 0) {
    return request(`/api/v1/workflows/${workflowId}/lifecycle-events?after=${after}&format=json`);
  },
  approveWorkflowPlan(workflowId, comment = "") {
    return request(`/api/v1/workflows/${workflowId}/approve-plan`, { method: "POST", body: { comment } });
  },
  startWorkflow(workflowId) {
    return request(`/api/v1/workflows/${workflowId}/start`, { method: "POST", body: {} });
  },
  getExecution(executionId) {
    return request(`/api/v1/workflow-executions/${executionId}`);
  },
  getExecutionEvents(executionId, after = 0) {
    return request(`/api/v1/workflow-executions/${executionId}/events?after=${after}&format=json`);
  },
  getExecutionArtifacts(executionId) {
    return request(`/api/v1/workflow-executions/${executionId}/artifacts`);
  },
  getArtifactContent(executionId, artifactId) {
    return request(`/api/v1/workflow-executions/${executionId}/artifacts/${artifactId}/content`);
  },
  getExecutionExplainContext(executionId) {
    return request(`/api/v1/workflow-executions/${executionId}/explain-context`);
  },
  getExecutionEvidenceReport(executionId) {
    return request(`/api/v1/workflow-executions/${executionId}/evidence-report`);
  },
  listProjectTemplates() {
    return request("/api/v1/project-templates");
  },
  instantiateProject(templateId, payload) {
    return request(`/api/v1/project-templates/${templateId}/instantiate`, { method: "POST", body: payload });
  },
  listProjects() {
    return request("/api/v1/projects");
  },
  updateProject(projectId, payload) {
    return request(`/api/v1/projects/${projectId}`, { method: "PATCH", body: payload });
  },
  deleteProject(projectId) {
    return request(`/api/v1/projects/${projectId}`, {
      method: "DELETE",
      headers: { "X-QWS-Confirm-Project-Id": projectId },
    });
  },
  getProject(projectId) {
    return request(`/api/v1/projects/${projectId}`);
  },
  getProjectProcess(projectId) {
    return request(`/api/v1/projects/${projectId}/process`);
  },
  getProjectWorkspaceBootstrap(projectId) {
    return request(`/api/v1/projects/${projectId}/workspace-bootstrap`);
  },
  dispatchProjectBlueprint(projectId, payload) {
    return request(`/api/v1/projects/${projectId}/planning/dispatch`, { method: "POST", body: payload });
  },
  listProjectDocuments(projectId) {
    return request(`/api/v1/projects/${projectId}/documents`);
  },
  saveProjectDocument(projectId, documentId, payload) {
    return request(`/api/v1/projects/${projectId}/documents/${encodeURIComponent(documentId)}`, { method: "PUT", body: payload });
  },
  exportProjectDocumentObsidian(projectId, documentId) {
    return request(`/api/v1/projects/${projectId}/documents/${encodeURIComponent(documentId)}/obsidian`);
  },
  listProjectAssets(projectId) {
    return request(`/api/v1/projects/${projectId}/assets`);
  },
  listProjectAutomations(projectId) {
    return request(`/api/v1/projects/${projectId}/automations`);
  },
  saveProjectAutomation(projectId, ruleId, payload) {
    return request(`/api/v1/projects/${projectId}/automations/${encodeURIComponent(ruleId)}`, { method: "PUT", body: payload });
  },
  runProjectAutomation(projectId, payload) {
    return request(`/api/v1/projects/${projectId}/automation-runs`, { method: "POST", body: payload });
  },
  decideProjectAutomationRecommendation(projectId, runId, recommendationId, payload) {
    return request(`/api/v1/projects/${projectId}/automation-runs/${encodeURIComponent(runId)}/recommendations/${encodeURIComponent(recommendationId)}/decision`, { method: "POST", body: payload });
  },
  getProjectCalibration(projectId) {
    return request(`/api/v1/projects/${projectId}/calibration`);
  },
  createBusinessIntake(projectId, payload) {
    return request(`/api/v1/projects/${projectId}/business-intakes`, { method: "POST", body: payload });
  },
  generateProcessDraft(projectId, payload) {
    return request(`/api/v1/projects/${projectId}/process-drafts/generate`, { method: "POST", body: payload });
  },
  applyProcessDraft(projectId, draftId, payload) {
    return request(`/api/v1/projects/${projectId}/process-drafts/${draftId}/apply`, { method: "POST", body: payload });
  },
  getProjectSchedule(projectId) {
    return request(`/api/v1/projects/${projectId}/schedule`);
  },
  getProjectGraph(projectId, viewType) {
    return request(`/api/v1/projects/${projectId}/graphs/${viewType}`);
  },
  saveProjectWorkflowGraph(projectId, payload) {
    return request(`/api/v1/projects/${projectId}/graphs/workflow`, { method: "PUT", body: payload });
  },
  getProjectResourcePlan(projectId) {
    return request(`/api/v1/projects/${projectId}/resource-plan`);
  },
  recommendProjectResourcePlan(projectId, payload) {
    return request(`/api/v1/projects/${projectId}/resource-plan/recommend`, { method: "POST", body: payload });
  },
  saveProjectResourcePlan(projectId, payload) {
    return request(`/api/v1/projects/${projectId}/resource-plan`, { method: "PUT", body: payload });
  },
  generateProjectSimulationDataset(projectId, simulatorId, payload) {
    return request(`/api/v1/projects/${projectId}/resource-plan/simulations/${encodeURIComponent(simulatorId)}/datasets`, { method: "POST", body: payload });
  },
  listProjectDatasets(projectId) {
    return request(`/api/v1/projects/${projectId}/datasets`);
  },
  listProjectModels(projectId) {
    return request(`/api/v1/projects/${projectId}/models`);
  },
  updateProjectTopologyNode(projectId, nodeId, payload) {
    return request(`/api/v1/projects/${projectId}/resource-plan/topology/nodes/${encodeURIComponent(nodeId)}`, { method: "PUT", body: payload });
  },
  askProjectResourceContext(projectId, payload) {
    return request(`/api/v1/projects/${projectId}/resource-plan/chat`, { method: "POST", body: payload });
  },
  getProjectTaskRelationDigest(projectId, taskId) {
    return request(`/api/v1/projects/${projectId}/tasks/${taskId}/relation-digest`);
  },
  getProjectTaskDeliveryManifests(projectId, taskId) {
    return request(`/api/v1/projects/${projectId}/tasks/${taskId}/delivery-manifests`);
  },
  decideProjectTaskDeliveryManifest(projectId, taskId, manifestId, payload) {
    return request(`/api/v1/projects/${projectId}/tasks/${taskId}/delivery-manifests/${manifestId}/decision`, { method: "POST", body: payload });
  },
  resolveProjectTaskChallenge(projectId, taskId, reviewId, payload) {
    return request(`/api/v1/projects/${projectId}/challenge-reviews/${reviewId}/decision`, {
      method: "POST",
      body: payload,
    });
  },
  checkProjectTaskDuplicates(projectId, payload) {
    return request(`/api/v1/projects/${projectId}/task-duplicate-check`, { method: "POST", body: payload });
  },
  createProjectTaskMergePreview(projectId, primaryTaskId, payload) {
    return request(`/api/v1/projects/${projectId}/tasks/${primaryTaskId}/merge-previews`, { method: "POST", body: payload });
  },
  applyProjectTaskMerge(projectId, mergeId, payload) {
    return request(`/api/v1/projects/${projectId}/task-merges/${mergeId}/apply`, { method: "POST", body: payload });
  },
  updateProjectTask(projectId, taskId, payload) {
    return request(`/api/v1/projects/${projectId}/tasks/${taskId}`, { method: "PATCH", body: payload });
  },
  editProjectTask(projectId, taskId, payload) {
    return request(`/api/v1/projects/${projectId}/tasks/${taskId}`, { method: "PUT", body: payload });
  },
  createProjectTask(projectId, payload) {
    return request(`/api/v1/projects/${projectId}/tasks`, { method: "POST", body: payload });
  },
  bindProjectTaskWorkflow(projectId, taskId, payload) {
    return request(`/api/v1/projects/${projectId}/tasks/${taskId}/workflow`, { method: "PUT", body: payload });
  },
  openTaskConversation(payload) {
    return request("/api/v1/task-conversations", { method: "POST", body: payload });
  },
  listTaskMessages(conversationId) {
    return request(`/api/v1/task-conversations/${conversationId}/messages`);
  },
  streamTaskMessage(conversationId, payload, onEvent) {
    return streamRequest(`/api/v1/task-conversations/${conversationId}/messages/stream`, payload, onEvent);
  },
  submitTaskClarification(payload) {
    return request("/api/chat/stream/clarify", { method: "POST", body: payload });
  },
  listTaskBackfillProposals(conversationId) {
    return request(`/api/v1/task-conversations/${conversationId}/backfill-proposals`);
  },
  materializeTaskBackfillProposal(conversationId, assistantRequestId) {
    return request(`/api/v1/task-conversations/${conversationId}/backfill-proposals`, {
      method: "POST",
      body: { assistant_request_id: assistantRequestId },
    });
  },
  discardTaskBackfillProposal(conversationId, proposalId) {
    return request(`/api/v1/task-conversations/${conversationId}/backfill-proposals/${proposalId}/discard`, { method: "POST" });
  },
  applyTaskBackfillProposal(conversationId, proposalId) {
    return request(`/api/v1/task-conversations/${conversationId}/backfill-proposals/${proposalId}/apply`, { method: "POST" });
  },
  completeTaskBackfillProposal(conversationId, proposalId, cardContext, appliedEvidence = {}) {
    return request(`/api/v1/task-conversations/${conversationId}/backfill-proposals/${proposalId}/complete`, {
      method: "POST",
      body: { card_context: cardContext, applied_evidence: appliedEvidence },
    });
  },
};
