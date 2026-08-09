import React, { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Link } from 'react-router-dom';
import { ArrowLeft, TrendingUp, Target, Database, FileText, Loader, Zap } from 'lucide-react';
import { useAuth } from '../auth/AuthContext';
import { useOrchestration } from '../hooks/useOrchestration';
import { generateRoleWorkflow } from '../services/orchestrationService';
import './RoleInsight.css';

export default function RoleInsight() {
  const { sessionScopeKey } = useAuth();
  const { sessionMeta, input } = useOrchestration({ scopeKey: sessionScopeKey });

  const [phase, setPhase] = useState(0); // 0: init, 1: generating, 2: done

  const [insightData, setInsightData] = useState({
    competitors: [
      { name: "Competitor A", focus: "分析中...", strength: "分析中...", weakness: "分析中..." }
    ],
    market_trends: [
      { trend_name: "趋势分析中...", impact: "评估中..." }
    ],
    internal_assets: [
      { asset_name: "资产检索中...", relevance: "评估中..." }
    ],
    insight_summary: "等待洞察..."
  });

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
  "competitors": [
    {
      "name": "竞品名称或类别",
      "focus": "该竞品的主打方向",
      "strength": "核心优势",
      "weakness": "关键劣势"
    }
  ],
  "market_trends": [
    {
      "trend_name": "市场或技术趋势名称",
      "impact": "对本项目的影响或机会点"
    }
  ],
  "internal_assets": [
    {
      "asset_name": "内部已有能力、资产或知识库内容",
      "relevance": "如何复用或借鉴（如果没有，写暂无直接可复用资产）"
    }
  ],
  "insight_summary": "一到两段话的最终执行摘要，总结切入点与核心战略建议"
}
注意：请返回至少2个竞品，2个市场趋势，2个内部资产。
`;
        const res = await generateRoleWorkflow(sessionMeta.sessionId, "insight", goal, dataRequirements);
        
        if (res && res.competitors) {
          setInsightData(res);
          if (res._cached) {
            setPhase(2);
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

  useEffect(() => {
    if (phase === 1) {
      const t = setTimeout(() => {
        setPhase(2);
      }, 5000);
      return () => clearTimeout(t);
    }
  }, [phase]);

  return (
    <div className="role-insight-container">
      <Link to="/orchestration" className="back-button">
        <ArrowLeft size={16} /> 返回 overview
      </Link>

      <div className="insight-content">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className={`bespoke-header ${phase === 2 ? 'is-ready' : ''}`}
        >
          <span className="role-tag">市场洞察专家</span>
          {phase === 0 ? (
            <>
              <h1>初始化分析环境，准备扫描市场格局。</h1>
              <p>市场洞察专家将通过 Hermes Main Agent 检索企业知识库并抓取外部情报，为您构建全局市场认知地图。</p>
            </>
          ) : phase === 1 ? (
            <>
              <h1>正在执行深度市场扫描与内部能力映射。</h1>
              <p>系统正并行抓取外部竞品情报、评估行业技术趋势，同时穿透企业内部知识库寻找可复用的资产与经验。</p>
            </>
          ) : (
            <>
              <h1>市场洞察与战略大盘已生成。</h1>
              <p>外部竞争格局与内部能力盘点已完成，您可以直接参考以下战略总结，或前往产品经理工作台将洞察转化为产品需求。</p>
            </>
          )}

          <div className="status-pills">
            <div className="pill-row">
              <span className={`status-pill ${phase === 2 ? 'done' : phase === 1 ? 'active' : 'waiting'}`}>外部扫描 {phase === 2 ? 'DONE' : phase === 1 ? 'SCANNING' : 'WAITING'}</span>
              <span className={`status-pill ${phase === 2 ? 'done' : phase === 1 ? 'active' : 'waiting'}`}>内部映射 {phase === 2 ? 'DONE' : phase === 1 ? 'MAPPING' : 'WAITING'}</span>
            </div>
            <span className="status-hint">{phase === 0 ? '准备启动' : phase === 1 ? '分析中...' : '洞察就绪'}</span>
          </div>
        </motion.div>

        <div className="workspace-section">
          <div className="workspace-header">
            <div className="ws-title-area">
              <span className="ws-tag">STRATEGY & INTELLIGENCE</span>
              <h2>洞察分析大盘</h2>
              <p>左侧为外部市场扫描（竞品与趋势），右侧为内部资产复用与最终战略洞察报告。</p>
            </div>
          </div>

          <div className="bespoke-grid insight-grid">
            <div className="grid-col span-2">
              <div className="col-header">
                <h3>外部市场扫描 (External Intel)</h3>
                <p>实时竞争格局与行业趋势追踪</p>
              </div>
              <div className="col-body">
                <div className="intel-section">
                  <h4 className="section-subtitle"><Target size={14}/> 核心竞对剖析</h4>
                  <div className="competitor-list">
                    {insightData.competitors.map((comp, idx) => (
                      <div key={idx} className="competitor-card">
                        <div className="comp-header">
                          <span className="comp-name">{comp.name}</span>
                          <span className="comp-focus">{comp.focus}</span>
                        </div>
                        <div className="comp-body">
                          <div className="comp-attr strength">
                            <strong>优势:</strong> {comp.strength}
                          </div>
                          <div className="comp-attr weakness">
                            <strong>劣势:</strong> {comp.weakness}
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>

                <div className="intel-section">
                  <h4 className="section-subtitle"><TrendingUp size={14}/> 宏观趋势与机会点</h4>
                  <div className="trends-list">
                    {insightData.market_trends.map((trend, idx) => (
                      <div key={idx} className="trend-item">
                        <span className="trend-name">{trend.trend_name}</span>
                        <span className="trend-impact">{trend.impact}</span>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </div>

            <div className="grid-col span-1">
              <div className="col-header">
                <h3>内部映射与战略 (Internal & Strategy)</h3>
                <p>组织能力盘点与最终执行建议</p>
              </div>
              <div className="col-body">
                <div className="intel-section">
                  <h4 className="section-subtitle"><Database size={14}/> 企业资产映射</h4>
                  <div className="assets-list">
                    {insightData.internal_assets.map((asset, idx) => (
                      <div key={idx} className="asset-card">
                        <div className="asset-name">{asset.asset_name}</div>
                        <div className="asset-relevance">{asset.relevance}</div>
                      </div>
                    ))}
                  </div>
                </div>

                <div className="intel-section summary-section">
                  <h4 className="section-subtitle"><Zap size={14}/> 战略洞察执行摘要</h4>
                  <div className={`insight-summary-card ${phase === 1 ? 'pulsing' : ''}`}>
                    <FileText size={24} className="summary-icon" />
                    <p>{insightData.insight_summary}</p>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
