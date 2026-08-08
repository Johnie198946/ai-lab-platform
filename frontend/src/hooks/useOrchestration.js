import { useEffect, useMemo, useState } from "react";
import { clearWorkspaceDraft, loadWorkspaceDraft, saveWorkspaceDraft } from "../auth/storage";
import { DEFAULT_GOAL } from "../config/env";
import { getPlatformStatus, orchestrateGoal, persistRole } from "../services/orchestrationService";

const INITIAL_MESSAGES = [
  {
    id: "assistant-welcome",
    role: "assistant",
    content:
      "请输入你的业务目标。我会先理解需求，再通过 ai-lab-platform 创建一支可执行的 6 角色团队，并展开需求输入页与关键角色页壳体。",
  },
];

const createUserMessage = (content) => ({
  id: `user-${Date.now()}`,
  role: "user",
  content,
});

const createAssistantMessage = (content) => ({
  id: `assistant-${Date.now()}`,
  role: "assistant",
  content,
});

const buildDefaultSessionMeta = () => ({
  sessionId: "",
  source: "ai-lab-platform",
  fallbackUsed: false,
  fallbackReason: "",
});

const buildDefaultSaveState = () => ({
  status: "idle",
  message: "修改后可回写到平台。",
});

const buildDefaultWorkspace = () => ({
  messages: INITIAL_MESSAGES,
  input: DEFAULT_GOAL,
  roles: [],
  selectedRoleId: null,
  sessionMeta: buildDefaultSessionMeta(),
  submitError: "",
  saveState: buildDefaultSaveState(),
});

const coerceWorkspace = (draft) => {
  if (!draft || typeof draft !== "object") {
    return buildDefaultWorkspace();
  }

  return {
    messages: Array.isArray(draft.messages) && draft.messages.length > 0 ? draft.messages : INITIAL_MESSAGES,
    input: typeof draft.input === "string" && draft.input.trim() ? draft.input : DEFAULT_GOAL,
    roles: Array.isArray(draft.roles) ? draft.roles : [],
    selectedRoleId: typeof draft.selectedRoleId === "string" ? draft.selectedRoleId : null,
    sessionMeta: {
      ...buildDefaultSessionMeta(),
      ...(draft.sessionMeta ?? {}),
    },
    submitError: typeof draft.submitError === "string" ? draft.submitError : "",
    saveState: {
      ...buildDefaultSaveState(),
      ...(draft.saveState ?? {}),
    },
  };
};

export const useOrchestration = ({ scopeKey }) => {
  const [messages, setMessages] = useState(INITIAL_MESSAGES);
  const [input, setInput] = useState(DEFAULT_GOAL);
  const [isThinking, setIsThinking] = useState(false);
  const [roles, setRoles] = useState([]);
  const [selectedRoleId, setSelectedRoleId] = useState(null);
  const [sessionMeta, setSessionMeta] = useState(buildDefaultSessionMeta);
  const [platformStatus, setPlatformStatus] = useState({
    status: "checking",
    message: "正在检测 ai-lab-platform 连接状态...",
  });
  const [submitError, setSubmitError] = useState("");
  const [saveState, setSaveState] = useState(buildDefaultSaveState);
  const [restoredScopeKey, setRestoredScopeKey] = useState("");

  const selectedRole = useMemo(
    () => roles.find((role) => role.id === selectedRoleId) ?? null,
    [roles, selectedRoleId],
  );

  useEffect(() => {
    const draft = coerceWorkspace(loadWorkspaceDraft(scopeKey));
    setMessages(draft.messages);
    setInput(draft.input);
    setRoles(draft.roles);
    setSelectedRoleId(draft.selectedRoleId);
    setSessionMeta(draft.sessionMeta);
    setSubmitError(draft.submitError);
    setSaveState(draft.saveState);
    setRestoredScopeKey(scopeKey);
  }, [scopeKey]);

  useEffect(() => {
    if (restoredScopeKey !== scopeKey) {
      return;
    }

    saveWorkspaceDraft(scopeKey, {
      messages,
      input,
      roles,
      selectedRoleId,
      sessionMeta,
      submitError,
      saveState,
    });
  }, [
    input,
    messages,
    roles,
    restoredScopeKey,
    saveState,
    scopeKey,
    selectedRoleId,
    sessionMeta,
    submitError,
  ]);

  useEffect(() => {
    let active = true;

    const loadStatus = async () => {
      try {
        const result = await getPlatformStatus();
        if (active) {
          setPlatformStatus(result);
        }
      } catch (error) {
        if (active) {
          setPlatformStatus({
            status: "offline",
            message: error.message || "后端暂不可用，将在提交时按配置决定是否降级。",
          });
        }
      }
    };

    loadStatus();
    return () => {
      active = false;
    };
  }, []);

  const submitPrompt = async () => {
    const trimmed = input.trim();
    if (!trimmed || isThinking) {
      return;
    }

    setMessages((prev) => [...prev, createUserMessage(trimmed)]);
    setIsThinking(true);
    setSubmitError("");
    setRoles([]);
    setSelectedRoleId(null);
    setSaveState({
      status: "idle",
      message: "生成完成后可保存角色配置。",
    });

    try {
      const result = await orchestrateGoal(trimmed);
      setMessages((prev) => [...prev, createAssistantMessage(result.reply)]);
      setRoles(result.roles);
      setSelectedRoleId(result.roles[0]?.id ?? null);
      setSessionMeta({
        sessionId: result.sessionId,
        source: result.source,
        fallbackUsed: result.fallbackUsed,
        fallbackReason: result.fallbackReason ?? "",
      });
      setPlatformStatus((prev) =>
        result.fallbackUsed
          ? {
              status: "degraded",
              message: result.fallbackReason || "编排请求已切换为本地兜底模式。",
            }
          : prev.status === "checking"
            ? { status: "online", message: "后端编排接口联调成功。" }
            : prev,
      );
    } catch (error) {
      const message = error.message || "编排失败，请检查后端接口配置。";
      setSubmitError(message);
      setMessages((prev) => [
        ...prev,
        createAssistantMessage(`本次编排失败：${message}`),
      ]);
    } finally {
      setIsThinking(false);
    }
  };

  const handleInputKeyDown = (event) => {
    if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
      submitPrompt();
    }
  };

  const handleRoleFieldChange = (roleId, field, value) => {
    setRoles((prev) =>
      prev.map((role) => (role.id === roleId ? { ...role, [field]: value } : role)),
    );
    setSaveState({
      status: "dirty",
      message: "当前修改尚未保存。",
    });
  };

  const saveSelectedRole = async () => {
    if (!selectedRole) {
      return;
    }

    setSaveState({
      status: "saving",
      message: "正在保存角色配置...",
    });

    try {
      const result = await persistRole({
        sessionId: sessionMeta.sessionId,
        roleId: selectedRole.id,
        role: selectedRole,
        fallbackUsed: sessionMeta.fallbackUsed,
      });

      setRoles((prev) =>
        prev.map((role) => (role.id === selectedRole.id ? result.role : role)),
      );
      setSaveState({
        status: result.persisted ? "saved" : "local",
        message: result.message,
      });
    } catch (error) {
      setSaveState({
        status: "error",
        message: error.message || "角色保存失败，请稍后重试。",
      });
    }
  };

  const clearWorkspace = () => {
    const workspace = buildDefaultWorkspace();
    clearWorkspaceDraft(scopeKey);
    setMessages(workspace.messages);
    setInput(workspace.input);
    setRoles(workspace.roles);
    setSelectedRoleId(workspace.selectedRoleId);
    setSessionMeta(workspace.sessionMeta);
    setSubmitError(workspace.submitError);
    setSaveState({
      status: "idle",
      message: "已清空本地会话，等待新的编排请求。",
    });
  };

  return {
    clearWorkspace,
    input,
    isThinking,
    messages,
    platformStatus,
    roles,
    saveState,
    selectedRole,
    selectedRoleId,
    sessionMeta,
    submitError,
    setInput,
    setSelectedRoleId,
    handleInputKeyDown,
    handleRoleFieldChange,
    saveSelectedRole,
    submitPrompt,
  };
};
