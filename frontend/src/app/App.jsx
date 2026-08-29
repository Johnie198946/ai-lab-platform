import { lazy, Suspense } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { ProtectedRoute } from "../components/ProtectedRoute";
import { useAuth } from "../auth/AuthContext";
import { LoginPage } from "../pages/LoginPage";
import { isShowroomAccount } from "../auth/entryRoute";

const OrchestrationPage = lazy(() => import("../pages/OrchestrationPage").then((module) => ({ default: module.OrchestrationPage })));
const AgentPage = lazy(() => import("../pages/AgentPage").then((module) => ({ default: module.AgentPage })));
const RoleInsight = lazy(() => import("../pages/RoleInsight"));
const RoleEngineering = lazy(() => import("../pages/RoleEngineering"));
const RoleFounder = lazy(() => import("../pages/RoleFounder"));
const RoleMarketing = lazy(() => import("../pages/RoleMarketing"));
const RoleSales = lazy(() => import("../pages/RoleSales"));
const RoleProduct = lazy(() => import("../pages/RoleProduct"));
const ArchitectPage = lazy(() => import("../pages/ArchitectWorkbenchPage"));
const AgencyPortalPage = lazy(() => import("../pages/AgencyPortalPage"));
const QuantumWorkspaceLayout = lazy(() => import("../features/quantum-workspace/QuantumWorkspaceLayout").then((module) => ({ default: module.QuantumWorkspaceLayout })));
const WorkspaceHomePage = lazy(() => import("../features/quantum-workspace/WorkspaceHomePage").then((module) => ({ default: module.WorkspaceHomePage })));
const ProjectWorkspacePage = lazy(() => import("../features/quantum-workspace/ProjectWorkspacePage").then((module) => ({ default: module.ProjectWorkspacePage })));

function ShowroomRedirect() {
  const { isAuthenticated, authSession } = useAuth();
  return <Navigate to={isAuthenticated ? "/agency" : "/login?next=/agency"} replace />;
}

export default function App() {
  const { isAuthenticated, authSession } = useAuth();

  return (
    <Suspense fallback={<div className="qw-page-state">正在加载工作区…</div>}><Routes>
      <Route
        path="/"
        element={<Navigate to={isAuthenticated ? (isShowroomAccount(authSession?.user) ? "/agency" : "/home") : "/login"} replace />}
      />
      <Route path="/login" element={<LoginPage />} />
      <Route path="/showroom/*" element={<ShowroomRedirect />} />
      <Route element={<ProtectedRoute />}>
        <Route path="/agency" element={<AgencyPortalPage />} />
        <Route element={<QuantumWorkspaceLayout />}>
          <Route path="/home" element={<WorkspaceHomePage />} />
          <Route path="/templates" element={<WorkspaceHomePage />} />
          <Route path="/projects/:projectId/taskboard" element={<ProjectWorkspacePage />} />
          <Route path="/projects/:projectId/schedule" element={<ProjectWorkspacePage />} />
          <Route path="/projects/:projectId/documents" element={<ProjectWorkspacePage />} />
          <Route path="/projects/:projectId/graph/:viewType" element={<ProjectWorkspacePage />} />
        </Route>
        <Route path="/architect" element={<ArchitectPage />} />
        <Route path="/orchestration" element={<OrchestrationPage />} />
        <Route path="/agents" element={<AgentPage />} />
        <Route path="/role/insight" element={<RoleInsight />} />
        <Route path="/role/engineering" element={<RoleEngineering />} />
        <Route path="/role/founder" element={<RoleFounder />} />
        <Route path="/role/marketing" element={<RoleMarketing />} />
        <Route path="/role/sales" element={<RoleSales />} />
        <Route path="/role/product" element={<RoleProduct />} />
      </Route>
      <Route
        path="*"
        element={<Navigate to={isAuthenticated ? (isShowroomAccount(authSession?.user) ? "/agency" : "/home") : "/login"} replace />}
      />
    </Routes></Suspense>
  );
}
