import { createContext, useContext, useEffect, useMemo, useState } from "react";
import { clearWorkspaceDraft } from "./storage";
import { clearAuthSession, loadAuthSession, saveAuthSession } from "./storage";
import { platformApi } from "../services/platformApi";

const AuthContext = createContext(null);

const getSessionScopeKey = (session) =>
  session?.user?.tenant_key || session?.user?.user_id || session?.identifier || "default";

const buildAuthSession = ({ accessToken = "", identifier = "", mode = "token", user }) => ({
  accessToken,
  identifier: identifier || user?.username || user?.user_id || "dev",
  mode,
  user,
});

export function AuthProvider({ children }) {
  const [authSession, setAuthSession] = useState(null);
  const [isReady, setIsReady] = useState(false);

  useEffect(() => {
    let active = true;

    const restoreSession = async () => {
      const storedSession = loadAuthSession();
      if (!storedSession) {
        if (active) {
          setIsReady(true);
        }
        return;
      }

      try {
        const user = await platformApi.getSessionMe({
          accessToken: storedSession.accessToken ?? "",
          skipSessionAuth: true,
        });
        if (active) {
          setAuthSession(
            buildAuthSession({
              accessToken: storedSession.accessToken ?? "",
              identifier: storedSession.identifier ?? "",
              mode: storedSession.mode ?? (storedSession.accessToken ? "token" : "dev"),
              user,
            }),
          );
        }
      } catch {
        clearAuthSession();
      } finally {
        if (active) {
          setIsReady(true);
        }
      }
    };

    restoreSession();
    return () => {
      active = false;
    };
  }, []);

  const login = async ({ identifier, password }) => {
    const accessToken = await platformApi.authenticate({ identifier, password });
    const user = await platformApi.getSessionMe({
      accessToken,
      skipSessionAuth: true,
    });
    const session = buildAuthSession({
      accessToken,
      identifier,
      mode: "token",
      user,
    });
    saveAuthSession(session);
    setAuthSession(session);
    return session;
  };

  const loginWithPhone = async ({ phone, code }) => {
    const accessToken = await platformApi.authenticatePhone({ phone, code });
    const user = await platformApi.getSessionMe({ accessToken, skipSessionAuth: true });
    const session = buildAuthSession({
      accessToken,
      identifier: phone,
      mode: "phone",
      user,
    });
    saveAuthSession(session);
    setAuthSession(session);
    return session;
  };

  const loginWithOAuthTicket = async ({ ticket }) => {
    const accessToken = await platformApi.completeOAuth({ ticket });
    const user = await platformApi.getSessionMe({ accessToken, skipSessionAuth: true });
    const session = buildAuthSession({
      accessToken,
      identifier: user?.username || "oauth-user",
      mode: "oauth",
      user,
    });
    saveAuthSession(session);
    setAuthSession(session);
    return session;
  };

  const loginWithToken = async ({ accessToken, identifier = "token-user" }) => {
    const user = await platformApi.getSessionMe({
      accessToken,
      skipSessionAuth: true,
    });
    const session = buildAuthSession({
      accessToken,
      identifier,
      mode: "token",
      user,
    });
    saveAuthSession(session);
    setAuthSession(session);
    return session;
  };

  const loginDev = async () => {
    const user = await platformApi.getSessionMe({
      accessToken: "",
      skipSessionAuth: true,
    });
    const session = buildAuthSession({
      accessToken: "",
      identifier: user?.username || "dev",
      mode: "dev",
      user,
    });
    saveAuthSession(session);
    setAuthSession(session);
    return session;
  };

  const logout = () => {
    clearWorkspaceDraft(getSessionScopeKey(authSession));
    clearAuthSession();
    setAuthSession(null);
  };

  const value = useMemo(
    () => ({
      authSession,
      isAuthenticated: Boolean(authSession),
      isReady,
      login,
      loginWithPhone,
      loginWithOAuthTicket,
      loginWithToken,
      loginDev,
      logout,
      sessionScopeKey: getSessionScopeKey(authSession),
    }),
    [authSession, isReady],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}
