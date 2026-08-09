import React, { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { Link } from 'react-router-dom';
import { ArrowLeft, Loader, TrendingUp, Clock, Activity, CheckCircle, ShieldCheck } from 'lucide-react';
import { useAuth } from '../auth/AuthContext';
import { useOrchestration } from '../hooks/useOrchestration';
import { generateRoleWorkflow } from '../services/orchestrationService';
import './RoleFounder.css';

const DATA_REQUIREMENTS = `
{
  "roi_metrics": {
    "estimated_revenue": "预估收益（如 ￥1,200,000）",
    "cost_saving": "降本比例（如 40%）",
    "time_to_market": "上市时间（如 2 Months）"
  },
  "timeline": [
    { "phase": "阶段名称", "date": "时间节点", "status": "Completed / In Progress / Pending" }
  ],
  "status_dashboard": [
    { "module": "模块名称", "health": "Healthy / Warning / Critical", "desc": "状态描述" }
  ],
  "approval_card": {
    "title": "审批事项名称",
    "amount": "涉及金额",
    "submitter": "提交人"
  },
  "advisor_message": "数字人顾问的一句话简短建议"
}
`;

export default function RoleFounder() {
  const { sessionScopeKey } = useAuth();
  const { sessionMeta, input } = useOrchestration({ scopeKey: sessionScopeKey });

  const [phase, setPhase] = useState(-1);
  const [data, setData] = useState(null);
  const [approved, setApproved] = useState(false);

  useEffect(() => {
    async function fetchWorkflow() {
      try {
        const goal = sessionMeta.goal || input || "项目评估与审批";
        const res = await generateRoleWorkflow(sessionMeta.sessionId, "founder", goal, DATA_REQUIREMENTS);
        if (res) {
          setData(res);
          setPhase(0);
        }
      } catch (err) {
        console.error("fetchWorkflow err", err);
        setPhase(0);
      }
    }
    fetchWorkflow();
  }, [sessionMeta.sessionId, input]);

  if (phase === -1 || !data) {
    return (
      <div className="role-founder-container loading">
        <Loader className="spin" size={48} />
        <span>正在连接 Hermes Main Agent 获取高管战情大盘...</span>
      </div>
    );
  }

  const getHealthColor = (health) => {
    if (health === 'Healthy') return 'text-green';
    if (health === 'Warning') return 'text-orange';
    return 'text-red';
  };

  const getStatusIcon = (status) => {
    if (status === 'Completed') return <CheckCircle size={16} className="text-green" />;
    if (status === 'In Progress') return <Loader size={16} className="text-blue spin-slow" />;
    return <Clock size={16} className="text-gray" />;
  };

  return (
    <div className="role-founder-container">
      <nav className="founder-nav">
        <Link to="/orchestration" className="back-button">
          <ArrowLeft size={18} /> 返回编排台
        </Link>
        <div className="nav-title">企业负责人 (Founder) - 高管战情室</div>
      </nav>

      <main className="founder-main">
        <div className="dashboard-grid">
          {/* Top: ROI Metrics */}
          <motion.div 
            className="panel roi-panel"
            initial={{ opacity: 0, y: -20 }}
            animate={{ opacity: 1, y: 0 }}
          >
            <div className="panel-header">
              <TrendingUp className="panel-icon text-blue" />
              <h2>ROI 核心指标</h2>
            </div>
            <div className="metrics-grid">
              <div className="metric-item">
                <div className="metric-label">预估收益 (Estimated Revenue)</div>
                <div className="metric-value text-blue">{data.roi_metrics?.estimated_revenue}</div>
              </div>
              <div className="metric-item">
                <div className="metric-label">预估降本 (Cost Saving)</div>
                <div className="metric-value text-green">{data.roi_metrics?.cost_saving}</div>
              </div>
              <div className="metric-item">
                <div className="metric-label">交付周期 (Time to Market)</div>
                <div className="metric-value text-purple">{data.roi_metrics?.time_to_market}</div>
              </div>
            </div>
          </motion.div>

          {/* Left: Timeline */}
          <motion.div 
            className="panel timeline-panel"
            initial={{ opacity: 0, x: -20 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: 0.1 }}
          >
            <div className="panel-header">
              <Clock className="panel-icon text-orange" />
              <h2>项目时间线 (Timeline)</h2>
            </div>
            <div className="timeline">
              {(data.timeline || []).map((item, idx) => (
                <div key={idx} className="timeline-item">
                  <div className="timeline-marker">
                    {getStatusIcon(item.status)}
                    {idx < data.timeline.length - 1 && <div className="timeline-line"></div>}
                  </div>
                  <div className="timeline-content">
                    <h3>{item.phase}</h3>
                    <span className="timeline-date">{item.date}</span>
                  </div>
                  <div className="timeline-status">{item.status}</div>
                </div>
              ))}
            </div>
          </motion.div>

          {/* Right: Status Dashboard & Approval */}
          <div className="right-column">
            <motion.div 
              className="panel status-panel"
              initial={{ opacity: 0, x: 20 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: 0.2 }}
            >
              <div className="panel-header">
                <Activity className="panel-icon text-purple" />
                <h2>状态大盘 (Health Status)</h2>
              </div>
              <div className="health-list">
                {(data.status_dashboard || []).map((item, idx) => (
                  <div key={idx} className="health-item">
                    <div className="health-info">
                      <h4>{item.module}</h4>
                      <p>{item.desc}</p>
                    </div>
                    <div className={`health-badge ${getHealthColor(item.health)}`}>
                      {item.health}
                    </div>
                  </div>
                ))}
              </div>
            </motion.div>

            <motion.div 
              className="panel approval-panel"
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.3 }}
            >
              <div className="panel-header">
                <ShieldCheck className="panel-icon text-green" />
                <h2>待办审批 (Approval)</h2>
              </div>
              <div className="approval-card">
                <h3>{data.approval_card?.title}</h3>
                <div className="approval-details">
                  <div className="detail-row">
                    <span>涉及金额：</span>
                    <strong>{data.approval_card?.amount}</strong>
                  </div>
                  <div className="detail-row">
                    <span>提交人：</span>
                    <strong>{data.approval_card?.submitter}</strong>
                  </div>
                </div>
                {approved ? (
                  <div className="approved-stamp">
                    <CheckCircle size={20} /> 已同意审批
                  </div>
                ) : (
                  <div className="approval-actions">
                    <button className="btn-reject">驳回</button>
                    <button className="btn-approve" onClick={() => setApproved(true)}>一键同意</button>
                  </div>
                )}
              </div>
            </motion.div>
          </div>
        </div>
      </main>

      {/* Digital Advisor */}
      <motion.div 
        className="digital-advisor"
        initial={{ opacity: 0, x: 50 }}
        animate={{ opacity: 1, x: 0 }}
        transition={{ delay: 0.5 }}
      >
        <div className="advisor-avatar">
          <img src="/assets/portrait-founder.jpg" alt="Advisor" onError={(e) => { e.target.onerror = null; e.target.src = "https://via.placeholder.com/48"; }} />
        </div>
        <div className="advisor-bubble">
          {data.advisor_message || "老板，这是本次项目的战情大盘，各项指标良好，请审批。"}
        </div>
      </motion.div>
    </div>
  );
}
