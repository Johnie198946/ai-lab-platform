export function RoleGrid({
  cardsRef,
  roles,
  selectedRoleId,
  sessionMeta,
  onSelect,
  onPointerMove,
}) {
  const roleStatusMap = {
    insight: "屏4 洞察",
    product: "等待洞察",
    engineering: "屏6 开发",
    marketing: "屏7 营销",
    sales: "等待营销",
    boss: "屏9 战情室",
  };

  return (
    <div className="roles-shell" ref={cardsRef}>
      <div className="roles-shell__header">
        <div>
          <span className="section-label">Role Cards</span>
          <h3>6 角色团队与关键页面入口</h3>
        </div>
        <p>
          {sessionMeta.fallbackUsed
            ? "后端不可用时切到受控兜底，但仍保留角色编辑和关键页讲解壳体。"
            : "当前角色由 ai-lab-platform 返回，并可继续回写保存。"}
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
              <div className="role-card__topline">
                <span className="role-card__badge">{role.badge}</span>
                <span className="role-card__status">{roleStatusMap[role.id] ?? "待配置"}</span>
              </div>
              <strong>{role.title}</strong>
              <span className="role-card__name">{role.name}</span>
              <p>{role.summary}</p>
              <div className="role-card__tags">
                {(role.skills ?? "")
                  .split(/[、,，]/)
                  .map((tag) => tag.trim())
                  .filter(Boolean)
                  .slice(0, 3)
                  .map((tag) => (
                    <span key={tag}>{tag}</span>
                  ))}
              </div>
              <span className="role-card__cta">打开关键页与配置</span>
            </button>
          ))
        )}
      </div>
    </div>
  );
}
