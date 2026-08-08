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
          Digital Human Console
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
          <h1>让数字人把一个目标拆成 6 角色链路</h1>
          <p>
            从需求输入开始，依次进入市场洞察、产品、开发、营销、销售与老板战情室。当前工作台优先重构登录、加载、输入页和关键角色页壳体，用于展厅稳定演示。
          </p>
        </div>

        <div className="status-stack">
          <div className="status-card">
            <span className="status-card__label">当前状态</span>
            <strong>{isThinking ? "正在编排角色与页面协议" : "等待新的业务需求"}</strong>
          </div>
          <div className="status-card">
            <span className="status-card__label">角色结果</span>
            <strong>{rolesCount > 0 ? `已生成 ${rolesCount} / 6 个角色` : "暂未生成角色"}</strong>
          </div>
          <div className="status-card status-card--accent">
            <span className="status-card__label">平台联调</span>
            <strong>{platformLabel}</strong>
            <p>{platformStatus.message}</p>
          </div>
          <div className="status-card">
            <span className="status-card__label">页面模式</span>
            <strong>{fallbackUsed ? "演示壳体优先" : "真实平台优先"}</strong>
            <p>{fallbackUsed ? "角色编辑先保存到前端草稿。" : "角色编辑将直接回写 ai-lab-platform。"}</p>
          </div>
        </div>

        <div className="signal-row">
          <span className="signal-pill">登录页</span>
          <span className="signal-pill">加载页</span>
          <span className="signal-pill">需求输入页</span>
          <span className="signal-pill">市场 / 开发 / 营销</span>
          <span className="signal-pill">协议驱动渲染</span>
        </div>
      </div>
    </section>
  );
}
