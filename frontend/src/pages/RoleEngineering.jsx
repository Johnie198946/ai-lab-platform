import React, { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { Link } from 'react-router-dom';
import { ArrowLeft, Loader, Cpu, Server, CheckCircle, Clock } from 'lucide-react';
import { useAuth } from '../auth/AuthContext';
import { useOrchestration } from '../hooks/useOrchestration';
import { generateRoleWorkflow } from '../services/orchestrationService';
import './RoleEngineering.css';

const DATA_REQUIREMENTS = `
{
  "hardware_grid": [
    { "task_type": "大模型推理", "hardware": "Nvidia A100 x 8", "status": "Ready", "usage": "85%" },
    { "task_type": "数据清洗", "hardware": "CPU 集群", "status": "Ready", "usage": "40%" }
  ],
  "model_catalog": [
    { "name": "DeepSeek-V3", "version": "v1.0", "status": "Online" },
    { "name": "Hermes-Main", "version": "v2.1", "status": "Online" }
  ],
  "advisor_message": "数字人顾问的一句话简短建议"
}
`;

export default function RoleEngineering() {
  const { sessionScopeKey } = useAuth();
  const { sessionMeta, input } = useOrchestration({ scopeKey: sessionScopeKey });

  const [phase, setPhase] = useState(-1);
  const [data, setData] = useState(null);

  useEffect(() => {
    async function fetchWorkflow() {
      try {
        const goal = sessionMeta.goal || input || "系统开发";
        const res = await generateRoleWorkflow(sessionMeta.sessionId, "engineering", goal, DATA_REQUIREMENTS);
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
      <div className="role-eng-container loading">
        <Loader className="spin" size={48} />
        <span>正在连接 Hermes Main Agent 获取工程架构数据...</span>
      </div>
    );
  }

  return (
    <div className="role-eng-container">
      <nav className="eng-nav">
        <Link to="/orchestration" className="back-button">
          <ArrowLeft size={18} /> 返回编排台
        </Link>
        <div className="nav-title">开发工程师 (Engineering)</div>
      </nav>

      <main className="eng-main">
        <div className="split-layout">
          {/* Left: Hardware Grid (2/3 width) */}
          <motion.div 
            className="hardware-section"
            initial={{ opacity: 0, x: -20 }}
            animate={{ opacity: 1, x: 0 }}
          >
            <div className="section-header">
              <Cpu className="header-icon" />
              <h2>算力与硬件匹配矩阵 (Hardware Grid)</h2>
            </div>
            <div className="hardware-grid">
              {(data.hardware_grid || []).map((item, idx) => (
                <div key={idx} className="hw-card">
                  <div className="hw-top">
                    <h3>{item.task_type}</h3>
                    <span className={\`status-badge \${item.status === 'Ready' ? 'ready' : 'pending'}\`}>
                      {item.status}
                    </span>
                  </div>
                  <div className="hw-bottom">
                    <div className="hw-info">
                      <span className="label">分配硬件:</span>
                      <span className="value">{item.hardware}</span>
                    </div>
                    <div className="hw-usage">
                      <div className="usage-bar">
                        <div className="usage-fill" style={{ width: item.usage || '0%' }}></div>
                      </div>
                      <span className="usage-text">{item.usage} 负载</span>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </motion.div>

          {/* Right: Model Catalog (1/3 width) */}
          <motion.div 
            className="model-section"
            initial={{ opacity: 0, x: 20 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: 0.2 }}
          >
            <div className="section-header">
              <Server className="header-icon" />
              <h2>模型目录 (Model Catalog)</h2>
            </div>
            <div className="model-list">
              {(data.model_catalog || []).map((model, idx) => (
                <div key={idx} className="model-item">
                  <div className="model-icon">
                    {model.status === 'Online' ? <CheckCircle size={20} className="text-green" /> : <Clock size={20} className="text-orange" />}
                  </div>
                  <div className="model-details">
                    <h4>{model.name}</h4>
                    <p>版本: {model.version}</p>
                  </div>
                  <div className="model-status">
                    {model.status}
                  </div>
                </div>
              ))}
            </div>
          </motion.div>
        </div>
      </main>

      {/* Digital Advisor */}
      <motion.div 
        className="digital-advisor"
        initial={{ opacity: 0, x: 50 }}
        animate={{ opacity: 1, x: 0 }}
        transition={{ delay: 0.4 }}
      >
        <div className="advisor-avatar">
          <img src="/assets/portrait-engineering.jpg" alt="Advisor" onError={(e) => { e.target.onerror = null; e.target.src = "https://via.placeholder.com/48"; }} />
        </div>
        <div className="advisor-bubble">
          {data.advisor_message || "架构设计已就绪，算力分配合理。"}
        </div>
      </motion.div>
    </div>
  );
}
