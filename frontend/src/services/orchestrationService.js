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

export const orchestrateGoal = async (goal, sessionId = null) => {
  try {
    // 聊天框一律走 Hermes main（用户拍板 8/9：通路都用 Hermes·知识库/技能/记忆在 Hermes）
    // 记忆接力（2026-08-09）：带 sessionId 时后端读取历史·多轮上下文连贯
    const session = await platformApi.createOrchestrationSession(goal, sessionId);
    return normalizeSession(session);
  } catch (error) {
    if (!ENABLE_DEMO_FALLBACK) {
      throw error;
    }
    return buildFallbackSession(goal, error.message);
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
