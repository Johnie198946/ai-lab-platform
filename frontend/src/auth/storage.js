const AUTH_STORAGE_KEY = "ai-lab-platform.auth";
const WORKSPACE_STORAGE_PREFIX = "ai-lab-platform.workspace";

const isBrowser = () => typeof window !== "undefined";

const readJson = (key) => {
  if (!isBrowser()) {
    return null;
  }

  try {
    const raw = window.localStorage.getItem(key);
    if (!raw) {
      return null;
    }
    return JSON.parse(raw);
  } catch {
    return null;
  }
};

const writeJson = (key, value) => {
  if (!isBrowser()) {
    return;
  }

  window.localStorage.setItem(key, JSON.stringify(value));
};

const removeKey = (key) => {
  if (!isBrowser()) {
    return;
  }

  window.localStorage.removeItem(key);
};

const workspaceStorageKey = (scopeKey = "default") => `${WORKSPACE_STORAGE_PREFIX}.${scopeKey}`;

export const loadAuthSession = () => readJson(AUTH_STORAGE_KEY);

export const saveAuthSession = (session) => {
  writeJson(AUTH_STORAGE_KEY, {
    ...session,
    savedAt: new Date().toISOString(),
  });
};

export const clearAuthSession = () => {
  removeKey(AUTH_STORAGE_KEY);
};

export const getAuthAccessToken = () => loadAuthSession()?.accessToken ?? "";

export const loadWorkspaceDraft = (scopeKey) => readJson(workspaceStorageKey(scopeKey));

export const saveWorkspaceDraft = (scopeKey, draft) => {
  writeJson(workspaceStorageKey(scopeKey), {
    ...draft,
    savedAt: new Date().toISOString(),
  });
};

export const clearWorkspaceDraft = (scopeKey) => {
  removeKey(workspaceStorageKey(scopeKey));
};
