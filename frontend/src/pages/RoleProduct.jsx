import React, { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { Link } from 'react-router-dom';
import { ArrowLeft, Loader, Layout, FileText, Users, Lightbulb } from 'lucide-react';
import { useAuth } from '../auth/AuthContext';
import { useOrchestration } from '../hooks/useOrchestration';
import { generateRoleWorkflow } from '../services/orchestrationService';
import './RoleProduct.css';

const DATA_REQUIREMENTS = `
{
  "summary_card": {
    "title": "产品核心定位",
    "description": "产品一句话描述或核心价值主张",
    "target_users": "目标用户群体描述"
  },
  "drift_scenes": [
    {
      "type": "PRD",
      "title": "产品需求文档 (PRD)",
      "content": "核心功能列表或需求概览"
    },
    {
      "type": "Wireframe",
      "title": "交互原型 (Wireframe)",
      "content": "页面流转说明或核心交互逻辑"
    },
    {
      "type": "UserStory",
      "title": "用户故事 (User Story)",
      "content": "作为...我希望...以便... (举例)"
    }
  ],
  "advisor_message": "数字人顾问的一句话简短建议"
}
`;

export default function RoleProduct() {
  const { sessionScopeKey } = useAuth();
  const { sessionMeta, input } = useOrchestration({ scopeKey: sessionScopeKey });

  const [phase, setPhase] = useState(-1);
  const [data, setData] = useState(null);

  useEffect(() => {
    async function fetchWorkflow() {
      try {
        const goal = sessionMeta.goal || input || "设计产品方案";
        const res = await generateRoleWorkflow(sessionMeta.sessionId, "product", goal, DATA_REQUIREMENTS);
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
      <div className="role-product-container loading">
        <Loader className="spin" size={48} />
        <span>正在连接 Hermes Main Agent 获取产品设计蓝图...</span>
      </div>
    );
  }

  const getSceneIcon = (type) => {
    switch(type) {
      case 'PRD': return <FileText size={24} />;
      case 'Wireframe': return <Layout size={24} />;
      case 'UserStory': return <Users size={24} />;
      default: return <Lightbulb size={24} />;
    }
  };

  return (
    <div className="role-product-container">
      <nav className="product-nav">
        <Link to="/orchestration" className="back-button">
          <ArrowLeft size={18} /> 返回编排台
        </Link>
        <div className="nav-title">产品经理 (Product) - 产品蓝图工作台</div>
      </nav>

      <main className="product-main">
        {/* SUMMARY-CARD */}
        <motion.section 
          className="summary-card-section"
          initial={{ opacity: 0, y: -20 }}
          animate={{ opacity: 1, y: 0 }}
        >
          <div className="summary-card">
            <div className="card-bg-glow"></div>
            <div className="card-content">
              <h2>{data.summary_card?.title || "产品核心定位"}</h2>
              <p className="description">{data.summary_card?.description}</p>
              <div className="target-users">
                <Users size={16} />
                <span><strong>目标用户：</strong>{data.summary_card?.target_users}</span>
              </div>
            </div>
          </div>
        </motion.section>

        {/* DRIFT-SCENE */}
        <motion.section 
          className="drift-scene-section"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.3 }}
        >
          <div className="drift-container">
            {(data.drift_scenes || []).map((scene, idx) => (
              <motion.div 
                key={idx} 
                className={\`drift-card scene-\${idx}\`}
                initial={{ opacity: 0, y: 50 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.4 + idx * 0.2, type: "spring", stiffness: 100 }}
                whileHover={{ y: -10, scale: 1.02 }}
              >
                <div className="scene-icon">
                  {getSceneIcon(scene.type)}
                </div>
                <h3>{scene.title}</h3>
                <div className="scene-content">
                  <p>{scene.content}</p>
                </div>
                <button className="view-details-btn">查看详情</button>
              </motion.div>
            ))}
          </div>
        </motion.section>
      </main>

      {/* Digital Advisor */}
      <motion.div 
        className="digital-advisor"
        initial={{ opacity: 0, x: 50 }}
        animate={{ opacity: 1, x: 0 }}
        transition={{ delay: 0.8 }}
      >
        <div className="advisor-avatar">
          <img src="/assets/portrait-product.jpg" alt="Advisor" onError={(e) => { e.target.onerror = null; e.target.src = "https://via.placeholder.com/48"; }} />
        </div>
        <div className="advisor-bubble">
          {data.advisor_message || "产品核心方案已成型，请查看相关交付物。"}
        </div>
      </motion.div>
    </div>
  );
}
