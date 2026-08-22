"use client";

import {
  createContext, useCallback, useContext, useEffect, useMemo, useRef, useState,
} from "react";
import { useRouter, usePathname } from "next/navigation";
import {
  login as apiLogin,
  logout as apiLogout,
  me as apiMe,
  register as apiRegister,
  setUnauthenticatedHandler,
  type AuthUser,
} from "@/lib/api";

/**
 * The client's entire authentication model: one question, asked once.
 *
 * The cookie is `HttpOnly`, so nothing here can read it — which is the point,
 * and which also means the client cannot decide for itself whether it is signed
 * in. It asks the server once (`GET /auth/me`) and holds the answer. The server
 * is always the authority; this is a cache of one boolean's worth of state.
 *
 * `"loading"` is a real state, not a nicety. Without it every guarded page
 * renders its signed-out branch for one frame before the answer arrives, so a
 * returning learner sees the login screen flash on every cold load.
 */
export type AuthState = AuthUser | null | "loading";

interface AuthContextValue {
  user: AuthUser | null;
  status: "loading" | "authenticated" | "anonymous";
  signIn: (email: string, password: string) => Promise<void>;
  signUp: (email: string, password: string, displayName?: string) => Promise<void>;
  signOut: () => Promise<void>;
  /** Re-ask the server. For after an action that may have changed the session. */
  refresh: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

/** Where an interrupted visit is remembered, so login can return the learner to it. */
export const NEXT_PARAM = "next";

/** Routes a signed-out visitor may see. Everything else redirects to /login. */
const PUBLIC_PATHS = new Set(["/login", "/signup"]);

export function isPublicPath(pathname: string): boolean {
  return PUBLIC_PATHS.has(pathname);
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<AuthState>("loading");
  const router = useRouter();
  const pathname = usePathname();

  // Read inside the 401 handler without making it depend on the current path —
  // the handler is registered once, and a dependency on `pathname` would
  // re-register it on every navigation.
  const pathRef = useRef(pathname);
  pathRef.current = pathname;

  const refresh = useCallback(async () => {
    try {
      setState(await apiMe());
    } catch {
      // The server is unreachable. NOT the same as signed out, and the
      // difference matters: treating it as signed out would bounce a learner to
      // the login screen every time the backend restarted, where they would
      // enter correct credentials and be told the server is down anyway.
      setState(null);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  /**
   * ONE reaction to a 401, for every endpoint in the app.
   *
   * Registered against the api module rather than wrapped around each call, so a
   * session that expires mid-lesson lands the learner on the login screen with
   * `?next=` pointing back at the lesson — from wherever they happened to be,
   * including calls added later that know nothing about auth.
   */
  useEffect(() => {
    setUnauthenticatedHandler(() => {
      setState(null);
      const here = pathRef.current ?? "/";
      if (isPublicPath(here)) return;
      router.replace(`/login?${NEXT_PARAM}=${encodeURIComponent(here)}`);
    });
    return () => setUnauthenticatedHandler(null);
  }, [router]);

  const value = useMemo<AuthContextValue>(() => ({
    user: state === "loading" ? null : state,
    status:
      state === "loading" ? "loading" : state ? "authenticated" : "anonymous",
    signIn: async (email, password) => {
      setState(await apiLogin(email, password));
    },
    signUp: async (email, password, displayName) => {
      setState(await apiRegister(email, password, displayName));
    },
    signOut: async () => {
      await apiLogout();
      setState(null);
      router.replace("/login");
    },
    refresh,
  }), [state, refresh, router]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (context === null) {
    throw new Error("useAuth must be used inside <AuthProvider>");
  }
  return context;
}
