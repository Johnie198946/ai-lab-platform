import { Link } from 'react-router-dom';
import React, { useEffect, useRef } from 'react';
import { useAuth } from '../auth/AuthContext';
import { useOrchestration } from '../hooks/useOrchestration';
import './RoleMarketing.css';

export default function RoleMarketing() {
  const { sessionScopeKey } = useAuth();
  const { roles } = useOrchestration({ scopeKey: sessionScopeKey });
  const role = roles.find((r) => r.id === 'marketing') || { name: '营销经理', summary: '从灵感确认到并行创作、评审收口，再到最终发布的营销创作流水线。' };

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
          <span className="pill">营销工作页</span>
          <span className="pill live"><span className="dot"></span>流水线运行中</span>
        </div>
      </header>

      <section className="page-body">
        <Link to="/orchestration" className="back-link" data-dom-id="back-overview-marketing">
          <span>←</span>
          <span>查看其他人的工作</span>
        </Link>

        <section className="hero">
          <article className="panel hero-card">
            <p className="eyebrow">{role.name}</p>
            <h1>{role.summary}</h1>
            <p className="hero-copy">
              页面重构为真实推进中的营销工作台：先锁定灵感初稿卡片，再让 4 张内容卡以 SSE 式流式状态并行推进，随后进入 MOR 5 节点评审，最后收口为可发布的渠道包。
            </p>
            <div className="hero-meta">
              <span className="status-pill is-active">初稿已确认</span>
              <span className="status-pill is-active">4 卡并行创作</span>
              <span className="status-pill">MOR 评审中</span>
              <span className="status-pill">发布待放行</span>
            </div>
          </article>

          <aside className="panel hero-summary">
            <div className="summary-stat">
              <span>并行卡片</span>
              <strong>4 张</strong>
              <p>主视觉、长文、社媒短帖、销售转发摘要同步推进。</p>
            </div>
            <div className="summary-stat">
              <span>评审节点</span>
              <strong>5 节点</strong>
              <p>Brand、Legal、产品、销售、运营联合收口。</p>
            </div>
            <div className="summary-stat">
              <span>发布结果</span>
              <strong>3 渠道</strong>
              <p>官网、公众号、销售转发包统一生成。</p>
            </div>
          </aside>
        </section>

        <section className="workspace">
          <div className="main-column">
            <article className="panel pipeline-card">
              <div className="section-head">
                <div className="section-title">
                  <p className="eyebrow">Pipeline</p>
                  <h2>营销创作主线</h2>
                </div>
                <span className="section-note">灵感初稿卡片确认 → 4 卡并行创作 60s+（SSE）→ MOR 5 节点评审 → 发布</span>
              </div>
              <div className="pipeline-rail">
                <div className="stage-node">
                  <small>阶段 01</small>
                  <strong>灵感初稿卡片确认</strong>
                  <p>将主叙事、受众切口与承接动作统一到可拍板的初稿卡片。</p>
                </div>
                <div className="stage-node">
                  <small>阶段 02</small>
                  <strong>4 卡并行创作</strong>
                  <p>四条内容线并行流式生成，持续输出草稿与修订记录。</p>
                </div>
                <div className="stage-node">
                  <small>阶段 03</small>
                  <strong>MOR 5 节点评审</strong>
                  <p>五个角色节点给出明确意见、风险和放行条件。</p>
                </div>
                <div className="stage-node">
                  <small>阶段 04</small>
                  <strong>发布</strong>
                  <p>聚合最终发布包、渠道结果与上线状态。</p>
                </div>
              </div>
            </article>

            <article className="panel pipeline-card">
              <div className="section-head">
                <div className="section-title">
                  <p className="eyebrow">Stage A</p>
                  <h2>灵感初稿卡片确认</h2>
                </div>
                <span className="section-note">点击卡片查看完整 markdown 内容</span>
              </div>
              <div className="idea-grid">
                <button className="idea-card interactive-card is-active" type="button" data-detail-id="idea-main">
                  <span className="mini-pill is-active">已选主稿</span>
                  <strong>可信 AI 协作，不再是概念演示</strong>
                  <p className="idea-snippet">从“能做什么”切到“企业为什么现在就能用”，强调可信、协作与落地速度。</p>
                  <div className="idea-footer">
                    <span>目标受众：业务负责人</span>
                    <span>点击展开</span>
                  </div>
                </button>
                <button className="idea-card interactive-card" type="button" data-detail-id="idea-alt-1">
                  <span className="mini-pill">备选切口</span>
                  <strong>从 30 天落地案例切入</strong>
                  <p className="idea-snippet">用时间压缩感建立 urgency，突出“不是规划，是已上线的协作能力”。</p>
                  <div className="idea-footer">
                    <span>目标受众：经营层</span>
                    <span>点击展开</span>
                  </div>
                </button>
                <button className="idea-card interactive-card" type="button" data-detail-id="idea-alt-2">
                  <span className="mini-pill">备选切口</span>
                  <strong>从营销生产率翻倍切入</strong>
                  <p className="idea-snippet">强调营销团队如何从单点工具升级到有评审、有发布的内容流水线。</p>
                  <div className="idea-footer">
                    <span>目标受众：营销团队</span>
                    <span>点击展开</span>
                  </div>
                </button>
              </div>
            </article>

            <article className="panel pipeline-card">
              <div className="section-head">
                <div className="section-title">
                  <p className="eyebrow">Stage B</p>
                  <h2>4 卡并行创作 60s+</h2>
                </div>
                <span className="section-note">四张内容卡同时推进，显示 SSE 式流式状态</span>
              </div>
              <div className="stream-grid">
                <button className="stream-card interactive-card" type="button" data-detail-id="stream-hero" style={{"-Progress":"84%"}}>
                  <div className="stream-head">
                    <span className="stream-kicker"><span className="stream-dot"></span>主视觉脚本</span>
                    <span className="stream-status">streaming · 68s</span>
                  </div>
                  <strong>开屏主视觉与标题语</strong>
                  <p className="stage-copy">正在补齐首屏标题、信任锚点与演示入口文案。</p>
                  <div className="progress-track"><div className="progress-bar"></div></div>
                  <div className="stream-lines">
                    <div className="stream-line"><span>00:12</span><span>生成第一版标题语，聚焦“可信协作”。</span></div>
                    <div className="stream-line"><span>00:27</span><span>补入客户场景句，加入 <strong>30 天上线</strong> 叙事。</span></div>
                    <div className="stream-line"><span>00:54</span><span>正在重写 CTA，保留更强的转化动作。</span></div>
                  </div>
                  <div className="stream-footer">
                    <span className="mini-pill is-active">版本 v3</span>
                    <span className="mini-pill">待 MOR</span>
                  </div>
                </button>

                <button className="stream-card interactive-card" type="button" data-detail-id="stream-longform" style={{"-Progress":"76%"}}>
                  <div className="stream-head">
                    <span className="stream-kicker"><span className="stream-dot"></span>长文主稿</span>
                    <span className="stream-status">streaming · 73s</span>
                  </div>
                  <strong>官网长文与案例段落</strong>
                  <p className="stage-copy">正文正在从产品特性改写为价值链与流程语言。</p>
                  <div className="progress-track"><div className="progress-bar"></div></div>
                  <div className="stream-lines">
                    <div className="stream-line"><span>00:10</span><span>已生成总论段，主打“从工具到系统”。</span></div>
                    <div className="stream-line"><span>00:31</span><span>插入营销并行创作示例，补足场景可信度。</span></div>
                    <div className="stream-line"><span>01:01</span><span>正在压缩技术细节，避免销售阅读阻力。</span></div>
                  </div>
                  <div className="stream-footer">
                    <span className="mini-pill is-active">正文 1,280 字</span>
                    <span className="mini-pill">待法务看词</span>
                  </div>
                </button>

                <button className="stream-card interactive-card" type="button" data-detail-id="stream-social" style={{"-Progress":"71%"}}>
                  <div className="stream-head">
                    <span className="stream-kicker"><span className="stream-dot"></span>社媒短帖</span>
                    <span className="stream-status">streaming · 66s</span>
                  </div>
                  <strong>社媒 4 连发短帖组</strong>
                  <p className="stage-copy">四条短帖正在对齐统一母叙事，同时控制单条信息密度。</p>
                  <div className="progress-track"><div className="progress-bar"></div></div>
                  <div className="stream-lines">
                    <div className="stream-line"><span>00:09</span><span>第一条完成，聚焦“可信协作”关键词。</span></div>
                    <div className="stream-line"><span>00:24</span><span>第二条加入 ROI 指向，准备引流到官网。</span></div>
                    <div className="stream-line"><span>00:58</span><span>第四条正在补齐转发话术与 tag 建议。</span></div>
                  </div>
                  <div className="stream-footer">
                    <span className="mini-pill is-active">4/4 生成</span>
                    <span className="mini-pill">待统一口吻</span>
                  </div>
                </button>

                <button className="stream-card interactive-card" type="button" data-detail-id="stream-sales" style={{"-Progress":"88%"}}>
                  <div className="stream-head">
                    <span className="stream-kicker"><span className="stream-dot"></span>销售转发摘要</span>
                    <span className="stream-status">streaming · 79s</span>
                  </div>
                  <strong>销售转发包与 1 页摘要</strong>
                  <p className="stage-copy">正在将市场稿压缩为高可转发、高可复述的销售版本。</p>
                  <div className="progress-track"><div className="progress-bar"></div></div>
                  <div className="stream-lines">
                    <div className="stream-line"><span>00:14</span><span>提炼出 3 个对外一句话卖点。</span></div>
                    <div className="stream-line"><span>00:36</span><span>加入异议处理，补足“是否可靠”的回答。</span></div>
                    <div className="stream-line"><span>01:07</span><span>正在生成客户群转发口径与跟进动作。</span></div>
                  </div>
                  <div className="stream-footer">
                    <span className="mini-pill is-active">可内转发</span>
                    <span className="mini-pill">待审批</span>
                  </div>
                </button>
              </div>
            </article>

            <article className="panel pipeline-card">
              <div className="section-head">
                <div className="section-title">
                  <p className="eyebrow">Stage C</p>
                  <h2>MOR 5 节点评审</h2>
                </div>
                <span className="section-note">每个评审节点均可点击查看详细意见</span>
              </div>
              <div className="review-grid">
                <button className="review-node interactive-card" type="button" data-detail-id="review-brand">
                  <span className="review-index">Node 01 · Brand</span>
                  <strong>品牌语气</strong>
                  <p className="review-snapshot">建议保留高级与可信，不要落成“效率工具”风格。</p>
                  <div className="review-footer">
                    <span>状态：通过，建议微调</span>
                  </div>
                  <span className="review-score">评分 8.9 / 10</span>
                </button>
                <button className="review-node interactive-card" type="button" data-detail-id="review-legal">
                  <span className="review-index">Node 02 · Legal</span>
                  <strong>法务用语</strong>
                  <p className="review-snapshot">需要替换“保证”“零风险”等绝对化表达。</p>
                  <div className="review-footer">
                    <span>状态：待改一轮</span>
                  </div>
                  <span className="review-score">评分 7.8 / 10</span>
                </button>
                <button className="review-node interactive-card" type="button" data-detail-id="review-product">
                  <span className="review-index">Node 03 · Product</span>
                  <strong>产品一致性</strong>
                  <p className="review-snapshot">主叙事已经对齐产品能力，但要补上评审链路描述。</p>
                  <div className="review-footer">
                    <span>状态：通过</span>
                  </div>
                  <span className="review-score">评分 9.1 / 10</span>
                </button>
                <button className="review-node interactive-card" type="button" data-detail-id="review-sales">
                  <span className="review-index">Node 04 · Sales</span>
                  <strong>销售可转发性</strong>
                  <p className="review-snapshot">需要更直白的客户收益句，以及一条可复制的话术。</p>
                  <div className="review-footer">
                    <span>状态：建议加转发句</span>
                  </div>
                  <span className="review-score">评分 8.4 / 10</span>
                </button>
                <button className="review-node interactive-card" type="button" data-detail-id="review-ops">
                  <span className="review-index">Node 05 · Ops</span>
                  <strong>运营发布检查</strong>
                  <p className="review-snapshot">发布时间、追踪链接、版本标识已经具备上线条件。</p>
                  <div className="review-footer">
                    <span>状态：可发布</span>
                  </div>
                  <span className="review-score">评分 9.3 / 10</span>
                </button>
              </div>
            </article>

            <article className="panel pipeline-card">
              <div className="section-head">
                <div className="section-title">
                  <p className="eyebrow">Stage D</p>
                  <h2>发布</h2>
                </div>
                <span className="section-note">展示最终发布包与渠道结果</span>
              </div>
              <div className="publish-grid">
                <section className="publish-package">
                  <span className="mini-pill is-active">最终发布包</span>
                  <strong>Campaign Release Bundle v1.0</strong>
                  <p className="channel-copy">发布包已经汇总为统一入口，包含官网主稿、社媒短帖、销售转发摘要、追踪参数与版本说明。</p>
                  <ul>
                    <li>官网首屏标题、长文正文、CTA 统一为同一母叙事。</li>
                    <li>4 条社媒短帖已完成长度压缩和标签建议。</li>
                    <li>销售转发包附带异议处理和跟进动作。</li>
                    <li>追踪链接、发布时间和发布 owner 已锁定。</li>
                  </ul>
                  <div className="publish-meta">
                    <span>版本：2026.08.08 / RC</span>
                    <span>状态：待最终放行</span>
                  </div>
                </section>

                <div className="channel-stack">
                  <button className="channel-card interactive-card" type="button" data-detail-id="publish-web">
                    <span className="mini-pill is-active">官网</span>
                    <strong>官网专题页</strong>
                    <p className="channel-snapshot">长文与主视觉已完成对齐，等待 MOR 通过后即可上线。</p>
                    <div className="channel-footer">
                      <span>上线窗口：10:30</span>
                      <span>点击查看结果</span>
                    </div>
                  </button>
                  <button className="channel-card interactive-card" type="button" data-detail-id="publish-wechat">
                    <span className="mini-pill">公众号</span>
                    <strong>公众号首发稿</strong>
                    <p className="channel-snapshot">标题与摘要完成，正文保留一处法务替换点。</p>
                    <div className="channel-footer">
                      <span>发送准备：92%</span>
                      <span>点击查看结果</span>
                    </div>
                  </button>
                  <button className="channel-card interactive-card" type="button" data-detail-id="publish-sales">
                    <span className="mini-pill">销售转发</span>
                    <strong>销售群转发包</strong>
                    <p className="channel-snapshot">转发话术、客户群版本和跟进动作已经打包。</p>
                    <div className="channel-footer">
                      <span>可转发人数：48</span>
                      <span>点击查看结果</span>
                    </div>
                  </button>
                </div>
              </div>
            </article>
          </div>

        </section>
      </section>
    </section>
  </main>

  <button className="agent-launcher" id="agentLauncher" type="button" aria-label="打开营销经理数字人"><span className="agent-launcher-mark">AI</span><span className="agent-launcher-copy"><strong id="agentLauncherRole">营销经理数字人</strong><span>右侧入口 · 点击后直接对话</span></span></button>
  <section className="agent-drawer" id="agentDrawer" aria-hidden="true"><div className="agent-drawer-panel"><div className="agent-drawer-head"><div><span className="agent-mini-label">右侧数字人入口</span><h3 id="agentRoleTitle">营销经理数字人</h3><p id="agentRoleIntro">补充创意、发布节奏和渠道建议，不跳出当前营销工作台。</p></div><button className="agent-drawer-close" id="agentDrawerClose" type="button" aria-label="关闭数字人面板">×</button></div><div className="agent-drawer-scroll"><div className="agent-hero-card"><div className="agent-avatar-shell"><div className="agent-avatar-core"></div><div className="agent-avatar-particles"><span></span><span></span><span></span></div><div className="agent-avatar-waves"><span></span><span></span><span></span><span></span></div></div><div className="agent-hero-copy"><span className="agent-status-pill">在线交互中</span><strong id="agentIdentityText">营销经理数字人</strong><p id="agentWelcomeCardText">可以继续追问创意主叙事、渠道节奏、评审收口和发布包建议。</p></div></div><div className="agent-card-grid"><article className="agent-info-card"><span>当前关注</span><strong id="agentFocusTitle">创意到发布闭环</strong><p id="agentFocusText">把灵感初稿、并行创作、评审与发布结果串成一个统一叙事。</p></article><article className="agent-info-card"><span>回答方式</span><strong id="agentModeTitle">创意化 + 可发布</strong><p id="agentModeText">优先补充主视觉、文案、渠道和上线动作，不做空泛概念。</p></article></div><div className="agent-suggestion-grid" id="agentSuggestionGrid"></div><div className="agent-dialogue-card"><div className="agent-dialogue-head"><span>对话流</span><small>输入后会追加用户与系统气泡</small></div><div className="agent-messages" id="agentMessages"></div></div></div><form className="agent-composer" id="agentComposer"><div className="agent-composer-shell"><textarea id="agentComposerInput" placeholder="例如：帮我补一版创意主叙事和发布节奏。"></textarea><div className="agent-composer-foot"><span className="agent-composer-hint">支持继续追问主叙事、短帖、渠道包和发布动作。</span><button className="agent-composer-send" type="submit">发送</button></div></div></form></div></section>

  <div className="marketing-chat-modal" id="marketing-chat-modal" hidden>
    <div className="marketing-chat-shell" role="dialog" aria-modal="true" aria-labelledby="marketing-chat-title">
      <div className="marketing-chat-header">
        <div className="marketing-chat-title-wrap">
          <span className="detail-tag">Trae Chat View</span>
          <h3 id="marketing-chat-title">可信 AI 协作，不再是概念演示</h3>
          <div className="marketing-chat-meta" id="marketing-chat-meta">灵感初稿卡片 · 已确认主稿</div>
        </div>
        <button className="marketing-chat-close" id="marketing-chat-close" type="button" aria-label="关闭">✕</button>
      </div>
      <div className="marketing-chat-statusbar">
        <span><strong>查看模式</strong> · 营销经理对话式工作区</span>
        <span id="marketing-chat-status">已载入当前卡片详情</span>
      </div>
      <div className="marketing-chat-messages" id="marketing-chat-messages"></div>
      <form className="marketing-chat-composer" id="marketing-chat-composer">
        <textarea className="composer-input" id="marketing-chat-input" placeholder="继续追问当前卡片，例如：帮我补一版更适合销售转发的话术"></textarea>
        <button className="composer-send" type="submit">发送</button>
      </form>
    </div>
  </div>

  
  

    </>
  );
}
