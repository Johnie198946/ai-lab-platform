import React, { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Link } from 'react-router-dom';
import { ArrowLeft, Code, Cpu, Play, Terminal, Database, Server, Loader } from 'lucide-react';
import { useAuth } from '../auth/AuthContext';
import { useOrchestration } from '../hooks/useOrchestration';
import { generateRoleWorkflow } from '../services/orchestrationService';
import './RoleEngineering.css';

export default function RoleEngineering() {
  const { sessionScopeKey } = useAuth();
  const { sessionMeta, input } = useOrchestration({ scopeKey: sessionScopeKey });

  const [phase, setPhase] = useState(0); // 0: blocked, 1: generating, 2: done
  const [swStep, setSwStep] = useState(0);
  const [swSteps, setSwSteps] = useState(["初始化环境..."]);
  const [codeSnippets, setCodeSnippets] = useState(["$ loading..."]);
  const [showVideo, setShowVideo] = useState(false);

  useEffect(() => {
    async function fetchWorkflow() {
      try {
        if (!sessionMeta.sessionId) return;
        const goal = sessionMeta.goal || input;
        if (!goal || !goal.trim()) {
          setPhase(2);
          return;
        }
        
        setPhase(1);
        const dataRequirements = `
{
  "tasks": [
    "解析 PRD 依赖与架构设计",
    "搭建后端 API 服务",
    "配置数据库与缓存",
    "部署上线与 CI/CD 配置"
  ],
  "details": [
    "执行 npm install 或相关初始化命令",
    "执行 uvicorn main:app 或相关启动命令",
    "执行 docker-compose up -d 或相关数据库部署命令",
    "输出部署成功的日志和地址"
  ],
  "summary": "最终的工程实现与硬件算力评估总结"
}`;
        const res = await generateRoleWorkflow(sessionMeta.sessionId, "engineering", goal, dataRequirements);
        
        if (res && res.tasks && res.tasks.length > 0) {
          setSwSteps(res.tasks);
          setCodeSnippets(res.details || res.tasks.map(t => `$ ${t}`));
          if (res._cached) {
            setPhase(2);
            setSwStep(res.tasks.length - 1);
          }
        } else {
          setSwSteps(["解析 PRD 依赖", "搭建后端 API", "配置数据库", "部署上线"]);
          setCodeSnippets(["$ npm install", "$ uvicorn main:app", "$ docker-compose up -d", "$ deploy success"]);
        }
      } catch (err) {
        console.error(err);
      }
    }
    fetchWorkflow();
  }, [sessionMeta.sessionId, input]);

  useEffect(() => {
    const t = setTimeout(() => {
      if (!sessionMeta.sessionId) {
        setPhase(2);
      }
    }, 3000);
    return () => clearTimeout(t);
  }, [sessionMeta.sessionId]);

  useEffect(() => {
    if (phase === 1) {
      let i = 0;
      const interval = setInterval(() => {
        if (i < swSteps.length - 1) {
          i++;
          setSwStep(i);
        } else {
          clearInterval(interval);
          setPhase(2);
        }
      }, 2000);
      return () => clearInterval(interval);
    }
  }, [phase, swSteps]);

  const handleMockTrigger = () => {
    if (phase === 0) setPhase(1);
  };

  return (
    <div className="role-eng-container">
      <Link to="/orchestration" className="back-button">
        <ArrowLeft size={16} /> 返回 overview
      </Link>

      <div className="eng-content">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className={`bespoke-header ${phase >= 1 ? 'is-ready' : ''}`}
        >
          <span className="role-tag">开发工程师</span>
          {phase === 0 ? (
            <>
              <h1>正在等待产品经理输出 PRD 与原型，研发工作台保持 blocked。</h1>
              <p>当前工作台已预置架构底座与硬件评估模板。开发工程师此刻不直接编码，而是等待上游 PRD 与线框图抵达后，自动进行软件系统构建与硬件算力匹配。</p>
            </>
          ) : phase === 1 ? (
            <>
              <h1>开发工程师已接收 PRD 与原型，正在并行执行软硬件构建。</h1>
              <p>系统正根据 JSON 数据结构自动生成前端组件与后端 API，同时对运行所需的硬件服务器算力进行智能评估与匹配。</p>
            </>
          ) : (
            <>
              <h1>软件架构搭建与硬件评估已完成，系统 Ready。</h1>
              <p>可运行的代码框架与服务器配置清单已输出。您可以直接审查终端日志与硬件演示，或前往营销经理的工作台。</p>
            </>
          )}

          <div className="status-pills">
            <div className="pill-row">
              <span className={`status-pill ${phase > 0 ? 'done' : 'waiting'}`}>PRD {phase > 0 ? 'DONE' : 'WAITING'}</span>
              <span className={`status-pill ${phase === 2 ? 'done' : phase === 1 ? 'active' : 'waiting'}`}>软件 {phase === 2 ? 'DONE' : phase === 1 ? 'BUILDING' : 'BLOCKED'}</span>
              <span className={`status-pill ${phase === 2 ? 'done' : phase === 1 ? 'active' : 'waiting'}`}>硬件 {phase === 2 ? 'DONE' : phase === 1 ? 'EVALUATING' : 'BLOCKED'}</span>
            </div>
            <span className="status-hint">{phase === 0 ? '准备接收 PRD' : phase === 1 ? '构建中...' : '流程完成'}</span>
          </div>
        </motion.div>

        <div className="workspace-section">
          <div className="workspace-header">
            <div className="ws-title-area">
              <span className="ws-tag">ARCHITECTURE + TERMINAL</span>
              <h2>研发工作台</h2>
              <p>左右分栏设计：左侧为架构拆解与代码终端，右侧为硬件算力配置卡片。</p>
            </div>
            {phase === 0 && (
              <button className="mock-btn" onClick={handleMockTrigger}>模拟 PRD 完成</button>
            )}
          </div>

          <div className="bespoke-grid eng-grid">
            <div className="grid-col span-2">
              <div className="col-header">
                <h3>软件构建 (Software)</h3>
                <p>架构自动拆解与终端执行日志</p>
              </div>
              <div className={`col-body ${phase === 0 ? 'empty-state' : ''}`}>
                {phase === 0 ? "等待输入数据" : (
                  <div className="software-panel">
                    <div className="arch-tags">
                      <span className="arch-tag"><Code size={14}/> React</span>
                      <span className="arch-tag"><Terminal size={14}/> FastAPI</span>
                      <span className="arch-tag"><Database size={14}/> PostgreSQL</span>
                    </div>
                    <div className="code-editor">
                      <div className="editor-header">
                        <div className="mac-dots">
                          <span className="dot red"></span>
                          <span className="dot yellow"></span>
                          <span className="dot green"></span>
                        </div>
                        <span className="file-name">Terminal - Build Process</span>
                      </div>
                      <div className="editor-body">
                        {swSteps.slice(0, swStep + 1).map((step, idx) => (
                          <div key={idx} className="log-entry">
                            <span className="log-time">[{new Date().toLocaleTimeString()}]</span>
                            <span className="log-text">{step}</span>
                            <pre className="log-code">{codeSnippets[idx]}</pre>
                          </div>
                        ))}
                        {phase === 1 && <div className="cursor-blink">_</div>}
                      </div>
                    </div>
                  </div>
                )}
              </div>
            </div>

            <div className="grid-col span-1">
              <div className="col-header">
                <h3>硬件评估 (Hardware)</h3>
                <p>算力需求匹配与设备演示</p>
              </div>
              <div className={`col-body ${phase === 0 ? 'empty-state' : ''}`}>
                {phase === 0 ? "等待输入数据" : (
                  <div className="hardware-panel">
                    <div className="hw-status">
                      <Server size={32} className={phase === 2 ? "hw-icon-ready" : "hw-icon-eval"} />
                      <h4>{phase === 2 ? "算力匹配完成" : "正在评估算力..."}</h4>
                    </div>
                    
                    <div className="hw-details">
                      <div className="hw-item">
                        <span className="hw-label">推荐配置</span>
                        <span className="hw-value">8C 32G / 1x NVIDIA T4</span>
                      </div>
                      <div className="hw-item">
                        <span className="hw-label">网络带宽</span>
                        <span className="hw-value">100 Mbps (BGP)</span>
                      </div>
                      <div className="hw-item">
                        <span className="hw-label">存储</span>
                        <span className="hw-value">500GB NVMe SSD</span>
                      </div>
                    </div>

                    <button 
                      className="play-demo-btn" 
                      disabled={phase !== 2}
                      onClick={() => setShowVideo(true)}
                    >
                      <Play size={16} /> 查看硬件演示
                    </button>
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      </div>

      <AnimatePresence>
        {showVideo && (
          <motion.div 
            className="video-modal-overlay"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={() => setShowVideo(false)}
          >
            <motion.div 
              className="video-modal-content"
              initial={{ scale: 0.9, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.9, opacity: 0 }}
              onClick={e => e.stopPropagation()}
            >
              <button className="close-video" onClick={() => setShowVideo(false)}>×</button>
              <h2>硬件研发演示</h2>
              <p>这里展示服务器的硬件算力配置与主板设计流程示意。</p>
              <div className="video-player-placeholder">
                <Play size={48} color="#fff" />
                <span>演示视频 (Demo)</span>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
