import { Link } from 'react-router-dom';
import React, { useEffect, useRef } from 'react';
import { useAuth } from '../auth/AuthContext';
import { useOrchestration } from '../hooks/useOrchestration';
import './RoleEngineering.css';

export default function RoleEngineering() {
  const { sessionScopeKey } = useAuth();
  const { roles } = useOrchestration({ scopeKey: sessionScopeKey });
  const role = roles.find((r) => r.id === 'engineering') || { name: '开发工程师', summary: '将任务画像、模型匹配与代码生成收束为一条更清晰的硬件研发工作流。' };

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
          <span className="pill">工程工作页</span>
          <span className="pill live"><span className="dot"></span>硬件研发路由中</span>
        </div>
      </header>
      <section className="page-body">
        <Link to="/orchestration" className="back-link" data-dom-id="back-overview-engineering"><span>←</span><span>查看其他人的工作</span></Link>
        <section className="summary-card">
          <div className="summary-text">
            <p className="eyebrow">{role.name}</p>
            <h1>{role.summary}</h1>
            <p className="summary-progress">左侧主区强化为三段：任务类型与硬件采样、模型负载匹配、代码生成与 JSON 输出。右侧辅区改为模型列表，持续展示可选模型、发布时间、上架时间，并跟随当前任务高亮推荐模型。</p>
          </div>
          <div className="summary-status">
            <span className="status-pill is-active">任务画像采样</span>
            <span className="status-pill">模型槽位匹配</span>
            <span className="status-pill">代码生成 / JSON</span>
            <span className="status-pill">原生交互</span>
          </div>
        </section>
        <section className="workbench">
          <section className="panel">
            <div className="panel-head">
              <div className="panel-copy">
                <p className="eyebrow">左滑主工作区</p>
                <h2>开发工程师工作流</h2>
                <p>切换主分区、选择任务卡、点击模型匹配或文件步骤时，右侧示意壳体与 JSON 结果都会同步变化，保留左滑 / 右入的感觉，但整体风格更克制。</p>
              </div>
              <div className="step-switcher">
                <button className="icon-button" id="engineering-prev" type="button" aria-label="上一分区">←</button>
                <button className="icon-button" id="engineering-next" type="button" aria-label="下一分区">→</button>
              </div>
            </div>
            <div className="step-rail" id="engineering-stage-tabs">
              <button className="step-tab is-active" type="button" data-stage="0"><small>Step 01</small><strong>任务类型与硬件采样</strong><span>任务画像映射算力等级</span></button>
              <button className="step-tab" type="button" data-stage="1"><small>Step 02</small><strong>模型负载匹配</strong><span>拖拽式匹配模型槽位</span></button>
              <button className="step-tab" type="button" data-stage="2"><small>Step 03</small><strong>代码生成与 JSON 输出</strong><span>文件树、代码片段、对象联动</span></button>
            </div>
            <div className="stage-viewport">
              <div className="stage-track" id="engineering-stage-track">
                <article className="stage-card">
                  <div className="section-head">
                    <span className="step-index">Step 01</span>
                    <h3>根据任务类型，对算力硬件的需求</h3>
                    <p className="section-description">将“硬件基础采样”改为任务画像采样，不只读设备基线，而是先判断不同任务类型对应的推理类型、推荐硬件、显存需求、延迟要求与备注。</p>
                  </div>
                  <div className="toolbar">
                    <div className="legend"><span>任务画像</span><span>推理类型</span><span>显存需求</span><span>延迟要求</span></div>
                    <span className="micro-pill is-active" id="sampling-tier">Tier-A</span>
                  </div>
                  <div className="sample-layout">
                    <div className="sample-grid" id="sampling-grid"></div>
                    <aside className="sample-detail">
                      <div><p className="eyebrow">当前采样结论</p><h3 id="sample-detail-title">PCB 画板子</h3></div>
                      <div className="detail-rows" id="sample-detail-rows"></div>
                      <div className="sample-note" id="sample-detail-note"></div>
                    </aside>
                  </div>
                </article>
                <article className="stage-card">
                  <div className="section-head">
                    <span className="step-index">Step 02</span>
                    <h3>模型负载匹配</h3>
                    <p className="section-description">左侧任务卡，中间投放区，右侧模型槽位。点击任务即可模拟拖拽激活与匹配，并显式展示模型名、发布时间、上架时间、模型类别，以及推荐模型、原因与替代模型。</p>
                  </div>
                  <div className="matching-layout">
                    <section className="task-list" id="task-list"></section>
                    <section className="drop-zone">
                      <div className="drop-top">
                        <span className="drop-pill">模拟拖拽投放区</span>
                        <div className="ghost-card" id="ghost-card"><strong id="ghost-title">PCB 画板子</strong><span id="ghost-copy">拖入推理模型槽位，优先稳定求解约束与规则校验。</span></div>
                        <div className="match-lines"><span></span><span></span><span></span><span></span></div>
                      </div>
                      <div>
                        <h4 id="drop-title">投放到推理模型槽位</h4>
                        <p className="section-description" id="drop-copy">当前任务更偏推理链路，系统建议先投放到推理模型，再给其他模型做替代路径。</p>
                      </div>
                    </section>
                    <section className="model-list" id="model-list"></section>
                  </div>
                  <section className="match-suggestion">
                    <div className="toolbar">
                      <div><p className="eyebrow">系统建议</p><h3 id="suggestion-title">推荐模型 · OpenAI o3</h3></div>
                      <span className="micro-pill is-active" id="suggestion-tag">偏推理匹配</span>
                    </div>
                    <div className="suggestion-copy" id="suggestion-copy">适合 PCB 画板子的规则推导、布线约束理解与多轮校验，延迟可以略高但需要更稳定的正确率。</div>
                    <div className="suggestion-rows">
                      <div className="pair"><span>推荐模型</span><strong id="suggestion-primary">OpenAI o3</strong></div>
                      <div className="pair"><span>原因</span><strong id="suggestion-reason">长链推理稳定，适合约束求解与高精度判断。</strong></div>
                      <div className="pair"><span>替代模型</span><strong id="suggestion-alt">GPT-4.1 / Claude 3.7 Sonnet</strong></div>
                    </div>
                  </section>
                </article>
                <article className="stage-card">
                  <div className="section-head">
                    <span className="step-index">Step 03</span>
                    <h3>代码生成与 JSON 输出</h3>
                    <p className="section-description">这里不是只展示最终 JSON，而是模拟写代码过程：左侧文件树，中间代码编辑器样式区域展示 3 个片段，右侧或下方保留可折叠 JSON viewer。</p>
                  </div>
                  <div className="code-layout">
                    <aside className="panel-box" style={{"padding":"14px"}}>
                      <div className="file-tree-head"><p className="eyebrow">生成步骤</p><h3>Artifacts</h3></div>
                      <div className="file-tree" id="file-tree"></div>
                    </aside>
                    <section className="editor-shell">
                      <div className="editor-topbar">
                        <div className="editor-title"><div className="window-dots"><span></span><span></span><span></span></div><strong id="editor-file">hardwareDecision.json</strong><span className="micro-pill is-active" id="editor-state">生成中</span></div>
                        <span className="micro-pill" id="editor-label">Step A · 采样对象</span>
                      </div>
                      <div className="editor-surface" id="editor-surface"></div>
                      <div className="code-summary" id="code-summary">先根据任务类型写入显存、延迟与推荐硬件，再把结论收束到 hardwareDecision.json 的首版对象。</div>
                    </section>
                    <section className="json-shell">
                      <div className="json-toolbar">
                        <div><p className="eyebrow">内置 JSON Viewer</p><h3 id="json-file">hardwareDecision.json</h3></div>
                        <span className="micro-pill is-active" id="json-label">输出对象 · 采样对象</span>
                      </div>
                      <div className="json-tree" id="json-tree"></div>
                    </section>
                  </div>
                </article>
              </div>
            </div>
          </section>
          <section className="video-shell is-ready" id="video-shell">
            <div className="video-head">
              <div><p className="eyebrow">右入辅区</p><h2>硬件研发示意</h2></div>
              <p id="video-description">右侧辅区改为模型列表，持续透出当前可选模型、发布时间和上架时间，并根据左侧任务与匹配结果高亮推荐模型。</p>
            </div>
            <section className="catalog-hero">
              <span className="catalog-kicker">模型目录</span>
              <div>
                <h3 id="video-title">当前推荐模型</h3>
                <p className="catalog-copy" id="video-copy">系统会根据左侧任务类型与模型匹配结果，自动提示当前更适合的模型与原因。</p>
              </div>
              <div className="catalog-summary">
                <strong id="video-scene">OpenAI o3</strong>
                <p className="catalog-copy" id="video-length">当前推荐：适合长链推理、规则约束校验与复杂判断。</p>
              </div>
            </section>
            <section className="catalog-grid" id="catalog-model-list"></section>
            <div className="video-notes">
              <div className="video-note"><strong>发布时间</strong><span id="note-1">每个模型都标注公开发布时间，帮助判断代际与能力边界。</span></div>
              <div className="video-note"><strong>上架时间</strong><span id="note-2">补充平台侧上架时间，便于研发评估接入窗口与可用性。</span></div>
              <div className="video-note"><strong>当前联动</strong><span id="note-3">左侧切换任务或匹配建议时，右侧会自动高亮当前更适合的模型。</span></div>
            </div>
          </section>
        </section>
      </section>
    </section>
  </main>
  <button className="agent-launcher" id="agentLauncher" type="button" aria-label="打开开发工程师数字人"><span className="agent-launcher-mark">AI</span><span className="agent-launcher-copy"><strong id="agentLauncherRole">开发工程师数字人</strong><span>右侧入口 · 在当前页继续追问</span></span></button>
  <section className="agent-drawer" id="agentDrawer" aria-hidden="true">
    <div className="agent-drawer-panel">
      <div className="agent-drawer-head">
        <div><span className="agent-mini-label">右侧数字人入口</span><h3 id="agentRoleTitle">开发工程师数字人</h3><p id="agentRoleIntro">补充算力、模型和部署建议，不影响现有三段式工程工作流。</p></div>
        <button className="agent-drawer-close" id="agentDrawerClose" type="button" aria-label="关闭数字人面板">×</button>
      </div>
      <div className="agent-drawer-scroll">
        <div className="agent-hero-card">
          <div className="agent-avatar-shell"><div className="agent-avatar-core"></div><div className="agent-avatar-particles"><span></span><span></span><span></span></div><div className="agent-avatar-waves"><span></span><span></span><span></span><span></span></div></div>
          <div className="agent-hero-copy"><span className="agent-status-pill">在线交互中</span><strong id="agentIdentityText">开发工程师数字人</strong><p id="agentWelcomeCardText">可以直接追问模型选型、算力档位、部署路径和代码输出建议。</p></div>
        </div>
        <div className="agent-card-grid">
          <article className="agent-info-card"><span>当前关注</span><strong id="agentFocusTitle">模型与硬件匹配</strong><p id="agentFocusText">把任务画像、模型槽位和部署产物串成一条可执行路线。</p></article>
          <article className="agent-info-card"><span>回答方式</span><strong id="agentModeTitle">工程化 + 可部署</strong><p id="agentModeText">优先补充算力预算、模型路由、缓存和监控建议。</p></article>
        </div>
        <div className="agent-suggestion-grid" id="agentSuggestionGrid"></div>
        <div className="agent-dialogue-card"><div className="agent-dialogue-head"><span>对话流</span><small>输入后会追加用户与系统气泡</small></div><div className="agent-messages" id="agentMessages"></div></div>
      </div>
      <form className="agent-composer" id="agentComposer">
        <div className="agent-composer-shell">
          <textarea id="agentComposerInput" placeholder="例如：帮我给这条任务补一版算力、模型和部署建议。"></textarea>
          <div className="agent-composer-foot"><span className="agent-composer-hint">支持继续追问算力、模型匹配、代码生成与部署路径。</span><button className="agent-composer-send" type="submit">发送</button></div>
        </div>
      </form>
    </div>
  </section>
  
  

    </>
  );
}
