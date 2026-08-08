import { AvatarPanel } from "../components/AvatarPanel";
import { ChatPanel } from "../components/ChatPanel";
import { useAuth } from "../auth/AuthContext";
import { handleCardPointerMove, useAmbientEffects } from "../hooks/useAmbientEffects";
import { useOrchestration } from "../hooks/useOrchestration";

export function OrchestrationPage() {
  const { authSession, logout, sessionScopeKey } = useAuth();
  const {
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
  } = useOrchestration({ scopeKey: sessionScopeKey });

  const { cardsRef, cursorCoreRef, cursorGlowRef } = useAmbientEffects({
    rolesCount: roles.length,
    selectedRoleId,
  });

  const userLabel =
    authSession?.user?.username || authSession?.identifier || authSession?.user?.user_id || "当前用户";

  return (
    <div className="app-shell">
      <div className="ambient-cursor ambient-cursor--core" ref={cursorCoreRef} />
      <div className="ambient-cursor ambient-cursor--glow" ref={cursorGlowRef} />

      <header className="workspace-topbar">
        <div>
          <div className="eyebrow">
            <span className="eyebrow__dot" />
            Secure Workspace
          </div>
          <h1>AI Lab 编排工作台</h1>
        </div>
        <div className="workspace-topbar__actions">
          <div className="workspace-chip">
            <span>{userLabel}</span>
            <strong>{authSession?.mode === "dev" ? "开发会话" : "已登录"}</strong>
          </div>
          <div className="workspace-chip">
            <span>租户</span>
            <strong>{authSession?.user?.tenant_key || "unknown"}</strong>
          </div>
          <button className="workspace-action" type="button" onClick={clearWorkspace}>
            清空本地会话
          </button>
          <button className="workspace-action workspace-action--ghost" type="button" onClick={logout}>
            退出登录
          </button>
        </div>
      </header>

      <main className="workspace">
        <AvatarPanel
          isThinking={isThinking}
          rolesCount={roles.length}
          platformStatus={platformStatus}
          fallbackUsed={sessionMeta.fallbackUsed}
        />

        <ChatPanel
          cardsRef={cardsRef}
          input={input}
          isThinking={isThinking}
          roles={roles}
          saveState={saveState}
          selectedRole={selectedRole}
          selectedRoleId={selectedRoleId}
          sessionMeta={sessionMeta}
          submitError={submitError}
          onInputChange={setInput}
          onInputKeyDown={handleInputKeyDown}
          onRoleFieldChange={handleRoleFieldChange}
          onRolePointerMove={handleCardPointerMove}
          onRoleSave={saveSelectedRole}
          onRoleSelect={setSelectedRoleId}
          onSubmit={submitPrompt}
          messages={messages}
        />
      </main>
    </div>
  );
}
