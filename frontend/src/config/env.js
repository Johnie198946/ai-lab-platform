const trimTrailingSlash = (value) => value.replace(/\/+$/, "");

export const API_BASE_URL = trimTrailingSlash(import.meta.env.VITE_API_BASE_URL ?? "");
export const AUTH_BASE_URL = trimTrailingSlash(import.meta.env.VITE_AUTH_BASE_URL ?? "");
export const API_TOKEN = (import.meta.env.VITE_API_TOKEN ?? "").trim();
export const ENABLE_DEMO_FALLBACK =
  String(import.meta.env.VITE_ENABLE_DEMO_FALLBACK ?? "false").toLowerCase() !== "false";
// 硬编码 300s：Hermes 固化技能/doc-maker 画图可达 2-5 分钟(2026-08-09·120s 会掐断长任务)
export const REQUEST_TIMEOUT_MS = 300000;
export const DEFAULT_GOAL = "";

export const API_ORIGIN_LABEL = API_BASE_URL || "same-origin / Vite proxy";
export const AUTH_ORIGIN_LABEL = AUTH_BASE_URL || "same-origin / Vite auth proxy";

export const buildApiUrl = (path) => `${API_BASE_URL}${path}`;
export const buildAuthUrl = (path) =>
  AUTH_BASE_URL ? `${AUTH_BASE_URL}${path}` : `/authen-api${path}`;
