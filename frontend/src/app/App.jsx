import { Navigate, Route, Routes } from "react-router-dom";
import { ProtectedRoute } from "../components/ProtectedRoute";
import { useAuth } from "../auth/AuthContext";
import { LoginPage } from "../pages/LoginPage";
import { OrchestrationPage } from "../pages/OrchestrationPage";
import { AgentPage } from "../pages/AgentPage";
import RoleInsight from "../pages/RoleInsight";
import RoleEngineering from "../pages/RoleEngineering";
import RoleFounder from "../pages/RoleFounder";
import RoleMarketing from "../pages/RoleMarketing";
import RoleSales from "../pages/RoleSales";
import RoleProduct from "../pages/RoleProduct";
import ArchitectPage from "../pages/ArchitectWorkbenchPage";
import ScenarioEntryPage from "../pages/ScenarioEntryPage";
import { isShowroomAccount } from "../auth/entryRoute";

function ShowroomRedirect() {
  const { isAuthenticated } = useAuth();
  return <Navigate to={isAuthenticated ? "/scenarios" : "/login?next=/scenarios"} replace />;
}

export default function App() {
  const { isAuthenticated, authSession } = useAuth();

  return (
    <Routes>
      <Route
        path="/"
        element={<Navigate to={isAuthenticated ? (isShowroomAccount(authSession?.user) ? "/scenarios" : "/orchestration") : "/login"} replace />}
      />
      <Route path="/login" element={<LoginPage />} />
      <Route path="/showroom/*" element={<ShowroomRedirect />} />
      <Route element={<ProtectedRoute />}>
        <Route path="/architect" element={<ArchitectPage />} />
        <Route path="/scenarios" element={<ScenarioEntryPage />} />
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
        element={<Navigate to={isAuthenticated ? "/orchestration" : "/login"} replace />}
      />
    </Routes>
  );
}
