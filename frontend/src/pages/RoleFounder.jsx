import React, { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Link } from 'react-router-dom';
import { ArrowLeft, TrendingUp, Clock, Target, CheckCircle, AlertTriangle, ShieldCheck, FileText, ChevronRight, Loader } from 'lucide-react';
import { useAuth } from '../auth/AuthContext';
import { useOrchestration } from '../hooks/useOrchestration';
import { generateRoleWorkflow } from '../services/orchestrationService';
import './RoleFounder.css';

export default function RoleFounder() {
  const { sessionScopeKey } = useAuth();
  const { sessionMeta, input } = useOrchestration({ scopeKey: sessionScopeKey });

  const [phase, setPhase] = useState(-1);
  const [approved, setApproved] = useState(false);
  const [showOnePager, setShowOnePager] = useState(false);

  const [founderDetails, setFounderDetails] = useState([
    "市场空缺明确，竞争底稿已生成",
    "PRD与原型图已输出",
    "软件环境就绪，硬件无需定制",
    "主打胶片与宣贯物料已发布"
  ]);
  const [founderSummary, setFounderSummary] = useState("");

  useEffect(() => {
    async function fetchWorkflow() {
      try {
        const goal = sessionMeta.goal || input || "我想做一个 AI 智能体编排平台，并且帮我完成营销和销售，请帮我端到端完成";
        const res = await generateRoleWorkflow(sessionMeta.sessionId, "boss", goal);
        if (res && res.details && res.details.length >= 4) {
          setFounderDetails(res.details);
          setFounderSummary(res.summary);
        }
      } catch (err) {
        console.error("fetchWorkflow err", err);
      } finally {
        setPhase(0);
      }
    }
    fetchWorkflow();
  }, [sessionMeta.sessionId, input]);

  const handleApprove = () => {
    setApproved(true);
    setTimeout(() => {
      setShowOnePager(true);
    }, 1000);
  };

  const timelineSteps = [
    { name: "市场洞察", status: "completed" },
    { name: "产品 PRD", status: "completed" },
    { name: "开发构建", status: "completed" },
    { name: "营销方案", status: "completed" },
    { name: "销售 Ready", status: approved ? "completed" : "pending" }
  ];

  const agentStatus = [
    { name: "市场洞察专家", status: "completed", desc: founderDetails[0] || "市场空缺明确，竞争底稿已生成" },
    { name: "产品经理", status: "completed", desc: founderDetails[1] || "PRD与原型图已输出" },
    { name: "开发工程师", status: "completed", desc: founderDetails[2] || "软件环境就绪，硬件无需定制" },
    { name: "营销经理", status: "completed", desc: founderDetails[3] || "主打胶片与宣贯物料已发布" },
    { name: "销售经理", status: approved ? "completed" : "warning", desc: approved ? "开始拓客打单" : "等待产品上线审批" }
  ];

  if (phase === -1) {
    return (
      <div className="role-founder-container" style={{display: 'flex', justifyContent: 'center', alignItems: 'center', color: '#fff'}}>
        <Loader className="spin" size={48} />
        <span style={{marginLeft: 16}}>正在连接 Hermes Main Agent 规划工作流...</span>
      </div>
    );
  }

  return (
    <div className="role-founder-container">
      <Link to="/orchestration" className="back-button">
        <ArrowLeft size={16} /> 返回指挥中心
      </Link>

      <div className="founder-content">
        <motion.div 
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="header-section"
        >
          <h1>C-Level 战情室</h1>
          <p>全局监控商业 ROI、资源消耗与端到端进度，进行高优决策与风险控制。</p>
        </motion.div>

        {/* 顶部：端到端进度与时间线 & ROI Metrics */}
        <motion.div 
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.1 }}
          className="top-dashboard"
        >
          <div className="timeline-card">
            <h3>端到端全流程里程碑</h3>
            <div className="timeline-track">
              {timelineSteps.map((step, idx) => (
                <React.Fragment key={step.name}>
                  <div className={`timeline-node ${step.status}`}>
                    {step.status === 'completed' ? <CheckCircle size={20} /> : <div className="circle-empty" />}
                    <span>{step.name}</span>
                  </div>
                  {idx < timelineSteps.length - 1 && <div className={`timeline-line ${timelineSteps[idx].status === 'completed' && timelineSteps[idx+1].status === 'completed' ? 'active' : ''}`} />}
                </React.Fragment>
              ))}
            </div>
          </div>

          <div className="roi-metrics">
            <div className="metric-card">
              <Clock className="metric-icon blue" />
              <div className="metric-data">
                <span className="label">Time-to-Market 加速</span>
                <strong className="value">60%</strong>
              </div>
            </div>
            <div className="metric-card">
              <TrendingUp className="metric-icon green" />
              <div className="metric-data">
                <span className="label">预期收益 (Q1)</span>
                <strong className="value">¥12.5M</strong>
              </div>
            </div>
            <div className="metric-card">
              <Target className="metric-icon purple" />
              <div className="metric-data">
                <span className="label">预计算力成本</span>
                <strong className="value">¥1.2M</strong>
              </div>
            </div>
          </div>
        </motion.div>

        <div className="bottom-layout">
          {/* 左侧：各角色 Agent 状态大盘 */}
          <motion.div 
            initial={{ opacity: 0, x: -20 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: 0.2 }}
            className="agent-grid"
          >
            <h3>Agent 状态大盘</h3>
            <div className="agent-list">
              {agentStatus.map(agent => (
                <div key={agent.name} className={`agent-status-card ${agent.status}`}>
                  <div className="agent-status-header">
                    <span className="agent-name">{agent.name}</span>
                    {agent.status === 'completed' ? <CheckCircle size={16} className="icon-success" /> : <AlertTriangle size={16} className="icon-warning" />}
                  </div>
                  <p>{agent.desc}</p>
                </div>
              ))}
            </div>
          </motion.div>

          {/* 右侧：核心决策卡片与审批流 */}
          <motion.div 
            initial={{ opacity: 0, x: 20 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: 0.3 }}
            className="decision-panel"
          >
            <h3>高优先级决策与审批</h3>
            
            <div className={`decision-card ${approved ? 'approved' : ''}`}>
              <div className="decision-header">
                <ShieldCheck className="decision-icon" />
                <h4>最终发布审批：AI智能体编排平台</h4>
              </div>
              <p>所有前序模块（市场、产品、研发、营销）均已完成并就绪。请确认是否正式授权上线该项目，并允许销售团队向客户发车。</p>
              
              {!approved ? (
                <button className="approve-btn" onClick={handleApprove}>
                  亲笔 Approve 授权发布
                </button>
              ) : (
                <div className="approved-stamp">
                  <CheckCircle size={16} /> 已授权发布
                </div>
              )}
            </div>

            <AnimatePresence>
              {showOnePager && (
                <motion.div 
                  initial={{ opacity: 0, height: 0, marginTop: 0 }}
                  animate={{ opacity: 1, height: 'auto', marginTop: 24 }}
                  className="one-pager-preview"
                >
                  <div className="one-pager-header">
                    <FileText size={20} />
                    <h4>高管决策一页纸 (Executive Briefing)</h4>
                  </div>
                  <div className="one-pager-content">
                    <div className="brief-section">
                      <h5>项目概述</h5>
                      <p>{founderSummary || "本项目已完成端到端的市场洞察、产品定义、技术研发与营销准备。预期在下一季度实现显著的营收增长与市占率提升。"}</p>
                      <p><strong>下一步计划：</strong> 授权销售团队开启全渠道推广，并启动下一代版本（v2.0）的需求收集。</p>
                    </div>
                    <div className="brief-section">
                      <h5>市场与竞品结论 (来自市场洞察)</h5>
                      <p>“市场空缺明确，字节/华为尚未完全占领该微分赛道，建议立即投入。”</p>
                    </div>
                    <div className="brief-section">
                      <h5>产品与研发概况 (来自 PM & 开发)</h5>
                      <p>产品核心亮点：智能算力路由。软件构建完成度：100%。硬件依赖：不涉及/自研算力卡适配完成。</p>
                    </div>
                    <div className="brief-section">
                      <h5>营销与销售准备度 (来自 营销 & 销售)</h5>
                      <p>营销一指禅与预热胶片已完成，MOR 流程已由 SPDT 经理提交通过；销售预估客单价与目标客户群（金融、电信数据中心客户）已锁定。</p>
                    </div>
                  </div>
                </motion.div>
              )}
            </AnimatePresence>

          </motion.div>
        </div>
      </div>
    </div>
  );
}
