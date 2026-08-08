import { Composer } from "./Composer";
import { MessageList } from "./MessageList";
import { RoleEditor } from "./RoleEditor";
import { RoleGrid } from "./RoleGrid";

export function ChatPanel({
  cardsRef,
  input,
  isThinking,
  roles,
  saveState,
  selectedRole,
  selectedRoleId,
  sessionMeta,
  submitError,
  onInputChange,
  onInputKeyDown,
  onRoleFieldChange,
  onRolePointerMove,
  onRoleSave,
  onRoleSelect,
  onSubmit,
  messages,
}) {
  return (
    <section className="chat-panel">
      <div className="panel-surface chat-panel__surface">
        <div className="chat-header">
          <div>
            <div className="eyebrow">
              <span className="eyebrow__dot" />
              AI 对话编排台
            </div>
            <h2>通过一句目标，生成完整执行团队</h2>
          </div>
          <div className="chat-header__meta">
            <span>AI orchestration</span>
            <span>Role config</span>
            <span>{sessionMeta.fallbackUsed ? "Local fallback" : "Platform synced"}</span>
          </div>
        </div>

        <MessageList messages={messages} isThinking={isThinking} />

        <Composer
          input={input}
          isThinking={isThinking}
          submitError={submitError}
          onChange={onInputChange}
          onKeyDown={onInputKeyDown}
          onSubmit={onSubmit}
        />

        <RoleGrid
          cardsRef={cardsRef}
          roles={roles}
          selectedRoleId={selectedRoleId}
          sessionMeta={sessionMeta}
          onSelect={onRoleSelect}
          onPointerMove={onRolePointerMove}
        />

        <RoleEditor
          role={selectedRole}
          saveState={saveState}
          fallbackUsed={sessionMeta.fallbackUsed}
          onFieldChange={onRoleFieldChange}
          onSave={onRoleSave}
        />
      </div>
    </section>
  );
}
