import React, { useState, useEffect, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Link } from 'react-router-dom';
import { ArrowLeft, Code, Cpu, Play, Terminal, Database, Cloud, FileJson, Loader } from 'lucide-react';
import { useAuth } from '../auth/AuthContext';
import { useOrchestration } from '../hooks/useOrchestration';
import { generateRoleWorkflow } from '../services/orchestrationService';
import './RoleEngineering.css';

export default function RoleEngineering() {
  const { sessionScopeKey } = useAuth();
  const { sessionMeta, input } = useOrchestration({ scopeKey: sessionScopeKey });

  const [phase, setPhase] = useState(-1); // -1: fetching, 0: done fetching
  const [tab, setTab] = useState('software'); // 'software' | 'hardware'
  const [showVideo, setShowVideo] = useState(false);
  
  // Software steps
  const [swStep, setSwStep] = useState(0);
  const [swSteps, setSwSteps] = useState(["初始化环境..."]);
  const [codeSnippets, setCodeSnippets] = useState(["$ loading..."]);

  useEffect(() => {
    async function fetchWorkflow() {
      try {
        const goal = sessionMeta.goal || input;
        if (!goal || !goal.trim()) {
          setSummary("⚠️ 尚未收到用户需求。请先返回编排页, 输入你的业务目标后再进入本角色工作流。");
          setPhase(0);
          return;
        }
        const res = await generateRoleWorkflow(sessionMeta.sessionId, "engineering", goal);
        if (res && res.tasks && res.tasks.length > 0) {
          setSwSteps(res.tasks);
          setCodeSnippets(res.details || res.tasks.map(t => `$ ${t}`));
          if (res._cached) {
            setPhase(0);
            setSwStep(res.tasks.length - 1);
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

  useEffect(() => {
    if (phase === 0 && tab === 'software' && swStep === 0) {
      let i = 0;
      const interval = setInterval(() => {
        if (i < swSteps.length - 1) {
          i++;
          setSwStep(i);
        } else {
          clearInterval(interval);
        }
      }, 2500);
      return () => clearInterval(interval);
    }
  }, [phase, tab, swSteps]);

  if (phase === -1) {
    return (
      <div className="role-eng-container" style={{display: 'flex', justifyContent: 'center', alignItems: 'center', color: '#fff'}}>
        <Loader className="spin" size={48} />
        <span style={{marginLeft: 16}}>正在连接 Hermes Main Agent 规划工作流...</span>
      </div>
    );
  }

  return (
    <div className="role-eng-container" style={{ overflowX: 'hidden' }}>
      <AnimatePresence>
        {!showVideo && (
          <motion.div 
            className="main-view"
            initial={{ x: '-100%' }}
            animate={{ x: 0 }}
            exit={{ x: '-100%' }}
            transition={{ type: "spring", stiffness: 300, damping: 30 }}
          >
            <Link to="/orchestration" className="back-button">
              <ArrowLeft size={16} /> 查看其他人的工作
            </Link>

            <div className="eng-content">
              <motion.div 
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                className="header-section"
              >
                <h1>开发工程师</h1>
                <p>将产品需求转化为可运行的代码，并评估硬件算力需求。</p>
              </motion.div>

              <div className="eng-tabs">
                <button 
                  className={`eng-tab ${tab === 'software' ? 'active' : ''}`}
                  onClick={() => setTab('software')}
                >
                  <Code size={18} /> 软件开发
                </button>
                <button 
                  className={`eng-tab ${tab === 'hardware' ? 'active' : ''}`}
                  onClick={() => setTab('hardware')}
                >
                  <Cpu size={18} /> 硬件评估
                </button>
              </div>

              <div className="tab-content">
                {tab === 'software' && (
                  <motion.div 
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    className="software-panel"
                  >
                    <div className="code-editor">
                      <div className="editor-header">
                        <div className="mac-dots">
                          <span className="dot red"></span>
                          <span className="dot yellow"></span>
                          <span className="dot green"></span>
                        </div>
                        <span className="file-name">Terminal - AI Agent Orchestration</span>
                      </div>
                      <div className="editor-body">
                        {swSteps.slice(0, swStep + 1).map((step, idx) => (
                          <div key={idx} className="log-entry">
                            <span className="log-time">[{new Date().toLocaleTimeString()}]</span>
                            <span className="log-text">{step}</span>
                            <pre className="log-code">{codeSnippets[idx]}</pre>
                          </div>
                        ))}
                        {swStep < swSteps.length - 1 && (
                          <div className="cursor-blink">_</div>
                        )}
                      </div>
                    </div>
                  </motion.div>
                )}

                {tab === 'hardware' && (
                  <motion.div 
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    className="hardware-panel"
                  >
                    <div className="hw-empty-state">
                      <Cpu size={64} className="hw-icon" />
                      <h3>本次任务不涉及硬件开发</h3>
                      <p>当前产品需求主要为纯软件系统与 API 调用，暂无定制硬件（如 PCB 画板、传感器集成等）的研发需求。</p>
                      <button className="play-demo-btn" onClick={() => setShowVideo(true)}>
                        <Play size={18} /> 查看硬件演示
                      </button>
                    </div>
                  </motion.div>
                )}
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      <AnimatePresence>
        {showVideo && (
          <motion.div 
            className="video-view"
            initial={{ x: '100%' }}
            animate={{ x: 0 }}
            exit={{ x: '100%' }}
            transition={{ type: "spring", stiffness: 300, damping: 30 }}
          >
            <button className="back-button" onClick={() => setShowVideo(false)}>
              <ArrowLeft size={16} /> 返回开发工作台
            </button>
            <div className="video-content">
              <h2>硬件研发演示</h2>
              <p>这里展示超聚变服务器的硬件算力配置与主板设计流程示意。</p>
              <div className="video-player">
                {/* 占位视频，可替换为真实URL */}
                <video src="https://www.w3schools.com/html/mov_bbb.mp4" autoPlay loop muted controls></video>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
