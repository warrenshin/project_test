"use client";

import Link from "next/link";
import { useAuth } from "@/lib/auth-context";
import { getLearningPaths, getLearningSummary } from "@/lib/api";
import { useAsync } from "@/lib/useAsync";
import { LoadingBlock, ErrorBlock } from "@/components/States";
import { VirtualFundsBanner } from "@/components/VirtualFundsBanner";
import type { LessonSummary } from "@/lib/types";

function firstLesson(paths: Awaited<ReturnType<typeof getLearningPaths>>): LessonSummary | null {
  for (const path of paths) {
    for (const course of path.courses) {
      for (const mod of course.modules) {
        if (mod.lessons.length > 0) return mod.lessons[0];
      }
    }
  }
  return null;
}

export default function HomePage() {
  const { portfolio, refreshPortfolio } = useAuth();
  const home = useAsync(
    () => Promise.all([getLearningPaths(), getLearningSummary()]),
    []
  );

  if (home.loading) return <LoadingBlock label="홈 화면을 불러오는 중입니다..." />;
  if (home.error) return <ErrorBlock message={home.error} onRetry={home.reload} />;

  const [paths, summary] = home.data!;
  const nextLesson = firstLesson(paths);

  return (
    <div className="stack">
      <h1>안녕하세요 👋</h1>
      <VirtualFundsBanner />

      <div className="card">
        <h2>내 포트폴리오</h2>
        {portfolio ? (
          <div className="stack">
            <div className="row-between">
              <span className="muted">총 자산</span>
              <strong>{Number(portfolio.total_assets).toLocaleString()} {portfolio.base_currency}</strong>
            </div>
            <div className="row-between">
              <span className="muted">가상현금</span>
              <span>{Number(portfolio.cash_balance).toLocaleString()} {portfolio.base_currency}</span>
            </div>
            <div className="row-between">
              <span className="muted">평가금액</span>
              <span>{Number(portfolio.positions_market_value).toLocaleString()} {portfolio.base_currency}</span>
            </div>
            <Link href="/portfolio" className="btn btn-block">
              포트폴리오 자세히 보기
            </Link>
          </div>
        ) : (
          <button className="btn" onClick={() => refreshPortfolio()} type="button">
            포트폴리오 불러오기
          </button>
        )}
      </div>

      <div className="card">
        <h2>오늘의 학습</h2>
        <div className="stack">
          <div className="row" style={{ flexWrap: "wrap" }}>
            <span className="badge badge-virtual">누적 XP {summary.total_xp}</span>
            <span className="badge badge-virtual">연속 학습 {summary.current_streak_days}일</span>
          </div>
          <p className="muted" style={{ margin: 0 }}>
            완료한 강의 {summary.lessons_completed}개 · 통과한 퀴즈 {summary.quizzes_passed}개
          </p>
          {nextLesson ? (
            <Link href={`/learn/${nextLesson.id}`} className="btn btn-primary btn-block">
              {nextLesson.title} 학습하기
            </Link>
          ) : (
            <Link href="/learn" className="btn btn-block">
              학습 목록 보기
            </Link>
          )}
        </div>
      </div>

      <div className="card">
        <h2>모의투자 시작하기</h2>
        <p className="muted">관심 있는 종목을 검색하고 투자일지를 작성한 뒤 가상으로 매수해보세요.</p>
        <Link href="/market" className="btn btn-block">
          종목 검색하기
        </Link>
      </div>
    </div>
  );
}
