import { Link } from 'react-router-dom';
import React, { useEffect, useRef } from 'react';
import { useAuth } from '../auth/AuthContext';
import { useOrchestration } from '../hooks/useOrchestration';
import './RoleSales.css';

export default function RoleSales() {
  const { sessionScopeKey } = useAuth();
  const { roles } = useOrchestration({ scopeKey: sessionScopeKey });
  const role = roles.find((r) => r.id === 'sales') || { name: '销售经理', summary: '将客户邮件整理成可切换的工作台，同时输出翻译、总结、回复建议与结构化 JSON。' };

  return (
    <>
      
  <main className="page-shell">
    <section className="app-shell">
      <header className="topbar">
        <div className="topbar-meta">
          <span className="brand-mark">AI Agent Orchestration</span>
          <span className="topbar-divider"></span>
          <span>角色工作流</span>
        </div>
        <div className="topbar-status">
          <span className="pill">销售工作页</span>
          <span className="pill live"><span className="dot"></span>邮件工作台在线</span>
        </div>
      </header>

      <section className="page-body">
        <Link to="/orchestration" className="back-link" data-dom-id="back-overview-sales">
          <span>←</span>
          <span>查看其他人的工作</span>
        </Link>

        <section className="summary-card">
          <div className="summary-text">
            <p className="eyebrow">{role.name}</p>
            <h1>{role.summary}</h1>
            <p className="summary-progress">页面不再使用漂移墙，而是回到销售日常更熟悉的邮件界面。左侧聚焦邮件列表与当前客户，右侧通过标签切换原始邮件、翻译、总结、回复建议和 JSON，保留跨角色工作流的连续性与返回入口。</p>
          </div>
          <div className="summary-status">
            <span className="status-pill is-active">邮件界面</span>
            <span className="status-pill">翻译</span>
            <span className="status-pill">总结</span>
            <span className="status-pill">回复建议</span>
            <span className="status-pill">JSON 视图</span>
          </div>
        </section>

        <section className="workbench" aria-label="销售邮件工作台">
          <section className="panel">
            <div className="panel-head">
              <div className="panel-copy">
                <p className="eyebrow">邮件界面</p>
                <h2>客户邮件列表</h2>
                <p>左侧保留销售日常查看方式：邮箱列表、优先级、阶段和当前客户摘要。点击不同邮件后，右侧详情区同步切换对应内容。</p>
              </div>
              <span className="micro-pill is-active" id="sales-mail-stage">报价推进</span>
            </div>

            <div className="mail-list" id="sales-mail-list">
              <article className="mail-item is-active" tabindex="0" role="button" data-mail="0">
                <small>来自 APAC Retail Group · 今天 09:12</small>
                <strong>Re: 关于 AI Agent 试点报价、数据边界和本地化要求</strong>
                <p>客户明确要求先看中文翻译、重点摘要和建议回复，希望在下周评审前确认部署方式与预算范围。</p>
              </article>
              <article className="mail-item" tabindex="0" role="button" data-mail="1">
                <small>来自 Nordic Manufacturing · 昨天 18:40</small>
                <strong>Follow-up on pilot timeline, security review and workshop agenda</strong>
                <p>重点在试点排期、安全审查材料，以及是否能提前提供工作坊议程与会前准备清单。</p>
              </article>
              <article className="mail-item" tabindex="0" role="button" data-mail="2">
                <small>来自 Horizon Commerce · 周二 14:06</small>
                <strong>Questions about multilingual support, CRM sync and next-step ownership</strong>
                <p>客户关注多语言能力、CRM 同步和内部责任分工，希望看到更清晰的下一步动作建议。</p>
              </article>
            </div>
          </section>

          <section className="mail-reader" id="sales-reader">
            <div className="mail-header">
              <div>
                <p className="eyebrow">当前邮件</p>
                <h2 id="sales-subject">Re: 关于 AI Agent 试点报价、数据边界和本地化要求</h2>
              </div>
              <div className="mail-meta">
                <span className="mail-tag" id="sales-priority">高优先级</span>
                <span className="mail-tag" id="sales-owner">Owner · 区域销售</span>
              </div>
            </div>

            <div className="meta-grid">
              <div className="meta-card">
                <strong>发件人</strong>
                <span id="sales-from">Emily Chen · APAC Retail Group</span>
              </div>
              <div className="meta-card">
                <strong>商机阶段</strong>
                <span id="sales-stage">报价推进 / 试点评审前</span>
              </div>
              <div className="meta-card">
                <strong>下一动作</strong>
                <span id="sales-next-action">发送中文摘要、部署说明和回复建议</span>
              </div>
            </div>

            <div className="tab-bar" id="sales-tab-bar" aria-label="邮件功能标签">
              <button className="tab-button is-active" type="button" data-tab="original">原始邮件</button>
              <button className="tab-button" type="button" data-tab="translation">翻译</button>
              <button className="tab-button" type="button" data-tab="summary">总结</button>
              <button className="tab-button" type="button" data-tab="reply">回复建议</button>
              <button className="tab-button" type="button" data-tab="json">JSON</button>
            </div>

            <div className="tab-panels">
              <section className="tab-panel is-active" data-panel="original">
                <div className="mail-body" id="sales-original-panel">
                  <p>Hi team,</p>
                  <p>Thanks again for the demo. Before our internal review next week, could you help us with three things:</p>
                  <ul>
                    <li>a Chinese summary we can circulate internally,</li>
                    <li>confirmation of whether customer data can remain within our local environment,</li>
                    <li>and a suggested reply for our procurement lead regarding pricing range and deployment options.</li>
                  </ul>
                  <blockquote>We would also appreciate a structured version of the email contents so our PMO can track decisions without rewriting them manually.</blockquote>
                  <p>Best,<br />Emily</p>
                </div>
              </section>

              <section className="tab-panel" data-panel="translation">
                <div className="mail-body" id="sales-translation-panel">
                  <p>您好，团队：</p>
                  <p>感谢上次演示。在我们下周内部评审之前，想请你们协助准备三项内容：</p>
                  <ul>
                    <li>一份可供内部转发的中文摘要；</li>
                    <li>确认客户数据是否可以完全保留在我们的本地环境中；</li>
                    <li>给采购负责人准备一段建议回复，说明价格区间和部署选项。</li>
                  </ul>
                  <blockquote>如果还能提供结构化版本的邮件内容，我们的 PMO 就不需要再手动整理决策事项。</blockquote>
                  <p>谢谢。<br />Emily</p>
                </div>
              </section>

              <section className="tab-panel" data-panel="summary">
                <div className="mail-body" id="sales-summary-panel">
                  <h3>重点摘要</h3>
                  <ul>
                    <li>客户需要一份可内部流转的中文版本，说明他们将在下周评审中使用。</li>
                    <li>数据边界和本地化部署是关键疑问，需明确是否支持本地环境闭环。</li>
                    <li>采购负责人需要价格区间与部署方式的标准说法，避免销售口径不一致。</li>
                    <li>客户希望邮件内容能结构化输出，减少 PMO 二次整理成本。</li>
                  </ul>
                </div>
              </section>

              <section className="tab-panel" data-panel="reply">
                <div className="reply-shell">
                  <div className="markdown" id="sales-reply-panel">
                    <h4>建议回复</h4>
                    <p>Hi Emily,</p>
                    <p>Thank you for outlining the review requirements so clearly. Below is a suggested response package we can send today:</p>
                    <ul>
                      <li>Provide a Chinese summary for internal circulation.</li>
                      <li>Confirm that a local deployment path is available for environments with strict data boundaries.</li>
                      <li>Share a pricing reply framework with two deployment options and the assumptions behind each range.</li>
                    </ul>
                    <p>We will also include a structured <code>JSON</code> summary so your PMO team can track decisions directly.</p>
                    <p>Best regards,<br />Sales Team</p>
                  </div>
                </div>
              </section>

              <section className="tab-panel" data-panel="json">
                <div className="json-shell">
                  <div className="json-toolbar">
                    <div>
                      <p className="eyebrow">可折叠 JSON</p>
                      <h3>mail-workbench.json</h3>
                    </div>
                    <span className="micro-pill is-active" id="sales-json-label">APAC Retail Group</span>
                  </div>
                  <div className="json-tree" id="sales-json-tree"></div>
                </div>
              </section>
            </div>
          </section>
        </section>
      </section>
    </section>
  </main>
  <button className="agent-launcher" id="agentLauncher" type="button" aria-label="打开销售经理数字人"><span className="agent-launcher-mark">AI</span><span className="agent-launcher-copy"><strong id="agentLauncherRole">销售经理数字人</strong><span>右侧入口 · 在当前页继续对话</span></span></button>
  <section className="agent-drawer" id="agentDrawer" aria-hidden="true"><div className="agent-drawer-panel"><div className="agent-drawer-head"><div><span className="agent-mini-label">右侧数字人入口</span><h3 id="agentRoleTitle">销售经理数字人</h3><p id="agentRoleIntro">补充邮件回复、异议处理和跟进动作，不打断当前销售邮件工作台。</p></div><button className="agent-drawer-close" id="agentDrawerClose" type="button" aria-label="关闭数字人面板">×</button></div><div className="agent-drawer-scroll"><div className="agent-hero-card"><div className="agent-avatar-shell"><div className="agent-avatar-core"></div><div className="agent-avatar-particles"><span></span><span></span><span></span></div><div className="agent-avatar-waves"><span></span><span></span><span></span><span></span></div></div><div className="agent-hero-copy"><span className="agent-status-pill">在线交互中</span><strong id="agentIdentityText">销售经理数字人</strong><p id="agentWelcomeCardText">可以直接追问客户回复、价格口径、异议处理和下一步跟进建议。</p></div></div><div className="agent-card-grid"><article className="agent-info-card"><span>当前关注</span><strong id="agentFocusTitle">邮件到跟进闭环</strong><p id="agentFocusText">把原始邮件、翻译、总结和回复建议转成可直接外发的话术。</p></article><article className="agent-info-card"><span>回答方式</span><strong id="agentModeTitle">客户导向 + 可发送</strong><p id="agentModeText">优先补充回复草稿、跟进节奏和异议应答，不只给摘要。</p></article></div><div className="agent-suggestion-grid" id="agentSuggestionGrid"></div><div className="agent-dialogue-card"><div className="agent-dialogue-head"><span>对话流</span><small>输入后会追加用户与系统气泡</small></div><div className="agent-messages" id="agentMessages"></div></div></div><form className="agent-composer" id="agentComposer"><div className="agent-composer-shell"><textarea id="agentComposerInput" placeholder="例如：帮我写一版更稳妥的客户回复。"></textarea><div className="agent-composer-foot"><span className="agent-composer-hint">支持继续追问回复草稿、异议处理和跟进动作。</span><button className="agent-composer-send" type="submit">发送</button></div></div></form></div></section>

  
  

    </>
  );
}
