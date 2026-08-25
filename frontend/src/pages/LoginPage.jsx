import { useEffect, useMemo, useRef, useState } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { isShowroomAccount, SHOWROOM_CONTROLLER_PATH } from "../auth/entryRoute";
import { platformApi } from "../services/platformApi";
import EvilEye from "../components/EvilEye";
import "./Login.css";

const getErrorMessage = (error) => error?.message || "登录失败，请稍后重试。";

export function LoginPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const {
    authSession,
    isAuthenticated,
    isReady,
    login,
    loginDev,
    loginWithPhone,
    loginWithOAuthTicket,
    loginWithToken,
  } = useAuth();

  const [identifier, setIdentifier] = useState("");
  const [password, setPassword] = useState("");
  const [phone, setPhone] = useState("");
  const [phoneCode, setPhoneCode] = useState("");
  const [token, setToken] = useState("");
  const [submittingMode, setSubmittingMode] = useState("");
  const [error, setError] = useState("");
  const [activeTab, setActiveTab] = useState("account");
  const [countdown, setCountdown] = useState(0);
  const [capabilities, setCapabilities] = useState(null);
  const oauthHandledRef = useRef(false);

  const query = useMemo(() => new URLSearchParams(location.search), [location.search]);
  const oauthTicket = query.get("oauth_ticket") || "";
  const oauthError = query.get("oauth_error") || "";
  const nextPath = useMemo(() => {
    const requestedPath = query.get("next") || "";
    if (requestedPath.startsWith("/") && !requestedPath.startsWith("//")) {
      return requestedPath;
    }
    return location.state?.from?.pathname || "/orchestration";
  }, [location.state, query]);

  useEffect(() => {
    let active = true;
    platformApi
      .getAuthCapabilities()
      .then((data) => active && setCapabilities(data))
      .catch(() => active && setCapabilities({ phone: { enabled: false }, oauth: {} }));
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    if (countdown <= 0) return undefined;
    const timer = window.setInterval(() => setCountdown((value) => Math.max(0, value - 1)), 1000);
    return () => window.clearInterval(timer);
  }, [countdown]);

  useEffect(() => {
    if (oauthError && !oauthTicket) {
      setError(oauthError === "authorization_cancelled" ? "已取消第三方授权。" : "第三方登录失败，请重试。");
    }
  }, [oauthError, oauthTicket]);

  useEffect(() => {
    if (!isReady || isAuthenticated || !oauthTicket || oauthHandledRef.current) return;
    oauthHandledRef.current = true;
    setSubmittingMode("oauth-callback");
    setError("");
    loginWithOAuthTicket({ ticket: oauthTicket })
      .then((session) => {
        if (isShowroomAccount(session?.user)) window.location.replace(SHOWROOM_CONTROLLER_PATH);
        else navigate(nextPath, { replace: true });
      })
      .catch((actionError) => {
        setError(getErrorMessage(actionError));
        oauthHandledRef.current = false;
        navigate("/login", { replace: true });
      })
      .finally(() => setSubmittingMode(""));
  }, [isAuthenticated, isReady, loginWithOAuthTicket, navigate, nextPath, oauthTicket]);

  useEffect(() => {
    if (isReady && isAuthenticated && isShowroomAccount(authSession?.user)) {
      window.location.replace(SHOWROOM_CONTROLLER_PATH);
    }
  }, [authSession, isAuthenticated, isReady]);

  const runAction = async (mode, action) => {
    setSubmittingMode(mode);
    setError("");
    try {
      const session = await action();
      if (isShowroomAccount(session?.user)) window.location.assign(SHOWROOM_CONTROLLER_PATH);
      else navigate(nextPath, { replace: true });
    } catch (actionError) {
      setError(getErrorMessage(actionError));
    } finally {
      setSubmittingMode("");
    }
  };

  const handlePasswordLogin = (event) => {
    event.preventDefault();
    return runAction("password", () => login({ identifier: identifier.trim(), password }));
  };

  const handlePhoneLogin = (event) => {
    event.preventDefault();
    return runAction("phone", () => loginWithPhone({ phone: phone.trim(), code: phoneCode.trim() }));
  };

  const handleTokenLogin = (event) => {
    event.preventDefault();
    return runAction("token", () => loginWithToken({ accessToken: token.trim(), identifier: identifier.trim() || "token-user" }));
  };

  const sendPhoneCode = async () => {
    setSubmittingMode("phone-code");
    setError("");
    try {
      await platformApi.sendPhoneCode({ phone: phone.trim() });
      setCountdown(60);
    } catch (actionError) {
      setError(getErrorMessage(actionError));
    } finally {
      setSubmittingMode("");
    }
  };

  const startOAuth = async (provider) => {
    setSubmittingMode(provider);
    setError("");
    try {
      const payload = await platformApi.startOAuth({ provider, client: "web" });
      if (!payload?.authorization_url) throw new Error("认证服务未返回授权地址。");
      window.location.assign(payload.authorization_url);
    } catch (actionError) {
      setError(getErrorMessage(actionError));
      setSubmittingMode("");
    }
  };

  if (!isReady || submittingMode === "oauth-callback") {
    return <div className="route-loading"><h1>正在恢复安全登录态...</h1></div>;
  }
  if (isAuthenticated) {
    if (isShowroomAccount(authSession?.user)) return <div className="route-loading"><h1>正在进入导览主控台…</h1></div>;
    return <Navigate to={nextPath} replace />;
  }

  const phoneEnabled = capabilities?.phone?.enabled === true;
  const wechatEnabled = capabilities?.oauth?.wechat?.enabled === true;
  const alipayEnabled = capabilities?.oauth?.alipay?.enabled === true;

  return (
    <main className="login-page" aria-label="登录入口页">
      <section className="login-grid">
        <article className="panel brand-panel" aria-label="品牌展示区">
          <div className="brand-visual" aria-hidden="true">
            <EvilEye eyeColor="#2a3f54" backgroundColor="#f5f6f8" intensity={0.6} pupilFollow={0.2} pupilSize={0.15} irisWidth={0.25} glowIntensity={0.2} scale={0.9} />
          </div>
        </article>

        <section className="panel login-panel" aria-label="登录表单区">
          <div className="login-card">
            <div className="login-head"><h2>欢迎回来</h2><p>选择熟悉的方式登录，继续进入你的智能编排工作台。</p></div>
            <div className="login-tabs" role="tablist" aria-label="登录方式">
              {[["account", "账号"], ["phone", "手机"], ["token", "Token"]].map(([key, label]) => (
                <button key={key} className="login-tab" type="button" role="tab" aria-selected={activeTab === key} onClick={() => setActiveTab(key)}>{label}</button>
              ))}
            </div>

            <div className="login-forms">
              {activeTab === "account" && (
                <form className="login-form is-active" onSubmit={handlePasswordLogin}>
                  <label className="field"><span className="field-label">账号</span><input type="text" value={identifier} onChange={(event) => setIdentifier(event.target.value)} autoComplete="username" placeholder="请输入账号" /></label>
                  <label className="field"><span className="field-label">密码</span><input type="password" value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="current-password" placeholder="请输入密码" /></label>
                  <button className="cta-button" type="submit" disabled={!identifier.trim() || !password || Boolean(submittingMode)}><span>{submittingMode === "password" ? "登录中..." : "进入智能编排"}</span><span aria-hidden="true">→</span></button>
                </form>
              )}
              {activeTab === "phone" && (
                <form className="login-form is-active" onSubmit={handlePhoneLogin}>
                  <label className="field"><span className="field-label">手机号码</span><input type="tel" value={phone} onChange={(event) => setPhone(event.target.value.replace(/[^0-9+ -]/g, ""))} autoComplete="tel" placeholder="请输入手机号" /></label>
                  <div className="phone-code-row">
                    <label className="field"><span className="field-label">验证码</span><input type="text" inputMode="numeric" maxLength={6} value={phoneCode} onChange={(event) => setPhoneCode(event.target.value.replace(/\D/g, ""))} autoComplete="one-time-code" placeholder="6 位验证码" /></label>
                    <button className="code-button" type="button" onClick={sendPhoneCode} disabled={!phoneEnabled || phone.replace(/\D/g, "").length < 11 || countdown > 0 || Boolean(submittingMode)}>{countdown > 0 ? `${countdown}s` : submittingMode === "phone-code" ? "发送中" : "获取验证码"}</button>
                  </div>
                  {!phoneEnabled && capabilities && <p className="channel-note">短信渠道尚未配置，暂不可用。</p>}
                  <button className="cta-button" type="submit" disabled={!phoneEnabled || phoneCode.length !== 6 || Boolean(submittingMode)}><span>{submittingMode === "phone" ? "登录中..." : "手机号登录 / 注册"}</span><span aria-hidden="true">→</span></button>
                </form>
              )}
              {activeTab === "token" && (
                <form className="login-form is-active" onSubmit={handleTokenLogin}>
                  <label className="field"><span className="field-label">Access Token</span><input type="text" value={token} onChange={(event) => setToken(event.target.value)} placeholder="请输入 Access Token" /></label>
                  <button className="cta-button" type="submit" disabled={!token.trim() || Boolean(submittingMode)}><span>{submittingMode === "token" ? "登录中..." : "使用 Token 登录"}</span><span aria-hidden="true">→</span></button>
                </form>
              )}
            </div>

            {error && <div className="login-error" role="alert">{error}</div>}
            <div className="assist-row"><span>企业安全域保护</span><strong>会话加密传输</strong></div>
            <div className="divider">快捷登录</div>
            <div className="quick-actions" aria-label="快捷登录方式">
              <button className="quick-button" type="button" onClick={() => startOAuth("wechat")} disabled={!wechatEnabled || Boolean(submittingMode)} title={wechatEnabled ? "微信登录" : "微信登录尚未配置"}><span className="quick-icon wechat" aria-hidden="true" /><span className="quick-label">{submittingMode === "wechat" ? "连接中..." : "微信"}</span></button>
              <button className="quick-button" type="button" onClick={() => startOAuth("alipay")} disabled={!alipayEnabled || Boolean(submittingMode)} title={alipayEnabled ? "支付宝登录" : "支付宝登录尚未配置"}><span className="quick-icon alipay" aria-hidden="true" /><span className="quick-label">{submittingMode === "alipay" ? "连接中..." : "支付宝"}</span></button>
            </div>
            {import.meta.env.DEV && <button className="dev-login-link" type="button" onClick={() => runAction("dev", () => loginDev())}>开发模式直连</button>}
            <p className="footnote">登录即表示你已阅读并同意平台服务协议与隐私说明。</p>
          </div>
        </section>
      </section>
    </main>
  );
}
