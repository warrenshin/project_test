"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useAuth, ApiError } from "@/lib/auth-context";

export default function SignupPage() {
  const { signup } = useAuth();
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [birthDate, setBirthDate] = useState("");
  const [agreedTerms, setAgreedTerms] = useState(false);
  const [agreedPrivacy, setAgreedPrivacy] = useState(false);
  const [marketingOptIn, setMarketingOptIn] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const canSubmit = email && password.length >= 8 && birthDate && agreedTerms && agreedPrivacy;

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (!canSubmit) {
      setError("필수 항목을 모두 입력하고 이용약관·개인정보 처리방침에 동의해주세요.");
      return;
    }
    setSubmitting(true);
    try {
      await signup({ email, password, birth_date: birthDate, marketingOptIn });
      router.push("/");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "회원가입에 실패했습니다.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="page" style={{ paddingTop: 48 }}>
      <div className="card stack">
        <div>
          <h1>회원가입</h1>
          <p className="muted">가상자금으로 시작하는 모의투자 · 만 14세 미만은 가입할 수 없습니다.</p>
        </div>
        <form onSubmit={handleSubmit} className="stack">
          <div className="field">
            <label htmlFor="email">이메일</label>
            <input id="email" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
          </div>
          <div className="field">
            <label htmlFor="password">비밀번호 (8자 이상)</label>
            <input
              id="password"
              type="password"
              required
              minLength={8}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </div>
          <div className="field">
            <label htmlFor="birthDate">생년월일</label>
            <input
              id="birthDate"
              type="date"
              required
              value={birthDate}
              onChange={(e) => setBirthDate(e.target.value)}
            />
          </div>
          <div className="field stack">
            <label className="row" style={{ fontWeight: 400 }}>
              <input
                type="checkbox"
                style={{ width: "auto" }}
                checked={agreedTerms}
                onChange={(e) => setAgreedTerms(e.target.checked)}
              />
              (필수) 이용약관에 동의합니다
            </label>
            <label className="row" style={{ fontWeight: 400 }}>
              <input
                type="checkbox"
                style={{ width: "auto" }}
                checked={agreedPrivacy}
                onChange={(e) => setAgreedPrivacy(e.target.checked)}
              />
              (필수) 개인정보 처리방침에 동의합니다
            </label>
            <label className="row" style={{ fontWeight: 400 }}>
              <input
                type="checkbox"
                style={{ width: "auto" }}
                checked={marketingOptIn}
                onChange={(e) => setMarketingOptIn(e.target.checked)}
              />
              (선택) 마케팅 정보 수신에 동의합니다
            </label>
          </div>
          {error && (
            <div className="banner banner-danger" role="alert">
              {error}
            </div>
          )}
          <button type="submit" className="btn btn-primary btn-block" disabled={submitting}>
            {submitting ? "가입 처리 중..." : "가상자금으로 시작하기"}
          </button>
        </form>
        <p className="muted" style={{ textAlign: "center" }}>
          이미 계정이 있으신가요? <Link href="/login">로그인</Link>
        </p>
      </div>
    </main>
  );
}
