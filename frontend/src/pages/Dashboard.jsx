import React, { useEffect, useRef } from 'react';
import './Dashboard.css';

export default function Dashboard() {
  return (
    <>
      
  <main className="orch-overview-shell">
    <section className="orch-stage" aria-label="需求输入工作台">
      <header className="orch-stage-header">
        <div id="ai-conversation-workspace" aria-label="工作总结">
          <div className="orch-workspace-grid">
            <div className="orch-summary-copy">
              <span className="orch-summary-kicker">工作总结</span>
              <h1 className="orch-summary-title">角色编排已就位</h1>
              <p className="orch-summary-goal">目标：搭建 AI 智能体编排平台，并由系统协同完成营销与销售闭环。</p>
              <p className="orch-summary-progress">6 个角色已就绪，等待进入工作流；如遇到营销/销售之外的其他场景，可先通过右侧通用对话框收集上下文与边界。</p>
              <div className="orch-summary-note" aria-label="通用交互说明">
                <span className="orch-summary-pill">其他场景入口</span>
                <span className="orch-summary-pill">需求理解</span>
                <span className="orch-summary-pill">决策追问</span>
                <span className="orch-summary-pill">文本输出</span>
              </div>
            </div>
            <aside className="orch-dialog-shell" aria-label="通用场景对话框">
              <div className="orch-dialog-head">
                <div>
                  <span className="orch-kicker">通用交互</span>
                  <strong>其他场景对话框</strong>
                  <p>除了“端到端完成营销和销售”这类预置链路，其他开放场景可先在这里完成需求理解、追问与文本化输出。</p>
                </div>
                <span className="orch-dialog-status" id="genericDialogStatus">ready</span>
              </div>
              <div className="orch-dialog-scenarios" id="genericScenarioChips" aria-label="场景示例"></div>
              <section className="orch-dialog-thread" id="genericDialogThread" aria-live="polite">
                <div className="orch-dialog-bubble orch-dialog-bubble--user" id="genericUserBubble"></div>
                <div className="orch-dialog-bubble orch-dialog-bubble--assistant">
                  <span className="orch-dialog-kicker">正在理解需求</span>
                  <strong id="genericDecisionTitle">正在识别目标范围</strong>
                  <div id="genericDecisionBody"></div>
                </div>
                <article className="orch-decision-card">
                  <strong id="genericFollowupTitle">下一步</strong>
                  <p id="genericFollowupText"></p>
                  <div className="orch-decision-tags" id="genericDecisionTags"></div>
                </article>
              </section>
              <div className="orch-composer" aria-label="场景输入框">
                <textarea id="genericScenarioInput" placeholder="例如：我想做一个 AI 智能体编排平台，并且帮我完成营销和销售，请帮我端到端完成"></textarea>
                <div className="orch-composer-foot">
                  <span className="orch-composer-hint">输入开放需求后，系统会先判断是直接编排角色，还是先进行补充追问。</span>
                  <button className="orch-send-button" id="genericScenarioSend" type="button">更新预览</button>
                </div>
              </div>
            </aside>
          </div>
        </div>
      </header>

      <section className="orch-wall-panel" aria-label="角色输入入口">
        <div className="orch-wall-stage">
          <div id="role-grid" aria-label="角色卡画廊"></div>
        </div>
      </section>
    </section>

    <div className="orch-modal-shell" id="roleModal" hidden>
      <div className="orch-modal-backdrop" data-close-modal></div>
      <section className="orch-modal-card" role="dialog" aria-modal="true" aria-labelledby="modalTitle">
        <button className="orch-modal-close" type="button" aria-label="关闭" data-close-modal>×</button>
        <div className="orch-modal-header">
          <span className="orch-kicker">role file</span>
          <h3 id="modalTitle">角色详情</h3>
        </div>

        <div className="orch-modal-view-toggle" role="tablist" aria-label="角色编辑视图">
          <button className="orch-modal-tab is-active" type="button" id="modalTabForm" data-modal-view="form" role="tab" aria-selected="true">表单编辑</button>
          <button className="orch-modal-tab" type="button" id="modalTabJson" data-modal-view="json" role="tab" aria-selected="false">JSON 视图</button>
        </div>

        <div className="orch-modal-panel" id="modalPanelForm">
          <div className="orch-modal-fields">
            <label className="orch-modal-field">
              <span>名字</span>
              <input id="modalName" type="text" value="" />
            </label>
            <label className="orch-modal-field">
              <span>职责</span>
              <textarea id="modalDuty" rows="4"></textarea>
            </label>
            <label className="orch-modal-field">
              <span>技能</span>
              <textarea id="modalSkills" rows="3"></textarea>
            </label>
          </div>
        </div>

        <div className="orch-modal-panel" id="modalPanelJson" hidden>
          <div className="orch-json-panel">
            <article className="orch-json-card" aria-live="polite">
              <strong>角色 JSON</strong>
              <p>当前角色对象会随着名字、职责、技能编辑实时同步，不写入文件，仅用于预览当前提交结构。</p>
              <pre className="orch-json-code" id="modalRoleJson"></pre>
            </article>
          </div>
        </div>

        <div className="orch-modal-actions">
          <a className="orch-route-button" id="enter-role-insight" data-route="insight" href="./role-insight.html" data-dom-id="enter-role-insight">进入工作流</a>
          <a className="orch-route-button" id="enter-role-product" data-route="product" href="./role-product.html" data-dom-id="enter-role-product">进入工作流</a>
          <a className="orch-route-button" id="enter-role-engineering" data-route="engineering" href="./role-engineering.html" data-dom-id="enter-role-engineering">进入工作流</a>
          <a className="orch-route-button" id="enter-role-marketing" data-route="marketing" href="./role-marketing.html" data-dom-id="enter-role-marketing">进入工作流</a>
          <a className="orch-route-button" id="enter-role-sales" data-route="sales" href="./role-sales.html" data-dom-id="enter-role-sales">进入工作流</a>
          <a className="orch-route-button" id="enter-role-founder" data-route="founder" href="./role-founder.html" data-dom-id="enter-role-founder">进入工作流</a>
        </div>
      </section>
    </div>
  </main>

  

    </>
  );
}
