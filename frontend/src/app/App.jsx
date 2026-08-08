import { Navigate, Route, Routes } from "react-router-dom";
import { ProtectedRoute } from "../components/ProtectedRoute";
import { useAuth } from "../auth/AuthContext";
import { LoginPage } from "../pages/LoginPage";
import { OrchestrationPage } from "../pages/OrchestrationPage";

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
      </Route>
      <Route
        path="*"
        element={<Navigate to={isAuthenticated ? "/orchestration" : "/login"} replace />}
      />
    </Routes>
  );
}
