import React, { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Link } from 'react-router-dom';
import { ArrowLeft, Clock, PenTool, Layout, FileText, CheckCircle, Loader, Monitor, MessageSquare } from 'lucide-react';
import { useAuth } from '../auth/AuthContext';
import { useOrchestration } from '../hooks/useOrchestration';
import { generateRoleWorkflow } from '../services/orchestrationService';
import './RoleProduct.css';

export default function RoleProduct() {
  const { sessionScopeKey } = useAuth();
  const { sessionMeta, input } = useOrchestration({ scopeKey: sessionScopeKey });

  const [phase, setPhase] = useState(0); // 0: waiting/blocked, 1: generating, 2: done
  const [prdProgress, setPrdProgress] = useState(0);
  const [wireframeProgress, setWireframeProgress] = useState(0);
  const [currentPrdStep, setCurrentPrdStep] = useState("");
  
  // Real data state
  const [prdSteps, setPrdSteps] = useState([]);
  const [wireframes, setWireframes] = useState([]);

  useEffect(() => {
    async function fetchWorkflow() {
      try {
        if (!sessionMeta.sessionId) return;
        const goal = sessionMeta.goal || input;
        if (!goal || !goal.trim()) {
          setPhase(2);
          return;
        }
        
        // Start simulation / fetching
        setPhase(1);
        const res = await generateRoleWorkflow(sessionMeta.sessionId, "product", goal);
        
        // Use the returned tasks or fallback
        if (res && res.tasks) {
          const half = Math.ceil(res.tasks.length / 2);
          setPrdSteps(res.tasks.slice(0, half));
          setWireframes(res.tasks.slice(half));
        } else {
          setPrdSteps(["需求结构化拆解", "业务流程图生成", "用例(Use Case)编写", "数据字典梳理"]);
          setWireframes(["首页 Dashboard", "工作流编排页", "分析报告页"]);
        }
      } catch (err) {
        console.error(err);
      }
    }
    fetchWorkflow();
  }, [sessionMeta.sessionId]);

  // Handle fake progress for generating phase
  useEffect(() => {
    if (phase === 1) {
      let startTime = Date.now();
      const duration = 8000;
      const interval = setInterval(() => {
        let elapsed = Date.now() - startTime;
        let p = Math.min(100, (elapsed / duration) * 100);
        setPrdProgress(p);
        setWireframeProgress(p * 0.8); // wireframe lags slightly

        let stepIndex = Math.floor((p / 100) * (prdSteps.length || 4));
        setCurrentPrdStep(prdSteps[stepIndex] || "正在生成...");

        if (p >= 100) {
          clearInterval(interval);
          setWireframeProgress(100);
          setPhase(2);
        }
      }, 100);
      return () => clearInterval(interval);
    }
  }, [phase, prdSteps]);

  // Handle mock button
  const handleMockTrigger = () => {
    if (phase === 0) setPhase(1);
  };

  return (
    <div className="role-product-container">
      <Link to="/orchestration" className="back-button">
        <ArrowLeft size={16} /> 返回 overview
      </Link>

      <div className="product-content">
        {/* Bespoke Header */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className={`bespoke-header ${phase >= 1 ? 'is-ready' : ''}`}
        >
          <span className="role-tag">产品经理</span>
          {phase === 0 ? (
            <>
              <h1>正在等待市场洞察输入，PRD 与原型保持 blocked，准备在结论抵达后进入 ready。</h1>
              <p>当前工作台已预置依赖映射、PRD JSON 结构与原型板位。产品经理此刻不继续扩写假设，而是等待市场洞察完成后一次性接收目标用户、动机、竞争缺口与优先级结论。</p>
            </>
          ) : phase === 1 ? (
            <>
              <h1>产品经理已接收上游洞察摘要，正在将需求结构化为 PRD 与交互原型。</h1>
              <p>系统正并行处理需求依赖关系、生成结构化的 PRD JSON 数据，并同步生成各个核心页面的高保真线框图。</p>
            </>
          ) : (
            <>
              <h1>PRD 与原型已就绪，当前可进入研发阶段。</h1>
              <p>结构化 PRD 和页面原型已全部生成完毕。您可以点击右侧 AI 数字人助手，或继续前往开发工程师的工作台。</p>
            </>
          )}

          <div className="status-pills">
            <div className="pill-row">
              <span className={`status-pill ${phase > 0 ? 'done' : 'waiting'}`}>市场洞察 {phase > 0 ? 'DONE' : 'WAITING'}</span>
              <span className={`status-pill ${phase === 2 ? 'done' : phase === 1 ? 'active' : 'waiting'}`}>PRD {phase === 2 ? 'DONE' : phase === 1 ? 'GENERATING' : 'BLOCKED'}</span>
              <span className={`status-pill ${phase === 2 ? 'done' : phase === 1 ? 'active' : 'waiting'}`}>原型 {phase === 2 ? 'DONE' : phase === 1 ? 'GENERATING' : 'BLOCKED'}</span>
            </div>
            <span className="status-hint">{phase === 0 ? '准备接收结论' : phase === 1 ? '处理中...' : '流程完成'}</span>
          </div>
        </motion.div>

        {/* Workspace */}
        <div className="workspace-section">
          <div className="workspace-header">
            <div className="ws-title-area">
              <span className="ws-tag">SUMMARY-CARD + DRIFT-SCENE</span>
              <h2>产品经理工作台</h2>
              <p>主体改为依赖状态、PRD JSON 与原型图画廊三段式交互。先看等待，再接收上游摘要，随后进入结构化 PRD 与原型细化。</p>
            </div>
            {phase === 0 && (
              <button className="mock-btn" onClick={handleMockTrigger}>模拟市场洞察完成</button>
            )}
          </div>

          <div className="bespoke-grid">
            {/* Column 1: 依赖状态 / 上游摘要 */}
            <div className="grid-col">
              <div className="col-header">
                <h3>市场洞察摘要 (依赖)</h3>
                <p>上游角色传递的核心信息</p>
              </div>
              <div className={`col-body ${phase === 0 ? 'empty-state' : ''}`}>
                {phase === 0 ? "暂无输入数据" : (
                  <div>
                    <p><strong>核心需求：</strong> {sessionMeta.goal || input}</p>
                    <p><strong>市场缺口：</strong> 缺乏端到端的全链路编排系统。</p>
                    <p><strong>优先级：</strong> 高优先级（需支持动态工作流和拖拽组件）。</p>
                    <div className="progress-bar-thin">
                      <div className="fill" style={{width: '100%'}}></div>
                    </div>
                    <p style={{marginTop: 8, color: '#007AFF', fontSize: 12}}>数据已加载完成</p>
                  </div>
                )}
              </div>
            </div>

            {/* Column 2: PRD JSON */}
            <div className="grid-col">
              <div className="col-header">
                <h3>结构化 PRD (JSON)</h3>
                <p>功能列表与数据字典</p>
              </div>
              <div className={`col-body ${phase === 0 ? 'empty-state' : ''}`}>
                {phase === 0 ? "等待生成" : (
                  <div>
                    <div className="doc-list-item">
                      <strong>1. 全局配置模块</strong>
                      {phase === 1 ? <span style={{color:'#888'}}>正在解析字段...</span> : <span>包含：会话保持、全局角色字典定义</span>}
                    </div>
                    <div className="doc-list-item">
                      <strong>2. 工作流引擎</strong>
                      {phase === 1 && prdProgress < 50 ? <span style={{color:'#888'}}>等待中...</span> : <span>包含：DAG节点调度、状态流转通知</span>}
                    </div>
                    {phase === 2 && prdSteps.map((task, idx) => (
                      <div className="doc-list-item" key={idx}>
                        <strong>{idx + 3}. {task}</strong>
                        <span>详细功能点已入库。</span>
                      </div>
                    ))}
                    {phase === 1 && (
                      <div style={{marginTop: 16}}>
                        <span style={{color: '#888'}}>{currentPrdStep} ({Math.floor(prdProgress)}%)</span>
                        <div className="progress-bar-thin">
                          <div className="fill" style={{width: `${prdProgress}%`}}></div>
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </div>
            </div>

            {/* Column 3: 原型图画廊 */}
            <div className="grid-col">
              <div className="col-header">
                <h3>交互原型 (Wireframes)</h3>
                <p>核心页面的线框板位</p>
              </div>
              <div className={`col-body ${phase === 0 ? 'empty-state' : ''}`}>
                {phase === 0 ? "等待生成" : (
                  <div>
                    {wireframes.map((wf, idx) => {
                      if (phase === 1 && wireframeProgress < (idx + 1) * (100 / wireframes.length)) return null;
                      return (
                        <div key={idx} style={{marginBottom: 16}}>
                          <div className="proto-img-mock">
                            <Layout size={24} style={{marginRight: 8}} />
                            {wf} 渲染完成
                          </div>
                        </div>
                      );
                    })}
                    {phase === 1 && (
                      <div style={{marginTop: 16}}>
                        <span style={{color: '#888'}}>生成原型布局... ({Math.floor(wireframeProgress)}%)</span>
                        <div className="progress-bar-thin">
                          <div className="fill" style={{width: `${wireframeProgress}%`}}></div>
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Floating AI Assistant */}
      <div className="ai-assistant-card">
        <div className="ai-icon-wrap">AI</div>
        <div className="ai-info">
          <h4>产品经理数字人</h4>
          <p>右侧入口 • 点击后在当前页对话</p>
        </div>
      </div>
    </div>
  );
}