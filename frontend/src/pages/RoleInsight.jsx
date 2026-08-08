import React, { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Link } from 'react-router-dom';
import { ArrowLeft, Search, Database, FileText, CheckCircle, Loader } from 'lucide-react';
import './RoleInsight.css';

const competitors = ["字节跳动", "阿里云", "腾讯", "华为", "浪潮", "H3C", "OpenAI", "Google", "Claude"];
const internals = ["产品路标", "算力产品族", "营销工具包", "研发物料"];

export default function RoleInsight() {
  const [phase, setPhase] = useState(0); // 0: init, 1: comp, 2: internal, 3: report, 4: done
  const [compProgress, setCompProgress] = useState(0);
  const [internalProgress, setInternalProgress] = useState(0);
  const [currentComp, setCurrentComp] = useState(competitors[0]);
  const [currentInternal, setCurrentInternal] = useState(internals[0]);
  const [reportStep, setReportStep] = useState(0);
  
  const reportSteps = [
    "正在整合竞争与内部数据...",
    "多维度交叉分析中...",
    "生成洞察报告草稿...",
    "调用 Office 工具编辑...",
    "完成 Word 文档生成"
  ];

  useEffect(() => {
    // 延迟一点启动
    const timer = setTimeout(() => setPhase(1), 500);
    return () => clearTimeout(timer);
  }, []);

  useEffect(() => {
    if (phase === 1) {
      let startTime = Date.now();
      const duration = 30000;
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
  }, [phase]);

  useEffect(() => {
    if (phase === 2) {
      let startTime = Date.now();
      const duration = 15000;
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
  }, [phase]);

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
  }, [phase]);

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
                <p><strong>执行摘要：</strong> 市场空缺明确，字节/华为尚未完全占领该微分赛道，建议结合超聚变现有的算力产品族优势，优先切入高认知价值场景。营销工具包与产品路标已完成对齐，建议立即投入研发。</p>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}
