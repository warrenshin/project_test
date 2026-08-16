"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useAuth, ApiError } from "@/lib/auth-context";

export default function LoginPage() {
  const { login } = useAuth();
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await login(email, password);
      router.push("/");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "로그인에 실패했습니다.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="page" style={{ paddingTop: 48 }}>
      <div className="card stack">
        <div>
          <h1>투자 연습</h1>
          <p className="muted">가상자금으로 배우는 AI 투자교육·모의투자 앱</p>
        </div>
        <div className="banner banner-info">
          이 앱은 교육·모의투자 서비스입니다. 실제 자금을 입출금하거나 실제 증권 주문을
          접수하지 않습니다.
        </div>
        <form onSubmit={handleSubmit} className="stack">
          <div className="field">
            <label htmlFor="email">이메일</label>
            <input
              id="email"
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              autoComplete="email"
            />
          </div>
          <div className="field">
            <label htmlFor="password">비밀번호</label>
            <input
              id="password"
              type="password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
            />
          </div>
          {error && (
            <div className="banner banner-danger" role="alert">
              {error}
            </div>
          )}
          <button type="submit" className="btn btn-primary btn-block" disabled={submitting}>
            {submitting ? "로그인 중..." : "로그인"}
          </button>
        </form>
        <p className="muted" style={{ textAlign: "center" }}>
          계정이 없으신가요? <Link href="/signup">회원가입</Link>
        </p>
      </div>
    </main>
  );
}
