import React, { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Link } from 'react-router-dom';
import { ArrowLeft, MessageSquare, Mail, Bell, Languages, Users, Search, Loader } from 'lucide-react';
import { useAuth } from '../auth/AuthContext';
import { useOrchestration } from '../hooks/useOrchestration';
import { generateRoleWorkflow } from '../services/orchestrationService';
import './RoleSales.css';

export default function RoleSales() {
  const { sessionScopeKey } = useAuth();
  const { sessionMeta, input } = useOrchestration({ scopeKey: sessionScopeKey });

  const [phase, setPhase] = useState(0); // 0: blocked, 1: generating, 2: done
  const [emailStatus, setEmailStatus] = useState('inbox'); // 'inbox' | 'compose' | 'sent'
  const [translation, setTranslation] = useState(false);

  const [salesDetails, setSalesDetails] = useState({
    pushContent: "【上新通知】AI智能体编排平台 上市资料包已发布！",
    emailSubject: "Inquiry about your new AI Orchestration Platform",
    emailBody: "I heard you guys are releasing a new AI platform. Could you share some details and the main slides?"
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
        const res = await generateRoleWorkflow(sessionMeta.sessionId, "sales", goal);
        
        if (res && res.details && res.details.length >= 2) {
          setSalesDetails({
            pushContent: res.details[0] || "【上新通知】营销资料包已发布！",
            emailSubject: res.tasks ? res.tasks[1] : "客户咨询",
            emailBody: res.details[1] || "请查收您的营销资料..."
          });
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
      }, 3000);
      return () => clearTimeout(t);
    }
  }, [phase]);

  const handleSendEmail = () => {
    setEmailStatus('sent');
    setTimeout(() => {
      setEmailStatus('inbox');
    }, 3000);
  };

  const handleMockTrigger = () => {
    if (phase === 0) setPhase(1);
  };

  return (
    <div className="role-sales-container">
      <Link to="/orchestration" className="back-button">
        <ArrowLeft size={16} /> 返回 overview
      </Link>

      <div className="sales-content">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className={`bespoke-header ${phase >= 1 ? 'is-ready' : ''}`}
        >
          <span className="role-tag">销售经理</span>
          {phase === 0 ? (
            <>
              <h1>正在等待营销物料与市场通稿，销售 CRM 拓客处于 blocked 状态。</h1>
              <p>当前工作台已预置飞书推送监听与客户 CRM 通讯录。销售团队在此阶段不进行盲目外呼，而是等待上游核心卖点、价格体系与宣传物料的完整抵达。</p>
            </>
          ) : phase === 1 ? (
            <>
              <h1>销售经理已接收最新营销资料包，正在同步 CRM 客户线索。</h1>
              <p>系统正根据产品的核心价值主张（Value Proposition）在 CRM 库中筛选匹配的潜在客户（Leads），并生成第一轮触达话术。</p>
            </>
          ) : (
            <>
              <h1>线索匹配完毕，一键触达通道已开启。</h1>
              <p>飞书内部知识库已更新。您可以直接向精准客户群发推介邮件，或使用 AI 翻译助手处理跨国业务咨询，最终可前往 Boss 战情室汇报。</p>
            </>
          )}

          <div className="status-pills">
            <div className="pill-row">
              <span className={`status-pill ${phase > 0 ? 'done' : 'waiting'}`}>营销物料 {phase > 0 ? 'DONE' : 'WAITING'}</span>
              <span className={`status-pill ${phase === 2 ? 'done' : phase === 1 ? 'active' : 'waiting'}`}>CRM 线索 {phase === 2 ? 'DONE' : phase === 1 ? 'SYNCING' : 'BLOCKED'}</span>
              <span className={`status-pill ${phase === 2 ? 'done' : phase === 1 ? 'active' : 'waiting'}`}>邮件触达 {phase === 2 ? 'DONE' : phase === 1 ? 'PREPARING' : 'BLOCKED'}</span>
            </div>
            <span className="status-hint">{phase === 0 ? '准备接收物料' : phase === 1 ? '同步中...' : '流程完成'}</span>
          </div>
        </motion.div>

        <div className="workspace-section">
          <div className="workspace-header">
            <div className="ws-title-area">
              <span className="ws-tag">INTERNAL PUSH + CRM + OUTREACH</span>
              <h2>销售工作台</h2>
              <p>三列式布局：内部飞书知识库通知、CRM 高意向客户线索池、客户邮件通讯客户端。</p>
            </div>
            {phase === 0 && (
              <button className="mock-btn" onClick={handleMockTrigger}>模拟营销完成</button>
            )}
          </div>

          <div className="bespoke-grid">
            <div className="grid-col">
              <div className="col-header">
                <h3>飞书内部推送 (Lark)</h3>
                <p>获取最新产品资料与卖点培训</p>
              </div>
              <div className={`col-body ${phase === 0 ? 'empty-state' : ''}`}>
                {phase === 0 ? "等待输入数据" : (
                  <div className="feishu-chat">
                    <div className="feishu-bubble system">
                      <div className="bubble-header"><Bell size={12}/> 营销知识库小助手</div>
                      <div className="bubble-content">
                        <p>📢 <strong>{salesDetails.pushContent}</strong></p>
                        <p>各位一线将士，最新产品的完整营销弹药包已为您准备就绪：</p>
                        <div className="material-list">
                          <div className="material-item">📄 产品核心一指禅.pdf</div>
                          <div className="material-item">📊 客户演示主打胶片.pptx</div>
                          <div className="material-item">💬 销售标准话术与Q&A.docx</div>
                        </div>
                        <p>祝大家开单顺利！🔥</p>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            </div>

            <div className="grid-col">
              <div className="col-header">
                <h3>CRM 客户线索 (Leads)</h3>
                <p>智能筛选的高意向潜在客户</p>
              </div>
              <div className={`col-body ${phase === 0 ? 'empty-state' : ''}`}>
                {phase === 0 ? "等待生成" : (
                  <div className="crm-list">
                    {phase === 1 && <div className="loading-text">正在从 10,000+ 库中检索匹配...</div>}
                    {phase === 2 && (
                      <>
                        <div className="crm-item high-intent">
                          <div className="crm-avatar"><Users size={16}/></div>
                          <div className="crm-info">
                            <strong>David Smith (CTO)</strong>
                            <span>TechCorp Inc. - 寻求降本增效</span>
                          </div>
                          <div className="crm-score">98分</div>
                        </div>
                        <div className="crm-item">
                          <div className="crm-avatar"><Users size={16}/></div>
                          <div className="crm-info">
                            <strong>Jane Doe (VP Product)</strong>
                            <span>Innovate LLC - 历史成单客户</span>
                          </div>
                          <div className="crm-score">85分</div>
                        </div>
                        <div className="crm-item">
                          <div className="crm-avatar"><Users size={16}/></div>
                          <div className="crm-info">
                            <strong>Michael Lee (CEO)</strong>
                            <span>Startup Co. - 刚刚融资</span>
                          </div>
                          <div className="crm-score">72分</div>
                        </div>
                      </>
                    )}
                  </div>
                )}
              </div>
            </div>

            <div className="grid-col">
              <div className="col-header">
                <h3>邮件触达 (Outreach)</h3>
                <p>带有 AI 辅助的客户沟通</p>
              </div>
              <div className={`col-body ${phase === 0 ? 'empty-state' : ''}`} style={{padding: 0}}>
                {phase === 0 ? <div style={{padding: 24, textAlign: 'center', color: '#bbb'}}>等待生成</div> : (
                  <div className="email-client">
                    {emailStatus === 'inbox' && (
                      <div className="email-inbox">
                        <div className="email-item unread" onClick={() => setEmailStatus('compose')}>
                          <div className="email-sender">David Smith</div>
                          <div className="email-subject">{salesDetails.emailSubject}</div>
                        </div>
                      </div>
                    )}

                    {emailStatus === 'compose' && (
                      <div className="email-compose">
                        <div className="email-toolbar">
                          <button className="back-btn" onClick={() => setEmailStatus('inbox')}>
                            <ArrowLeft size={14} /> 返回
                          </button>
                          <button className="translate-btn" onClick={() => setTranslation(!translation)}>
                            <Languages size={14} /> AI 翻译
                          </button>
                        </div>
                        <div className="email-thread">
                          <div className="email-meta">
                            <span>From: David Smith</span>
                          </div>
                          <p>{salesDetails.emailBody}</p>

                          <AnimatePresence>
                            {translation && (
                              <motion.div 
                                initial={{ opacity: 0, height: 0 }}
                                animate={{ opacity: 1, height: 'auto' }}
                                exit={{ opacity: 0, height: 0 }}
                                className="ai-translation-box"
                              >
                                <strong>AI 中文翻译：</strong>
                                <p>听说你们正在发布一个新的 AI 平台。能否分享一些详细信息和主要的演示胶片？</p>
                              </motion.div>
                            )}
                          </AnimatePresence>
                        </div>
                        <div className="email-reply">
                          <textarea placeholder="使用 AI 辅助撰写回复..." defaultValue={`Hi David,\n\nThanks for reaching out! Attached is our latest pitch deck.\n\nBest,\nSales Team`}></textarea>
                          <button className="send-btn" onClick={handleSendEmail}>发送邮件</button>
                        </div>
                      </div>
                    )}

                    {emailStatus === 'sent' && (
                      <div className="email-sent">
                        <div className="success-icon">✓</div>
                        <p>邮件发送成功</p>
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
