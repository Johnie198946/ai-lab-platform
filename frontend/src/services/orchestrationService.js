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
    // 快慢分流（2026-08-09·iOS 30s 限制修复）：
    // 软件开发项目类需求 → 编排（六角色·慢 38s）
    // 普通对话/查询 → /api/chat（DeepSeek+知识库·快 8s）
    const isDevProject = /(做|开发|搭建|构建|实现|创建|设计一个|搞一个|做一个).{0,20}(平台|系统|应用|软件|网站|小程序|工具|程序|产品|机器人|agent|Agent|AI|智能体|助手|模块|功能)/.test(goal)
      || /(端到端|帮我完成|帮我实现|全流程|编排)/.test(goal);
    if (!isDevProject) {
      const chat = await platformApi.chat(goal);
      return normalizeSession({ session_id: crypto.randomUUID().replace(/-/g, "").slice(0, 32), goal, reply: chat.answer ?? chat.reply ?? "已处理", roles: [] });
    }
    const session = await platformApi.createOrchestrationSession(goal);
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
