import { Composer } from "./Composer";
import { MessageList } from "./MessageList";
import { RoleEditor } from "./RoleEditor";
import { RoleGrid } from "./RoleGrid";
import { RoleStagePanel } from "./RoleStagePanel";

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
              需求输入页
            </div>
            <h2>用一句需求，启动 6 角色全链路协作</h2>
            <p>
              按照 6 角色输出协议，这里统一承接数字人对话、需求输入、角色卡片和关键角色页入口。
            </p>
          </div>
          <div className="chat-header__meta">
            <span>数字人对话</span>
            <span>6 角色卡片</span>
            <span>{sessionMeta.fallbackUsed ? "受控兜底" : "平台联调"}</span>
          </div>
        </div>

        <div className="requirements-shell">
          <div className="requirements-shell__main">
            <div className="requirements-block">
              <div className="requirements-block__header">
                <div>
                  <span className="section-label">Conversation</span>
                  <h3>数字人对话与加载反馈</h3>
                </div>
                <p>过程使用流式反馈呈现，结果将在角色卡片和关键页面中继续展开。</p>
              </div>
              <MessageList messages={messages} isThinking={isThinking} />
            </div>

            <div className="requirements-block requirements-block--composer">
              <div className="requirements-block__header">
                <div>
                  <span className="section-label">Input</span>
                  <h3>需求输入区</h3>
                </div>
                <p>目标越具体，角色职责、技能边界和后续页面分区越稳定。</p>
              </div>
              <Composer
                input={input}
                isThinking={isThinking}
                submitError={submitError}
                onChange={onInputChange}
                onKeyDown={onInputKeyDown}
                onSubmit={onSubmit}
              />
            </div>
          </div>

          <aside className="requirements-shell__side">
            <div className="requirements-sidecard">
              <span className="section-label">Protocol</span>
              <h3>固定 6 角色</h3>
              <p>市场洞察专家 / 产品经理 / 开发工程师 / 营销经理 / 销售经理 / 老板</p>
            </div>
            <div className="requirements-sidecard">
              <span className="section-label">Render Rule</span>
              <h3>过程与结果分离</h3>
              <p>过程走 SSE 动效，结果走 JSON 区块渲染，Word 只承担下载动作。</p>
            </div>
            <div className="requirements-sidecard">
              <span className="section-label">Stage</span>
              <h3>当前联调状态</h3>
              <p>
                {sessionMeta.fallbackUsed
                  ? "后端异常时保持前端演示壳体可用，便于继续编辑和讲解。"
                  : "角色与会话优先使用 ai-lab-platform 的真实返回结果。"}
              </p>
            </div>
          </aside>
        </div>

        <RoleGrid
          cardsRef={cardsRef}
          roles={roles}
          selectedRoleId={selectedRoleId}
          sessionMeta={sessionMeta}
          onSelect={onRoleSelect}
          onPointerMove={onRolePointerMove}
        />

        <RoleStagePanel role={selectedRole} />

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
