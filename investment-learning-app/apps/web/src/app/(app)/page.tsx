"use client";

import Link from "next/link";
import { useAuth } from "@/lib/auth-context";
import { ApiError, getActiveUserChallenge, getLearningPaths, getLearningSummary } from "@/lib/api";
import { useAsync } from "@/lib/useAsync";
import { LoadingBlock, ErrorBlock } from "@/components/States";
import { VirtualFundsBanner } from "@/components/VirtualFundsBanner";
import { NotificationList } from "@/components/NotificationList";
import type { LessonSummary, UserChallengeResponse } from "@/lib/types";

async function loadActiveChallengeOrNull(): Promise<UserChallengeResponse | null> {
  try {
    return await getActiveUserChallenge();
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) return null;
    throw err;
  }
}

function ChallengeWidget() {
  const challenge = useAsync(loadActiveChallengeOrNull, []);

  if (challenge.loading) return null;
  if (challenge.error) return null; // 홈 화면 핵심 흐름을 막지 않는다 — 위젯 하나 실패로 홈 전체를 에러로 만들지 않는다.

  if (!challenge.data) {
    return (
      <div className="card">
        <h2>7일 학습 챌린지</h2>
        <p className="muted">학습·퀴즈·투자일지·모의투자를 하나로 이어주는 7일 챌린지를 시작해보세요.</p>
        <Link href="/challenge" className="btn btn-primary btn-block">
          챌린지 시작하기
        </Link>
      </div>
    );
  }

  const uc = challenge.data;
  if (uc.status === "COMPLETED") {
    return (
      <div className="card">
        <h2>7일 챌린지</h2>
        <p className="muted">🎉 7일 챌린지를 완주했습니다. 획득 XP {uc.total_xp_earned}</p>
        <Link href="/badges" className="btn btn-block">
          내 배지 보기
        </Link>
      </div>
    );
  }

  const today = uc.days.find((d) => d.day_number === uc.current_day);
  const todaysCompleted = today ? today.missions.filter((m) => m.completed).length : 0;
  const todaysTotal = today ? today.missions.length : 0;
  const completedDays = uc.days.filter((d) => d.status === "COMPLETED").length;

  return (
    <div className="card">
      <h2>7일 챌린지 · Day {uc.current_day}/{uc.total_days}</h2>
      <div className="stack">
        <p className="muted" style={{ margin: 0 }}>
          오늘 미션 {todaysCompleted}/{todaysTotal}개 완료 · 지금까지 {completedDays}일 완료
        </p>
        <div className="progress-track">
          <div className="progress-fill" style={{ width: `${Math.round((completedDays / uc.total_days) * 100)}%` }} />
        </div>
        {uc.next_action && <p style={{ margin: 0 }}>다음 할 일: <strong>{uc.next_action.title}</strong></p>}
        <Link href="/challenge" className="btn btn-primary btn-block">
          이어하기
        </Link>
      </div>
    </div>
  );
}

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
      <NotificationList />
      <ChallengeWidget />

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
