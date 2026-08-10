import { ENABLE_DEMO_FALLBACK } from "../config/env";
import { getAuthAccessToken } from "../auth/storage";
import { buildApiUrl } from "../config/env";
import { platformApi } from "./platformApi";

const cleanText = (value, fallback = "") => {
  if (typeof value !== "string") return fallback;
  const trimmed = value.trim();
  return trimmed || fallback;
};

const normalizeRole = (role) => ({
  id: cleanText(role?.id, `role-${Math.random().toString(36).slice(2, 8)}`),
  title: cleanText(role?.title, "未命名角色"),
  badge: cleanText(role?.badge, "角色"),
  summary: cleanText(role?.summary, ""),
  name: cleanText(role?.name, ""),
  responsibility: cleanText(role?.responsibility, ""),
  skills: cleanText(role?.skills, ""),
  focus: cleanText(role?.focus, ""),
});

const normalizeSession = (session) => ({
  sessionId: cleanText(session?.session_id, ""),
  reply: cleanText(session?.reply, "已接收你的目标。"),
  source: cleanText(session?.source, "ai-lab-platform"),
  fallbackUsed: false,
  roles: Array.isArray(session?.roles) ? session.roles.map(normalizeRole) : [],
});

const buildFallbackSession = (goal, reason = "") => ({
  sessionId: "",
  reply: `后端暂不可用。当前目标是：${goal}。`,
  source: "frontend-fallback",
  fallbackUsed: true,
  fallbackReason: reason,
  roles: [],
});

export const getPlatformStatus = async () => {
  const health = await platformApi.getHealth();
  return {
    status: "online",
    message: `后端在线，版本 ${health?.version ?? "unknown"}`,
  };
};

export const orchestrateGoal = async (goal, sessionId = null) => {
  try {
    const session = await platformApi.createOrchestrationSession(goal, sessionId);
    return normalizeSession(session);
  } catch (error) {
    if (!ENABLE_DEMO_FALLBACK) {
      throw error;
    }
    return buildFallbackSession(goal, error.message);
  }
};

export const orchestrateGoalStream = async (goal, sessionId = null, onChunk) => {
  try {
    const controller = new AbortController();
    const timeoutId = window.setTimeout(() => controller.abort(), 480000);

    const headers = new Headers({
      "Content-Type": "application/json",
      "Accept": "text/event-stream",
    });
    
    const accessToken = getAuthAccessToken();
    if (accessToken) {
      headers.set("Authorization", `Bearer ${accessToken}`);
    }

    const body = sessionId ? { goal, session_id: sessionId, stream: true } : { goal, stream: true };

    const response = await fetch(buildApiUrl("/api/orchestration/sessions"), {
      method: "POST",
      headers,
      body: JSON.stringify(body),
      signal: controller.signal,
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let fullReply = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";

      for (const line of lines) {
        if (line.startsWith("data: ")) {
          const data = line.slice(6).trim();
          if (data === "[DONE]") continue;
          
          try {
            const chunk = JSON.parse(data);
            const content = chunk.content || chunk.text || chunk.delta || "";
            if (content) {
              fullReply += content;
              onChunk?.(content, fullReply);
            }
          } catch {
            // 非 JSON 行·忽略
          }
        }
      }
    }

    window.clearTimeout(timeoutId);
    // 从响应头接回后端真实 session_id（首轮流式时后端通过 X-Session-ID 返回新建的 client_sid）
    // Header 缺失时 fallback 到传入的旧 sessionId（容错·不抛异常）
    const sidFromHeader = response.headers.get("X-Session-ID") || sessionId;
    return { reply: fullReply, sessionId: sidFromHeader || "", streamed: true };
  } catch (error) {
    if (error.name === "AbortError") {
      throw new Error("请求超时");
    }
    throw error;
  }
};

export const generateRoleWorkflow = async (sessionId, roleId, goal, dataRequirements) => {
  const cacheKey = `workflow_cache_${sessionId}_${roleId}`;
  const cached = localStorage.getItem(cacheKey);
  if (cached) {
    try {
      const parsed = JSON.parse(cached);
      parsed._cached = true;
      return parsed;
    } catch (e) {}
  }
  try {
    const res = await platformApi.generateRoleWorkflow(sessionId, roleId, goal, dataRequirements);
    if (res && res.tasks) {
      localStorage.setItem(cacheKey, JSON.stringify(res));
    }
    return res;
  } catch (error) {
    console.error("generateRoleWorkflow api err:", error);
    return {
      tasks: ["分析需求中..."],
      details: ["正在为您处理..."],
      summary: "生成中，请稍候...",
      _cached: false
    };
  }
};

export const persistRole = async ({ sessionId, roleId, role, fallbackUsed }) => {
  if (!sessionId || fallbackUsed) {
    return {
      persisted: false,
      mode: "local",
      role: normalizeRole(role),
      message: "当前为本地兜底模式，已仅保存到前端草稿。",
    };
  }

  const savedRole = await platformApi.updateRole(sessionId, roleId, role);
  return {
    persisted: true,
    mode: "remote",
    role: normalizeRole(savedRole),
    message: "角色配置已回写到 ai-lab-platform。",
  };
};
