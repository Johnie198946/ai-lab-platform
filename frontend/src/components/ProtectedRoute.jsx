import { Navigate, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";

export function ProtectedRoute() {
  const { isAuthenticated, isReady } = useAuth();
  const location = useLocation();

  if (!isReady) {
    return (
      <div className="route-loading">
        <div className="route-loading__panel">
          <span className="eyebrow">
            <span className="eyebrow__dot" />
            Session Guard
          </span>
          <h1>正在恢复会话</h1>
          <p>校验登录态后会自动进入受保护编排页。</p>
        </div>
      </div>
    );
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace state={{ from: location }} />;
  }

  return <Outlet />;
}
