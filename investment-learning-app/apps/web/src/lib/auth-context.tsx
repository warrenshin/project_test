"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import {
  ApiError,
  getMe,
  getMyPortfolio,
  login as apiLogin,
  logout as apiLogout,
  purgeLegacyLocalStorageTokens,
  setAuthFailureHandler,
  signup as apiSignup,
} from "./api";
import type { PortfolioResponse, UserResponse } from "./types";

interface AuthContextValue {
  status: "loading" | "authenticated" | "unauthenticated";
  user: UserResponse | null;
  portfolio: PortfolioResponse | null;
  refreshPortfolio: () => Promise<void>;
  login: (email: string, password: string) => Promise<void>;
  signup: (payload: {
    email: string;
    password: string;
    birth_date: string;
    marketingOptIn: boolean;
  }) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [status, setStatus] = useState<"loading" | "authenticated" | "unauthenticated">("loading");
  const [user, setUser] = useState<UserResponse | null>(null);
  const [portfolio, setPortfolio] = useState<PortfolioResponse | null>(null);
  const router = useRouter();

  const loadPortfolio = useCallback(async () => {
    const p = await getMyPortfolio();
    setPortfolio(p);
    return p;
  }, []);

  const clearLocalAuthState = useCallback(() => {
    setUser(null);
    setPortfolio(null);
    setStatus("unauthenticated");
  }, []);

  // 인증 쿠키는 HttpOnly라 JS로 존재 여부를 알 수 없다 — 마운트 시 항상 서버에
  // /v1/auth/me로 물어봐서 로그인 상태를 확정한다. 초기 상태는 "loading"으로
  // 고정해 서버/클라이언트 첫 렌더가 항상 일치하게 한다.
  useEffect(() => {
    purgeLegacyLocalStorageTokens();

    let cancelled = false;
    getMe()
      .then((me) => {
        if (cancelled) return;
        setUser(me);
        return loadPortfolio();
      })
      .then(() => {
        if (!cancelled) setStatus("authenticated");
      })
      .catch(() => {
        if (!cancelled) clearLocalAuthState();
      });
    return () => {
      cancelled = true;
    };
  }, [loadPortfolio, clearLocalAuthState]);

  // access token refresh까지 실패하면(=재로그인이 필요하면) api.ts가 이 핸들러를
  // 호출한다. 무한 재시도 대신 즉시 로그아웃 상태로 전환해 로그인 화면으로 보낸다.
  useEffect(() => {
    setAuthFailureHandler(() => {
      clearLocalAuthState();
    });
    return () => setAuthFailureHandler(null);
  }, [clearLocalAuthState]);

  // 로그아웃 후 브라우저 뒤로가기로 bfcache에서 이전 화면이 그대로 복원되는 것을
  // 막는다 — 복원 시(event.persisted) 인증 상태를 다시 확인해, 이미 로그아웃된
  // 상태라면 보호된 화면 대신 로그인 화면으로 보낸다.
  useEffect(() => {
    function handlePageShow(event: PageTransitionEvent) {
      if (!event.persisted) return;
      getMe()
        .then((me) => {
          setUser(me);
          return loadPortfolio();
        })
        .then(() => setStatus("authenticated"))
        .catch(() => clearLocalAuthState());
    }
    window.addEventListener("pageshow", handlePageShow);
    return () => window.removeEventListener("pageshow", handlePageShow);
  }, [loadPortfolio, clearLocalAuthState]);

  const login = useCallback(
    async (email: string, password: string) => {
      const me = await apiLogin({ email, password });
      setUser(me);
      await loadPortfolio();
      setStatus("authenticated");
    },
    [loadPortfolio]
  );

  const signup = useCallback(
    async (payload: { email: string; password: string; birth_date: string; marketingOptIn: boolean }) => {
      const me = await apiSignup({
        email: payload.email,
        password: payload.password,
        birth_date: payload.birth_date,
        consents: [
          { consent_type: "TERMS", version: "v1", agreed: true },
          { consent_type: "PRIVACY", version: "v1", agreed: true },
          { consent_type: "MARKETING", version: "v1", agreed: payload.marketingOptIn },
        ],
      });
      setUser(me);
      await loadPortfolio();
      setStatus("authenticated");
    },
    [loadPortfolio]
  );

  const logout = useCallback(() => {
    // 서버에 알리기 전에 먼저 로컬 상태부터 지워 화면이 즉시 반응하게 한다.
    // 서버 호출이 실패해도(네트워크 오류 등) 사용자 관점에서는 이미 로그아웃된
    // 것으로 보여야 하므로 실패를 굳이 사용자에게 노출하지 않는다.
    clearLocalAuthState();
    apiLogout().catch(() => {});
    router.push("/login");
  }, [router, clearLocalAuthState]);

  const refreshPortfolio = useCallback(async () => {
    await loadPortfolio();
  }, [loadPortfolio]);

  const value = useMemo(
    () => ({ status, user, portfolio, refreshPortfolio, login, signup, logout }),
    [status, user, portfolio, refreshPortfolio, login, signup, logout]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}

export { ApiError };
