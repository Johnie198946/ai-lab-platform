export function RoleGrid({
  cardsRef,
  roles,
  selectedRoleId,
  sessionMeta,
  onSelect,
  onPointerMove,
}) {
  return (
    <div className="roles-shell" ref={cardsRef}>
      <div className="roles-shell__header">
        <div>
          <span className="section-label">Agent Team</span>
          <h3>自动生成的 6 个角色卡片</h3>
        </div>
        <p>
          {sessionMeta.fallbackUsed
            ? "后端不可用时会切到受控兜底，但仍保留可编辑流程。"
            : "当前角色由 ai-lab-platform 返回，并支持回写保存。"}
        </p>
      </div>

      <div className="roles-grid">
        {roles.length === 0 ? (
          <div className="roles-placeholder">
            <span className="roles-placeholder__icon">+</span>
            <p>发送需求后，平台会在这里生成角色团队。</p>
          </div>
        ) : (
          roles.map((role) => (
            <button
              key={role.id}
              type="button"
              className={`role-card ${selectedRoleId === role.id ? "role-card--active" : ""}`}
              onClick={() => onSelect(role.id)}
              onPointerMove={onPointerMove}
            >
              <span className="role-card__badge">{role.badge}</span>
              <strong>{role.title}</strong>
              <p>{role.summary}</p>
              <span className="role-card__cta">打开配置</span>
            </button>
          ))
        )}
      </div>
    </div>
  );
}
