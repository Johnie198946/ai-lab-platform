const trimTrailingSlash = (value) => value.replace(/\/+$/, "");

export const API_BASE_URL = trimTrailingSlash(import.meta.env.VITE_API_BASE_URL ?? "");
export const AUTH_BASE_URL = trimTrailingSlash(import.meta.env.VITE_AUTH_BASE_URL ?? "");
export const API_TOKEN = (import.meta.env.VITE_API_TOKEN ?? "").trim();
export const ENABLE_DEMO_FALLBACK =
  String(import.meta.env.VITE_ENABLE_DEMO_FALLBACK ?? "false").toLowerCase() !== "false";
export const REQUEST_TIMEOUT_MS = Number(import.meta.env.VITE_REQUEST_TIMEOUT_MS ?? 15000);
export const DEFAULT_GOAL =
  "我想做一个 AI 智能体编排平台，并且帮我完成营销和销售，请帮我端到端完成";

export const API_ORIGIN_LABEL = API_BASE_URL || "same-origin / Vite proxy";
export const AUTH_ORIGIN_LABEL = AUTH_BASE_URL || "same-origin / Vite auth proxy";

export const buildApiUrl = (path) => `${API_BASE_URL}${path}`;
export const buildAuthUrl = (path) =>
  AUTH_BASE_URL ? `${AUTH_BASE_URL}${path}` : `/authen-api${path}`;
