import { useState, useRef, useEffect } from "react";
import { useAuth } from "../auth/AuthContext";
import { useOrchestration } from "../hooks/useOrchestration";
import { useNavigate } from "react-router-dom";
import TextType from "../components/TextType";
import SplitText from "../components/SplitText";
import Orb from "../components/Orb";
import BorderGlow from "../components/BorderGlow";
import ReactMarkdown from "react-markdown";
import "./Dashboard.css";
export function OrchestrationPage() {
  const { authSession, logout, sessionScopeKey } = useAuth();
  const navigate = useNavigate();
  const {
    input,
    roles,
    selectedRole,
    selectedRoleId,
    setInput,
    setSelectedRoleId,
    handleRoleFieldChange,
    submitPrompt,
    isThinking,
    messages,
    handleInputKeyDown,
    saveSelectedRole,
    saveState,
  } = useOrchestration({ scopeKey: sessionScopeKey });

  const [isModalOpen, setIsModalOpen] = useState(false);
  const [modalView, setModalView] = useState("form");
  const [selectedMarkdown, setSelectedMarkdown] = useState(null);

  const threadRef = useRef(null);

  useEffect(() => {
    if (threadRef.current) {
      threadRef.current.scrollTop = threadRef.current.scrollHeight;
    }
  }, [messages]);

  const handleCardClick = (roleKey) => {
    setSelectedRoleId(roleKey);
    setSelectedMarkdown(null);
    setIsModalOpen(true);
  };

  const handleMarkdownClick = (content) => {
    setSelectedMarkdown(content);
    setIsModalOpen(true);
  };

  const handleCloseModal = () => {
    setIsModalOpen(false);
    setSelectedMarkdown(null);
  };

  const handleNavigateToRole = (roleKey) => {
    navigate(`/role/${roleKey}`);
  };

  return (
    <main className="orch-overview-shell">
      <section className="orch-stage" aria-label="需求输入工作台">
        <header className="orch-stage-header">
          <div id="ai-conversation-workspace" aria-label="工作总结">
            <div className="orch-workspace-grid">
              <div className="orch-summary-copy" style={{ position: 'relative' }}>
                {messages.length > 0 && messages[messages.length - 1].role === 'assistant' && messages[messages.length - 1].isMarkdown ? (
                  <div style={{ height: '100%', display: 'flex', flexDirection: 'column', justifyContent: 'center' }}>
                    <BorderGlow onClick={() => handleMarkdownClick(messages[messages.length - 1].content)}>
                      <div style={{ padding: '20px' }}>
                        <h2 style={{ marginBottom: '16px', color: '#fff' }}>系统已生成方案内容</h2>
                        <p style={{ color: '#ccc', marginBottom: '24px' }}>点击此处查看详细 Markdown 大纲与执行细节。</p>
                        <div style={{ opacity: 0.6, fontSize: '14px', display: '-webkit-box', WebkitLineClamp: 10, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>
                          <ReactMarkdown>{messages[messages.length - 1].content}</ReactMarkdown>
                        </div>
                      </div>
                    </BorderGlow>
                  </div>
                ) : (
                  <>
                    <span className="orch-summary-kicker">工作总结</span>
                    <h1 className="orch-summary-title">
                      <TextType text="你好！今天又有什么新想法？" speed={100} />
                    </h1>
                    <div style={{ position: 'absolute', top: '140px', left: '20px' }}>
                      <Orb color="rgba(43, 129, 255, 0.25)" size={280} blur={50} speed={12} />
                      <Orb color="rgba(100, 200, 255, 0.2)" size={200} blur={40} speed={15} />
                    </div>
                  </>
                )}
              </div>
              <aside className="orch-dialog-shell" aria-label="通用场景对话框">
                <div className="orch-dialog-head">
                  <div>
                    <span className="orch-kicker">通用交互</span>
                    <strong>其他场景对话框</strong>
                    <p>除了“端到端完成营销和销售”这类预置链路，其他开放场景可先在这里完成需求理解、追问与文本化输出。</p>
                  </div>
                  <span className="orch-dialog-status">ready</span>
                </div>
                
                <section className="orch-dialog-thread" aria-live="polite" ref={threadRef}>
                  {messages.map((msg, index) => (
                    <div
                      key={msg.id}
                      className={`orch-dialog-bubble orch-dialog-bubble--${msg.role}`}
                    >
                      {msg.role === "assistant" ? (
                        <>
                          <span className="orch-dialog-kicker">系统回复</span>
                          <div>
                            {index === messages.length - 1 ? (
                              msg.isMarkdown ? "请参考左侧内容" : <SplitText text={msg.content} delay={30} />
                            ) : (
                              msg.isMarkdown ? "请参考左侧内容" : msg.content
                            )}
                          </div>
                        </>
                      ) : (
                        msg.content
                      )}
                    </div>
                  ))}
                </section>
                <div className="orch-composer" aria-label="场景输入框">
                  <textarea
                    autoFocus
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    onKeyDown={handleInputKeyDown}
                    placeholder="例如：我想做一个 AI 智能体编排平台..."
                  />
                  <div className="orch-composer-foot">
                    <span className="orch-composer-hint">输入开放需求后，系统会先判断是直接编排角色，还是先进行补充追问。支持回车发送。</span>
                    <button className="orch-send-button" type="button" onClick={submitPrompt} disabled={isThinking || !input.trim()}>
                      {isThinking ? "生成中..." : "发送"}
                    </button>
                  </div>
                </div>
              </aside>
            </div>
          </div>
        </header>

        {roles.length > 0 && (
          <section className="orch-wall-panel" aria-label="角色输入入口">
            <div className="orch-wall-stage">
              <div id="role-grid" aria-label="角色卡画廊">
                {roles.map(role => {
                  const isActive = selectedRoleId === role.id;
                  const roleData = {
                    image: `/assets/portrait-${role.id}.jpg`,
                    index: role.id === 'insight' ? '01' : role.id === 'product' ? '02' : role.id === 'engineering' ? '03' : role.id === 'marketing' ? '04' : role.id === 'sales' ? '05' : '06',
                    caption: role.name.substring(0,2),
                    tagA: 'system',
                    tagB: '交付',
                    height: '340px',
                    position: 'center'
                  };
                  return (
                    <button
                      key={role.id}
                      className={`orch-role-card ${isActive ? 'is-active' : ''}`}
                      type="button"
                      style={{'--card-height': roleData.height, '--portrait-position': roleData.position}}
                      onClick={() => handleCardClick(role.id)}
                    >
                      <div className="orch-role-card__media">
                        <img src={roleData.image} alt={role.name} />
                      </div>
                      <div className="orch-role-card__veil" aria-hidden="true"></div>
                      <div className="orch-role-card__chrome" aria-hidden="true"></div>
                      <div className="orch-role-card__meta">
                        <span className="orch-role-card__index">{roleData.index}</span>
                        <span className="orch-role-card__route">{role.id}</span>
                      </div>
                      <div className="orch-role-card__body">
                        <div className="orch-role-card__label-row">
                          <span className="orch-role-card__caption">{roleData.caption}</span>
                        </div>
                        <h3 className="orch-role-card__title">{role.name}</h3>
                        <div className="orch-role-card__tag-row">
                          <span className="orch-role-card__tag">{roleData.tagA}</span>
                          <span className="orch-role-card__tag">{roleData.tagB}</span>
                        </div>
                        <span className="orch-role-card__hint">点击查看详情</span>
                      </div>
                    </button>
                  )
                })}
              </div>
            </div>
          </section>
        )}
      </section>

      {isModalOpen && (selectedRole || selectedMarkdown) && (
        <div className="orch-modal-shell is-open">
          <div className="orch-modal-backdrop" onClick={handleCloseModal}></div>
          <section className="orch-modal-card" style={selectedMarkdown ? { maxWidth: '800px', width: '90vw' } : {}}>
            <button className="orch-modal-close" type="button" onClick={handleCloseModal}>×</button>
            <div className="orch-modal-header">
              <span className="orch-kicker">{selectedMarkdown ? "markdown content" : "role file"}</span>
              <h3>{selectedMarkdown ? "详细方案内容" : selectedRole.name}</h3>
            </div>

            {selectedMarkdown ? (
              <div className="orch-modal-panel" style={{ padding: '24px', overflowY: 'auto', maxHeight: '70vh', color: '#fff', background: '#111' }}>
                <ReactMarkdown>{selectedMarkdown}</ReactMarkdown>
              </div>
            ) : (
              <>
                <div className="orch-modal-view-toggle">
                  <button 
                    className={`orch-modal-tab ${modalView === 'form' ? 'is-active' : ''}`}
                    onClick={() => setModalView('form')}
                  >表单编辑</button>
                  <button 
                    className={`orch-modal-tab ${modalView === 'json' ? 'is-active' : ''}`}
                    onClick={() => setModalView('json')}
                  >JSON 视图</button>
                </div>

                {modalView === 'form' ? (
                  <div className="orch-modal-panel">
                    <div className="orch-modal-fields">
                      <label className="orch-modal-field">
                        <span>名字</span>
                        <input 
                          type="text" 
                          value={selectedRole.name || ''} 
                          onChange={e => handleRoleFieldChange('name', e.target.value)} 
                        />
                      </label>
                      <label className="orch-modal-field">
                        <span>职责</span>
                        <textarea 
                          rows="4" 
                          value={selectedRole.duty || ''}
                          onChange={e => handleRoleFieldChange('duty', e.target.value)} 
                        />
                      </label>
                      <label className="orch-modal-field">
                        <span>技能</span>
                        <textarea 
                          rows="3" 
                          value={selectedRole.skills || ''}
                          onChange={e => handleRoleFieldChange('skills', e.target.value)} 
                        />
                      </label>
                    </div>
                  </div>
                ) : (
                  <div className="orch-modal-panel">
                    <div className="orch-json-panel">
                      <article className="orch-json-card">
                        <strong>角色 JSON</strong>
                        <pre className="orch-json-code">
                          {JSON.stringify(selectedRole, null, 2)}
                        </pre>
                      </article>
                    </div>
                  </div>
                )}

                <div className="orch-modal-actions">
                  <button
                    className="orch-route-button"
                    onClick={saveSelectedRole}
                    disabled={saveState.status === "saving"}
                  >
                    {saveState.status === "saving" ? "保存中..." : "保存修改"}
                  </button>
                  <button
                    className="orch-route-button is-active"
                    onClick={() => handleNavigateToRole(selectedRole.id)}
                  >
                    进入工作流
                  </button>
                </div>
              </>
            )}
          </section>
        </div>
      )}
    </main>
  );
}
