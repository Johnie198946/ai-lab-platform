export function RoleEditor({ role, saveState, fallbackUsed, onFieldChange, onSave }) {
  if (!role) {
    return null;
  }

  return (
    <div className="editor-panel">
      <div className="editor-panel__header">
        <div>
          <span className="section-label">Role Editor</span>
          <h3>{role.title} 配置区</h3>
          <p>点击角色卡后，可在这里调整名字、摘要、职责和技能，确保输出物与现场讲解保持一致。</p>
        </div>
        <span className="editor-panel__hint">{fallbackUsed ? "本地草稿" : "平台回写"}</span>
      </div>

      <div className={`integration-banner integration-banner--${saveState.status}`}>
        {saveState.message}
      </div>

      <div className="editor-grid">
        <label className="field">
          <span>名字</span>
          <input
            value={role.name}
            onChange={(event) => onFieldChange(role.id, "name", event.target.value)}
            placeholder="输入角色名字"
          />
        </label>

        <label className="field">
          <span>角色焦点</span>
          <input value={role.focus ?? ""} readOnly />
        </label>

        <label className="field field--wide">
          <span>摘要</span>
          <textarea
            value={role.summary}
            onChange={(event) => onFieldChange(role.id, "summary", event.target.value)}
            placeholder="输入角色摘要"
            rows={3}
          />
        </label>

        <label className="field field--wide">
          <span>职责</span>
          <textarea
            value={role.responsibility}
            onChange={(event) => onFieldChange(role.id, "responsibility", event.target.value)}
            placeholder="输入角色职责"
            rows={3}
          />
        </label>

        <label className="field field--wide">
          <span>技能</span>
          <textarea
            value={role.skills}
            onChange={(event) => onFieldChange(role.id, "skills", event.target.value)}
            placeholder="输入角色技能，使用顿号或逗号分隔"
            rows={3}
          />
        </label>
      </div>

      <div className="editor-actions">
        <button type="button" onClick={onSave}>
          {fallbackUsed ? "保存到本地草稿" : "保存到 ai-lab-platform"}
        </button>
      </div>
    </div>
  );
}
