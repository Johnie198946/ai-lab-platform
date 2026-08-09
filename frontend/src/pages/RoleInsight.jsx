import React, { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Link } from 'react-router-dom';
import { ArrowLeft, Loader, User, Zap, Target, TrendingUp, Search } from 'lucide-react';
import { useAuth } from '../auth/AuthContext';
import { useOrchestration } from '../hooks/useOrchestration';
import { generateRoleWorkflow } from '../services/orchestrationService';
import './RoleInsight.css';

const DATA_REQUIREMENTS = `
{
  "verdict": "值得做 / 不值得做 / 有条件地做（一句话结论，管理层视角）",
  "hero_insight": "以管理层视角判断的核心洞察总结（约50字，含是否值得做的判断）",
  "role_tasks": [
    { "role": "产品经理", "role_id": "product", "tasks": ["基于调研结果要做的具体事1", "具体事2"] },
    { "role": "开发工程师", "role_id": "engineering", "tasks": ["基于调研结果要做的具体事1", "具体事2"] },
    { "role": "营销经理", "role_id": "marketing", "tasks": ["基于调研结果要做的具体事1", "具体事2"] },
    { "role": "销售经理", "role_id": "sales", "tasks": ["基于调研结果要做的具体事1", "具体事2"] },
    { "role": "老板", "role_id": "boss", "tasks": ["基于调研结果要做的具体事1", "具体事2"] }
  ],
  "conclusions": [
    { "title": "结论先行小标题", "desc": "具体说明" }
  ],
  "opportunities": [
    { "title": "机会位小标题", "desc": "具体说明" }
  ],
  "actions": [
    { "title": "建议动作小标题", "desc": "具体说明" }
  ],
  "waterfall_items": [
    {
      "title": "洞察卡片标题",
      "content": "洞察卡片具体数据或分析",
      "tag": "外部竞争/市场空间/对手优势/对手劣势/入局时机/内部重心/基本盘/优势能力/战略支持/流程支持/团队能力",
      "source": "数据来源（外部资料标注来源；内部搜不到写'知识库暂无相关信息'）"
    }
  ],
  "advisor_message": "数字人顾问的一句话简短建议"
}
`;

export default function RoleInsight() {
  const { sessionScopeKey } = useAuth();
  const { sessionMeta, input } = useOrchestration({ scopeKey: sessionScopeKey });

  const [phase, setPhase] = useState(-1); // -1: fetching, 0: fetched
  const [data, setData] = useState(null);

  useEffect(() => {
    async function fetchWorkflow() {
      try {
        const goal = sessionMeta.goal || input || "分析当前市场";
        const res = await generateRoleWorkflow(sessionMeta.sessionId, "insight", goal, DATA_REQUIREMENTS);
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
      <div className="role-insight-container loading">
        <Loader className="spin" size={48} />
        <span>正在连接 Hermes Main Agent 获取洞察数据...</span>
      </div>
    );
  }

  return (
    <div className="role-insight-container">
      <nav className="insight-nav">
        <Link to="/orchestration" className="back-button">
          <ArrowLeft size={18} /> 返回编排台
        </Link>
        <div className="nav-title">市场洞察专家 (Market Insight)</div>
      </nav>

      <main className="insight-main">
        {/* Verdict Banner: 值不值得做(2026-08-09 用户拍板: 洞察核心=立项判断) */}
        {data.verdict && (
          <motion.div 
            className="verdict-banner"
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
          >
            <span className="verdict-label">立项判断</span>
            <span className="verdict-text">{data.verdict}</span>
          </motion.div>
        )}

        {/* Hero Section */}
        <motion.section 
          className="hero-section"
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
        >
          <div className="hero-icon"><Search size={32} /></div>
          <h1 className="hero-title">“{data.hero_insight || "正在分析市场格局与潜在机会..."}”</h1>
        </motion.section>

        {/* 3-Column Grid */}
        <section className="three-col-grid">
          <motion.div 
            className="grid-col"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.1 }}
          >
            <div className="col-header">
              <Zap className="col-icon text-blue" />
              <h2>结论先行</h2>
            </div>
            <div className="col-cards">
              {(data.conclusions || []).slice(0, 3).map((item, idx) => (
                <div key={idx} className="insight-card light-card">
                  <h3>{item.title}</h3>
                  <p>{item.desc}</p>
                </div>
              ))}
            </div>
          </motion.div>

          <motion.div 
            className="grid-col"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.2 }}
          >
            <div className="col-header">
              <Target className="col-icon text-green" />
              <h2>机会位</h2>
            </div>
            <div className="col-cards">
              {(data.opportunities || []).slice(0, 3).map((item, idx) => (
                <div key={idx} className="insight-card light-card">
                  <h3>{item.title}</h3>
                  <p>{item.desc}</p>
                </div>
              ))}
            </div>
          </motion.div>

          <motion.div 
            className="grid-col"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.3 }}
          >
            <div className="col-header">
              <TrendingUp className="col-icon text-purple" />
              <h2>建议动作</h2>
            </div>
            <div className="col-cards">
              {(data.actions || []).slice(0, 3).map((item, idx) => (
                <div key={idx} className="insight-card light-card">
                  <h3>{item.title}</h3>
                  <p>{item.desc}</p>
                </div>
              ))}
            </div>
          </motion.div>
        </section>

        {/* Waterfall Wall */}
        <motion.section 
          className="waterfall-section"
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.4 }}
        >
          <h2 className="section-title">洞察工作墙</h2>
          <div className="waterfall-grid">
            {(data.waterfall_items || []).map((item, idx) => (
              <div key={idx} className="waterfall-item">
                <div className="item-meta">
                  <span className="item-tag">{item.tag}</span>
                  <span className="item-source">{item.source}</span>
                </div>
                <h3>{item.title}</h3>
                <p>{item.content}</p>
              </div>
            ))}
          </div>
        </motion.section>

        {/* Role Tasks: 若要做 → 5 角色任务清单(其他角色的前提输入, 2026-08-09 用户拍板) */}
        {(data.role_tasks || []).length > 0 && (
          <motion.section 
            className="role-tasks-section"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.5 }}
          >
            <h2 className="section-title">若要做 · 各角色任务清单</h2>
            <div className="role-tasks-grid">
              {(data.role_tasks || []).map((rt, idx) => (
                <div key={idx} className="role-task-card">
                  <div className="role-task-head">
                    <span className="role-task-badge">{rt.role_id}</span>
                    <h3>{rt.role}</h3>
                  </div>
                  <ul>
                    {(rt.tasks || []).map((t, i) => (
                      <li key={i}>{t}</li>
                    ))}
                  </ul>
                </div>
              ))}
            </div>
          </motion.section>
        )}
      </main>

      {/* Digital Advisor */}
      <motion.div 
        className="digital-advisor"
        initial={{ opacity: 0, x: 50 }}
        animate={{ opacity: 1, x: 0 }}
        transition={{ delay: 0.6 }}
      >
        <div className="advisor-avatar">
          <img src="/assets/portrait-insight.jpg" alt="Advisor" onError={(e) => { e.target.onerror = null; e.target.src = "https://via.placeholder.com/48"; }} />
        </div>
        <div className="advisor-bubble">
          {data.advisor_message || "我已经为您整理好了最新的洞察分析。"}
        </div>
      </motion.div>
    </div>
  );
}
