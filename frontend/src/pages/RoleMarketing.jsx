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

  const [phase, setPhase] = useState(-1); // -1: fetching, 0: fetched
  const [step, setStep] = useState('inspiration'); // inspiration, creation, review, publish, done
  
  const [marketingTasks, setMarketingTasks] = useState(["收集产品原型图", "分析产品特性", "提炼产品卖点", "生成营销文案"]);

  // Inspiration state
  const [inspConfirmed, setInspConfirmed] = useState(false);

  // Creation state
  const [creationProgress, setCreationProgress] = useState(0);
  const [infoProgress, setInfoProgress] = useState(0);
  const [infoTarget, setInfoTarget] = useState("");
  
  // Review state
  const [reviewNodes, setReviewNodes] = useState([
    { id: 1, role: "产品经理", status: "pending" },
    { id: 2, role: "市场代表", status: "pending" },
    { id: 3, role: "研发代表", status: "pending" },
    { id: 4, role: "产品主管", status: "pending" },
    { id: 5, role: "SPDT经理", status: "pending" }
  ]);
  const [reviewing, setReviewing] = useState(false);

  // Publish state
  const [publishing, setPublishing] = useState(false);

  useEffect(() => {
    async function fetchWorkflow() {
      try {
        // sessionMeta 尚未从 localStorage 恢复(首轮渲染/直达刷新), 保持 loading 等恢复
        if (!sessionMeta.sessionId) {
          return;
        }
        // 必须基于用户真实输入的需求执行, 不允许静默 fallback 到默认文案(2026-08-09 用户报告"两个进程")
        const goal = sessionMeta.goal || input;
        if (!goal || !goal.trim()) {
          setSummary("⚠️ 尚未收到用户需求。请先返回编排页, 输入你的业务目标后再进入本角色工作流。");
          setPhase(0);
          return;
        }
      const res = await generateRoleWorkflow(sessionMeta.sessionId, "marketing", goal);
        if (res && res.tasks && res.tasks.length > 0) {
          setMarketingTasks(res.tasks);
          if (res._cached) {
            setPhase(0);
            setStep('done');
            setCreationProgress(100);
            setInfoProgress(100);
            setReviewNodes(prev => prev.map(node => ({ ...node, status: 'approved' })));
          } else {
            setPhase(0);
          }
        }
      } catch (err) {
        console.error("fetchWorkflow err", err);
        setPhase(0);
      }
    }
    fetchWorkflow();
  }, [sessionMeta.sessionId, input]);

  // 兜底: 3 秒后仍未恢复 sessionId(无历史 session/直达页面) → 提示先回编排页, 避免永久 loading(2026-08-09)
  useEffect(() => {
    const t = setTimeout(() => {
      if (!sessionMeta.sessionId) {
        setSummary("⚠️ 未找到已编排的会话。请先返回编排页, 输入你的业务目标生成六角色后, 再进入本角色工作流。");
        setPhase(0);
      }
    }, 3000);
    return () => clearTimeout(t);
  }, [sessionMeta.sessionId]);

  // Phase 0: Wait for Market Insight
  useEffect(() => {
    if (phase === 0 && step === 'creation') {
      let start = Date.now();
      
      // 15s info collection progress
      const infoInterval = setInterval(() => {
        let elapsed = Date.now() - start;
        let p = Math.min(100, (elapsed / 15000) * 100);
        setInfoProgress(p);
        
        let index = Math.floor((p / 100) * marketingTasks.length);
        if (index >= marketingTasks.length) index = marketingTasks.length - 1;
        setInfoTarget(marketingTasks[index] || "正在生成...");
        
        if (p >= 100) clearInterval(infoInterval);
      }, 100);

      // 60s total creation progress
      const createInterval = setInterval(() => {
        let elapsed = Date.now() - start;
        let p = Math.min(100, (elapsed / 60000) * 100);
        setCreationProgress(p);
        
        if (p >= 100) {
          clearInterval(createInterval);
          setStep('review');
        }
      }, 1000); // update less frequently for the long one

      return () => {
        clearInterval(infoInterval);
        clearInterval(createInterval);
      };
    }
  }, [phase, step, marketingTasks]);

  const handleConfirmInspiration = () => {
    setInspConfirmed(true);
    setTimeout(() => setStep('creation'), 500);
  };

  const handleStartReview = () => {
    setReviewing(true);
    let current = 0;
    const interval = setInterval(() => {
      if (current < reviewNodes.length) {
        setReviewNodes(prev => prev.map((node, i) => 
          i === current ? { ...node, status: 'approved' } : node
        ));
        current++;
      } else {
        clearInterval(interval);
        setTimeout(() => setStep('publish'), 1000);
      }
    }, 1500);
  };

  const handlePublish = () => {
    setPublishing(true);
    setTimeout(() => {
      setPublishing(false);
      setStep('done');
    }, 3000);
  };

  if (phase === -1) {
    return (
      <div className="role-marketing-container" style={{display: 'flex', justifyContent: 'center', alignItems: 'center', color: '#fff'}}>
        <Loader className="spin" size={48} />
        <span style={{marginLeft: 16}}>正在连接 Hermes Main Agent 规划工作流...</span>
      </div>
    );
  }

  return (
    <div className="role-marketing-container">
      <Link to="/orchestration" className="back-button">
        <ArrowLeft size={16} /> 查看其他人的工作
      </Link>

      <div className="marketing-content">
        <motion.div 
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="header-section"
        >
          <h1>营销经理</h1>
          <p>基于产品PRD与市场洞察，端到端完成超聚变风格营销物料的创作、评审与发布。</p>
        </motion.div>

        <div className="workflow-stepper">
          {['inspiration', 'creation', 'review', 'publish', 'done'].map((s, i) => {
            const labels = ["灵感创作", "材料创作", "MOR评审", "材料发布", "完成"];
            const isActive = step === s;
            const isPast = ['inspiration', 'creation', 'review', 'publish', 'done'].indexOf(step) > i;
            return (
              <div key={s} className={`step-indicator ${isActive ? 'active' : ''} ${isPast ? 'past' : ''}`}>
                <div className="step-circle">{isPast ? <CheckCircle size={16} /> : i + 1}</div>
                <span>{labels[i]}</span>
                {i < 4 && <div className="step-line" />}
              </div>
            );
          })}
        </div>

        <div className="step-content-area">
          <AnimatePresence mode="wait">
            {step === 'inspiration' && (
              <motion.div 
                key="insp"
                initial={{ opacity: 0, x: 20 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: -20 }}
                className="step-panel"
              >
                <div className="panel-header">
                  <Lightbulb className="icon" />
                  <h2>一键灵感创作初稿</h2>
                </div>
                <div className="cards-grid">
                  <div className="info-card">
                    <h4>超聚变风格描述</h4>
                    <p>科技感、企业级、红色与深空灰主色调，强调算力底座与稳定可靠。</p>
                  </div>
                  <div className="info-card">
                    <h4>研发物料有哪些</h4>
                    <p>API接口文档、系统架构图、算力调度模型说明、硬件选型报告。</p>
                  </div>
                  <div className="info-card">
                    <h4>特性与卖点</h4>
                    <p>极致性能、安全合规、端到端自动化、开箱即用的AI引擎。</p>
                  </div>
                  <div className="info-card">
                    <h4>上市物料分类</h4>
                    <p>主打胶片、一指禅、产品规格书、新闻通稿、销售话术卡。</p>
                  </div>
                </div>
                <div className="action-row">
                  <p>请确认是否按照以上思路进行后续材料创作？</p>
                  <button className="primary-btn" onClick={handleConfirmInspiration} disabled={inspConfirmed}>
                    {inspConfirmed ? '已确认' : '确认并开始创作'}
                  </button>
                </div>
              </motion.div>
            )}

            {step === 'creation' && (
              <motion.div 
                key="create"
                initial={{ opacity: 0, x: 20 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: -20 }}
                className="step-panel"
              >
                <div className="panel-header">
                  <LayoutTemplate className="icon" />
                  <h2>材料并行创作中 (预计60秒)</h2>
                </div>
                
                <div className="creation-grid">
                  <div className="creation-card info-collection">
                    <h4>产品信息收集</h4>
                    <div className="progress-container">
                      <div className="progress-bar" style={{ width: `${infoProgress}%` }} />
                    </div>
                    <div className="details">
                      <span>{Math.floor(infoProgress)}%</span>
                      <span className="target">{infoTarget}</span>
                    </div>
                  </div>

                  {['主打胶片', '一指禅', '产品规格书'].map((item, idx) => (
                    <div key={item} className="creation-card">
                      <h4>{item}</h4>
                      <div className="progress-container">
                        {/* They all complete at 60s, maybe slightly offset visually */}
                        <div className="progress-bar" style={{ width: `${creationProgress}%` }} />
                      </div>
                      <div className="details">
                        <span>{Math.floor(creationProgress)}%</span>
                        <span className="target">AI生成中...</span>
                      </div>
                    </div>
                  ))}
                </div>
              </motion.div>
            )}

            {step === 'review' && (
              <motion.div 
                key="review"
                initial={{ opacity: 0, x: 20 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: -20 }}
                className="step-panel"
              >
                <div className="panel-header">
                  <Users className="icon" />
                  <h2>MOR 流程评审</h2>
                </div>
                <p className="desc-text">所有材料已生成完毕。现在将安排评审，并自动推送飞书和邮箱通知相关节点负责人。</p>
                
                <div className="review-nodes">
                  {reviewNodes.map(node => (
                    <div key={node.id} className={`review-node ${node.status}`}>
                      <div className="node-icon">
                        {node.status === 'approved' ? <CheckCircle /> : <Loader className={node.status === 'pending' && reviewing ? 'spin' : ''} />}
                      </div>
                      <div className="node-info">
                        <h4>{node.role}</h4>
                        <span>{node.status === 'approved' ? '已批准' : '待审批'}</span>
                      </div>
                    </div>
                  ))}
                </div>

                {!reviewing && (
                  <button className="primary-btn" onClick={handleStartReview}>
                    一键发起 MOR 评审
                  </button>
                )}
              </motion.div>
            )}

            {step === 'publish' && (
              <motion.div 
                key="publish"
                initial={{ opacity: 0, x: 20 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: -20 }}
                className="step-panel"
              >
                <div className="panel-header">
                  <Send className="icon" />
                  <h2>材料发布与一线宣贯</h2>
                </div>
                <p className="desc-text">MOR 评审已全部通过，准许发布。</p>
                
                <div className="publish-actions">
                  <div className="pub-card">
                    <h4>营销知识库</h4>
                    <p>将主打胶片、一指禅、产品规格书归档至公司 KM 库。</p>
                  </div>
                  <div className="pub-card">
                    <h4>飞书公众号</h4>
                    <p>生成宣贯图文，推送至全员。</p>
                  </div>
                  <div className="pub-card">
                    <h4>邮件通知</h4>
                    <p>将销售话术与资料包打包发送给每一位一线销售经理。</p>
                  </div>
                </div>

                <button className="primary-btn" onClick={handlePublish} disabled={publishing}>
                  {publishing ? <><Loader className="spin" size={16} /> 正在执行一键发布...</> : '一键执行发布'}
                </button>
              </motion.div>
            )}

            {step === 'done' && (
              <motion.div 
                key="done"
                initial={{ opacity: 0, scale: 0.95 }}
                animate={{ opacity: 1, scale: 1 }}
                className="step-panel done-panel"
              >
                <CheckCircle size={64} className="done-icon" />
                <h2>营销工作流全部完成</h2>
                <p>营销物料已成功发布，一线销售经理已收到弹药包，可以开始拓客打单。</p>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>
    </div>
  );
}
