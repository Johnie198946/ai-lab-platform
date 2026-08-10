import { getAuthAccessToken } from "../auth/storage";
import { API_TOKEN, REQUEST_TIMEOUT_MS, buildApiUrl, buildAuthUrl } from "../config/env";

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
};
