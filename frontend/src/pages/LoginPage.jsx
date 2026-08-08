import { useMemo, useState } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { API_ORIGIN_LABEL, AUTH_ORIGIN_LABEL, ENABLE_DEMO_FALLBACK } from "../config/env";

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

  const nextPath = useMemo(
    () => location.state?.from?.pathname || "/orchestration",
    [location.state],
  );

  if (!isReady) {
    return (
      <div className="route-loading">
        <div className="route-loading__panel">
          <span className="eyebrow">
            <span className="eyebrow__dot" />
            Auth Restore
          </span>
          <h1>正在检查已有登录态</h1>
          <p>如果本地已有有效会话，将自动跳转到受保护编排页。</p>
        </div>
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
    <div className="login-shell">
      <div className="login-noise" />
      <section className="login-hero">
        <div className="eyebrow">
          <span className="eyebrow__dot" />
          Protected Orchestration
        </div>
        <h1>登录后进入 AI Lab 编排工作台</h1>
        <p>
          会话、角色编辑和最近一次编排结果会保存在浏览器中；重新进入后优先恢复你的工作现场。
        </p>
        <div className="login-highlights">
          <span className="signal-pill">受保护路由</span>
          <span className="signal-pill">会话恢复</span>
          <span className="signal-pill">角色回写</span>
          <span className="signal-pill">默认禁用伪 fallback</span>
        </div>
      </section>

      <section className="login-panel">
        <div className="login-panel__header">
          <span className="section-label">Auth</span>
          <h2>使用 Authen 账号或现有 Bearer Token 登录</h2>
          <p>工作台页面仅在登录后可访问。开发环境若关闭 JWT 校验，也可使用开发会话直连。</p>
        </div>

        <form className="login-form" onSubmit={handlePasswordLogin}>
          <label className="field">
            <span>账号</span>
            <input
              value={identifier}
              onChange={(event) => setIdentifier(event.target.value)}
              placeholder="admin / 邮箱 / 用户名"
              autoComplete="username"
            />
          </label>

          <label className="field">
            <span>密码</span>
            <input
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              placeholder="输入 Authen 密码"
              autoComplete="current-password"
            />
          </label>

          <button
            className="login-button"
            type="submit"
            disabled={!identifier.trim() || !password || Boolean(submittingMode)}
          >
            {submittingMode === "password" ? "登录中..." : "账号密码登录"}
          </button>
        </form>

        <form className="login-form login-form--secondary" onSubmit={handleTokenLogin}>
          <label className="field field--wide">
            <span>Bearer Token</span>
            <textarea
              value={token}
              onChange={(event) => setToken(event.target.value)}
              placeholder="粘贴现有 access token，用于快速联调"
              rows={4}
            />
          </label>

          <button
            className="login-button login-button--ghost"
            type="submit"
            disabled={!token.trim() || Boolean(submittingMode)}
          >
            {submittingMode === "token" ? "校验中..." : "使用 Token 登录"}
          </button>
        </form>

        <div className="login-dev">
          <button
            className="login-button login-button--dev"
            type="button"
            onClick={() => runAction("dev", () => loginDev())}
            disabled={Boolean(submittingMode)}
          >
            {submittingMode === "dev" ? "连接中..." : "开发模式直连"}
          </button>
          <p>仅当后端未启用 JWT 校验时可用；如果返回 401，说明当前环境必须提供有效 token。</p>
        </div>

        {error ? <div className="integration-banner integration-banner--error">{error}</div> : null}

        <div className="login-meta">
          <div className="status-card">
            <span className="status-card__label">平台地址</span>
            <strong>{API_ORIGIN_LABEL}</strong>
          </div>
          <div className="status-card">
            <span className="status-card__label">认证地址</span>
            <strong>{AUTH_ORIGIN_LABEL}</strong>
          </div>
          <div className="status-card status-card--accent">
            <span className="status-card__label">Fallback 默认值</span>
            <strong>{ENABLE_DEMO_FALLBACK ? "已启用" : "已禁用"}</strong>
          </div>
        </div>
      </section>
    </div>
  );
}
