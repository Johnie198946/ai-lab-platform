import { Link } from 'react-router-dom';
import React, { useEffect, useRef } from 'react';
import { useAuth } from '../auth/AuthContext';
import { useOrchestration } from '../hooks/useOrchestration';
import './RoleFounder.css';

export default function RoleFounder() {
  const { sessionScopeKey } = useAuth();
  const { roles } = useOrchestration({ scopeKey: sessionScopeKey });
  const role = roles.find((r) => r.id === 'boss') || { name: '老板', summary: '用一屏收住时间线、ROI、状态大盘、审批卡，以及高管一页纸。' };

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
          <span className="pill">老板视角</span>
          <span className="pill live"><span className="dot"></span>战情室运行中</span>
        </div>
      </header>

      <section className="page-body">
        <Link to="/orchestration" className="back-link" data-dom-id="back-overview-founder">
          <span>←</span>
          <span>查看其他人的工作</span>
        </Link>

        <section className="hero">
          <article className="panel hero-card">
            <p className="eyebrow">{role.name}</p>
            <h1>{role.summary}</h1>
            <p className="hero-copy">
              页面重构为老板视角的战情室，而不是普通角色流程页。重点不在具体产出怎么做，而在什么时候该拍板、哪些指标越线、哪里有风险，以及今天建议采取什么动作。
            </p>
            <div className="hero-meta">
              <span className="status-pill is-active">经营判断中</span>
              <span className="status-pill">ROI 过线</span>
              <span className="status-pill">风险可控</span>
              <span className="status-pill">审批待签发</span>
            </div>
          </article>

          <aside className="panel hero-side">
            <div className="score-card">
              <span>今日结论</span>
              <strong>可继续投入</strong>
              <p>建议继续推进发布，但需先完成法务措辞修订与预算封顶确认。</p>
            </div>
            <div className="score-card">
              <span>预测回收周期</span>
              <strong>4.8 月</strong>
              <p>在当前转化假设下，投放与产出关系仍优于内部基线。</p>
            </div>
            <div className="score-card">
              <span>高优先级动作</span>
              <strong>2 项</strong>
              <p>批准发布窗口；锁定销售跟进资源，避免上线后线索承接掉速。</p>
            </div>
          </aside>
        </section>

        <section className="war-grid">
          <div className="main-column">
            <article className="panel war-room">
              <div className="section-head">
                <div className="section-title">
                  <p className="eyebrow">War Room</p>
                  <h2>时间线</h2>
                </div>
                <span className="section-note">老板先看关键时点，再决定是否放行与加码</span>
              </div>
              <div className="timeline-grid">
                <button className="timeline-item interactive-card is-active" type="button" data-detail-id="timeline-1">
                  <span className="timeline-stamp">08:10 · 初稿确认</span>
                  <strong>主叙事拍板</strong>
                  <p>从“AI 能做什么”切换到“企业为什么现在就要上”。</p>
                  <div className="timeline-foot">
                    <span>Owner：市场负责人</span>
                    <span>点击展开</span>
                  </div>
                </button>
                <button className="timeline-item interactive-card" type="button" data-detail-id="timeline-2">
                  <span className="timeline-stamp">09:40 · 并行产出</span>
                  <strong>4 卡创作并发推进</strong>
                  <p>官网、社媒、销售摘要与主视觉同步生成并收口。</p>
                  <div className="timeline-foot">
                    <span>状态：持续推进</span>
                    <span>点击展开</span>
                  </div>
                </button>
                <button className="timeline-item interactive-card" type="button" data-detail-id="timeline-3">
                  <span className="timeline-stamp">11:15 · 风险识别</span>
                  <strong>MOR 评审收口</strong>
                  <p>法务措辞待修订，其他节点已接近放行。</p>
                  <div className="timeline-foot">
                    <span>状态：风险可控</span>
                    <span>点击展开</span>
                  </div>
                </button>
                <button className="timeline-item interactive-card" type="button" data-detail-id="timeline-4">
                  <span className="timeline-stamp">14:00 · 放行窗口</span>
                  <strong>发布与承接准备</strong>
                  <p>需要老板批准发布窗口与销售跟进资源。</p>
                  <div className="timeline-foot">
                    <span>动作：待签发</span>
                    <span>点击展开</span>
                  </div>
                </button>
              </div>
            </article>

            <article className="panel war-room">
              <div className="section-head">
                <div className="section-title">
                  <p className="eyebrow">ROI</p>
                  <h2>ROI 指标区</h2>
                </div>
                <span className="section-note">所有指标卡均可点击查看口径、假设与风险</span>
              </div>
              <div className="metrics-grid">
                <button className="metric-card interactive-card" type="button" data-detail-id="roi-pipeline">
                  <span className="timeline-stamp">Pipeline ROI</span>
                  <strong>线索投资回报</strong>
                  <span className="metric-value">3.4x</span>
                  <p className="metric-copy">基于官网专题页、公众号与销售转发联合测算。</p>
                  <div className="metric-foot">
                    <span className="metric-trend">高于基线 +18%</span>
                    <span>点击展开</span>
                  </div>
                </button>
                <button className="metric-card interactive-card" type="button" data-detail-id="roi-payback">
                  <span className="timeline-stamp">Payback</span>
                  <strong>回收周期</strong>
                  <span className="metric-value">4.8 月</span>
                  <p className="metric-copy">按销售承接效率和历史成交时长回推。</p>
                  <div className="metric-foot">
                    <span className="metric-trend">优于目标 0.7 月</span>
                    <span>点击展开</span>
                  </div>
                </button>
                <button className="metric-card interactive-card" type="button" data-detail-id="roi-cac">
                  <span className="timeline-stamp">CAC</span>
                  <strong>获客成本</strong>
                  <span className="metric-value">¥2,860</span>
                  <p className="metric-copy">营销投放、内容制作与销售跟进工时统一计入。</p>
                  <div className="metric-foot">
                    <span className="metric-trend">控制在阈值内</span>
                    <span>点击展开</span>
                  </div>
                </button>
                <button className="metric-card interactive-card" type="button" data-detail-id="roi-capacity">
                  <span className="timeline-stamp">Capacity</span>
                  <strong>销售承接容量</strong>
                  <span className="metric-value">82%</span>
                  <p className="metric-copy">线索承接能力接近上限，需要同步安排跟进节奏。</p>
                  <div className="metric-foot">
                    <span className="metric-trend">需资源补位</span>
                    <span>点击展开</span>
                  </div>
                </button>
              </div>
            </article>

            <article className="panel war-room">
              <div className="section-head">
                <div className="section-title">
                  <p className="eyebrow">Dashboard</p>
                  <h2>状态大盘</h2>
                </div>
                <span className="section-note">用轻量状态卡看经营盘面，而非重色 cockpit</span>
              </div>
              <div className="dashboard-grid">
                <button className="dashboard-card interactive-card" type="button" data-detail-id="board-brand">
                  <span className="dashboard-label">Brand</span>
                  <strong>品牌一致性</strong>
                  <p className="dashboard-copy">调性稳定，已满足高管预期，避免过度营销化表达。</p>
                  <span className="dashboard-state">稳定</span>
                  <div className="dashboard-foot">
                    <span>最后更新：11:06</span>
                    <span>点击展开</span>
                  </div>
                </button>
                <button className="dashboard-card interactive-card" type="button" data-detail-id="board-legal">
                  <span className="dashboard-label">Legal</span>
                  <strong>合规措辞</strong>
                  <p className="dashboard-copy">两处绝对化表述需替换，不影响主叙事结构。</p>
                  <span className="dashboard-state is-alert">待修订</span>
                  <div className="dashboard-foot">
                    <span>最后更新：11:15</span>
                    <span>点击展开</span>
                  </div>
                </button>
                <button className="dashboard-card interactive-card" type="button" data-detail-id="board-sales">
                  <span className="dashboard-label">Sales</span>
                  <strong>销售承接</strong>
                  <p className="dashboard-copy">转发包完整，但若放量需要加 1 名跟进 owner。</p>
                  <span className="dashboard-state is-alert">逼近阈值</span>
                  <div className="dashboard-foot">
                    <span>最后更新：11:28</span>
                    <span>点击展开</span>
                  </div>
                </button>
                <button className="dashboard-card interactive-card" type="button" data-detail-id="board-release">
                  <span className="dashboard-label">Release</span>
                  <strong>发布准备</strong>
                  <p className="dashboard-copy">渠道、链接与 owner 已锁定，等待审批卡签发。</p>
                  <span className="dashboard-state">待放行</span>
                  <div className="dashboard-foot">
                    <span>最后更新：11:42</span>
                    <span>点击展开</span>
                  </div>
                </button>
              </div>
            </article>

            <article className="panel war-room">
              <div className="section-head">
                <div className="section-title">
                  <p className="eyebrow">Approval</p>
                  <h2>审批卡</h2>
                </div>
                <span className="section-note">点击查看决策信息、风险与建议动作</span>
              </div>
              <div className="approval-grid">
                <button className="approval-card interactive-card" type="button" data-detail-id="approval-release">
                  <span className="approval-label">审批卡 A</span>
                  <strong>是否批准今日发布窗口</strong>
                  <p className="approval-copy">涉及官网专题页、公众号首发与销售转发包同步上线。</p>
                  <div className="decision-row">
                    <span className="decision-chip">建议批准</span>
                    <span className="mini-pill">高优先级</span>
                  </div>
                  <div className="approval-meta">
                    <span>风险：法务措辞</span>
                    <span>点击展开</span>
                  </div>
                </button>
                <button className="approval-card interactive-card" type="button" data-detail-id="approval-budget">
                  <span className="approval-label">审批卡 B</span>
                  <strong>是否追加销售承接资源</strong>
                  <p className="approval-copy">若按当前预估放量，销售线索承接容量将在本周触顶。</p>
                  <div className="decision-row">
                    <span className="decision-chip is-pending">建议有条件批准</span>
                    <span className="mini-pill">资源类</span>
                  </div>
                  <div className="approval-meta">
                    <span>风险：人效波动</span>
                    <span>点击展开</span>
                  </div>
                </button>
                <button className="approval-card interactive-card" type="button" data-detail-id="approval-risk">
                  <span className="approval-label">审批卡 C</span>
                  <strong>是否接受当前措辞风险后上线</strong>
                  <p className="approval-copy">若不等待修订，可以抢时间窗口，但需承担表述争议风险。</p>
                  <div className="decision-row">
                    <span className="decision-chip is-risk">建议暂不批准</span>
                    <span className="mini-pill">风险类</span>
                  </div>
                  <div className="approval-meta">
                    <span>风险：品牌与合规</span>
                    <span>点击展开</span>
                  </div>
                </button>
              </div>
            </article>

            <article className="panel war-room">
              <div className="section-head">
                <div className="section-title">
                  <p className="eyebrow">Executive</p>
                  <h2>高管一页纸</h2>
                </div>
                <span className="section-note">支持 markdown 展示，点击查看完整一页纸内容</span>
              </div>
              <button className="onepager-card interactive-card" type="button" data-detail-id="onepager-main">
                <span className="mini-pill is-active">Executive One Pager</span>
                <strong>今天的经营结论、关键风险与建议动作</strong>
                <p className="card-copy">适合老板在 1 分钟内完成判断：可否发布、是否加码、哪里要盯。</p>
                <div className="score-strip">
                  <span>阅读方式：Markdown</span>
                  <span>点击展开</span>
                </div>
              </button>
            </article>
          </div>
        </section>
      </section>
    </section>
  </main>

  <button className="agent-launcher" id="agentLauncher" type="button" aria-label="打开老板数字人"><span className="agent-launcher-mark">AI</span><span className="agent-launcher-copy"><strong id="agentLauncherRole">老板数字人</strong><span>右侧入口 · 点击后查看决策对话</span></span></button>
  <section className="agent-drawer" id="agentDrawer" aria-hidden="true"><div className="agent-drawer-panel"><div className="agent-drawer-head"><div><span className="agent-mini-label">右侧数字人入口</span><h3 id="agentRoleTitle">老板数字人</h3><p id="agentRoleIntro">补充决策摘要、ROI 判断和风险建议，不打断当前战情室。</p></div><button className="agent-drawer-close" id="agentDrawerClose" type="button" aria-label="关闭数字人面板">×</button></div><div className="agent-drawer-scroll"><div className="agent-hero-card"><div className="agent-avatar-shell"><div className="agent-avatar-core"></div><div className="agent-avatar-particles"><span></span><span></span><span></span></div><div className="agent-avatar-waves"><span></span><span></span><span></span><span></span></div></div><div className="agent-hero-copy"><span className="agent-status-pill">在线交互中</span><strong id="agentIdentityText">老板数字人</strong><p id="agentWelcomeCardText">可以继续追问是否放行、ROI 是否过线、风险边界和资源加码建议。</p></div></div><div className="agent-card-grid"><article className="agent-info-card"><span>当前关注</span><strong id="agentFocusTitle">决策与 ROI</strong><p id="agentFocusText">把时间线、指标、风险和审批动作压成老板能快速拍板的答案。</p></article><article className="agent-info-card"><span>回答方式</span><strong id="agentModeTitle">结论先行 + 风险清楚</strong><p id="agentModeText">优先给一页式结论、ROI 判断和风险动作，而不是铺陈过程。</p></article></div><div className="agent-suggestion-grid" id="agentSuggestionGrid"></div><div className="agent-dialogue-card"><div className="agent-dialogue-head"><span>对话流</span><small>输入后会追加用户与系统气泡</small></div><div className="agent-messages" id="agentMessages"></div></div></div><form className="agent-composer" id="agentComposer"><div className="agent-composer-shell"><textarea id="agentComposerInput" placeholder="例如：帮我压成一句决策结论和两条风险动作。"></textarea><div className="agent-composer-foot"><span className="agent-composer-hint">支持继续追问放行判断、ROI、预算和风险边界。</span><button className="agent-composer-send" type="submit">发送</button></div></div></form></div></section>

  <div className="founder-modal-shell" id="founderModalShell" aria-hidden="true">
    <div className="founder-modal-backdrop" id="founderModalBackdrop"></div>
    <section className="founder-modal-content" role="dialog" aria-modal="true" aria-labelledby="founderModalTitle">
      <header className="founder-modal-header">
        <div>
          <span className="founder-modal-tag">对话工作台</span>
          <h3 className="founder-modal-title" id="founderModalTitle">老板视角详情</h3>
          <div className="founder-modal-meta" id="founderModalMeta">点击卡片查看经营结论</div>
        </div>
        <button className="founder-modal-close" id="founderModalClose" type="button" aria-label="关闭详情窗口">✕</button>
      </header>
      <div className="founder-modal-statusbar">
        <span className="system-pill"><span className="system-signal"></span><span id="founderModalStatus">系统正在整理老板视角结论</span></span>
        <span className="system-note">Trae 风格输出窗</span>
      </div>
      <div className="founder-modal-stream">
        <div className="chat-row user">
          <div className="chat-bubble user">
            <div className="chat-role">老板</div>
            <div className="chat-text" id="founderModalPrompt">老板正在查看：经营摘要</div>
          </div>
        </div>
        <div className="chat-row system">
          <div className="chat-bubble system">
            <div className="chat-role">系统输出</div>
            <div className="modal-markdown" id="founderModalMarkdown"></div>
          </div>
        </div>
      </div>
      <div className="founder-modal-composer">
        <div className="composer-shell">
          <textarea id="founderModalInput" placeholder="继续追问，例如：请把风险拆成品牌 / 合规 / 销售承接三类。"></textarea>
          <div className="composer-foot">
            <span className="composer-hint">这里补上真正的输入区，方便老板继续追问、索要摘要压缩版，或要求系统给出下一步动作。</span>
            <button className="composer-send" id="founderModalSend" type="button">发送追问</button>
          </div>
        </div>
      </div>
    </section>
  </div>

  
  

    </>
  );
}
