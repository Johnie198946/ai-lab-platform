const trimTrailingSlash = (value) => value.replace(/\/+$/, "");

export const API_BASE_URL = trimTrailingSlash(import.meta.env.VITE_API_BASE_URL ?? "");
export const AUTH_BASE_URL = trimTrailingSlash(import.meta.env.VITE_AUTH_BASE_URL ?? "");
export const API_TOKEN = (import.meta.env.VITE_API_TOKEN ?? "").trim();
export const ENABLE_DEMO_FALLBACK =
  String(import.meta.env.VITE_ENABLE_DEMO_FALLBACK ?? "false").toLowerCase() !== "false";
export const REQUEST_TIMEOUT_MS = Number(import.meta.env.VITE_REQUEST_TIMEOUT_MS ?? 120000);
export const DEFAULT_GOAL = "";

export const API_ORIGIN_LABEL = API_BASE_URL || "same-origin / Vite proxy";
export const AUTH_ORIGIN_LABEL = AUTH_BASE_URL || "same-origin / Vite auth proxy";

export const buildApiUrl = (path) => `${API_BASE_URL}${path}`;
export const buildAuthUrl = (path) =>
  AUTH_BASE_URL ? `${AUTH_BASE_URL}${path}` : `/authen-api${path}`;
