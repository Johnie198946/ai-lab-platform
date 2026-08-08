import { AvatarPanel } from "../components/AvatarPanel";
import { ChatPanel } from "../components/ChatPanel";
import { handleCardPointerMove, useAmbientEffects } from "../hooks/useAmbientEffects";
import { useOrchestration } from "../hooks/useOrchestration";

export default function App() {
  const {
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
  } = useOrchestration();

  const { cardsRef, cursorCoreRef, cursorGlowRef } = useAmbientEffects({
    rolesCount: roles.length,
    selectedRoleId,
  });

  return (
    <div className="app-shell">
      <div className="ambient-cursor ambient-cursor--core" ref={cursorCoreRef} />
      <div className="ambient-cursor ambient-cursor--glow" ref={cursorGlowRef} />

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
