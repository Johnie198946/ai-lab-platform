import React, { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Link } from 'react-router-dom';
import { ArrowLeft, TrendingUp, Clock, Target, CheckCircle, AlertTriangle, ShieldCheck, FileText, Loader } from 'lucide-react';
import { useAuth } from '../auth/AuthContext';
import { useOrchestration } from '../hooks/useOrchestration';
import { generateRoleWorkflow } from '../services/orchestrationService';
import './RoleFounder.css';

export default function RoleFounder() {
  const { sessionScopeKey } = useAuth();
  const { sessionMeta, input } = useOrchestration({ scopeKey: sessionScopeKey });

  const [phase, setPhase] = useState(0); // 0: blocked, 1: deciding, 2: approved
  const [approved, setApproved] = useState(false);

  const [founderDetails, setFounderDetails] = useState([
    "市场空缺明确，竞争底稿已生成",
    "PRD与原型图已输出",
    "软件环境就绪，硬件无需定制",
    "主打胶片与宣贯物料已发布"
  ]);

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
        const res = await generateRoleWorkflow(sessionMeta.sessionId, "boss", goal);
        
        if (res && res.details && res.details.length >= 4) {
          setFounderDetails(res.details);
          if (res._cached) {
            setPhase(2);
            setApproved(true);
          }
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

  const handleApprove = () => {
    setApproved(true);
    setPhase(2);
  };

  const handleMockTrigger = () => {
    if (phase === 0) setPhase(1);
  };

  const timelineSteps = [
    { name: "市场洞察", status: phase >= 1 ? "completed" : "pending" },
    { name: "产品 PRD", status: phase >= 1 ? "completed" : "pending" },
    { name: "开发构建", status: phase >= 1 ? "completed" : "pending" },
    { name: "营销方案", status: phase >= 1 ? "completed" : "pending" },
    { name: "销售就绪", status: phase === 2 ? "completed" : phase === 1 ? "active" : "pending" }
  ];

  const agentStatus = [
    { name: "市场洞察专家", status: phase >= 1 ? "completed" : "pending", desc: phase >= 1 ? founderDetails[0] : "等待输入" },
    { name: "产品经理", status: phase >= 1 ? "completed" : "pending", desc: phase >= 1 ? founderDetails[1] : "等待输入" },
    { name: "开发工程师", status: phase >= 1 ? "completed" : "pending", desc: phase >= 1 ? founderDetails[2] : "等待输入" },
    { name: "营销经理", status: phase >= 1 ? "completed" : "pending", desc: phase >= 1 ? founderDetails[3] : "等待输入" },
    { name: "销售经理", status: phase === 2 ? "completed" : phase === 1 ? "warning" : "pending", desc: phase === 2 ? "开始拓客打单" : "等待审批授权" }
  ];

  return (
    <div className="role-founder-container">
      <Link to="/orchestration" className="back-button">
        <ArrowLeft size={16} /> 返回 overview
      </Link>

      <div className="founder-content">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className={`bespoke-header ${phase === 2 ? 'is-ready' : ''}`}
        >
          <span className="role-tag">老板 (Founder)</span>
          {phase === 0 ? (
            <>
              <h1>前序节点未完成，战情室大盘暂无数据，审批处于 blocked 状态。</h1>
              <p>老板角色作为最终决策者，无需参与一线执行，而是等待市场、产品、研发、营销等节点汇总数据，进行 ROI 与进度审查。</p>
            </>
          ) : phase === 1 ? (
            <>
              <h1>所有前序业务模块已提交数据，正在等待最终发布审批。</h1>
              <p>全局 ROI 预期与各 Agent 工作产物已汇总至大盘。请审查资源消耗与交付成果，并决定是否正式投入市场。</p>
            </>
          ) : (
            <>
              <h1>项目已获批上线，销售管道已全面打通。</h1>
              <p>端到端流程闭环完成。各节点团队已进入生产状态，您的决策已同步至全员。</p>
            </>
          )}

          <div className="status-pills">
            <div className="pill-row">
              <span className={`status-pill ${phase >= 1 ? 'done' : 'waiting'}`}>业务数据 {phase >= 1 ? 'DONE' : 'WAITING'}</span>
              <span className={`status-pill ${phase === 2 ? 'done' : phase === 1 ? 'active' : 'waiting'}`}>最终审批 {phase === 2 ? 'APPROVED' : phase === 1 ? 'DECIDING' : 'BLOCKED'}</span>
            </div>
            <span className="status-hint">{phase === 0 ? '等待前序节点' : phase === 1 ? '待审批' : '流程闭环'}</span>
          </div>
        </motion.div>

        <div className="workspace-section">
          <div className="workspace-header">
            <div className="ws-title-area">
              <span className="ws-tag">WAR ROOM + APPROVAL</span>
              <h2>C-Level 战情室</h2>
              <p>全局监控商业 ROI、资源消耗与端到端进度，进行高优决策与风险控制。</p>
            </div>
            {phase === 0 && (
              <button className="mock-btn" onClick={handleMockTrigger}>模拟前序完成</button>
            )}
          </div>

          <div className="founder-dashboard">
            {/* Top Section: Timeline & ROI */}
            <div className="top-dashboard">
              <div className="timeline-card">
                <h3>端到端全流程里程碑</h3>
                <div className="timeline-track">
                  {timelineSteps.map((step, idx) => (
                    <React.Fragment key={step.name}>
                      <div className={`timeline-node ${step.status}`}>
                        {step.status === 'completed' ? <CheckCircle size={20} /> : step.status === 'active' ? <AlertTriangle size={20} /> : <div className="circle-empty" />}
                        <span>{step.name}</span>
                      </div>
                      {idx < timelineSteps.length - 1 && <div className={`timeline-line ${timelineSteps[idx].status === 'completed' && (timelineSteps[idx+1].status === 'completed' || timelineSteps[idx+1].status === 'active') ? 'active' : ''}`} />}
                    </React.Fragment>
                  ))}
                </div>
              </div>

              <div className="roi-metrics">
                <div className={`metric-card ${phase === 0 ? 'disabled' : ''}`}>
                  <Clock className="metric-icon blue" />
                  <div className="metric-data">
                    <span className="label">Time-to-Market 加速</span>
                    <strong className="value">{phase === 0 ? '--' : '60%'}</strong>
                  </div>
                </div>
                <div className={`metric-card ${phase === 0 ? 'disabled' : ''}`}>
                  <TrendingUp className="metric-icon green" />
                  <div className="metric-data">
                    <span className="label">预期收益 (Q1)</span>
                    <strong className="value">{phase === 0 ? '--' : '¥12.5M'}</strong>
                  </div>
                </div>
                <div className={`metric-card ${phase === 0 ? 'disabled' : ''}`}>
                  <Target className="metric-icon purple" />
                  <div className="metric-data">
                    <span className="label">预计算力成本</span>
                    <strong className="value">{phase === 0 ? '--' : '¥1.2M'}</strong>
                  </div>
                </div>
              </div>
            </div>

            {/* Bottom Section: Agent Grid & Approval */}
            <div className="bottom-layout">
              <div className="agent-grid-panel">
                <h3>Agent 执行状态快照</h3>
                <div className="agent-list">
                  {agentStatus.map(agent => (
                    <div key={agent.name} className={`agent-status-card ${agent.status}`}>
                      <div className="agent-status-header">
                        <span className="agent-name">{agent.name}</span>
                        {agent.status === 'completed' && <CheckCircle size={16} className="icon-success" />}
                        {agent.status === 'warning' && <AlertTriangle size={16} className="icon-warning" />}
                        {agent.status === 'pending' && <Clock size={16} className="icon-pending" />}
                      </div>
                      <p>{agent.desc}</p>
                    </div>
                  ))}
                </div>
              </div>

              <div className="decision-panel">
                <h3>高优先级决策与审批</h3>
                {phase === 0 ? (
                  <div className="decision-card blocked">
                    <ShieldCheck className="decision-icon" />
                    <p>等待前序节点汇总数据...</p>
                  </div>
                ) : (
                  <div className={`decision-card ${approved ? 'approved' : ''}`}>
                    <div className="decision-header">
                      <ShieldCheck className="decision-icon" />
                      <h4>最终发布审批：{sessionMeta.goal || input || "当前项目"}</h4>
                    </div>
                    <p>所有前序模块（市场、产品、研发、营销）均已完成并就绪。请确认是否正式授权上线该项目，并允许销售团队向客户发车。</p>
                    
                    {!approved ? (
                      <button className="approve-btn" onClick={handleApprove}>
                        授权发布 (Approve)
                      </button>
                    ) : (
                      <div className="approved-stamp">
                        <CheckCircle size={20} />
                        <span>已授权上线，项目流转至销售端</span>
                      </div>
                    )}
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
