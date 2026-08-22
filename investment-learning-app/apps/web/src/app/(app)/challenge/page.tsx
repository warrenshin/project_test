"use client";

import Link from "next/link";
import { useState } from "react";
import { useAuth } from "@/lib/auth-context";
import {
  ApiError,
  getActiveUserChallenge,
  getChallengeDetail,
  getChallenges,
  startChallenge,
} from "@/lib/api";
import { useAsync } from "@/lib/useAsync";
import { LoadingBlock, ErrorBlock } from "@/components/States";
import { MissionActionForm } from "@/components/MissionActionForm";
import type {
  ChallengeDayStatus,
  ChallengeDetailResponse,
  MissionVerifyResponse,
  UserChallengeDayResponse,
  UserChallengeResponse,
} from "@/lib/types";

const DAY_STATUS_ICON: Record<ChallengeDayStatus, string> = {
  LOCKED: "🔒",
  AVAILABLE: "▶️",
  IN_PROGRESS: "🟡",
  COMPLETED: "✅",
};

const DAY_STATUS_LABEL: Record<ChallengeDayStatus, string> = {
  LOCKED: "잠김",
  AVAILABLE: "시작 전",
  IN_PROGRESS: "진행 중",
  COMPLETED: "완료",
};

async function loadActiveOrNull(): Promise<UserChallengeResponse | null> {
  try {
    return await getActiveUserChallenge();
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) return null;
    throw err;
  }
}

export default function ChallengePage() {
  const active = useAsync(loadActiveOrNull, []);
  // 미션 완료 직후 배지·XP 배너를 보여줘야 하는데, 매번 새로고침 때마다
  // 전체 화면을 로딩 스피너로 덮어버리면(useAsync가 재조회 중 loading을
  // true로 돌리므로) ActiveChallengeView가 언마운트되면서 방금 띄운 배너
  // state가 사라진다. 최초 진입 때만 전체 로딩 화면을 보여주고, 이후
  // 재조회(reload)는 기존 화면을 유지한 채 조용히 갱신되게 한다.
  const [hasLoadedOnce, setHasLoadedOnce] = useState(false);
  const [prevLoading, setPrevLoading] = useState(active.loading);
  if (active.loading !== prevLoading) {
    setPrevLoading(active.loading);
    if (!active.loading) setHasLoadedOnce(true);
  }

  if (active.loading && !hasLoadedOnce) {
    return <LoadingBlock label="챌린지 정보를 불러오는 중입니다..." />;
  }
  if (active.error) return <ErrorBlock message={active.error} onRetry={active.reload} />;

  if (!active.data) {
    return <ChallengeIntro onStarted={active.reload} />;
  }

  return <ActiveChallengeView userChallenge={active.data} onReload={active.reload} />;
}

function ChallengeIntro({ onStarted }: { onStarted: () => void }) {
  const detail = useAsync<ChallengeDetailResponse>(async () => {
    const list = await getChallenges();
    if (list.length === 0) throw new ApiError(404, "이용 가능한 챌린지가 없습니다.");
    return getChallengeDetail(list[0].id);
  }, []);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (detail.loading) return <LoadingBlock label="챌린지 소개를 불러오는 중입니다..." />;
  if (detail.error) return <ErrorBlock message={detail.error} onRetry={detail.reload} />;
  const challenge = detail.data!;

  async function handleStart() {
    setStarting(true);
    setError(null);
    try {
      await startChallenge(challenge.id);
      onStarted();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "챌린지를 시작하지 못했습니다.");
    } finally {
      setStarting(false);
    }
  }

  return (
    <div className="stack">
      <h1>{challenge.title}</h1>
      <div className="card">
        <p style={{ margin: 0 }}>{challenge.description}</p>
      </div>

      <div className="card">
        <h2>{challenge.total_days}일 동안 하는 일</h2>
        <div className="stack">
          {challenge.days.map((day) => (
            <div key={day.day_number} className="day-row">
              <span className="day-status-icon">Day {day.day_number}</span>
              <div>
                <strong>{day.title}</strong>
                {day.description && (
                  <p className="muted" style={{ margin: "2px 0 0" }}>
                    {day.description}
                  </p>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="banner banner-info">
        수익률이나 거래 횟수는 어디에도 점수로 반영되지 않습니다. 학습을 끝내고,
        퀴즈를 통과하고, 일지를 성실히 쓰고, 복기하는 &ldquo;과정&rdquo; 자체가 보상 대상입니다.
      </div>

      <button className="btn btn-primary btn-block" onClick={handleStart} disabled={starting} type="button">
        {starting ? "시작하는 중..." : "7일 챌린지 시작하기"}
      </button>
      {error && <ErrorBlock message={error} />}
    </div>
  );
}

function ActiveChallengeView({
  userChallenge,
  onReload,
}: {
  userChallenge: UserChallengeResponse;
  onReload: () => void;
}) {
  const { portfolio } = useAuth();
  const [expandedDay, setExpandedDay] = useState<number>(userChallenge.current_day);
  const [banner, setBanner] = useState<MissionVerifyResponse | null>(null);

  const progressPct = Math.round(
    (userChallenge.days.filter((d) => d.status === "COMPLETED").length / userChallenge.total_days) * 100
  );

  function handleVerified(result: MissionVerifyResponse) {
    setBanner(result);
    onReload();
  }

  if (userChallenge.status === "COMPLETED") {
    return (
      <div className="stack">
        <div className="card stack" style={{ textAlign: "center" }}>
          <h1>🎉 7일 챌린지를 완주했습니다!</h1>
          <p className="muted">투자 논리를 세우고, 반대 근거를 찾고, 복기하는 습관을 7일간 이어왔습니다.</p>
          <p>누적 획득 XP: <strong>{userChallenge.total_xp_earned}</strong></p>
          <Link href="/badges" className="btn btn-primary btn-block">
            내 배지 보기
          </Link>
        </div>
        <DayMap
          userChallenge={userChallenge}
          expandedDay={expandedDay}
          setExpandedDay={setExpandedDay}
          onVerified={handleVerified}
          portfolioId={portfolio?.id ?? null}
        />
      </div>
    );
  }

  return (
    <div className="stack">
      <h1>{userChallenge.challenge_title}</h1>

      {banner && <MissionResultBanner result={banner} onDismiss={() => setBanner(null)} />}

      <div className="card stack">
        <div className="row-between">
          <span>Day {userChallenge.current_day} / {userChallenge.total_days}</span>
          <span className="badge badge-virtual">누적 XP {userChallenge.total_xp_earned}</span>
        </div>
        <div className="progress-track" role="progressbar" aria-valuenow={progressPct} aria-valuemin={0} aria-valuemax={100}>
          <div className="progress-fill" style={{ width: `${progressPct}%` }} />
        </div>
        <p className="muted" style={{ margin: 0 }}>완료한 Day {userChallenge.days.filter((d) => d.status === "COMPLETED").length}개 / {userChallenge.total_days}개</p>
        {userChallenge.next_action && (
          <p style={{ margin: 0 }}>다음 할 일: <strong>{userChallenge.next_action.title}</strong></p>
        )}
      </div>

      <DayMap
        userChallenge={userChallenge}
        expandedDay={expandedDay}
        setExpandedDay={setExpandedDay}
        onVerified={handleVerified}
        portfolioId={portfolio?.id ?? null}
      />
    </div>
  );
}

function MissionResultBanner({
  result,
  onDismiss,
}: {
  result: MissionVerifyResponse;
  onDismiss: () => void;
}) {
  return (
    <div className="banner banner-info stack">
      <div className="row-between">
        <strong>미션을 완료했습니다{result.xp_awarded > 0 ? ` · +${result.xp_awarded} XP` : ""}</strong>
        <button className="btn" onClick={onDismiss} type="button" aria-label="닫기">
          닫기
        </button>
      </div>
      {result.newly_awarded_badges.length > 0 && (
        <div className="row" style={{ flexWrap: "wrap" }}>
          {result.newly_awarded_badges.map((b) => (
            <span key={b.code} className="badge badge-earned">🏅 {b.title}</span>
          ))}
        </div>
      )}
      {result.day_completed && <p style={{ margin: 0 }}>이 Day의 모든 필수 미션을 완료했습니다!</p>}
      {result.challenge_completed && <p style={{ margin: 0 }}>7일 챌린지를 완주했습니다!</p>}
    </div>
  );
}

function DayMap({
  userChallenge,
  expandedDay,
  setExpandedDay,
  onVerified,
  portfolioId,
}: {
  userChallenge: UserChallengeResponse;
  expandedDay: number;
  setExpandedDay: (day: number) => void;
  onVerified: (result: MissionVerifyResponse) => void;
  portfolioId: string | null;
}) {
  return (
    <div className="card">
      <h2>7일 진행 지도</h2>
      <div className="stack">
        {userChallenge.days.map((day) => (
          <DayCard
            key={day.day_number}
            day={day}
            userChallengeId={userChallenge.id}
            expanded={expandedDay === day.day_number}
            onToggle={() => setExpandedDay(expandedDay === day.day_number ? -1 : day.day_number)}
            onVerified={onVerified}
            portfolioId={portfolioId}
          />
        ))}
      </div>
    </div>
  );
}

function DayCard({
  day,
  userChallengeId,
  expanded,
  onToggle,
  onVerified,
  portfolioId,
}: {
  day: UserChallengeDayResponse;
  userChallengeId: string;
  expanded: boolean;
  onToggle: () => void;
  onVerified: (result: MissionVerifyResponse) => void;
  portfolioId: string | null;
}) {
  const isLocked = day.status === "LOCKED";
  const completedCount = day.missions.filter((m) => m.completed).length;

  return (
    <div>
      <button
        className="day-row"
        style={{
          width: "100%",
          background: "none",
          border: "none",
          cursor: isLocked ? "default" : "pointer",
          textAlign: "left",
          padding: "10px 0",
        }}
        onClick={onToggle}
        disabled={isLocked}
        type="button"
        aria-expanded={expanded}
      >
        <span className="day-status-icon" aria-hidden="true">{DAY_STATUS_ICON[day.status]}</span>
        <div style={{ flex: 1 }}>
          <div className="row-between">
            <span className={day.status === "IN_PROGRESS" ? "day-row-current" : undefined}>
              Day {day.day_number} · {day.title}
            </span>
            <span className="muted">{DAY_STATUS_LABEL[day.status]}</span>
          </div>
          <p className="muted" style={{ margin: "2px 0 0" }}>
            미션 {completedCount}/{day.missions.length}개 완료
          </p>
        </div>
      </button>

      {expanded && !isLocked && (
        <div className="stack" style={{ paddingLeft: 32, paddingBottom: 12 }}>
          {day.missions.map((mission) => (
            <div key={mission.id} className="mission-row">
              <span aria-hidden="true">{mission.completed ? "✅" : "⬜"}</span>
              <div style={{ flex: 1 }}>
                <div className="row-between">
                  <strong>{mission.title}</strong>
                  <span className="muted">+{mission.xp_amount} XP</span>
                </div>
                {mission.description && <p className="muted" style={{ margin: "2px 0 0" }}>{mission.description}</p>}
                {mission.completed ? (
                  <p className="muted" style={{ margin: "4px 0 0" }}>완료함</p>
                ) : (
                  <MissionActionForm
                    userChallengeId={userChallengeId}
                    mission={mission}
                    portfolioId={portfolioId}
                    onVerified={onVerified}
                  />
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
