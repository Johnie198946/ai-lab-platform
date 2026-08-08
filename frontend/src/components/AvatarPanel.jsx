export function AvatarPanel({ isThinking, rolesCount, platformStatus, fallbackUsed }) {
  const platformLabel =
    platformStatus.status === "online"
      ? "联调在线"
      : platformStatus.status === "degraded"
        ? "兜底模式"
        : platformStatus.status === "offline"
          ? "连接异常"
          : "检测中";

  return (
    <section className="avatar-panel">
      <div className="panel-surface avatar-panel__surface">
        <div className="eyebrow">
          <span className="eyebrow__dot" />
          Digital Human Workspace
        </div>

        <div className="avatar-stage">
          <div className="avatar-aura" />
          <div className="avatar-body">
            <div className="avatar-head">
              <span className="avatar-eye avatar-eye--left" />
              <span className="avatar-eye avatar-eye--right" />
              <span className="avatar-mouth" />
            </div>
            <div className="avatar-neck" />
            <div className="avatar-shoulder" />
          </div>
          <div className="avatar-ring avatar-ring--outer" />
          <div className="avatar-ring avatar-ring--inner" />
        </div>

        <div className="avatar-copy">
          <h1>让数字人为你编排一整支 AI 团队</h1>
          <p>
            用低干扰、对话式的交互方式，把复杂的业务目标拆成可执行角色，并持续补全每个角色的职责、能力与协同关系。
          </p>
        </div>

        <div className="status-stack">
          <div className="status-card">
            <span className="status-card__label">当前状态</span>
            <strong>{isThinking ? "正在思考与组建角色" : "等待你的下一条指令"}</strong>
          </div>
          <div className="status-card">
            <span className="status-card__label">编排结果</span>
            <strong>{rolesCount > 0 ? `已生成 ${rolesCount} 个角色` : "暂未生成角色"}</strong>
          </div>
          <div className="status-card status-card--accent">
            <span className="status-card__label">平台联调</span>
            <strong>{platformLabel}</strong>
            <p>{platformStatus.message}</p>
          </div>
          <div className="status-card">
            <span className="status-card__label">当前模式</span>
            <strong>{fallbackUsed ? "受控本地兜底" : "真实平台接口"}</strong>
            <p>{fallbackUsed ? "角色编辑会先保存在前端草稿。" : "角色编辑将直接回写 ai-lab-platform。"}</p>
          </div>
        </div>

        <div className="signal-row">
          <span className="signal-pill">白色系</span>
          <span className="signal-pill">低饱和</span>
          <span className="signal-pill">轻量动效</span>
          <span className="signal-pill">角色可编辑</span>
          <span className="signal-pill">平台联调</span>
        </div>
      </div>
    </section>
  );
}
