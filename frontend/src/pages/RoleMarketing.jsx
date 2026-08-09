import React, { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Link } from 'react-router-dom';
import { ArrowLeft, Lightbulb, LayoutTemplate, Users, Send, CheckCircle, Loader } from 'lucide-react';
import { useAuth } from '../auth/AuthContext';
import { useOrchestration } from '../hooks/useOrchestration';
import { generateRoleWorkflow } from '../services/orchestrationService';
import './RoleMarketing.css';

export default function RoleMarketing() {
  const { sessionScopeKey } = useAuth();
  const { sessionMeta, input } = useOrchestration({ scopeKey: sessionScopeKey });

  const [phase, setPhase] = useState(0); // 0: input, 1: creation, 2: review, 3: publish, 4: done
  const [marketingTasks, setMarketingTasks] = useState([]);
  
  // Creation state
  const [creationProgress, setCreationProgress] = useState(0);
  
  // Review state
  const [reviewNodes, setReviewNodes] = useState([
    { id: 1, role: "产品经理", status: "pending" },
    { id: 2, role: "市场代表", status: "pending" },
    { id: 3, role: "研发代表", status: "pending" },
    { id: 4, role: "产品主管", status: "pending" },
    { id: 5, role: "SPDT经理", status: "pending" }
  ]);
  
  useEffect(() => {
    async function fetchWorkflow() {
      try {
        if (!sessionMeta.sessionId) return;
        const goal = sessionMeta.goal || input;
        if (!goal || !goal.trim()) {
          setPhase(4);
          return;
        }
        
        const res = await generateRoleWorkflow(sessionMeta.sessionId, "marketing", goal);
        if (res && res.tasks) {
          setMarketingTasks(res.tasks);
        } else {
          setMarketingTasks(["收集产品原型图", "分析产品特性", "提炼产品卖点", "生成营销文案"]);
        }
      } catch (err) {
        console.error(err);
      }
    }
    fetchWorkflow();
  }, [sessionMeta.sessionId]);

  const startCreation = () => {
    setPhase(1);
    let start = Date.now();
    const duration = 6000;
    const interval = setInterval(() => {
      let p = Math.min(100, ((Date.now() - start) / duration) * 100);
      setCreationProgress(p);
      if (p >= 100) {
        clearInterval(interval);
        setPhase(2);
      }
    }, 100);
  };

  const startReview = () => {
    setPhase(2);
    let index = 0;
    const interval = setInterval(() => {
      setReviewNodes(prev => prev.map((node, i) => i === index ? { ...node, status: "approved" } : node));
      index++;
      if (index >= 5) {
        clearInterval(interval);
        setTimeout(() => setPhase(3), 500);
      }
    }, 1200);
  };

  const startPublish = () => {
    setPhase(4);
  };

  return (
    <div className="role-marketing-container">
      <Link to="/orchestration" className="back-button">
        <ArrowLeft size={16} /> 返回 overview
      </Link>

      <div className="marketing-content">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className={`bespoke-header ${phase >= 4 ? 'is-ready' : ''}`}
        >
          <span className="role-tag">营销经理</span>
          {phase === 0 ? (
            <>
              <h1>等待开始并行产出营销材料，PRD 与原型输入已就绪。</h1>
              <p>当前工作台已预置营销策略映射、官网专题页与销售摘要板位。确认需求后，系统将并行生成多维度对外材料。</p>
            </>
          ) : phase === 1 ? (
            <>
              <h1>正在并行产出营销材料，等待收口进行 MOR 评审。</h1>
              <p>系统正并行处理官网专题页、公众号软文、一指禅销售摘要与主视觉，产出进度将实时映射至工作台。</p>
            </>
          ) : phase === 2 ? (
            <>
              <h1>进入 MOR 评审阶段，法务及各节点代表正在校验。</h1>
              <p>内容生成完毕，系统自动分发至五大节点进行合规与一致性校验。评审通过后即刻进入发布准备期。</p>
            </>
          ) : phase === 3 ? (
            <>
              <h1>评审已通过，进入发布准备阶段。</h1>
              <p>所有对外材料已冻结版本，请进行最终的渠道分发配置与一键发布确认。</p>
            </>
          ) : (
            <>
              <h1>发布已完成，营销生命周期闭环。</h1>
              <p>各类营销资产已成功推送至知识库、全员大群及外部渠道，可前往老板战情室查看当前放行状态。</p>
            </>
          )}

          <div className="status-pills">
            <div className="pill-row">
              <span className={`status-pill ${phase > 0 ? 'done' : phase === 0 ? 'active' : 'waiting'}`}>并行产出 {phase > 0 ? 'DONE' : phase === 0 ? 'READY' : 'WAITING'}</span>
              <span className={`status-pill ${phase > 2 ? 'done' : phase === 2 ? 'active' : phase < 2 ? 'waiting' : ''}`}>MOR评审 {phase > 2 ? 'DONE' : phase === 2 ? 'REVIEWING' : 'BLOCKED'}</span>
              <span className={`status-pill ${phase === 4 ? 'done' : phase === 3 ? 'active' : phase < 3 ? 'waiting' : ''}`}>发布准备 {phase === 4 ? 'DONE' : phase === 3 ? 'READY' : 'BLOCKED'}</span>
            </div>
            <span className="status-hint">{phase === 0 ? '等待手动启动' : phase === 4 ? '流程完成' : '执行中...'}</span>
          </div>
        </motion.div>

        {/* Workspace */}
        <div className="workspace-section">
          <div className="workspace-header">
            <div className="ws-title-area">
              <span className="ws-tag">PARALLEL-CREATION + MOR-REVIEW</span>
              <h2>营销工作流大盘</h2>
              <p>四类核心材料并发推进，集成 MOR (Marketing Operations Review) 五级审批放行。</p>
            </div>
          </div>

          <div className="bespoke-grid">
            {/* Column 1: 并行产出 */}
            <div className="grid-col">
              <div className="col-header">
                <h3>1. 并行产出推进</h3>
                <p>官网、社媒、摘要与主视觉</p>
              </div>
              <div className="col-body">
                {phase === 0 ? (
                  <div style={{ textAlign: 'center', paddingTop: 40 }}>
                    <p style={{ color: '#666', marginBottom: 20 }}>输入依赖已满足，可启动生成</p>
                    <button className="primary-btn" onClick={startCreation}>启动并行创作</button>
                  </div>
                ) : (
                  <div>
                    <div className="creation-card">
                      <h4>官网专题页 & 软文</h4>
                      <div className="progress-container">
                        <div className="progress-bar" style={{width: `${creationProgress}%`}}></div>
                      </div>
                      <div className="details">
                        <span>文案与结构</span>
                        <span>{Math.floor(creationProgress)}%</span>
                      </div>
                    </div>
                    <div className="creation-card">
                      <h4>一指禅销售摘要</h4>
                      <div className="progress-container">
                        <div className="progress-bar" style={{width: `${Math.max(0, creationProgress - 10)}%`}}></div>
                      </div>
                      <div className="details">
                        <span>卖点提炼</span>
                        <span>{Math.floor(Math.max(0, creationProgress - 10))}%</span>
                      </div>
                    </div>
                    <div className="creation-card">
                      <h4>产品主视觉图 (KV)</h4>
                      <div className="progress-container">
                        <div className="progress-bar" style={{width: `${Math.max(0, creationProgress - 20)}%`}}></div>
                      </div>
                      <div className="details">
                        <span>Midjourney 生成中</span>
                        <span>{Math.floor(Math.max(0, creationProgress - 20))}%</span>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            </div>

            {/* Column 2: MOR 评审 */}
            <div className="grid-col">
              <div className="col-header">
                <h3>2. MOR 评审收口</h3>
                <p>多节点合规与质量把控</p>
              </div>
              <div className={`col-body ${phase < 2 ? 'empty-state' : ''}`}>
                {phase < 2 ? (
                  phase === 1 ? "等待材料生成完成..." : "前置任务未完成"
                ) : (
                  <div>
                    {phase === 2 && reviewNodes[0].status === 'pending' && (
                      <div style={{ textAlign: 'center', marginBottom: 20 }}>
                        <button className="primary-btn" onClick={startReview}>发起 MOR 评审</button>
                      </div>
                    )}
                    {reviewNodes.map(node => (
                      <div key={node.id} className={`review-node ${node.status === 'approved' ? 'approved' : ''}`}>
                        <div className="node-icon">
                          {node.status === 'approved' ? <CheckCircle size={16} /> : <Loader size={16} className={phase === 2 && reviewNodes.find(n => n.status === 'pending')?.id === node.id ? "spin" : ""} />}
                        </div>
                        <div className="node-info">
                          <h4>{node.role}</h4>
                          <span>{node.status === 'approved' ? '已同意放行' : '等待校验'}</span>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>

            {/* Column 3: 发布准备 */}
            <div className="grid-col">
              <div className="col-header">
                <h3>3. 发布准备与触达</h3>
                <p>知识库、全员群与客户邮件</p>
              </div>
              <div className={`col-body ${phase < 3 ? 'empty-state' : ''}`}>
                {phase < 3 ? (
                  "需通过 MOR 评审后解锁"
                ) : (
                  <div>
                    <div className="pub-card">
                      <h4>企业知识库 (KM)</h4>
                      <p>将销售一指禅归档至销售赋能专区</p>
                    </div>
                    <div className="pub-card">
                      <h4>飞书全员大群</h4>
                      <p>推送新版本上线与官网更新通知</p>
                    </div>
                    <div className="pub-card">
                      <h4>客户营销邮件 (EDM)</h4>
                      <p>生成邮件模板并准备推送至高意向客户库</p>
                    </div>
                    
                    {phase === 3 && (
                      <div style={{ textAlign: 'center', marginTop: 24 }}>
                        <button className="primary-btn" onClick={startPublish} style={{width: '100%', justifyContent: 'center'}}>
                          一键执行发布
                        </button>
                      </div>
                    )}
                    {phase === 4 && (
                      <div style={{ textAlign: 'center', marginTop: 24, color: '#34C759', fontWeight: 600 }}>
                        <CheckCircle size={32} style={{marginBottom: 8}} />
                        <div>发布流已完成</div>
                      </div>
                    )}
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Floating AI Assistant */}
      <div className="ai-assistant-card" style={{position: 'fixed', right: 40, bottom: 40, background: 'rgba(255,255,255,0.8)', backdropFilter: 'blur(12px)', border: '1px solid #eaeaea', borderRadius: 16, padding: 16, display: 'flex', alignItems: 'center', gap: 16, boxShadow: '0 12px 32px rgba(0,0,0,0.08)', cursor: 'pointer'}}>
        <div className="ai-icon-wrap" style={{width: 40, height: 40, borderRadius: 10, background: '#f0f0f0', display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 600, color: '#555', fontSize: 14}}>AI</div>
        <div className="ai-info">
          <h4 style={{margin: '0 0 4px 0', fontSize: 14, fontWeight: 600}}>营销数字人</h4>
          <p style={{margin: 0, fontSize: 12, color: '#888'}}>右侧入口 • 点击对话</p>
        </div>
      </div>
    </div>
  );
}
