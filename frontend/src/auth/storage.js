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

  try {
    window.localStorage.setItem(key, JSON.stringify(value));
  } catch (error) {
    console.warn(`localStorage QuotaExceededError when setting key: ${key}. Clearing draft storage and retrying.`, error);
    try {
        if (key.startsWith(WORKSPACE_STORAGE_PREFIX)) {
            removeKey(key);
            // 进一步压缩对象以防止重试失败
            const minimalValue = { savedAt: new Date().toISOString() };
            window.localStorage.setItem(key, JSON.stringify(minimalValue));
        }
    } catch (retryError) {
        console.error("Failed to save to localStorage after retry", retryError);
    }
  }
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
  // Omit extremely large fields like long inputs or giant base64 attachments from being saved to prevent QuotaExceededError
  const sanitizedDraft = { ...draft };
  if (sanitizedDraft.input && sanitizedDraft.input.length > 5000) {
      sanitizedDraft.input = sanitizedDraft.input.substring(0, 5000) + "\n...[内容过长，为防止本地存储爆满已截断，上传的巨型附件内容不会被保存到草稿中]";
  }

  writeJson(workspaceStorageKey(scopeKey), {
    ...sanitizedDraft,
    savedAt: new Date().toISOString(),
  });
};

export const clearWorkspaceDraft = (scopeKey) => {
  removeKey(workspaceStorageKey(scopeKey));
};
