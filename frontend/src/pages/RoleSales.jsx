import React, { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Link } from 'react-router-dom';
import { ArrowLeft, Loader, Mail, Search, Tag, Clock, Building, Send, ChevronRight } from 'lucide-react';
import { useAuth } from '../auth/AuthContext';
import { useOrchestration } from '../hooks/useOrchestration';
import { generateRoleWorkflow } from '../services/orchestrationService';
import './RoleSales.css';

const DATA_REQUIREMENTS = `
{
  "emails": [
    {
      "id": "1",
      "sender": "客户姓名",
      "company": "客户公司",
      "time": "10:42 AM",
      "subject": "邮件标题",
      "tag": "高意向/需跟进",
      "original_body": "原始英文邮件内容",
      "translated_body": "翻译后的中文内容",
      "summary": "AI总结的邮件核心诉求",
      "reply_suggestion": "AI生成的建议回复话术"
    }
  ],
  "advisor_message": "数字人顾问的一句话简短建议"
}
`;

export default function RoleSales() {
  const { sessionScopeKey } = useAuth();
  const { sessionMeta, input } = useOrchestration({ scopeKey: sessionScopeKey });

  const [phase, setPhase] = useState(-1);
  const [data, setData] = useState(null);
  const [selectedEmailId, setSelectedEmailId] = useState(null);
  const [activeTab, setActiveTab] = useState('original'); // original, translation, summary, reply

  useEffect(() => {
    async function fetchWorkflow() {
      try {
        const goal = sessionMeta.goal || input || "处理客户邮件";
        const res = await generateRoleWorkflow(sessionMeta.sessionId, "sales", goal, DATA_REQUIREMENTS);
        if (res) {
          setData(res);
          if (res.emails && res.emails.length > 0) {
            setSelectedEmailId(res.emails[0].id);
          }
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
      <div className="role-sales-container loading">
        <Loader className="spin" size={48} />
        <span>正在连接 Hermes Main Agent 获取邮件处理流水线...</span>
      </div>
    );
  }

  const emails = data.emails || [];
  const selectedEmail = emails.find(e => e.id === selectedEmailId) || emails[0];

  return (
    <div className="role-sales-container">
      <nav className="sales-nav">
        <Link to="/orchestration" className="back-button">
          <ArrowLeft size={18} /> 返回编排台
        </Link>
        <div className="nav-title">销售经理 (Sales) - 智能邮件终端</div>
      </nav>

      <main className="sales-main">
        <div className="email-client">
          {/* Left: Email List */}
          <div className="email-sidebar">
            <div className="sidebar-header">
              <h2>收件箱 (Inbox)</h2>
              <div className="search-box">
                <Search size={14} />
                <input type="text" placeholder="搜索邮件..." />
              </div>
            </div>
            <div className="email-list">
              {emails.map((email) => (
                <div 
                  key={email.id} 
                  className={\`email-item \${selectedEmailId === email.id ? 'active' : ''}\`}
                  onClick={() => setSelectedEmailId(email.id)}
                >
                  <div className="item-top">
                    <span className="sender">{email.sender}</span>
                    <span className="time">{email.time}</span>
                  </div>
                  <div className="item-subject">{email.subject}</div>
                  <div className="item-meta">
                    <span className="company"><Building size={12} /> {email.company}</span>
                    <span className="tag"><Tag size={12} /> {email.tag}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Right: Email Processing Panel */}
          <div className="email-content">
            {selectedEmail ? (
              <>
                <div className="content-header">
                  <div className="header-info">
                    <h2>{selectedEmail.subject}</h2>
                    <div className="sender-details">
                      <div className="avatar">{selectedEmail.sender.charAt(0)}</div>
                      <div className="details">
                        <span className="name">{selectedEmail.sender}</span>
                        <span className="org">{selectedEmail.company}</span>
                      </div>
                    </div>
                  </div>
                </div>

                <div className="processing-panel">
                  <div className="tabs">
                    <button className={\`tab \${activeTab === 'original' ? 'active' : ''}\`} onClick={() => setActiveTab('original')}>原始邮件</button>
                    <button className={\`tab \${activeTab === 'translation' ? 'active' : ''}\`} onClick={() => setActiveTab('translation')}>AI 翻译</button>
                    <button className={\`tab \${activeTab === 'summary' ? 'active' : ''}\`} onClick={() => setActiveTab('summary')}>AI 总结</button>
                    <button className={\`tab \${activeTab === 'reply' ? 'active' : ''}\`} onClick={() => setActiveTab('reply')}>AI 回复建议</button>
                  </div>

                  <div className="tab-content">
                    <AnimatePresence mode="wait">
                      {activeTab === 'original' && (
                        <motion.div key="original" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="text-content">
                          {selectedEmail.original_body}
                        </motion.div>
                      )}
                      {activeTab === 'translation' && (
                        <motion.div key="translation" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="text-content translated">
                          {selectedEmail.translated_body}
                        </motion.div>
                      )}
                      {activeTab === 'summary' && (
                        <motion.div key="summary" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="text-content summary">
                          <div className="ai-badge">✨ AI Summary</div>
                          <p>{selectedEmail.summary}</p>
                        </motion.div>
                      )}
                      {activeTab === 'reply' && (
                        <motion.div key="reply" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="reply-editor">
                          <div className="ai-badge">✨ AI Suggested Reply</div>
                          <textarea 
                            className="reply-textarea" 
                            defaultValue={selectedEmail.reply_suggestion}
                          />
                          <div className="reply-actions">
                            <button className="send-btn">
                              <Send size={16} /> 发送回复
                            </button>
                          </div>
                        </motion.div>
                      )}
                    </AnimatePresence>
                  </div>
                </div>
              </>
            ) : (
              <div className="empty-state">
                <Mail size={48} />
                <p>请选择一封邮件进行处理</p>
              </div>
            )}
          </div>
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
          <img src="/assets/portrait-sales.jpg" alt="Advisor" onError={(e) => { e.target.onerror = null; e.target.src = "https://via.placeholder.com/48"; }} />
        </div>
        <div className="advisor-bubble">
          {data.advisor_message || "我已经为您分析了最新的客户邮件，请查看高意向客户。"}
        </div>
      </motion.div>
    </div>
  );
}
