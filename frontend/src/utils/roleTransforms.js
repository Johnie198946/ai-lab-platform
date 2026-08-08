import { ROLE_BLUEPRINTS } from "../data/roleBlueprints";

const ROLE_FOCUS_HINTS = {
  insight: ["市场", "客户", "竞品", "机会", "行业"],
  product: ["产品", "平台", "编排", "体验", "流程"],
  engineering: ["开发", "工程", "接口", "前端", "后端"],
  marketing: ["营销", "传播", "品牌", "内容", "增长"],
  sales: ["销售", "商机", "线索", "转化", "成交"],
  boss: ["战略", "预算", "决策", "经营", "目标"],
};

const cleanText = (value, fallback = "") => {
  if (typeof value !== "string") {
    return fallback;
  }
  const trimmed = value.trim();
  return trimmed || fallback;
};

const createFocus = (roleId, goal) => {
  const matched = (ROLE_FOCUS_HINTS[roleId] ?? []).filter((term) => goal.includes(term));
  if (matched.length > 0) {
    return `优先关注：${matched.slice(0, 3).join(" / ")}。`;
  }
  return `围绕目标“${goal.slice(0, 36)}”补齐执行细节。`;
};

export const normalizeRole = (role, fallback = {}) => ({
  id: cleanText(role?.id, fallback.id ?? `role-${Math.random().toString(36).slice(2, 8)}`),
  title: cleanText(role?.title, fallback.title ?? "未命名角色"),
  badge: cleanText(role?.badge, fallback.badge ?? "角色"),
  summary: cleanText(role?.summary, fallback.summary ?? ""),
  name: cleanText(role?.name, fallback.name ?? ""),
  responsibility: cleanText(role?.responsibility, fallback.responsibility ?? ""),
  skills: cleanText(role?.skills, fallback.skills ?? ""),
  focus: cleanText(role?.focus, fallback.focus ?? ""),
});

export const normalizeSession = (session) => {
  const fallbackRoles = ROLE_BLUEPRINTS;
  const roles = Array.isArray(session?.roles) ? session.roles : [];

  return {
    sessionId: cleanText(session?.session_id, ""),
    reply: cleanText(
      session?.reply,
      "已接收你的目标，并生成了一组可以继续编辑的角色配置。",
    ),
    source: cleanText(session?.source, "ai-lab-platform"),
    fallbackUsed: false,
    roles: roles.map((role, index) => normalizeRole(role, fallbackRoles[index])),
  };
};

export const buildFallbackSession = (goal, reason = "") => ({
  sessionId: "",
  reply:
    `后端暂不可用，已切换到受控本地兜底。当前目标是：${goal}。` +
    "你仍然可以继续编辑角色配置，待接口恢复后再回写到平台。",
  source: "frontend-fallback",
  fallbackUsed: true,
  fallbackReason: reason,
  roles: ROLE_BLUEPRINTS.map((role) =>
    normalizeRole(
      {
        ...role,
        summary: `${role.summary} ${createFocus(role.id, goal)}`,
        responsibility: `${role.responsibility} 围绕当前目标：${goal.slice(0, 48)}。`,
        focus: createFocus(role.id, goal),
      },
      role,
    ),
  ),
});
