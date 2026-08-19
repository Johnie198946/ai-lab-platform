import { useEffect } from "react";
import { Navigate, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { isShowroomAccount, SHOWROOM_CONTROLLER_PATH } from "../auth/entryRoute";

export function ProtectedRoute() {
  const { authSession, isAuthenticated, isReady } = useAuth();
  const location = useLocation();
  const shouldEnterShowroom = isReady && isAuthenticated && isShowroomAccount(authSession?.user);

  useEffect(() => {
    if (shouldEnterShowroom) {
      window.location.replace(SHOWROOM_CONTROLLER_PATH);
    }
  }, [shouldEnterShowroom]);

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

  if (shouldEnterShowroom) {
    return (
      <div className="route-loading">
        <div className="route-loading__panel">
          <h1>正在进入导览主控台…</h1>
        </div>
      </div>
    );
  }

  return <Outlet />;
}
