import React, { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Link } from 'react-router-dom';
import { ArrowLeft, Search, Database, FileText, CheckCircle, Loader } from 'lucide-react';
import { useAuth } from '../auth/AuthContext';
import { useOrchestration } from '../hooks/useOrchestration';
import { generateRoleWorkflow } from '../services/orchestrationService';
import './RoleInsight.css';

export default function RoleInsight() {
  const { sessionScopeKey } = useAuth();
  const { sessionMeta, input } = useOrchestration({ scopeKey: sessionScopeKey });

  const [phase, setPhase] = useState(-1); // -1: fetching, 0: init, 1: comp, 2: internal, 3: report, 4: done
  const [compProgress, setCompProgress] = useState(0);
  const [internalProgress, setInternalProgress] = useState(0);
  
  const [competitors, setCompetitors] = useState(["分析中..."]);
  const [internals, setInternals] = useState(["检索中..."]);
  const [reportSteps, setReportSteps] = useState(["生成中..."]);
  const [summary, setSummary] = useState("正在生成执行摘要...");

  const [currentComp, setCurrentComp] = useState("");
  const [currentInternal, setCurrentInternal] = useState("");
  const [reportStep, setReportStep] = useState(0);

  useEffect(() => {
    async function fetchWorkflow() {
      try {
        const goal = sessionMeta.goal || input || "我想做一个 AI 智能体编排平台，并且帮我完成营销和销售，请帮我端到端完成";
        const res = await generateRoleWorkflow(sessionMeta.sessionId, "insight", goal);
        if (res && res.tasks && res.tasks.length > 0) {
          // split tasks into competitors and internals for demo
          const half = Math.ceil(res.tasks.length / 2);
          setCompetitors(res.tasks.slice(0, half));
          setInternals(res.tasks.slice(half));
          setReportSteps(res.details || ["文档生成中..."]);
          setSummary(res.summary || "分析完成。");
        }
      } catch (err) {
        console.error("fetchWorkflow err", err);
      } finally {
        setPhase(0);
      }
    }
    fetchWorkflow();
  }, [sessionMeta.sessionId, input]);

  useEffect(() => {
    if (phase === 0) {
      setCurrentComp(competitors[0] || "");
      setCurrentInternal(internals[0] || "");
      const timer = setTimeout(() => setPhase(1), 500);
      return () => clearTimeout(timer);
    }
  }, [phase, competitors, internals]);

  useEffect(() => {
    if (phase === 1) {
      let startTime = Date.now();
      const duration = 15000;
      const interval = setInterval(() => {
        let elapsed = Date.now() - startTime;
        let p = Math.min(100, (elapsed / duration) * 100);
        setCompProgress(p);
        
        let compIndex = Math.floor((p / 100) * competitors.length);
        if (compIndex >= competitors.length) compIndex = competitors.length - 1;
        setCurrentComp(competitors[compIndex]);

        if (p >= 100) {
          clearInterval(interval);
          setPhase(2);
        }
      }, 100);
      return () => clearInterval(interval);
    }
  }, [phase, competitors]);

  useEffect(() => {
    if (phase === 2) {
      let startTime = Date.now();
      const duration = 10000;
      const interval = setInterval(() => {
        let elapsed = Date.now() - startTime;
        let p = Math.min(100, (elapsed / duration) * 100);
        setInternalProgress(p);

        let intIndex = Math.floor((p / 100) * internals.length);
        if (intIndex >= internals.length) intIndex = internals.length - 1;
        setCurrentInternal(internals[intIndex]);

        if (p >= 100) {
          clearInterval(interval);
          setPhase(3);
        }
      }, 100);
      return () => clearInterval(interval);
    }
  }, [phase, internals]);

  useEffect(() => {
    if (phase === 3) {
      let i = 0;
      const interval = setInterval(() => {
        if (i < reportSteps.length - 1) {
          i++;
          setReportStep(i);
        } else {
          clearInterval(interval);
          setPhase(4);
        }
      }, 1500);
      return () => clearInterval(interval);
    }
  }, [phase, reportSteps]);

  if (phase === -1) {
    return (
      <div className="role-insight-container" style={{display: 'flex', justifyContent: 'center', alignItems: 'center', color: '#fff'}}>
        <Loader className="spin" size={48} />
        <span style={{marginLeft: 16}}>正在连接 Hermes Main Agent 规划工作流...</span>
      </div>
    );
  }

  return (
    <div className="role-insight-container">
      <Link to="/orchestration" className="back-button">
        <ArrowLeft size={16} /> 查看其他人的工作
      </Link>

      <div className="insight-content">
        <motion.div 
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="header-section"
        >
          <h1>市场洞察专家</h1>
          <p>正在为您进行端到端的市场与竞对分析，生成高管洞察报告。</p>
        </motion.div>

        <div className="tasks-grid">
          {/* Task 1: 竞对分析 */}
          <motion.div 
            className={`task-card ${phase >= 1 ? 'active' : ''}`}
            initial={{ opacity: 0, x: -20 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: 0.2 }}
          >
            <div className="task-header">
              <Search className="icon" />
              <h3>竞争对手信息搜集</h3>
              {phase > 1 ? <CheckCircle className="status-icon done" /> : phase === 1 ? <Loader className="status-icon spin" /> : null}
            </div>
            <div className="progress-container">
              <div className="progress-bar" style={{ width: `${compProgress}%` }} />
            </div>
            <div className="task-details">
              <span className="percentage">{Math.floor(compProgress)}%</span>
              <AnimatePresence mode="wait">
                {phase === 1 && (
                  <motion.span 
                    key={currentComp}
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -10 }}
                    className="current-target"
                  >
                    正在分析: {currentComp}
                  </motion.span>
                )}
              </AnimatePresence>
              {phase > 1 && <span className="current-target">分析完成</span>}
            </div>
          </motion.div>

          {/* Task 2: 内部映射 */}
          <motion.div 
            className={`task-card ${phase >= 2 ? 'active' : ''}`}
            initial={{ opacity: 0, x: -20 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: 0.4 }}
          >
            <div className="task-header">
              <Database className="icon" />
              <h3>企业内部信息收集</h3>
              {phase > 2 ? <CheckCircle className="status-icon done" /> : phase === 2 ? <Loader className="status-icon spin" /> : null}
            </div>
            <div className="progress-container">
              <div className="progress-bar" style={{ width: `${internalProgress}%` }} />
            </div>
            <div className="task-details">
              <span className="percentage">{Math.floor(internalProgress)}%</span>
              <AnimatePresence mode="wait">
                {phase === 2 && (
                  <motion.span 
                    key={currentInternal}
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -10 }}
                    className="current-target"
                  >
                    正在检索: {currentInternal}
                  </motion.span>
                )}
              </AnimatePresence>
              {phase > 2 && <span className="current-target">检索完成</span>}
            </div>
          </motion.div>

          {/* Task 3: 报告生成 */}
          <motion.div 
            className={`task-card ${phase >= 3 ? 'active' : ''}`}
            initial={{ opacity: 0, x: -20 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: 0.6 }}
          >
            <div className="task-header">
              <FileText className="icon" />
              <h3>洞察报告编纂</h3>
              {phase > 3 ? <CheckCircle className="status-icon done" /> : phase === 3 ? <Loader className="status-icon spin" /> : null}
            </div>
            <div className="report-status">
              {phase >= 3 && (
                <motion.div 
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  className="report-step-text"
                >
                  {reportSteps[reportStep]}
                </motion.div>
              )}
            </div>
          </motion.div>
        </div>

        {/* Final Output */}
        <AnimatePresence>
          {phase === 4 && (
            <motion.div 
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              className="final-output-card"
            >
              <div className="word-doc-preview">
                <FileText size={48} className="word-icon" />
                <div className="doc-info">
                  <h4>AI行业洞察与超聚变战略建议.docx</h4>
                  <p>包含竞对分析、内部能力盘点及可落地的管理层建议。</p>
                </div>
                <button className="download-btn">查看文档</button>
              </div>
              <div className="ai-summary">
                <p><strong>执行摘要：</strong> {summary}</p>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}
