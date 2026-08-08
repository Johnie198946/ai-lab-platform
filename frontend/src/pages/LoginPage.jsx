import { useMemo, useState, useEffect, useRef } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { API_ORIGIN_LABEL, AUTH_ORIGIN_LABEL, ENABLE_DEMO_FALLBACK } from "../config/env";
import EvilEye from "../components/EvilEye";
import "./Login.css";

const getErrorMessage = (error) => error?.message || "登录失败，请检查账号、密码或 token。";

export function LoginPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const { isAuthenticated, isReady, login, loginDev, loginWithToken } = useAuth();
  
  const [identifier, setIdentifier] = useState("");
  const [password, setPassword] = useState("");
  const [token, setToken] = useState("");
  const [submittingMode, setSubmittingMode] = useState("");
  const [error, setError] = useState("");
  const [activeTab, setActiveTab] = useState("account");

  const nextPath = useMemo(
    () => location.state?.from?.pathname || "/orchestration",
    [location.state],
  );

  if (!isReady) {
    return (
      <div className="route-loading" style={{display:'grid', placeItems:'center', minHeight:'100vh', background:'#f5f6f8'}}>
        <h1>正在恢复登录态与工作台入口...</h1>
      </div>
    );
  }

  if (isReady && isAuthenticated) {
    return <Navigate to={nextPath} replace />;
  }

  const runAction = async (mode, action) => {
    setSubmittingMode(mode);
    setError("");
    try {
      await action();
      navigate(nextPath, { replace: true });
    } catch (actionError) {
      setError(getErrorMessage(actionError));
    } finally {
      setSubmittingMode("");
    }
  };

  const handlePasswordLogin = async (event) => {
    event.preventDefault();
    await runAction("password", () =>
      login({
        identifier: identifier.trim(),
        password,
      }),
    );
  };

  const handleTokenLogin = async (event) => {
    event.preventDefault();
    await runAction("token", () =>
      loginWithToken({
        accessToken: token.trim(),
        identifier: identifier.trim() || "token-user",
      }),
    );
  };

  return (
    <main className="login-page" aria-label="登录入口页">
      <section className="login-grid">
        <article className="panel brand-panel" aria-label="品牌展示区">
          <div className="brand-visual" aria-hidden="true" style={{ width: '100%', height: '100%', overflow: 'hidden', borderRadius: '30px' }}>
            <EvilEye 
              eyeColor="#000000"
              backgroundColor="#f5f6f8"
              intensity={1.0}
              pupilFollow={0.2}
            />
          </div>
        </article>

        <section className="panel login-panel" aria-label="登录表单区">
          <div className="login-card">
            <div className="login-head">
              <h2>欢迎回来</h2>
              <p>选择熟悉的方式登录，继续进入你的智能编排工作台。</p>
            </div>

            <div className="login-tabs" role="tablist" aria-label="登录方式">
              <button 
                className="login-tab" 
                type="button" 
                role="tab" 
                aria-selected={activeTab === 'account'} 
                onClick={() => setActiveTab('account')}
              >
                账号登录
              </button>
              <button 
                className="login-tab" 
                type="button" 
                role="tab" 
                aria-selected={activeTab === 'email'} 
                onClick={() => setActiveTab('email')}
              >
                Token 登录
              </button>
            </div>

            <div className="login-forms">
              {activeTab === 'account' ? (
                <form className="login-form is-active" id="form-account" onSubmit={handlePasswordLogin}>
                  <label className="field">
                    <span className="field-label">账号</span>
                    <input 
                      type="text" 
                      value={identifier}
                      onChange={(e) => setIdentifier(e.target.value)}
                      autoComplete="username" 
                      placeholder="请输入账号" 
                    />
                  </label>
                  <label className="field">
                    <span className="field-label">密码</span>
                    <input 
                      type="password" 
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      autoComplete="current-password" 
                      placeholder="请输入密码" 
                    />
                  </label>
                  
                  {error && <div style={{color:'red', fontSize:'12px', marginTop:'8px'}}>{error}</div>}

                  <button 
                    className="cta-button" 
                    type="submit" 
                    disabled={!identifier.trim() || !password || Boolean(submittingMode)}
                    style={{border:'none', cursor:'pointer'}}
                  >
                    <span>{submittingMode === 'password' ? '登录中...' : '进入智能编排'}</span>
                    <span aria-hidden="true">→</span>
                    <span className="cta-ripple" aria-hidden="true"></span>
                  </button>
                </form>
              ) : (
                <form className="login-form is-active" id="form-email" onSubmit={handleTokenLogin}>
                  <label className="field">
                    <span className="field-label">Token</span>
                    <input 
                      type="text" 
                      value={token}
                      onChange={(e) => setToken(e.target.value)}
                      placeholder="请输入 Access Token" 
                    />
                  </label>
                  
                  {error && <div style={{color:'red', fontSize:'12px', marginTop:'8px'}}>{error}</div>}

                  <button 
                    className="cta-button" 
                    type="submit" 
                    disabled={!token.trim() || Boolean(submittingMode)}
                    style={{border:'none', cursor:'pointer'}}
                  >
                    <span>{submittingMode === 'token' ? '登录中...' : '进入智能编排'}</span>
                    <span aria-hidden="true">→</span>
                    <span className="cta-ripple" aria-hidden="true"></span>
                  </button>
                </form>
              )}
            </div>

            <div className="assist-row">
              <span>企业安全域保护</span>
              <strong>会话加密传输</strong>
            </div>

            <div className="divider">快捷登录</div>

            <div className="quick-actions" aria-label="快捷登录方式">
              <button 
                className="quick-button" 
                type="button" 
                onClick={() => runAction("dev", () => loginDev())}
                disabled={Boolean(submittingMode)}
              >
                <span className="quick-label">{submittingMode === 'dev' ? '连接中...' : '开发模式直连'}</span>
              </button>
            </div>

            <p className="footnote">登录即表示你已阅读并同意平台服务协议与隐私说明。</p>
          </div>
        </section>
      </section>
    </main>
  );
}
