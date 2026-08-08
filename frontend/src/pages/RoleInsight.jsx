import { Link } from 'react-router-dom';
import React, { useEffect, useRef } from 'react';
import { useAuth } from '../auth/AuthContext';
import { useOrchestration } from '../hooks/useOrchestration';
import './RoleInsight.css';

export default function RoleInsight() {
  const { sessionScopeKey } = useAuth();
  const { roles } = useOrchestration({ scopeKey: sessionScopeKey });
  const role = roles.find((r) => r.id === 'insight') || { name: '市场洞察专家', summary: '以管理层视角判断 AI 行业格局、我方机会位与优先动作。' };

  return (
    <>
      
  <main className="page-shell" id="page-role-insight">
    <section className="app-shell">
      <header className="topbar">
        <div className="topbar-meta"><span className="brand-mark">AI Agent Orchestration</span><span className="topbar-divider"></span><span>角色工作流</span></div>
        <div className="topbar-status"><span className="pill">洞察工作页</span><span className="pill"><span className="dot"></span>文本工作台</span></div>
      </header>
      <section className="page-body">
        <Link to="/orchestration" className="back-link" data-dom-id="back-overview-insight"><span>←</span><span>查看其他人的工作</span></Link>
        <section className="summary-card" aria-label="市场洞察专家摘要">
          <div className="summary-text">
            <p className="eyebrow">{role.name}</p>
            <h1>{role.summary}</h1>
            <p className="summary-progress">这一页不试图展示所有分析过程，而是采用更接近咨询顾问首页的表达：先给结论框架，再进入三条分析主线，最后收束成可供管理层决策的判断、机会位和动作建议。</p>
            <div className="summary-meta"><span className="chip is-waiting" id="hero-stage-chip">等待任务启动</span><span className="chip" id="hero-overall-chip">0 / 3 已完成</span></div>
            <div className="summary-meta"><span className="chip">行业格局</span><span className="chip">技术路线</span><span className="chip">商业化窗口</span><span className="chip">竞争分层</span><span className="chip">建议动作</span></div>
            <div className="executive-strip" aria-label="管理层摘要框架">
              <article className="executive-card">
                <span>结论先行</span>
                <strong>行业正在从“模型能力竞争”过渡到“入口与交付竞争”。</strong>
                <p>头部玩家的差异不只在模型本身，更在入口控制、组织渗透和方案交付能力。</p>
              </article>
              <article className="executive-card">
                <span>机会位</span>
                <strong>我方更适合切入“高认知价值 + 可编纂输出”的场景。</strong>
                <p>优先把行业洞察、销售陪练、管理层摘要这类结果型场景做深，而不是泛化平台叙事。</p>
              </article>
              <article className="executive-card">
                <span>建议动作</span>
                <strong>先强化证据链，再扩展系统集成。</strong>
                <p>短期优先补足行业案例、可量化收益与可信交付表述，中期再扩大到复杂闭环。</p>
              </article>
            </div>
          </div>
          <div className="status-group">
            <span className="status-pill is-waiting" id="summary-pill-competitor">竞对采集</span>
            <span className="status-pill is-waiting" id="summary-pill-internal">内部映射</span>
            <span className="status-pill is-waiting" id="summary-pill-report">报告编纂</span>
            <span className="status-pill is-active" id="summary-pill-console">文本工作台</span>
            <article className="advisor-entry">
              <span>顾问入口</span>
              <strong>数字人顾问可直接补充管理层洞察</strong>
              <p>如果你想进一步压缩成董事会语言、拆成风险/机会/动作，或直接让它补一段结论摘要，可从这里继续追问。</p>
              <button className="secondary-button" type="button" data-open-agent>打开数字人顾问</button>
            </article>
          </div>
        </section>
        <section className="drift-scene" aria-label="洞察工作墙">
          <div className="scene-head">
            <div className="scene-copy">
              <p className="eyebrow">AI 行业分析路径</p>
              <h2>洞察工作墙</h2>
              <p>三条主线分别对应行业地图、内部供给与战略建议。页面更像咨询项目的管理层首页：先给结论框架，再允许你点击进入每条分析主线的顾问式文本工作台。</p>
            </div>
            <span className="scene-note" id="scene-note">点击分析主线，进入顾问式文本工作台</span>
          </div>
          <div className="drift-plane">
            <div className="drift-wall">
              <div className="drift-row" data-direction="left" style={{"--duration":"36s"}}>
                <div className="drift-track">
                  <button className="wall-tile" type="button" data-task-key="competitor" data-open-modal="competitor" data-dom-id="open-modal-competitor"><span className="tile-media"></span><div className="tile-content"><div className="tile-copy"><span className="tile-kicker">分析主线 01</span><h3>AI 行业格局与竞对地图</h3><p>覆盖字节跳动、阿里云、腾讯、华为、浪潮、H3C、OpenAI、Google、Claude，围绕市场分层、能力栈、生态位置与商业化路径展开对照。</p></div><div className="tile-meta"><span className="chip is-waiting" data-role="chip">待启动</span><span className="tile-note" data-role="note">9 个行业样本待判读</span></div><div className="tile-track"><div className="tile-fill" data-role="bar"></div></div><p className="tile-tail" data-role="tail">点击打开文本工作台，查看咨询式研判如何沉淀为竞对地图。</p></div></button>
                  <button className="wall-tile" type="button" data-task-key="internal" data-open-modal="internal" data-dom-id="open-modal-internal"><span className="tile-media"></span><div className="tile-content"><div className="tile-copy"><span className="tile-kicker">分析主线 02</span><h3>内部能力盘点与供给映射</h3><p>围绕产品路标、算力产品族、营销工具包、研发物料，判断哪些内部供给能承接 AI 机会位，哪些短板需要补足。</p></div><div className="tile-meta"><span className="chip is-waiting" data-role="chip">待启动</span><span className="tile-note" data-role="note">4 类内部证据待映射</span></div><div className="tile-track"><div className="tile-fill" data-role="bar"></div></div><p className="tile-tail" data-role="tail">点击打开文本工作台，查看能力盘点如何被收束为建议底稿。</p></div></button>
                  <button className="wall-tile" type="button" data-task-key="report" data-open-modal="report" data-dom-id="open-modal-report"><span className="tile-media"></span><div className="tile-content"><div className="tile-copy"><span className="tile-kicker">分析主线 03</span><h3>战略判断与建议动作</h3><p>依赖前两步完成后启动，把行业判断、竞争差异、我方机会位与优先级建议压缩为管理层可读的最终输出。</p></div><div className="tile-meta"><span className="chip is-waiting" data-role="chip">等待前序</span><span className="tile-note" data-role="note">依赖前两条分析主线</span></div><div className="tile-track"><div className="tile-fill" data-role="bar"></div></div><p className="tile-tail" data-role="tail">点击打开文本工作台，查看摘要卡与 Word 咨询报告如何生成。</p></div></button>
                  <button className="wall-tile" type="button" data-task-key="competitor" data-open-modal="competitor"><span className="tile-media"></span><div className="tile-content"><div className="tile-copy"><span className="tile-kicker">分析主线 01</span><h3>AI 行业格局与竞对地图</h3><p>在同一主线中审视头部平台厂商、云厂商、大模型厂商与生态玩家的角色分层。</p></div><div className="tile-meta"><span className="chip is-waiting" data-role="chip">待启动</span><span className="tile-note" data-role="note">市场分层</span></div><div className="tile-track"><div className="tile-fill" data-role="bar"></div></div><p className="tile-tail" data-role="tail">重复出现只为强化行业地图感，不引入新的业务分支。</p></div></button>
                  <button className="wall-tile" type="button" data-task-key="internal" data-open-modal="internal"><span className="tile-media"></span><div className="tile-content"><div className="tile-copy"><span className="tile-kicker">分析主线 02</span><h3>内部能力盘点与供给映射</h3><p>把内部资料转成“现有抓手 / 可放大能力 / 仍待补强项”的结构化上下文。</p></div><div className="tile-meta"><span className="chip is-waiting" data-role="chip">待启动</span><span className="tile-note" data-role="note">供给底稿</span></div><div className="tile-track"><div className="tile-fill" data-role="bar"></div></div><p className="tile-tail" data-role="tail">进入模态框后继续保留文本工作台式的进度、日志与结果区。</p></div></button>
                  <button className="wall-tile" type="button" data-task-key="report" data-open-modal="report"><span className="tile-media"></span><div className="tile-content"><div className="tile-copy"><span className="tile-kicker">分析主线 03</span><h3>战略判断与建议动作</h3><p>完成前置后自动切入编纂工作台，把顾问判断收束为结论先行的摘要与文档卡。</p></div><div className="tile-meta"><span className="chip is-waiting" data-role="chip">等待前序</span><span className="tile-note" data-role="note">管理层输出</span></div><div className="tile-track"><div className="tile-fill" data-role="bar"></div></div><p className="tile-tail" data-role="tail">在透视墙中重复出现，但始终只指向同一项战略建议任务。</p></div></button>
                </div>
              </div>
              <div className="drift-row" data-direction="right" style={{"--duration":"42s"}}>
                <div className="drift-track">
                  <button className="wall-tile" type="button" data-task-key="internal" data-open-modal="internal"><span className="tile-media"></span><div className="tile-content"><div className="tile-copy"><span className="tile-kicker">分析主线 02</span><h3>内部能力盘点与供给映射</h3><p>关注产品路标、算力产品族、营销工具包与研发物料，判断哪些能力能形成 AI 行业切入点。</p></div><div className="tile-meta"><span className="chip is-waiting" data-role="chip">待启动</span><span className="tile-note" data-role="note">4 类资料待映射</span></div><div className="tile-track"><div className="tile-fill" data-role="bar"></div></div><p className="tile-tail" data-role="tail">保持同一任务语义，以漂移运动形成统一的顾问工作墙。</p></div></button>
                  <button className="wall-tile" type="button" data-task-key="report" data-open-modal="report"><span className="tile-media"></span><div className="tile-content"><div className="tile-copy"><span className="tile-kicker">分析主线 03</span><h3>战略判断与建议动作</h3><p>等待竞对地图与内部映射完成后，再进入最终的判断收束与文档生产阶段。</p></div><div className="tile-meta"><span className="chip is-waiting" data-role="chip">等待前序</span><span className="tile-note" data-role="note">战略工作台</span></div><div className="tile-track"><div className="tile-fill" data-role="bar"></div></div><p className="tile-tail" data-role="tail">若条件未满足，打开后将明确停留在等待状态。</p></div></button>
                  <button className="wall-tile" type="button" data-task-key="competitor" data-open-modal="competitor"><span className="tile-media"></span><div className="tile-content"><div className="tile-copy"><span className="tile-kicker">分析主线 01</span><h3>AI 行业格局与竞对地图</h3><p>研究公开站点与产品入口，为后续竞争差异和商业化路径判断建立可编纂对照底稿。</p></div><div className="tile-meta"><span className="chip is-waiting" data-role="chip">待启动</span><span className="tile-note" data-role="note">竞对底稿</span></div><div className="tile-track"><div className="tile-fill" data-role="bar"></div></div><p className="tile-tail" data-role="tail">点击时直接进入研究模态框，查看行业判读过程。</p></div></button>
                  <button className="wall-tile" type="button" data-task-key="internal" data-open-modal="internal"><span className="tile-media"></span><div className="tile-content"><div className="tile-copy"><span className="tile-kicker">分析主线 02</span><h3>内部能力盘点与供给映射</h3><p>把内部资料压缩成可直接供战略判断调用的上下文、证据块与能力抓手。</p></div><div className="tile-meta"><span className="chip is-waiting" data-role="chip">待启动</span><span className="tile-note" data-role="note">证据纳入</span></div><div className="tile-track"><div className="tile-fill" data-role="bar"></div></div><p className="tile-tail" data-role="tail">三行漂移墙中重复出现，但只围绕同一个顾问任务入口展开。</p></div></button>
                  <button className="wall-tile" type="button" data-task-key="report" data-open-modal="report"><span className="tile-media"></span><div className="tile-content"><div className="tile-copy"><span className="tile-kicker">分析主线 03</span><h3>战略判断与建议动作</h3><p>在文本工作台里承接整合、判断、排序、编辑、Office 与 Word 的逐步结果展示。</p></div><div className="tile-meta"><span className="chip is-waiting" data-role="chip">等待前序</span><span className="tile-note" data-role="note">摘要与报告</span></div><div className="tile-track"><div className="tile-fill" data-role="bar"></div></div><p className="tile-tail" data-role="tail">结果区继续保留摘要占位与 Word 卡片，不回退为长流程页面。</p></div></button>
                  <button className="wall-tile" type="button" data-task-key="competitor" data-open-modal="competitor"><span className="tile-media"></span><div className="tile-content"><div className="tile-copy"><span className="tile-kicker">分析主线 01</span><h3>AI 行业格局与竞对地图</h3><p>角色定位、能力栈、生态位置与管理启示仍在同一任务中完成，不拆成零散看板。</p></div><div className="tile-meta"><span className="chip is-waiting" data-role="chip">待启动</span><span className="tile-note" data-role="note">行业判读</span></div><div className="tile-track"><div className="tile-fill" data-role="bar"></div></div><p className="tile-tail" data-role="tail">漂移墙强调任务存在感，但不会把页面重新拉回为复杂 dashboard。</p></div></button>
                </div>
              </div>
              <div className="drift-row" data-direction="left" style={{"--duration":"48s"}}>
                <div className="drift-track">
                  <button className="wall-tile" type="button" data-task-key="report" data-open-modal="report"><span className="tile-media"></span><div className="tile-content"><div className="tile-copy"><span className="tile-kicker">分析主线 03</span><h3>战略判断与建议动作</h3><p>该主线持续提示依赖关系，完成前置后再转换为可启动状态。</p></div><div className="tile-meta"><span className="chip is-waiting" data-role="chip">等待前序</span><span className="tile-note" data-role="note">依赖控制</span></div><div className="tile-track"><div className="tile-fill" data-role="bar"></div></div><p className="tile-tail" data-role="tail">模态框内继续保留进度条、日志流、结果摘要与 Word 卡片。</p></div></button>
                  <button className="wall-tile" type="button" data-task-key="competitor" data-open-modal="competitor"><span className="tile-media"></span><div className="tile-content"><div className="tile-copy"><span className="tile-kicker">分析主线 01</span><h3>AI 行业格局与竞对地图</h3><p>把九个竞对对象的研究过程统一折叠在文本工作台里，首屏只保留行业地图入口与状态。</p></div><div className="tile-meta"><span className="chip is-waiting" data-role="chip">待启动</span><span className="tile-note" data-role="note">9 个对象</span></div><div className="tile-track"><div className="tile-fill" data-role="bar"></div></div><p className="tile-tail" data-role="tail">视觉语言保持克制，但任务文本明确服务于 AI 行业洞察场景。</p></div></button>
                  <button className="wall-tile" type="button" data-task-key="internal" data-open-modal="internal"><span className="tile-media"></span><div className="tile-content"><div className="tile-copy"><span className="tile-kicker">分析主线 02</span><h3>内部能力盘点与供给映射</h3><p>四类内部资料被整理成面向战略建议的可调用底稿，而不是单纯静态罗列。</p></div><div className="tile-meta"><span className="chip is-waiting" data-role="chip">待启动</span><span className="tile-note" data-role="note">能力抽取</span></div><div className="tile-track"><div className="tile-fill" data-role="bar"></div></div><p className="tile-tail" data-role="tail">点击后继续沿用既有状态机与重新运行逻辑。</p></div></button>
                  <button className="wall-tile" type="button" data-task-key="report" data-open-modal="report"><span className="tile-media"></span><div className="tile-content"><div className="tile-copy"><span className="tile-kicker">分析主线 03</span><h3>战略判断与建议动作</h3><p>最终完成后将展示后端摘要占位与 AI 行业洞察建议报告 Word 卡片。</p></div><div className="tile-meta"><span className="chip is-waiting" data-role="chip">等待前序</span><span className="tile-note" data-role="note">Word 输出</span></div><div className="tile-track"><div className="tile-fill" data-role="bar"></div></div><p className="tile-tail" data-role="tail">克制白底、轻玻璃边框与细网格背景延续整页统一语言。</p></div></button>
                  <button className="wall-tile" type="button" data-task-key="competitor" data-open-modal="competitor"><span className="tile-media"></span><div className="tile-content"><div className="tile-copy"><span className="tile-kicker">分析主线 01</span><h3>AI 行业格局与竞对地图</h3><p>任务卡在透视平面里缓慢漂移，但用户始终可识别这是三条分析主线之一。</p></div><div className="tile-meta"><span className="chip is-waiting" data-role="chip">待启动</span><span className="tile-note" data-role="note">漂移墙入口</span></div><div className="tile-track"><div className="tile-fill" data-role="bar"></div></div><p className="tile-tail" data-role="tail">关闭动画偏好下会停用漂移效果，保留同样的任务语义与交互。</p></div></button>
                  <button className="wall-tile" type="button" data-task-key="internal" data-open-modal="internal"><span className="tile-media"></span><div className="tile-content"><div className="tile-copy"><span className="tile-kicker">分析主线 02</span><h3>内部能力盘点与供给映射</h3><p>内部映射与研发物料整理由同一模态框承接，不拆分额外业务卡片。</p></div><div className="tile-meta"><span className="chip is-waiting" data-role="chip">待启动</span><span className="tile-note" data-role="note">同一工作台</span></div><div className="tile-track"><div className="tile-fill" data-role="bar"></div></div><p className="tile-tail" data-role="tail">通过重复卡位形成墙面感，但内容仍只围绕三条分析主线本身。</p></div></button>
                </div>
              </div>
            </div>
          </div>
        </section>
      </section>
    </section>
  </main>
  <button className="agent-launcher" id="agentLauncher" type="button" aria-label="打开市场洞察专家数字人"><span className="agent-launcher-mark">AI</span><span className="agent-launcher-copy"><strong id="agentLauncherRole">市场洞察顾问数字人</strong><span>管理层洞察入口 · 点击后直接追问</span></span></button>
  <section className="agent-drawer" id="agentDrawer" aria-hidden="true"><div className="agent-drawer-panel"><div className="agent-drawer-head"><div><span className="agent-mini-label">右侧数字人入口</span><h3 id="agentRoleTitle">市场洞察专家数字人</h3><p id="agentRoleIntro">补充竞对分析、用户动机和洞察结论，不影响现有模态工作台。</p></div><button className="agent-drawer-close" id="agentDrawerClose" type="button" aria-label="关闭数字人面板">×</button></div><div className="agent-drawer-scroll"><div className="agent-hero-card"><div className="agent-avatar-shell"><div className="agent-avatar-core"></div><div className="agent-avatar-particles"><span></span><span></span><span></span></div><div className="agent-avatar-waves"><span></span><span></span><span></span><span></span></div></div><div className="agent-hero-copy"><span className="agent-status-pill">在线交互中</span><strong id="agentIdentityText">市场洞察专家数字人</strong><p id="agentWelcomeCardText">可以继续追问竞对差异、内部映射、结论压缩和报告编纂建议。</p></div></div><div className="agent-card-grid"><article className="agent-info-card"><span>当前关注</span><strong id="agentFocusTitle">竞对到结论闭环</strong><p id="agentFocusText">把采集、内部资料和报告编纂压成更易复用的洞察表达。</p></article><article className="agent-info-card"><span>回答方式</span><strong id="agentModeTitle">洞察化 + 可编纂</strong><p id="agentModeText">优先补充差异点、机会点和可进入报告的结论，不只复述过程。</p></article></div><div className="agent-suggestion-grid" id="agentSuggestionGrid"></div><div className="agent-dialogue-card"><div className="agent-dialogue-head"><span>对话流</span><small>输入后会追加用户与系统气泡</small></div><div className="agent-messages" id="agentMessages"></div></div></div><form className="agent-composer" id="agentComposer"><div className="agent-composer-shell"><textarea id="agentComposerInput" placeholder="例如：帮我把竞对差异压成 3 条管理层结论。"></textarea><div className="agent-composer-foot"><span className="agent-composer-hint">支持继续追问竞对、内部映射、报告摘要与建议动作。</span><button className="agent-composer-send" type="submit">发送</button></div></div></form></div></section>
  <div className="overlay" id="modal-overlay" hidden></div>
  <section className="modal" id="modal-competitor" aria-hidden="true">
    <div className="modal-shell" role="dialog" aria-modal="true" aria-labelledby="modal-title-competitor" data-dom-id="modal-competitor-workbench">
      <div className="modal-head"><div className="modal-copy modal-title"><span className="eyebrow">行业格局工作台</span><h2 id="modal-title-competitor">AI 行业格局与竞对地图</h2><p>以顾问式文本输出持续展示行业分析过程。任务会在 32 至 36 秒内依次判断角色定位、能力栈、商业化方式、生态位置与管理启示，并最终沉淀为竞对地图底稿。</p></div><div className="toolbar"><button className="secondary-button" type="button" data-rerun="competitor" data-dom-id="rerun-competitor">重新运行</button><button className="ghost-button" type="button" data-close-modal>关闭</button></div></div>
      <div className="modal-layout">
        <section className="workspace">
          <article className="progress-card"><div className="progress-meta"><span id="modal-status-competitor">待启动</span><span id="modal-time-competitor">预计 34 秒</span></div><div className="track"><div className="fill" id="modal-bar-competitor"></div></div><div className="progress-meta" style={{"marginTop":"10px"}}><span id="modal-label-competitor">等待启动行业格局研究</span><span id="modal-percent-competitor">0%</span></div></article>
          <article className="console-card"><div className="console-head"><span className="section-label">consulting log</span><span className="subtle-note">行业判读 / 路线拆解 / 顾问笔记</span></div><ul className="console" id="console-competitor"></ul></article>
        </section>
        <aside className="result-stack">
          <article className="result-card"><div className="console-head"><span className="section-label">行业地图对象</span><span className="subtle-note">点击项查看顾问详情</span></div><ul className="entity-list" id="entity-list-competitor"></ul></article>
          <article className="summary-card panel-card"><span className="chip is-waiting" id="summary-chip-competitor">研究窗口待命</span><h3>阶段结论</h3><p id="summary-text-competitor">任务完成后，这里会以文本卡片方式确认行业格局、能力分层与竞对地图已纳入对照底稿，并保留当前研究窗口的完成状态。</p></article>
          <article className="doc-card detail-card" id="competitor-detail-card"><div className="detail-card-head"><div><span className="section-label">顾问详情</span><h3 id="competitor-detail-title">选择一个竞对对象</h3></div><span className="chip is-waiting" id="competitor-detail-chip">待查看</span></div><div className="detail-card-body" id="competitor-detail-body"><p className="detail-empty">点击右侧竞对对象，即可在当前模态框内展开 markdown 详情。</p></div></article>
        </aside>
      </div>
    </div>
  </section>
  <section className="modal" id="modal-internal" aria-hidden="true">
    <div className="modal-shell" role="dialog" aria-modal="true" aria-labelledby="modal-title-internal" data-dom-id="modal-internal-workbench">
      <div className="modal-head"><div className="modal-copy modal-title"><span className="eyebrow">内部能力工作台</span><h2 id="modal-title-internal">内部能力盘点与供给映射</h2><p>以搜索、抽取、映射、纳入上下文的文本式过程展示内部资料收束。任务会在 15 至 18 秒内判断各类资料能否支撑 AI 行业打法、可形成哪些切入点，以及仍需补足的短板。</p></div><div className="toolbar"><button className="secondary-button" type="button" data-rerun="internal" data-dom-id="rerun-internal">重新运行</button><button className="ghost-button" type="button" data-close-modal>关闭</button></div></div>
      <div className="modal-layout">
        <section className="workspace">
          <article className="progress-card"><div className="progress-meta"><span id="modal-status-internal">待启动</span><span id="modal-time-internal">预计 16 秒</span></div><div className="track"><div className="fill" id="modal-bar-internal"></div></div><div className="progress-meta" style={{"marginTop":"10px"}}><span id="modal-label-internal">等待启动内部能力盘点</span><span id="modal-percent-internal">0%</span></div></article>
          <article className="console-card"><div className="console-head"><span className="section-label">mapping log</span><span className="subtle-note">能力抽取 / 机会映射 / 供给判断</span></div><ul className="console" id="console-internal"></ul></article>
        </section>
        <aside className="result-stack">
          <article className="result-card"><div className="console-head"><span className="section-label">内部供给对象</span><span className="subtle-note">点击项查看详情</span></div><ul className="internal-list" id="entity-list-internal"></ul></article>
          <article className="summary-card panel-card"><span className="chip is-waiting" id="summary-chip-internal">整理窗口待命</span><h3>阶段结论</h3><p id="summary-text-internal">完成后，这里会说明四类内部资料如何映射到 AI 行业机会位、可形成哪些切入点，并作为后续建议动作的证据底稿。</p></article>
          <article className="doc-card detail-card" id="internal-detail-card"><div className="detail-card-head"><div><span className="section-label">映射详情</span><h3 id="internal-detail-title">选择一个内部资料对象</h3></div><span className="chip is-waiting" id="internal-detail-chip">待查看</span></div><div className="detail-card-body" id="internal-detail-body"><p className="detail-empty">点击右侧资料项，即可在当前模态框内展开内部资料摘录与映射摘要。</p></div></article>
        </aside>
      </div>
    </div>
  </section>
  <section className="modal" id="modal-report" aria-hidden="true">
    <div className="modal-shell" role="dialog" aria-modal="true" aria-labelledby="modal-title-report" data-dom-id="modal-report-workbench">
      <div className="modal-head"><div className="modal-copy modal-title"><span className="eyebrow">战略建议工作台</span><h2 id="modal-title-report">战略判断与建议动作</h2><p>该流程依赖前两步完成。若前置任务未完成，则清楚展示等待状态；一旦条件满足，窗口会自动进入行业判断、竞争差异收束、我方机会位识别、优先级排序与 Word 交付的文本式编纂流程。</p></div><div className="toolbar"><button className="secondary-button" type="button" data-rerun="report" data-dom-id="rerun-report">重新运行</button><button className="ghost-button" type="button" data-close-modal>关闭</button></div></div>
      <div className="modal-layout">
        <section className="workspace">
          <article className="progress-card"><div className="progress-meta"><span id="modal-status-report">等待前置工作完成</span><span id="modal-time-report">预计 12 秒</span></div><div className="track"><div className="fill" id="modal-bar-report"></div></div><div className="progress-meta" style={{"marginTop":"10px"}}><span id="modal-label-report">等待前置工作完成</span><span id="modal-percent-report">0%</span></div></article>
          <article className="waiting-box" id="report-waiting-box"><div className="waiting-meta"><span className="chip is-waiting" id="report-waiting-chip">等待前置工作完成</span><span className="subtle-note" id="report-waiting-note">需先完成 AI 行业格局与竞对地图、内部能力盘点与供给映射</span></div><p>当前不启动战略判断流程。待前两步完成后，再次打开这个窗口即可自动进入文本工作台式的建议编纂过程。</p></article>
          <article className="console-card hidden" id="report-console-card"><div className="console-head"><span className="section-label">strategy log</span><span className="subtle-note">判断收束 / 建议排序 / Office</span></div><ul className="console" id="console-report"></ul></article>
        </section>
        <aside className="result-stack">
          <article className="result-card"><div className="console-head"><span className="section-label">判断步骤</span><span className="subtle-note">依赖前序结果</span></div><ul className="report-list" id="report-step-list"></ul></article>
          <article className="summary-card panel-card interactive-surface" id="report-summary-card" data-open-report-detail="summary" data-dom-id="report-summary-placeholder" tabindex="0" role="button" aria-label="查看后端文本摘要预览"><span className="chip is-waiting" id="summary-chip-report">等待编纂完成</span><h3>管理层摘要占位</h3><p id="summary-text-report">前序数据尚未汇合。完成后，这里会展示一段面向管理层的判断摘要，占位真实返回的行业判断、竞争差异、我方机会位与建议动作。</p></article>
          <article className="doc-card interactive-surface" id="report-word-card" data-open-report-detail="doc" data-dom-id="report-word-card" tabindex="0" role="button" aria-label="查看 Word 文档详情"><div className="doc-card-head"><span className="chip is-waiting" id="doc-chip-report">Word 输出待生成</span><span className="subtle-note" id="doc-note-report">等待调用 Office 工具</span></div><h3>AI 行业洞察建议报告.docx</h3><p id="doc-text-report">编纂流程完成后，这里会明确显示管理层咨询报告的完成状态，并保持克制的完成仪式感。</p><div className="result-meta"><span id="doc-meta-left-report">建议主文档</span><span id="doc-meta-right-report">未生成</span></div></article>
          <article className="doc-card detail-card" id="report-detail-card"><div className="detail-card-head"><div><span className="section-label">展开内容</span><h3 id="report-detail-title">点击摘要或文档卡查看内容</h3></div><span className="chip is-waiting" id="report-detail-chip">待查看</span></div><div className="detail-card-body" id="report-detail-body"><p className="detail-empty">摘要卡会展开完整 markdown 预览，Word 卡会展开文档元信息、章节摘要与导出状态。</p></div></article>
        </aside>
      </div>
    </div>
  </section>

  
  

    </>
  );
}
