import { Navigate, Route, Routes } from "react-router-dom";
import { ProtectedRoute } from "../components/ProtectedRoute";
import { useAuth } from "../auth/AuthContext";
import { LoginPage } from "../pages/LoginPage";
import { OrchestrationPage } from "../pages/OrchestrationPage";
import RoleInsight from "../pages/RoleInsight";
import RoleEngineering from "../pages/RoleEngineering";
import RoleFounder from "../pages/RoleFounder";
import RoleMarketing from "../pages/RoleMarketing";
import RoleSales from "../pages/RoleSales";
// fallback for product which didn't have specific html design
import RoleProduct from "../pages/RoleInsight";

export default function App() {
  const { isAuthenticated } = useAuth();

  return (
    <Routes>
      <Route
        path="/"
        element={<Navigate to={isAuthenticated ? "/orchestration" : "/login"} replace />}
      />
      <Route path="/login" element={<LoginPage />} />
      <Route element={<ProtectedRoute />}>
        <Route path="/orchestration" element={<OrchestrationPage />} />
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
