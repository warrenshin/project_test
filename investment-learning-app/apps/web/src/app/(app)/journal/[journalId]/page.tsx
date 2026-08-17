"use client";

import Link from "next/link";
import { use, useState } from "react";
import { ApiError, getJournal, getJournalCoaching, submitPostTradeReview } from "@/lib/api";
import { useAsync } from "@/lib/useAsync";
import { LoadingBlock, ErrorBlock } from "@/components/States";
import type { JournalCoachingResponse } from "@/lib/types";

export default function JournalDetailPage({ params }: { params: Promise<{ journalId: string }> }) {
  const { journalId } = use(params);
  const journal = useAsync(() => getJournal(journalId), [journalId]);

  const [followedPlan, setFollowedPlan] = useState<"true" | "false">("true");
  const [expectationGap, setExpectationGap] = useState("");
  const [behaviorToRepeat, setBehaviorToRepeat] = useState("");
  const [behaviorToChange, setBehaviorToChange] = useState("");
  const [reviewSubmitting, setReviewSubmitting] = useState(false);
  const [reviewError, setReviewError] = useState<string | null>(null);

  const [coaching, setCoaching] = useState<JournalCoachingResponse | null>(null);
  const [coachingLoading, setCoachingLoading] = useState(false);
  const [coachingError, setCoachingError] = useState<string | null>(null);

  async function handleSubmitReview(e: React.FormEvent) {
    e.preventDefault();
    setReviewSubmitting(true);
    setReviewError(null);
    try {
      await submitPostTradeReview(journalId, {
        followed_plan: followedPlan === "true",
        expectation_gap: expectationGap || undefined,
        behavior_to_repeat: behaviorToRepeat || undefined,
        behavior_to_change: behaviorToChange || undefined,
      });
      journal.reload();
    } catch (err) {
      setReviewError(err instanceof ApiError ? err.message : "복기 저장 중 오류가 발생했습니다.");
    } finally {
      setReviewSubmitting(false);
    }
  }

  async function handleLoadCoaching() {
    setCoachingLoading(true);
    setCoachingError(null);
    try {
      const res = await getJournalCoaching(journalId);
      setCoaching(res);
    } catch (err) {
      setCoachingError(err instanceof ApiError ? err.message : "코칭 결과를 불러오지 못했습니다.");
    } finally {
      setCoachingLoading(false);
    }
  }

  if (journal.loading) return <LoadingBlock label="투자일지를 불러오는 중입니다..." />;
  if (journal.error) return <ErrorBlock message={journal.error} onRetry={journal.reload} />;
  const j = journal.data!;
  const needsReview = j.order_id !== null && j.followed_plan === null;
  const hasReview = j.followed_plan !== null;

  return (
    <div className="stack">
      <Link href="/journal" className="link-back">
        ← 투자일지 목록
      </Link>
      <h1>투자일지</h1>

      <div className="card stack">
        <h2>거래 전 논리</h2>
        <p style={{ margin: 0, whiteSpace: "pre-wrap" }}>{j.thesis}</p>
        {j.supporting_evidence && j.supporting_evidence.length > 0 && (
          <div>
            <span className="muted">근거</span>
            <ul style={{ margin: "4px 0 0" }}>
              {j.supporting_evidence.map((e, i) => <li key={i}>{e}</li>)}
            </ul>
          </div>
        )}
        {j.counter_evidence && j.counter_evidence.length > 0 && (
          <div>
            <span className="muted">반대 근거</span>
            <ul style={{ margin: "4px 0 0" }}>
              {j.counter_evidence.map((e, i) => <li key={i}>{e}</li>)}
            </ul>
          </div>
        )}
        {j.process_score !== null && (
          <div className="row-between">
            <span className="muted">과정 점수</span>
            <strong>{Number(j.process_score).toFixed(0)}점</strong>
          </div>
        )}
        {!j.order_id && (
          <div className="banner banner-info">아직 이 일지와 연결된 체결 주문이 없습니다.</div>
        )}
      </div>

      {needsReview && (
        <form className="card stack" onSubmit={handleSubmitReview}>
          <h2>거래 후 복기</h2>
          <div className="field">
            <label htmlFor="followed">계획대로 실행했나요?</label>
            <select id="followed" value={followedPlan} onChange={(e) => setFollowedPlan(e.target.value as "true" | "false")}>
              <option value="true">예, 계획대로 실행했습니다</option>
              <option value="false">아니요, 계획과 다르게 실행했습니다</option>
            </select>
          </div>
          <div className="field">
            <label htmlFor="gap">기대와 실제 결과의 차이</label>
            <textarea id="gap" rows={2} value={expectationGap} onChange={(e) => setExpectationGap(e.target.value)} />
          </div>
          <div className="field">
            <label htmlFor="repeat">다음에도 반복하고 싶은 행동</label>
            <textarea id="repeat" rows={2} value={behaviorToRepeat} onChange={(e) => setBehaviorToRepeat(e.target.value)} />
          </div>
          <div className="field">
            <label htmlFor="change">고치고 싶은 행동</label>
            <textarea id="change" rows={2} value={behaviorToChange} onChange={(e) => setBehaviorToChange(e.target.value)} />
          </div>
          {reviewError && <ErrorBlock message={reviewError} />}
          <button className="btn btn-primary btn-block" type="submit" disabled={reviewSubmitting}>
            {reviewSubmitting ? "저장 중..." : "복기 저장"}
          </button>
        </form>
      )}

      {hasReview && (
        <div className="card stack">
          <h2>거래 후 복기</h2>
          <div className="row-between">
            <span className="muted">계획 준수 여부</span>
            <span>{j.followed_plan ? "계획대로 실행" : "계획과 다르게 실행"}</span>
          </div>
          {j.expectation_gap && <p className="muted" style={{ margin: 0 }}>{j.expectation_gap}</p>}
        </div>
      )}

      <div className="card stack">
        <h2>규칙 기반 AI 코칭</h2>
        <p className="muted">
          과정 점수와 관찰된 거래 패턴을 바탕으로 한 코칭입니다. 매수·매도 지시나 수익 보장이 아닌
          교육적 설명만 제공합니다.
        </p>
        {!coaching && (
          <button className="btn btn-block" onClick={handleLoadCoaching} disabled={coachingLoading} type="button">
            {coachingLoading ? "코칭을 불러오는 중..." : "AI 코칭 확인"}
          </button>
        )}
        {coachingError && <ErrorBlock message={coachingError} onRetry={handleLoadCoaching} />}
        {coaching && (
          <div className="stack">
            {coaching.degraded && (
              <div className="banner banner-warning">
                AI 응답을 받지 못해 규칙 기반 폴백 코칭으로 대체되었습니다.
              </div>
            )}
            <p style={{ whiteSpace: "pre-wrap", margin: 0 }}>{coaching.content}</p>
            {coaching.sources.length > 0 && (
              <div>
                <span className="muted">근거 자료</span>
                <ul style={{ margin: "4px 0 0" }}>
                  {coaching.sources.map((s, i) => (
                    <li key={i} className="muted">
                      {s.title} ({s.source}{s.as_of ? `, ${new Date(s.as_of).toLocaleString("ko-KR")}` : ""})
                    </li>
                  ))}
                </ul>
              </div>
            )}
            <p className="muted" style={{ margin: 0 }}>모델: {coaching.model} · 프롬프트 버전: {coaching.prompt_version}</p>
          </div>
        )}
      </div>
    </div>
  );
}
