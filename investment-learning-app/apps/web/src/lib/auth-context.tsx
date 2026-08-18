"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { ApiError, clearTokens, getMyPortfolio, getStoredTokens, login as apiLogin, signup as apiSignup, storeTokens } from "./api";
import type { PortfolioResponse, TokenResponse } from "./types";

interface AuthContextValue {
  status: "loading" | "authenticated" | "unauthenticated";
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
  const [portfolio, setPortfolio] = useState<PortfolioResponse | null>(null);
  const router = useRouter();

  const loadPortfolio = useCallback(async () => {
    const p = await getMyPortfolio();
    setPortfolio(p);
    return p;
  }, []);

  // 마운트 시 1회 저장된 토큰의 유효성을 외부 API로 확인하는 부트스트랩 effect다.
  // 초기 상태를 "loading"으로 고정해 서버/클라이언트 첫 렌더가 항상 일치하도록 하고
  // (localStorage는 클라이언트에만 존재), 실제 인증 상태 확정은 이 effect에서만 한다.
  /* eslint-disable react-hooks/set-state-in-effect -- 마운트 1회성 부트스트랩이며 즉시 재귀 렌더를 유발하지 않는다 */
  useEffect(() => {
    const { accessToken } = getStoredTokens();
    if (!accessToken) {
      setStatus("unauthenticated");
      return;
    }
    loadPortfolio()
      .then(() => setStatus("authenticated"))
      .catch(() => {
        clearTokens();
        setStatus("unauthenticated");
      });
  }, [loadPortfolio]);
  /* eslint-enable react-hooks/set-state-in-effect */

  const afterAuth = useCallback(
    async (tokens: TokenResponse) => {
      storeTokens(tokens);
      await loadPortfolio();
      setStatus("authenticated");
    },
    [loadPortfolio]
  );

  const login = useCallback(
    async (email: string, password: string) => {
      const tokens = await apiLogin({ email, password });
      await afterAuth(tokens);
    },
    [afterAuth]
  );

  const signup = useCallback(
    async (payload: { email: string; password: string; birth_date: string; marketingOptIn: boolean }) => {
      const tokens = await apiSignup({
        email: payload.email,
        password: payload.password,
        birth_date: payload.birth_date,
        consents: [
          { consent_type: "TERMS", version: "v1", agreed: true },
          { consent_type: "PRIVACY", version: "v1", agreed: true },
          { consent_type: "MARKETING", version: "v1", agreed: payload.marketingOptIn },
        ],
      });
      await afterAuth(tokens);
    },
    [afterAuth]
  );

  const logout = useCallback(() => {
    clearTokens();
    setPortfolio(null);
    setStatus("unauthenticated");
    router.push("/login");
  }, [router]);

  const refreshPortfolio = useCallback(async () => {
    await loadPortfolio();
  }, [loadPortfolio]);

  const value = useMemo(
    () => ({ status, portfolio, refreshPortfolio, login, signup, logout }),
    [status, portfolio, refreshPortfolio, login, signup, logout]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}

export { ApiError };
