import { API_TOKEN, REQUEST_TIMEOUT_MS, buildApiUrl } from "../config/env";

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

const request = async (path, options = {}) => {
  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);

  try {
    const headers = new Headers(options.headers ?? {});
    headers.set("Accept", "application/json");
    if (options.body !== undefined) {
      headers.set("Content-Type", "application/json");
    }
    if (API_TOKEN) {
      headers.set("Authorization", `Bearer ${API_TOKEN}`);
    }

    const response = await fetch(buildApiUrl(path), {
      method: options.method ?? "GET",
      headers,
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
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
  createOrchestrationSession(goal) {
    return request("/api/orchestration/sessions", {
      method: "POST",
      body: { goal },
    });
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
};
