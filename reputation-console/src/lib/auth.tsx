"use client";

// Cookie-based session: the API sets an httpOnly session cookie + a CSRF cookie on
// login. There is NO token in JS (defends against XSS token theft). The session is
// rehydrated on load via GET /auth/me (the cookie is sent automatically).

import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { apiFetch } from "./api";
import type { User } from "./types";

interface AuthState {
  user: User | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthCtx = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    apiFetch<User>("/auth/me")
      .then((u) => setUser(u))
      .catch(() => setUser(null))
      .finally(() => setLoading(false));
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const r = await apiFetch<{ user: User }>("/auth/login", { method: "POST", body: { email, password } });
    setUser(r.user);
  }, []);

  const logout = useCallback(async () => {
    try {
      await apiFetch("/auth/logout", { method: "POST" });
    } catch {
      /* clear locally regardless */
    }
    setUser(null);
  }, []);

  return <AuthCtx.Provider value={{ user, loading, login, logout }}>{children}</AuthCtx.Provider>;
}

export function useAuth(): AuthState {
  const c = useContext(AuthCtx);
  if (!c) throw new Error("useAuth must be used within <AuthProvider>");
  return c;
}
