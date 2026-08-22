"use client";

import Link from "next/link";
import { useState } from "react";
import { ApiError, listMyJournals, searchInstruments, verifyChallengeMission } from "@/lib/api";
import type {
  InstrumentSummary,
  JournalResponse,
  MissionVerifyPayload,
  MissionVerifyResponse,
  UserMissionResponse,
} from "@/lib/types";
import { useAsync } from "@/lib/useAsync";
import { ErrorBlock } from "@/components/States";

/** 미션 유형별로 필요한 입력만 보여주고, 서버의 /verify로 그대로 제출한다.
 * 완료 여부·XP·배지는 여기서 판단하지 않는다 — 서버 응답을 그대로 반영할 뿐이다. */
export function MissionActionForm({
  userChallengeId,
  mission,
  portfolioId,
  onVerified,
}: {
  userChallengeId: string;
  mission: UserMissionResponse;
  portfolioId: string | null;
  onVerified: (result: MissionVerifyResponse) => void;
}) {
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reason, setReason] = useState<string | null>(null);

  async function submit(payload: MissionVerifyPayload) {
    setSubmitting(true);
    setError(null);
    setReason(null);
    try {
      const res = await verifyChallengeMission(userChallengeId, mission.id, payload);
      if (res.mission_completed || res.already_completed) {
        onVerified(res);
      } else {
        setReason(res.reason ?? "아직 완료 조건을 채우지 못했습니다.");
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "확인 중 오류가 발생했습니다.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="stack" style={{ marginTop: 8 }}>
      <MissionInput mission={mission} portfolioId={portfolioId} submitting={submitting} onSubmit={submit} />
      {reason && <div className="banner banner-warning">{reason}</div>}
      {error && <ErrorBlock message={error} />}
    </div>
  );
}

function MissionInput({
  mission,
  portfolioId,
  submitting,
  onSubmit,
}: {
  mission: UserMissionResponse;
  portfolioId: string | null;
  submitting: boolean;
  onSubmit: (payload: MissionVerifyPayload) => void;
}) {
  const config = mission.public_config as Record<string, unknown>;

  switch (mission.mission_type) {
    case "LESSON_COMPLETE":
    case "QUIZ_PASS": {
      const lessonId = (config.lesson_id as string) ?? null;
      return (
        <div className="row" style={{ flexWrap: "wrap" }}>
          {lessonId && (
            <Link href={`/learn/${lessonId}`} className="btn">
              강의로 이동
            </Link>
          )}
          <button className="btn btn-primary" onClick={() => onSubmit({})} disabled={submitting} type="button">
            {submitting ? "확인 중..." : "완료 확인"}
          </button>
        </div>
      );
    }

    case "GOAL_NOTE":
      return <GoalNoteInput minLength={Number(config.min_length ?? 5)} submitting={submitting} onSubmit={onSubmit} />;

    case "SCENARIO_CHOICE":
      return (
        <ScenarioChoiceInput
          options={(config.options as Record<string, string>) ?? {}}
          submitting={submitting}
          onSubmit={onSubmit}
        />
      );

    case "DISCLOSURE_ACK":
      return <DisclosureAckInput submitting={submitting} onSubmit={onSubmit} />;

    case "ORDER_PREVIEW":
      return <OrderPreviewInput portfolioId={portfolioId} submitting={submitting} onSubmit={onSubmit} />;

    case "JOURNAL_PRE_TRADE":
      return (
        <JournalPickerInput
          submitting={submitting}
          onSubmit={onSubmit}
          filter={(j) => !!j.thesis && !j.order_id}
          emptyMessage="아직 거래 전 일지가 없습니다. 종목 상세 화면에서 매수 전 일지를 작성해보세요."
          linkHref="/market"
          linkLabel="종목 검색하러 가기"
        />
      );

    case "ORDER_PREVIEW_LINKED_JOURNAL":
      return (
        <JournalPickerInput
          submitting={submitting}
          onSubmit={onSubmit}
          filter={(j) => !!j.thesis && !!j.stop_loss_condition && (j.counter_evidence?.length ?? 0) > 0}
          emptyMessage="연결할 수 있는 거래 전 일지가 없습니다. Day 3에서 먼저 일지를 완성해주세요."
        />
      );

    case "POST_TRADE_REVIEW":
      return (
        <JournalPickerInput
          submitting={submitting}
          onSubmit={onSubmit}
          filter={(j) => j.followed_plan !== null}
          emptyMessage="거래 후 복기를 작성한 일지가 없습니다. 일지 상세 화면에서 먼저 복기를 남겨주세요."
          linkHref="/journal"
          linkLabel="내 투자일지 보기"
        />
      );

    case "PROCESS_SCORE_CHECK":
      return (
        <JournalPickerInput
          submitting={submitting}
          onSubmit={onSubmit}
          filter={(j) => j.process_score !== null}
          emptyMessage="아직 과정 점수가 계산된 일지가 없습니다."
          linkHref="/journal"
          linkLabel="내 투자일지 보기"
        />
      );

    case "PORTFOLIO_CONCENTRATION_REVIEW":
    case "BIAS_REVIEW":
    case "COACHING_CONFIRM":
      return (
        <button className="btn btn-primary btn-block" onClick={() => onSubmit({})} disabled={submitting} type="button">
          {submitting ? "확인 중..." : "확인 완료"}
        </button>
      );

    default:
      return (
        <button className="btn btn-primary btn-block" onClick={() => onSubmit({})} disabled={submitting} type="button">
          {submitting ? "확인 중..." : "완료 확인"}
        </button>
      );
  }
}

function GoalNoteInput({
  minLength,
  submitting,
  onSubmit,
}: {
  minLength: number;
  submitting: boolean;
  onSubmit: (payload: MissionVerifyPayload) => void;
}) {
  const [note, setNote] = useState("");
  return (
    <div className="stack">
      <div className="field">
        <label htmlFor="goal-note">{minLength}자 이상 입력해주세요</label>
        <textarea id="goal-note" rows={3} value={note} onChange={(e) => setNote(e.target.value)} />
      </div>
      <button
        className="btn btn-primary btn-block"
        onClick={() => onSubmit({ note })}
        disabled={submitting || note.trim().length < minLength}
        type="button"
      >
        {submitting ? "저장 중..." : "저장하고 완료 확인"}
      </button>
    </div>
  );
}

function ScenarioChoiceInput({
  options,
  submitting,
  onSubmit,
}: {
  options: Record<string, string>;
  submitting: boolean;
  onSubmit: (payload: MissionVerifyPayload) => void;
}) {
  const [choice, setChoice] = useState<string | null>(null);
  return (
    <div className="stack">
      {Object.entries(options).map(([key, label]) => (
        <label key={key} className="row" style={{ fontWeight: 400 }}>
          <input
            type="radio"
            name="scenario-choice"
            checked={choice === key}
            onChange={() => setChoice(key)}
            style={{ width: "auto" }}
          />
          {label}
        </label>
      ))}
      <button
        className="btn btn-primary btn-block"
        onClick={() => choice && onSubmit({ choice })}
        disabled={submitting || !choice}
        type="button"
      >
        {submitting ? "확인 중..." : "선택 확인"}
      </button>
    </div>
  );
}

function DisclosureAckInput({
  submitting,
  onSubmit,
}: {
  submitting: boolean;
  onSubmit: (payload: MissionVerifyPayload) => void;
}) {
  const [checked, setChecked] = useState(false);
  return (
    <div className="stack">
      <label className="row" style={{ fontWeight: 400 }}>
        <input type="checkbox" checked={checked} onChange={(e) => setChecked(e.target.checked)} style={{ width: "auto" }} />
        이 모든 거래는 실제 자금이 아닌 가상자금으로 이루어지는 모의투자임을 확인했습니다.
      </label>
      <button
        className="btn btn-primary btn-block"
        onClick={() => onSubmit({ acknowledged: true })}
        disabled={submitting || !checked}
        type="button"
      >
        {submitting ? "확인 중..." : "확인"}
      </button>
    </div>
  );
}

function OrderPreviewInput({
  portfolioId,
  submitting,
  onSubmit,
}: {
  portfolioId: string | null;
  submitting: boolean;
  onSubmit: (payload: MissionVerifyPayload) => void;
}) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<InstrumentSummary[]>([]);
  const [selected, setSelected] = useState<InstrumentSummary | null>(null);
  const [quantity, setQuantity] = useState("1");
  const [searching, setSearching] = useState(false);

  async function handleSearch() {
    if (!query.trim()) return;
    setSearching(true);
    try {
      setResults(await searchInstruments(query.trim()));
    } catch {
      setResults([]);
    } finally {
      setSearching(false);
    }
  }

  if (!portfolioId) {
    return <p className="muted">포트폴리오 정보를 불러오는 중입니다.</p>;
  }

  return (
    <div className="stack">
      <p className="muted" style={{ margin: 0 }}>
        실제 체결은 필요 없습니다 — 예상 비용만 미리 확인하면 완료됩니다.
      </p>
      {!selected ? (
        <div className="stack">
          <div className="row">
            <input
              placeholder="종목명 또는 티커 검색"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleSearch()}
            />
            <button className="btn" onClick={handleSearch} disabled={searching} type="button">
              검색
            </button>
          </div>
          {results.map((r) => (
            <button
              key={r.id}
              className="card"
              style={{ marginBottom: 0, textAlign: "left", cursor: "pointer" }}
              onClick={() => setSelected(r)}
              type="button"
            >
              <strong>{r.name}</strong> <span className="muted">{r.ticker}</span>
            </button>
          ))}
        </div>
      ) : (
        <div className="stack">
          <div className="row-between">
            <span>
              <strong>{selected.name}</strong> <span className="muted">{selected.ticker}</span>
            </span>
            <button className="btn" onClick={() => setSelected(null)} type="button">
              변경
            </button>
          </div>
          <div className="field">
            <label htmlFor="mission-order-qty">수량</label>
            <input
              id="mission-order-qty"
              type="number"
              min="1"
              step="1"
              value={quantity}
              onChange={(e) => setQuantity(e.target.value)}
            />
          </div>
          <button
            className="btn btn-primary btn-block"
            disabled={submitting || !quantity || Number(quantity) <= 0}
            onClick={() =>
              onSubmit({
                portfolio_id: portfolioId,
                instrument_id: selected.id,
                side: "BUY",
                order_type: "MARKET",
                quantity,
              })
            }
            type="button"
          >
            {submitting ? "확인 중..." : "예상 비용 확인하고 완료"}
          </button>
        </div>
      )}
    </div>
  );
}

function JournalPickerInput({
  submitting,
  onSubmit,
  filter,
  emptyMessage,
  linkHref,
  linkLabel,
}: {
  submitting: boolean;
  onSubmit: (payload: MissionVerifyPayload) => void;
  filter: (journal: JournalResponse) => boolean;
  emptyMessage: string;
  linkHref?: string;
  linkLabel?: string;
}) {
  const journals = useAsync(() => listMyJournals(), []);
  const [journalId, setJournalId] = useState<string | null>(null);

  if (journals.loading) return <p className="muted">일지를 불러오는 중입니다...</p>;
  if (journals.error) return <ErrorBlock message={journals.error} onRetry={journals.reload} />;

  const candidates = (journals.data ?? []).filter(filter);
  if (candidates.length === 0) {
    return (
      <div className="stack">
        <p className="muted" style={{ margin: 0 }}>{emptyMessage}</p>
        {linkHref && (
          <Link href={linkHref} className="btn btn-block">
            {linkLabel}
          </Link>
        )}
      </div>
    );
  }

  return (
    <div className="stack">
      {candidates.map((j) => (
        <label key={j.id} className="row" style={{ fontWeight: 400 }}>
          <input
            type="radio"
            name="journal-picker"
            checked={journalId === j.id}
            onChange={() => setJournalId(j.id)}
            style={{ width: "auto" }}
          />
          {j.thesis ?? "(제목 없음)"}
        </label>
      ))}
      <button
        className="btn btn-primary btn-block"
        onClick={() => journalId && onSubmit({ journal_id: journalId })}
        disabled={submitting || !journalId}
        type="button"
      >
        {submitting ? "확인 중..." : "이 일지로 완료 확인"}
      </button>
    </div>
  );
}
