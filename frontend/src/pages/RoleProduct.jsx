import React, { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Link } from 'react-router-dom';
import { ArrowLeft, Clock, PenTool, Layout, FileText, CheckCircle, Loader, Monitor } from 'lucide-react';
import { useAuth } from '../auth/AuthContext';
import { useOrchestration } from '../hooks/useOrchestration';
import { generateRoleWorkflow } from '../services/orchestrationService';
import './RoleProduct.css';

const mockPrototypes = [
  { id: 1, name: "Dashboard Overview", image: "https://images.unsplash.com/photo-1618761714954-0b8cd0026356?auto=format&fit=crop&q=80&w=800" },
  { id: 2, name: "Agent Workflow", image: "https://images.unsplash.com/photo-1551288049-bebda4e38f71?auto=format&fit=crop&q=80&w=800" },
  { id: 3, name: "Analytics Report", image: "https://images.unsplash.com/photo-1551288049-bebda4e38f71?auto=format&fit=crop&q=80&w=800" } // reused just for mock
];

export default function RoleProduct() {
  const { sessionScopeKey } = useAuth();
  const { sessionMeta, input } = useOrchestration({ scopeKey: sessionScopeKey });

  const [phase, setPhase] = useState(-1); // -1: fetching, 0: wait, 1: prd, 2: wireframe, 3: done
  const [prdProgress, setPrdProgress] = useState(0);
  const [wireframeProgress, setWireframeProgress] = useState(0);

  const [prdSteps, setPrdSteps] = useState(["分析需求中..."]);
  const [wireframeSteps, setWireframeSteps] = useState(["设计中..."]);
  const [summary, setSummary] = useState("正在生成产品文档...");

  const [currentPrdStep, setCurrentPrdStep] = useState("");
  const [currentWireframeStep, setCurrentWireframeStep] = useState("");
  const [selectedProto, setSelectedProto] = useState(null);

  useEffect(() => {
    async function fetchWorkflow() {
      try {
        const goal = sessionMeta.goal || input;
        if (!goal || !goal.trim()) {
          setSummary("⚠️ 尚未收到用户需求。请先返回编排页, 输入你的业务目标后再进入本角色工作流。");
          setPhase(3);
          return;
        }
        const res = await generateRoleWorkflow(sessionMeta.sessionId, "product", goal);
        if (res && res.tasks && res.tasks.length > 0) {
          const half = Math.ceil(res.tasks.length / 2);
          setPrdSteps(res.tasks.slice(0, half));
          setWireframeSteps(res.tasks.slice(half));
          setSummary(res.summary || "PRD 与原型设计完成。");
          if (res._cached) {
            setPhase(3);
            setPrdProgress(100);
            setWireframeProgress(100);
            setCurrentPrdStep(res.tasks[half - 1] || "");
            setCurrentWireframeStep(res.tasks[res.tasks.length - 1] || "");
          } else {
            setPhase(0);
          }
        }
      } catch (err) {
        console.error("fetchWorkflow err", err);
        setPhase(0);
      }
    }
    fetchWorkflow();
  }, [sessionMeta.sessionId, input]);

  // Phase 0: Wait for Market Insight
  useEffect(() => {
    if (phase === 0) {
      setCurrentPrdStep(prdSteps[0] || "");
      setCurrentWireframeStep(wireframeSteps[0] || "");
      const timer = setTimeout(() => setPhase(1), 1000); // reduced wait
      return () => clearTimeout(timer);
    }
  }, [phase, prdSteps, wireframeSteps]);

  // Phase 1: PRD generation (10s)
  useEffect(() => {
    if (phase === 1) {
      let startTime = Date.now();
      const duration = 10000;
      const interval = setInterval(() => {
        let elapsed = Date.now() - startTime;
        let p = Math.min(100, (elapsed / duration) * 100);
        setPrdProgress(p);
        
        let stepIndex = Math.floor((p / 100) * prdSteps.length);
        if (stepIndex >= prdSteps.length) stepIndex = prdSteps.length - 1;
        setCurrentPrdStep(prdSteps[stepIndex]);

        if (p >= 100) {
          clearInterval(interval);
          setPhase(2);
        }
      }, 100);
      return () => clearInterval(interval);
    }
  }, [phase, prdSteps]);

  // Phase 2: Wireframe generation (10s)
  useEffect(() => {
    if (phase === 2) {
      let startTime = Date.now();
      const duration = 10000;
      const interval = setInterval(() => {
        let elapsed = Date.now() - startTime;
        let p = Math.min(100, (elapsed / duration) * 100);
        setWireframeProgress(p);
        
        let stepIndex = Math.floor((p / 100) * wireframeSteps.length);
        if (stepIndex >= wireframeSteps.length) stepIndex = wireframeSteps.length - 1;
        setCurrentWireframeStep(wireframeSteps[stepIndex]);

        if (p >= 100) {
          clearInterval(interval);
          setPhase(3);
        }
      }, 100);
      return () => clearInterval(interval);
    }
  }, [phase, wireframeSteps]);

  if (phase === -1) {
    return (
      <div className="role-product-container" style={{display: 'flex', justifyContent: 'center', alignItems: 'center', color: '#fff'}}>
        <Loader className="spin" size={48} />
        <span style={{marginLeft: 16}}>正在连接 Hermes Main Agent 规划工作流...</span>
      </div>
    );
  }

  return (
    <div className="role-product-container">
      <Link to="/orchestration" className="back-button">
        <ArrowLeft size={16} /> 查看其他人的工作
      </Link>

      <div className="product-content">
        <motion.div 
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="header-section"
        >
          <h1>产品经理</h1>
          <p>将市场洞察转化为产品需求与交互原型，构建可落地的产品蓝图。</p>
        </motion.div>

        <AnimatePresence mode="wait">
          {phase === 0 ? (
            <motion.div 
              key="waiting"
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              className="waiting-card"
            >
              <Clock className="spin-icon" size={48} />
              <h2>等待市场洞察专家完成工作...</h2>
              <p>产品经理需要基于详实的市场分析与竞对数据，才能开始 PRD 撰写与原型设计。</p>
            </motion.div>
          ) : (
            <motion.div 
              key="working"
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              className="tasks-grid"
            >
              {/* Task 1: PRD */}
              <motion.div className={`task-card ${phase >= 1 ? 'active' : ''}`}>
                <div className="task-header">
                  <PenTool className="icon" />
                  <h3>撰写产品 PRD</h3>
                  {phase > 1 ? <CheckCircle className="status-icon done" /> : phase === 1 ? <Loader className="status-icon spin" /> : null}
                </div>
                <div className="progress-container">
                  <div className="progress-bar" style={{ width: `${prdProgress}%` }} />
                </div>
                <div className="task-details">
                  <span className="percentage">{Math.floor(prdProgress)}%</span>
                  <AnimatePresence mode="wait">
                    {phase === 1 && (
                      <motion.span 
                        key={currentPrdStep}
                        initial={{ opacity: 0, y: 10 }}
                        animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0, y: -10 }}
                        className="current-target"
                      >
                        {currentPrdStep}
                      </motion.span>
                    )}
                  </AnimatePresence>
                  {phase > 1 && <span className="current-target">PRD 撰写完成</span>}
                </div>
              </motion.div>

              {/* Task 2: Wireframe */}
              <motion.div className={`task-card ${phase >= 2 ? 'active' : ''}`}>
                <div className="task-header">
                  <Layout className="icon" />
                  <h3>绘制产品原型图</h3>
                  {phase > 2 ? <CheckCircle className="status-icon done" /> : phase === 2 ? <Loader className="status-icon spin" /> : null}
                </div>
                <div className="progress-container">
                  <div className="progress-bar" style={{ width: `${wireframeProgress}%` }} />
                </div>
                <div className="task-details">
                  <span className="percentage">{Math.floor(wireframeProgress)}%</span>
                  <AnimatePresence mode="wait">
                    {phase === 2 && (
                      <motion.span 
                        key={currentWireframeStep}
                        initial={{ opacity: 0, y: 10 }}
                        animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0, y: -10 }}
                        className="current-target"
                      >
                        {currentWireframeStep}
                      </motion.span>
                    )}
                  </AnimatePresence>
                  {phase > 2 && <span className="current-target">原型图绘制完成</span>}
                </div>
              </motion.div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Final Output */}
        <AnimatePresence>
          {phase === 3 && (
            <motion.div 
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              className="output-section"
            >
              <h3>工作输出</h3>
              <div className="output-grid">
                <div className="prd-doc-card">
                  <FileText size={32} className="doc-icon" />
                  <div className="doc-info">
                    <h4>AI智能体编排平台_PRD_v1.0.pdf</h4>
                    <p>详细的产品需求、功能列表及数据字典</p>
                  </div>
                  <button className="view-btn">阅读报告</button>
                </div>

                <div className="prototype-gallery">
                  <h4>产品原型图</h4>
                  <div className="gallery-grid">
                    {mockPrototypes.map(p => (
                      <div key={p.id} className="gallery-item" onClick={() => setSelectedProto(p)}>
                        <img src={p.image} alt={p.name} />
                        <div className="gallery-overlay">
                          <Monitor size={24} />
                          <span>{p.name}</span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* Prototype Modal */}
      <AnimatePresence>
        {selectedProto && (
          <motion.div 
            className="proto-modal-backdrop"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={() => setSelectedProto(null)}
          >
            <motion.div 
              className="proto-modal-content"
              initial={{ scale: 0.9, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.9, opacity: 0 }}
              onClick={e => e.stopPropagation()}
            >
              <img src={selectedProto.image} alt={selectedProto.name} />
              <button className="close-modal" onClick={() => setSelectedProto(null)}>×</button>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}