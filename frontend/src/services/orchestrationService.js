import { ENABLE_DEMO_FALLBACK } from "../config/env";
import { normalizeRole, normalizeSession, buildFallbackSession } from "../utils/roleTransforms";
import { platformApi } from "./platformApi";

export const getPlatformStatus = async () => {
  const health = await platformApi.getHealth();
  return {
    status: "online",
    message: `后端在线，版本 ${health?.version ?? "unknown"}`,
  };
};

export const orchestrateGoal = async (goal) => {
  try {
    const session = await platformApi.createOrchestrationSession(goal);
    return normalizeSession(session);
  } catch (error) {
    if (!ENABLE_DEMO_FALLBACK) {
      throw error;
    }
    return buildFallbackSession(goal, error.message);
  }
};

export const generateRoleWorkflow = async (sessionId, roleId, goal) => {
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
    const res = await platformApi.generateRoleWorkflow(sessionId, roleId, goal);
    if (res && res.tasks) {
      localStorage.setItem(cacheKey, JSON.stringify(res));
    }
    return res;
  } catch (error) {
    console.error("generateRoleWorkflow api err:", error);
    // fallback 
    return {
      tasks: ["分析需求中..."],
      details: ["正在为您处理..."],
      summary: "生成中，请稍候...",
      _cached: false
    }
  }
};

export const persistRole = async ({ sessionId, roleId, role, fallbackUsed }) => {
  if (!sessionId || fallbackUsed) {
    return {
      persisted: false,
      mode: "local",
      role: normalizeRole(role, role),
      message: "当前为本地兜底模式，已仅保存到前端草稿。",
    };
  }

  const savedRole = await platformApi.updateRole(sessionId, roleId, role);
  return {
    persisted: true,
    mode: "remote",
    role: normalizeRole(savedRole, role),
    message: "角色配置已回写到 ai-lab-platform。",
  };
};
