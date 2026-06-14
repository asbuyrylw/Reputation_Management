"use client";

// Auth context: holds the JWT + current user, exposes login/logout, and rehydrates
// on reload via GET /auth/me. NOTE (Phase 5 hardening): the token lives in
// localStorage for local-first simplicity; move to an httpOnly refresh cookie before
// any hosted/multi-user deployment.

import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { apiFetch } from "./api";
import type { User } from "./types";

const TOKEN_KEY = "rc_token";

interface AuthState {
  user: User | null;
  token: string | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthCtx = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [token, setToken] = useState<string | null>(null);
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const t = typeof window !== "undefined" ? localStorage.getItem(TOKEN_KEY) : null;
    if (!t) {
      setLoading(false);
      return;
    }
    setToken(t);
    apiFetch<User>("/auth/me", { token: t })
      .then((u) => setUser(u))
      .catch(() => {
        localStorage.removeItem(TOKEN_KEY);
        setToken(null);
      })
      .finally(() => setLoading(false));
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const r = await apiFetch<{ access_token: string; user: User }>("/auth/login", {
      method: "POST",
      body: { email, password },
    });
    localStorage.setItem(TOKEN_KEY, r.access_token);
    setToken(r.access_token);
    setUser(r.user);
  }, []);

  const logout = useCallback(() => {
    localStorage.removeItem(TOKEN_KEY);
    setToken(null);
    setUser(null);
  }, []);

  return (
    <AuthCtx.Provider value={{ user, token, loading, login, logout }}>
      {children}
    </AuthCtx.Provider>
  );
}

export function useAuth(): AuthState {
  const c = useContext(AuthCtx);
  if (!c) throw new Error("useAuth must be used within <AuthProvider>");
  return c;
}
