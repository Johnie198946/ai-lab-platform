import React, { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Link } from 'react-router-dom';
import { ArrowLeft, MessageSquare, Mail, Bell, Languages, ArrowRight, CheckCircle, Search, Loader } from 'lucide-react';
import { useAuth } from '../auth/AuthContext';
import { useOrchestration } from '../hooks/useOrchestration';
import { generateRoleWorkflow } from '../services/orchestrationService';
import './RoleSales.css';

export default function RoleSales() {
  const { sessionScopeKey } = useAuth();
  const { sessionMeta, input } = useOrchestration({ scopeKey: sessionScopeKey });

  const [phase, setPhase] = useState(-1); // -1: fetching, 0: fetched
  const [view, setView] = useState('feishu'); // 'feishu' | 'email'
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
      const res = await generateRoleWorkflow(sessionMeta.sessionId, "sales", goal);
        if (res && res.details && res.details.length >= 2) {
          setSalesDetails({
            pushContent: res.details[0] || "【上新通知】营销资料包已发布！",
            emailSubject: res.tasks ? res.tasks[1] : "客户咨询",
            emailBody: res.details[1] || "请查收您的营销资料..."
          });
        }
      } catch (err) {
        console.error("fetchWorkflow err", err);
      } finally {
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

  const handleSendEmail = () => {
    setEmailStatus('sent');
    setTimeout(() => {
      setEmailStatus('inbox');
    }, 3000);
  };

  if (phase === -1) {
    return (
      <div className="role-sales-container" style={{display: 'flex', justifyContent: 'center', alignItems: 'center', color: '#fff'}}>
        <Loader className="spin" size={48} />
        <span style={{marginLeft: 16}}>正在连接 Hermes Main Agent 规划工作流...</span>
      </div>
    );
  }

  return (
    <div className="role-sales-container">
      <Link to="/orchestration" className="back-button">
        <ArrowLeft size={16} /> 查看其他人的工作
      </Link>

      <div className="sales-content">
        <motion.div 
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="header-section"
        >
          <h1>销售经理</h1>
          <p>接收内部营销物料推送，并通过邮件直接触达客户，实现一键翻译与智能回复。</p>
        </motion.div>

        <div className="sales-layout">
          <div className="sales-sidebar">
            <button className={`nav-btn ${view === 'feishu' ? 'active' : ''}`} onClick={() => setView('feishu')}>
              <Bell size={18} /> 飞书营销推送
            </button>
            <button className={`nav-btn ${view === 'email' ? 'active' : ''}`} onClick={() => setView('email')}>
              <Mail size={18} /> 客户邮件沟通
            </button>
          </div>

          <div className="sales-main">
            <AnimatePresence mode="wait">
              {view === 'feishu' && (
                <motion.div 
                  key="feishu"
                  initial={{ opacity: 0, x: 20 }}
                  animate={{ opacity: 1, x: 0 }}
                  exit={{ opacity: 0, x: -20 }}
                  className="feishu-panel"
                >
                  <div className="feishu-header">
                    <MessageSquare size={24} color="#0066ff" />
                    <h2>飞书消息 - 营销赋能</h2>
                  </div>
                  <div className="feishu-chat">
                    <div className="feishu-bubble system">
                      <div className="bubble-header">营销知识库小助手</div>
                      <div className="bubble-content">
                        <p>📢 <strong>{salesDetails.pushContent}</strong></p>
                        <p>各位一线将士，最新产品的完整营销弹药包已为您准备就绪：</p>
                        <div className="material-list">
                          <div className="material-item">📄 AI智能体编排_一指禅.pdf</div>
                          <div className="material-item">📊 AI智能体编排_主打胶片.pptx</div>
                          <div className="material-item">💬 销售标准话术与Q&A.docx</div>
                        </div>
                        <p>祝大家开单顺利！🔥</p>
                        <button className="feishu-action-btn" onClick={() => setView('email')}>
                          <Mail size={16} /> 一键触达客户
                        </button>
                      </div>
                    </div>
                  </div>
                </motion.div>
              )}

              {view === 'email' && (
                <motion.div 
                  key="email"
                  initial={{ opacity: 0, x: 20 }}
                  animate={{ opacity: 1, x: 0 }}
                  exit={{ opacity: 0, x: -20 }}
                  className="email-panel"
                >
                  <div className="email-header">
                    <h2>邮件工作台</h2>
                    <div className="search-bar">
                      <Search size={16} />
                      <input type="text" placeholder="搜索邮件..." />
                    </div>
                  </div>

                  {emailStatus === 'inbox' && (
                    <div className="email-inbox">
                      <div className="email-item unread" onClick={() => setEmailStatus('compose')}>
                        <div className="email-sender">David Smith (CTO)</div>
                        <div className="email-subject">{salesDetails.emailSubject}</div>
                        <div className="email-time">10:42 AM</div>
                      </div>
                      <div className="email-item">
                        <div className="email-sender">Jane Doe</div>
                        <div className="email-subject">Re: Partnership opportunity</div>
                        <div className="email-time">Yesterday</div>
                      </div>
                    </div>
                  )}

                  {emailStatus === 'compose' && (
                    <div className="email-compose">
                      <div className="email-toolbar">
                        <button className="back-btn" onClick={() => setEmailStatus('inbox')}>
                          <ArrowLeft size={16} /> 返回
                        </button>
                        <button className="translate-btn" onClick={() => setTranslation(!translation)}>
                          <Languages size={16} /> 一键翻译与总结
                        </button>
                      </div>

                      <div className="email-thread">
                        <div className="incoming-email">
                          <div className="email-meta">
                            <span>From: David Smith (CTO)</span>
                            <span>To: me</span>
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
                                <h4>🤖 AI 翻译与总结</h4>
                                <p><strong>翻译：</strong>团队你好，我们正在评估几个用于内部工作流自动化的AI平台。我看到了你们最近关于新AI编排平台的公告。你能否提供更多关于它如何处理多智能体协作的细节，以及我们在第一季度可以预期的典型ROI？期待您的回复。David</p>
                                <p><strong>总结：</strong>客户 (CTO) 对新产品感兴趣，核心关注点为：1. 多智能体协作机制 2. 第一季度的投资回报率 (ROI)。</p>
                                <p><strong>推荐回复：</strong>已自动为您生成包含一指禅附件的专业回复。</p>
                              </motion.div>
                            )}
                          </AnimatePresence>
                        </div>

                        <div className="reply-box">
                          <div className="reply-header">Reply to David Smith</div>
                          <textarea 
                            className="reply-input" 
                            defaultValue={translation ? "Dear David,\n\nThank you for reaching out. Our AI Orchestration Platform is designed specifically to solve complex enterprise workflows through dynamic multi-agent collaboration. By routing tasks to specialized agents (e.g., Insight, Product, Engineering), we eliminate redundant compute overhead.\n\nRegarding ROI, our early adopters typically see a 60% reduction in time-to-market and a break-even within the first 2 months.\n\nI have attached our One-Pager and Pitch Deck for your reference. Would you be available for a 15-minute demo next Tuesday?\n\nBest regards,\nSales Manager" : ""}
                            placeholder="Type your reply here..."
                          ></textarea>
                          <div className="reply-actions">
                            <div className="attachments">
                              <span className="attachment-tag">AI智能体编排_一指禅.pdf</span>
                              <span className="attachment-tag">AI智能体编排_主打胶片.pptx</span>
                            </div>
                            <button className="send-btn" onClick={handleSendEmail}>
                              发送 <ArrowRight size={16} />
                            </button>
                          </div>
                        </div>
                      </div>
                    </div>
                  )}

                  {emailStatus === 'sent' && (
                    <motion.div 
                      initial={{ opacity: 0, scale: 0.95 }}
                      animate={{ opacity: 1, scale: 1 }}
                      className="sent-success"
                    >
                      <CheckCircle size={64} color="#00cc66" />
                      <h2>邮件发送成功</h2>
                      <p>营销物料已成功触达客户，系统将自动跟进后续状态。</p>
                    </motion.div>
                  )}
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        </div>
      </div>
    </div>
  );
}
