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

const parseMarkdownSections = (md) => {
  const sections = [];
  // 先按 ## 分主节，再在主节内按 ### 分子节
  const topRegex = /^##\s+(.*)$/gm;
  let topMatch;
  let topIndex = 0;
  let currentTop = null;

  const parseSubsections = (bodyText) => {
    const subs = [];
    const subRegex = /^###\s+(.*)$/gm;
    let m;
    let last = 0;
    let cur = null;
    while ((m = subRegex.exec(bodyText)) !== null) {
      if (cur) {
        cur.content = bodyText.substring(last, m.index).trim();
      } else {
        const intro = bodyText.substring(0, m.index).trim();
        if (intro) subs.push({ title: '概述', content: intro, level: 3 });
      }
      cur = { title: m[1], content: '', level: 3 };
      subs.push(cur);
      last = m.index + m[0].length;
    }
    if (cur) {
      cur.content = bodyText.substring(last).trim();
    }
    return subs;
  };

  while ((topMatch = topRegex.exec(md)) !== null) {
    if (currentTop) {
      currentTop.content = md.substring(topIndex, topMatch.index).trim();
    } else {
      const intro = md.substring(0, topMatch.index).trim();
      if (intro) {
        sections.push({ title: '引言', content: intro, id: 'intro', subs: [] });
      }
    }
    const bodyText = md.substring(topMatch.index + topMatch[0].length);
    const subs = parseSubsections(bodyText);
    currentTop = {
      title: topMatch[1],
      id: `sec-${topMatch.index}`,
      content: '',
      subs,
    };
    sections.push(currentTop);
    topIndex = topMatch.index + topMatch[0].length;
  }
  if (currentTop) {
    currentTop.content = md.substring(topIndex).trim();
  } else if (sections.length === 0) {
    sections.push({ title: '执行方案', content: md.trim(), id: 'all', subs: [] });
  }
  return sections;
};

const MarkdownAccordion = ({ content }) => {
  const sections = parseMarkdownSections(content);
  const [expandedId, setExpandedId] = useState(sections.length > 0 ? sections[0].id : null);
  const [expandedSubs, setExpandedSubs] = useState({});

  const toggleSub = (secId, subIdx) => {
    setExpandedSubs((prev) => ({
      ...prev,
      [`${secId}-${subIdx}`]: !prev[`${secId}-${subIdx}`],
    }));
  };

  return (
    <div className="orch-markdown-accordion">
      {sections.map((sec) => {
        const isExpanded = expandedId === sec.id;
        const hasSubs = (sec.subs || []).length > 0;
        return (
          <div key={sec.id} className={`orch-accordion-item ${isExpanded ? 'is-expanded' : ''}`}>
            <button 
              className="orch-accordion-header" 
              onClick={() => setExpandedId(isExpanded ? null : sec.id)}
            >
              <span className="orch-accordion-title">{sec.title}</span>
              <span className="orch-accordion-icon">{isExpanded ? '−' : '+'}</span>
            </button>
            {isExpanded && (
              <div className="orch-accordion-body">
                {!hasSubs && sec.content && (
                  <ReactMarkdown
                    components={{
                      p: ({node, ...props}) => <p style={{margin: '0 0 8px', lineHeight: '1.5'}} {...props} />,
                      ul: ({node, ...props}) => <ul style={{paddingLeft: '20px', margin: '0 0 8px'}} {...props} />,
                      ol: ({node, ...props}) => <ol style={{paddingLeft: '20px', margin: '0 0 8px'}} {...props} />,
                      li: ({node, ...props}) => <li style={{marginBottom: '4px'}} {...props} />,
                      strong: ({node, ...props}) => <strong style={{color: '#fff', fontWeight: '600'}} {...props} />
                    }}
                  >
                    {sec.content}
                  </ReactMarkdown>
                )}
                {hasSubs && (
                  <div className="orch-accordion-subs">
                    {sec.subs.map((sub, subIdx) => {
                      const subKey = `${sec.id}-${subIdx}`;
                      const subOpen = !!expandedSubs[subKey];
                      return (
                        <div key={subKey} className={`orch-sub-item ${subOpen ? 'is-open' : ''}`}>
                          <button className="orch-sub-header" onClick={() => toggleSub(sec.id, subIdx)}>
                            <span className="orch-sub-title">{sub.title}</span>
                            <span className="orch-accordion-icon">{subOpen ? '−' : '+'}</span>
                          </button>
                          {subOpen && (
                            <div className="orch-sub-body">
                              <ReactMarkdown
                                components={{
                                  p: ({node, ...props}) => <p style={{margin: '0 0 8px', lineHeight: '1.5'}} {...props} />,
                                  ul: ({node, ...props}) => <ul style={{paddingLeft: '20px', margin: '0 0 8px'}} {...props} />,
                                  li: ({node, ...props}) => <li style={{marginBottom: '4px'}} {...props} />,
                                  strong: ({node, ...props}) => <strong style={{color: '#fff', fontWeight: '600'}} {...props} />
                                }}
                              >
                                {sub.content}
                              </ReactMarkdown>
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
};

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
  const [dragOverlay, setDragOverlay] = useState(false);
  // 用来追踪真正的进入/离开次数，防止子元素触发的 dragleave 导致蒙层闪烁或常驻
  const dragCounter = useRef(0);

  useEffect(() => {
    const handleDragEnter = (e) => {
      e.preventDefault();
      e.stopPropagation();
      dragCounter.current += 1;
      if (e.dataTransfer.items && e.dataTransfer.items.length > 0) {
        setDragOverlay(true);
      }
    };

    const handleDragOver = (e) => {
      e.preventDefault();
      e.stopPropagation();
    };

    const handleDragLeave = (e) => {
      e.preventDefault();
      e.stopPropagation();
      dragCounter.current -= 1;
      if (dragCounter.current === 0) {
        setDragOverlay(false);
      }
    };

    const handleDrop = (e) => {
      e.preventDefault();
      e.stopPropagation();
      dragCounter.current = 0;
      setDragOverlay(false);
      
      if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
        const file = e.dataTransfer.files[0];
        const reader = new FileReader();
        reader.onload = (ev) => {
          setInput(prev => prev + (prev ? '\n' : '') + `[附件内容: ${file.name}]\n${ev.target.result}\n`);
        };
        reader.readAsText(file);
      }
    };

    window.addEventListener('dragenter', handleDragEnter);
    window.addEventListener('dragover', handleDragOver);
    window.addEventListener('dragleave', handleDragLeave);
    window.addEventListener('drop', handleDrop);

    return () => {
      window.removeEventListener('dragenter', handleDragEnter);
      window.removeEventListener('dragover', handleDragOver);
      window.removeEventListener('dragleave', handleDragLeave);
      window.removeEventListener('drop', handleDrop);
    };
  }, [setInput]);

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
      <div
        style={{
          position: "fixed",
          top: 16,
          right: 20,
          zIndex: 50,
          display: "flex",
          gap: 10,
        }}
      >
        <button
          type="button"
          className="orch-nav-button"
          onClick={() => navigate("/agents")}
          style={{
            background: "rgba(43,129,255,0.15)",
            border: "1px solid rgba(43,129,255,0.45)",
            color: "#9cc0ff",
            borderRadius: 999,
            padding: "7px 16px",
            cursor: "pointer",
            fontSize: "0.85rem",
            fontWeight: 600,
          }}
        >
          🤖 子 Agent 工厂
        </button>
      </div>
      {dragOverlay && (
        <div style={{
          position: 'fixed',
          top: 0, left: 0, right: 0, bottom: 0,
          backgroundColor: 'rgba(0, 0, 0, 0.7)',
          zIndex: 9999,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          pointerEvents: 'none'
        }}>
          <div style={{
            border: '2px dashed #fff',
            borderRadius: '12px',
            padding: '40px 80px',
            color: '#fff',
            fontSize: '24px',
            fontWeight: 'bold',
            background: 'rgba(255, 255, 255, 0.1)'
          }}>
            松开鼠标上传文件到对话
          </div>
        </div>
      )}
      <section className="orch-stage" aria-label="需求输入工作台">
        <header className="orch-stage-header">
          <div id="ai-conversation-workspace" aria-label="工作总结">
            <div className="orch-workspace-grid">
              <div className="orch-summary-copy" style={{ position: 'relative' }}>
                {messages.length > 0 && messages[messages.length - 1].role === 'assistant' && messages[messages.length - 1].isMarkdown ? (
                  <div style={{ height: '100%', display: 'flex', flexDirection: 'column', justifyContent: 'center' }}>
                    <BorderGlow onClick={() => handleMarkdownClick(messages[messages.length - 1].content)}>
                      <div style={{ padding: '0', display: 'flex', flexDirection: 'column', height: '100%' }}>
                        <h2 style={{ marginBottom: '16px', color: '#fff', fontSize: '1.25rem', flexShrink: 0 }}>系统已生成方案内容</h2>
                        <p style={{ color: '#ccc', marginBottom: '16px', fontSize: '0.875rem', flexShrink: 0 }}>点击卡片展开查看具体步骤和执行细节。</p>
                        <div style={{
                          opacity: 0.9,
                          fontSize: '14px',
                          display: 'block',
                          flex: 1,
                          overflowY: 'auto',
                          overflowX: 'hidden',
                          color: '#e0e0e0',
                          lineHeight: '1.6',
                          borderTop: '1px solid #333',
                          paddingTop: '16px',
                          paddingRight: '8px'
                        }} className="markdown-preview-scroll">
                          <MarkdownAccordion content={messages[messages.length - 1].content} />
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
                          <div className="orch-dialog-markdown">
                            <ReactMarkdown
                              components={{
                                h2: ({node, ...props}) => <h2 style={{margin: '10px 0 6px', fontSize: '1.05rem', color: '#fff'}} {...props} />,
                                h3: ({node, ...props}) => <h3 style={{margin: '8px 0 4px', fontSize: '0.95rem', color: '#fff'}} {...props} />,
                                p: ({node, ...props}) => <p style={{margin: '0 0 8px', lineHeight: '1.5'}} {...props} />,
                                ul: ({node, ...props}) => <ul style={{paddingLeft: '20px', margin: '0 0 8px'}} {...props} />,
                                ol: ({node, ...props}) => <ol style={{paddingLeft: '20px', margin: '0 0 8px'}} {...props} />,
                                li: ({node, ...props}) => <li style={{marginBottom: '4px'}} {...props} />,
                                strong: ({node, ...props}) => <strong style={{color: '#fff', fontWeight: '600'}} {...props} />
                              }}
                            >
                              {msg.content}
                            </ReactMarkdown>
                          </div>
                        </>
                      ) : (
                        msg.content
                      )}
                    </div>
                  ))}
                  {isThinking && (
                    <div className="orch-dialog-bubble orch-dialog-bubble--assistant">
                      <span className="orch-dialog-kicker">系统思考中</span>
                      <div className="orch-typing-indicator">
                        <span></span>
                        <span></span>
                        <span></span>
                      </div>
                    </div>
                  )}
                </section>
                <div className="orch-composer" aria-label="场景输入框" 
                     onDragOver={(e) => { e.preventDefault(); e.stopPropagation(); }}
                     onDrop={(e) => {
                       e.preventDefault();
                       e.stopPropagation();
                       if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
                         const file = e.dataTransfer.files[0];
                         const reader = new FileReader();
                         reader.onload = (ev) => {
                           setInput(prev => prev + (prev ? '\n' : '') + `[附件内容: ${file.name}]\n${ev.target.result}\n`);
                         };
                         reader.readAsText(file);
                       }
                     }}>
                  <textarea
                    autoFocus
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    onKeyDown={handleInputKeyDown}
                    placeholder="例如：我想做一个 AI 智能体编排平台...（支持拖拽TXT/Markdown文件至此）"
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
                    caption: role.title || role.name.substring(0,2),
                    tagA: role.skills ? (role.skills.split(/[,、]/)[0] || 'system') : 'system',
                    tagB: role.skills ? (role.skills.split(/[,、]/)[1] || '交付') : '交付',
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
                        <span>姓名</span>
                        <input 
                          type="text" 
                          value={selectedRole.name || ''} 
                          onChange={e => handleRoleFieldChange('name', e.target.value)} 
                        />
                      </label>
                      <label className="orch-modal-field">
                        <span>角色</span>
                        <input 
                          type="text" 
                          value={selectedRole.title || ''} 
                          onChange={e => handleRoleFieldChange('title', e.target.value)} 
                        />
                      </label>
                      <label className="orch-modal-field">
                        <span>职责</span>
                        <textarea 
                          rows="4" 
                          value={selectedRole.responsibility || ''}
                          onChange={e => handleRoleFieldChange('responsibility', e.target.value)} 
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
