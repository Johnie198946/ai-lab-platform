import { LogOut, Network, Workflow } from "lucide-react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useAuth } from "../../auth/AuthContext";
import "./quantumWorkspace.css";

export function QuantumWorkspaceLayout() {
  const { authSession, logout } = useAuth();
  const navigate = useNavigate();
  const signOut = () => {
    logout();
    navigate("/login", { replace: true });
  };

  return (
    <div className="qw-app">
      <header className="qw-header">
        <NavLink to="/home" className="qw-brand" aria-label="QuantumWorkspace Home">
          <span className="qw-spectrum" aria-hidden="true"><i /><i /><i /></span>
          <span>QuantumWorkspace</span>
        </NavLink>
        <nav className="qw-nav" aria-label="主导航">
          <NavLink to="/home">Home</NavLink>
          <NavLink to="/templates">模板库</NavLink>
          <NavLink to="/orchestration"><Workflow size={15} /> AI Lab Runtime</NavLink>
          <NavLink to="/architect"><Network size={15} /> Architect</NavLink>
        </nav>
        <div className="qw-account">
          <span>{authSession?.user?.username || authSession?.identifier || "用户"}</span>
          <button type="button" onClick={signOut} aria-label="退出登录"><LogOut size={16} /></button>
        </div>
      </header>
      <main className="qw-main"><Outlet /></main>
    </div>
  );
}
