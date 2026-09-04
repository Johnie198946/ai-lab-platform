import React, { useEffect, useRef } from 'react';
import './Loading.css';

export default function Loading() {
  return (
    <>
      
  <main className="loading-page">
    <section className="loading-shell" id="loadingShell" data-complete="false" aria-labelledby="loading-title">
      <div className="loading-copy">
        <div className="status-row">
          <span className="status-label">加载页</span>
          <span className="status-state" id="loadingState" aria-live="polite">生成中</span>
        </div>

        <div>
          <h1 id="loading-title">正在生成执行路径</h1>
          <p id="loadingDescription">系统正在重排关键阶段，准备进入总览结果。</p>
        </div>

        <div className="metrics">
          <div className="metric">
            <span>进度读数</span>
            <strong id="progressValue">00%</strong>
          </div>
          <div className="metric">
            <span>倒计时</span>
            <strong id="countdownValue">05s</strong>
          </div>
        </div>

        <div className="progress-rail" aria-hidden="true">
          <span id="progressBar"></span>
        </div>

        <a
          href="./overview.html"
          className="orch-enter-button"
          data-dom-id="enter-overview-after-loading"
          id="enterOverviewButton"
          aria-disabled="true"
          tabindex="-1"
        >
          <span>进入总览</span>
          <span aria-hidden="true">→</span>
        </a>
      </div>

      <div className="cards-panel" aria-hidden="true">
        <div className="cards-stage" id="cardsStage">
          <div className="stage-caption">Card Swap Loading</div>

          <article className="loading-card" data-card="0">
            <div className="card-header">
              <span className="card-step">Phase 01</span>
              <span className="card-badge">A1</span>
            </div>
            <h2>目标解析</h2>
            <p>归一任务约束、优先级与上下文入口，生成清晰执行目标。</p>
            <div className="card-meta">
              <strong>Intent Framing</strong>
              <div className="card-track"><span className="is-live"></span><span></span><span></span></div>
            </div>
          </article>

          <article className="loading-card" data-card="1">
            <div className="card-header">
              <span className="card-step">Phase 02</span>
              <span className="card-badge">R2</span>
            </div>
            <h2>角色召回</h2>
            <p>匹配执行角色与能力边界，准备最合适的编排参与单元。</p>
            <div className="card-meta">
              <strong>Agent Recall</strong>
              <div className="card-track"><span></span><span className="is-live"></span><span></span></div>
            </div>
          </article>

          <article className="loading-card" data-card="2">
            <div className="card-header">
              <span className="card-step">Phase 03</span>
              <span className="card-badge">W3</span>
            </div>
            <h2>工作流装配</h2>
            <p>合并步骤顺序、依赖关系与交付路径，形成可执行结构。</p>
            <div className="card-meta">
              <strong>Flow Assembly</strong>
              <div className="card-track"><span></span><span></span><span className="is-live"></span></div>
            </div>
          </article>

          <article className="loading-card" data-card="3">
            <div className="card-header">
              <span className="card-step">Phase 04</span>
              <span className="card-badge">Q4</span>
            </div>
            <h2>输出校验</h2>
            <p>回收结果一致性与完成态信号，确保交付入口已准备就绪。</p>
            <div className="card-meta">
              <strong>Output Check</strong>
              <div className="card-track"><span className="is-live"></span><span className="is-live"></span><span></span></div>
            </div>
          </article>
        </div>
      </div>
    </section>
  </main>

  

    </>
  );
}
