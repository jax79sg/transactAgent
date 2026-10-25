import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";

import { login as apiLogin } from "../api/auth";
import { registerAuthHandlers, setToken } from "../api/client";

const SESSION_STORAGE_KEY = "transactagent_token"; // Question 1 = C: sessionStorage

interface AuthContextValue {
  token: string | null;
  isAuthenticated: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setTokenState] = useState<string | null>(() => {
    const saved = sessionStorage.getItem(SESSION_STORAGE_KEY);
    // The API client needs the token before this component's effects run: React runs a child's effects first, so a
    // page's first requests would otherwise go out without it, get a 401, and the 401 handler would sign the user
    // out on every full page load (reload, or opening a link in a signed-in tab). Setting it is idempotent.
    setToken(saved);
    return saved;
  });

  const logout = useCallback(() => {
    sessionStorage.removeItem(SESSION_STORAGE_KEY);
    setTokenState(null);
    setToken(null);
  }, []);

  useEffect(() => {
    // Centralized 401 handling (business-logic-model.md): any API call anywhere in
    // the app that gets a 401 clears the session, here, once.
    registerAuthHandlers(() => token, logout);
  }, [token, logout]);

  useEffect(() => {
    setToken(token);
  }, [token]);

  const login = useCallback(async (username: string, password: string) => {
    const response = await apiLogin(username, password);
    sessionStorage.setItem(SESSION_STORAGE_KEY, response.token);
    setTokenState(response.token);
  }, []);

  return (
    <AuthContext.Provider value={{ token, isAuthenticated: token !== null, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within an AuthProvider");
  return ctx;
}
