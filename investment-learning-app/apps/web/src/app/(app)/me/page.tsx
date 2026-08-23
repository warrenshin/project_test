"use client";

import Link from "next/link";
import { useState } from "react";
import { useAuth } from "@/lib/auth-context";
import { getBiasReport, acknowledgeBiasEvent, ApiError } from "@/lib/api";
import { useAsync } from "@/lib/useAsync";
import { LoadingBlock, ErrorBlock, EmptyBlock } from "@/components/States";
import type { BiasSignal } from "@/lib/types";

const SEVERITY_LABEL: Record<string, string> = {
  HIGH: "높음",
  MEDIUM: "보통",
  LOW: "낮음",
};

// 심각도는 색상만으로 구분하지 않는다(위험도를 색으로만 표시하면 안 됨) —
// 항상 텍스트 라벨과 함께 표시하고, 색도 "위험 신호=빨강" 한 가지로만 쓰지
// 않는다(정보성 파란색 계열도 섞어 쓴다).
const SEVERITY_BADGE_CLASS: Record<string, string> = {
  HIGH: "badge-warning",
  MEDIUM: "badge-warning",
  LOW: "badge-virtual",
};

const DATA_SUFFICIENCY_LABEL: Record<string, string> = {
  SUFFICIENT: "판단 가능",
  INSUFFICIENT: "데이터 부족",
  MARKET_DATA_UNAVAILABLE: "시세 데이터 없음",
};

function formatDate(iso: string | null): string | null {
  if (!iso) return null;
  try {
    return new Date(iso).toLocaleString("ko-KR", { dateStyle: "medium", timeStyle: "short" });
  } catch {
    return iso;
  }
}

function BiasCard({
  signal,
  onAcknowledge,
  acknowledging,
  ackError,
}: {
  signal: BiasSignal;
  onAcknowledge: (signal: BiasSignal) => void;
  acknowledging: boolean;
  ackError: string | null;
}) {
  const isInsufficient = signal.data_sufficiency !== "SUFFICIENT";

  return (
    <div className="card" style={{ marginBottom: 0 }} data-testid={`bias-card-${signal.bias_code}`}>
      <div className="row-between">
        <strong>{signal.display_name}</strong>
        <div className="row" style={{ gap: 6 }}>
          {signal.detected && signal.severity && (
            <span className={`badge ${SEVERITY_BADGE_CLASS[signal.severity] ?? "badge-virtual"}`}>
              심각도 {SEVERITY_LABEL[signal.severity] ?? signal.severity}
            </span>
          )}
          <span className="badge badge-virtual">{DATA_SUFFICIENCY_LABEL[signal.data_sufficiency]}</span>
        </div>
      </div>

      {isInsufficient ? (
        <p className="muted" style={{ margin: "8px 0 0" }} data-testid="bias-insufficient-message">
          {signal.description}
          {" "}
          (표본 {signal.sample_size}건 / 최소 {signal.minimum_sample_size}건 필요)
        </p>
      ) : (
        <>
          <p style={{ margin: "8px 0 0" }}>{signal.evidence_summary}</p>
          <p className="muted" style={{ margin: "6px 0 0" }}>제안: {signal.coaching_direction}</p>
        </>
      )}

      <details style={{ marginTop: 8 }}>
        <summary style={{ cursor: "pointer", fontSize: 13, color: "var(--color-text-muted)" }}>
          근거·한계 자세히 보기
        </summary>
        <div className="stack" style={{ marginTop: 8 }}>
          <p style={{ margin: 0, fontSize: 13 }}>
            <strong>표본:</strong> {signal.sample_size}건 (최소 {signal.minimum_sample_size}건)
            {signal.window_start && signal.window_end && (
              <>
                {" · "}
                {formatDate(signal.window_start)} ~ {formatDate(signal.window_end)}
              </>
            )}
          </p>
          <p style={{ margin: 0, fontSize: 13 }}>
            <strong>이 판단의 한계:</strong> {signal.limitations}
          </p>
          {signal.self_check_questions.length > 0 && (
            <div style={{ margin: 0, fontSize: 13 }}>
              <strong>스스로 점검해보기:</strong>
              <ul style={{ margin: "4px 0 0", paddingLeft: 18 }}>
                {signal.self_check_questions.map((q) => (
                  <li key={q}>{q}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </details>

      <div className="row-between" style={{ marginTop: 12, flexWrap: "wrap", gap: 8 }}>
        <span className="muted" style={{ fontSize: 12 }}>
          {signal.related_lesson_id && (
            <Link href={`/learn/${signal.related_lesson_id}`}>관련 학습 콘텐츠 보기</Link>
          )}
        </span>
        {signal.detected && signal.id && (
          signal.acknowledged_at ? (
            <span className="muted" style={{ fontSize: 12 }}>
              확인함 ({formatDate(signal.acknowledged_at)})
            </span>
          ) : (
            <button
              className="btn"
              type="button"
              disabled={acknowledging}
              onClick={() => onAcknowledge(signal)}
            >
              {acknowledging ? "처리 중..." : "확인했어요"}
            </button>
          )
        )}
      </div>
      {ackError && (
        <p className="muted" style={{ marginTop: 6, color: "var(--color-danger-text)" }}>
          {ackError}
        </p>
      )}
    </div>
  );
}

export default function MePage() {
  const { logout } = useAuth();
  const bias = useAsync(() => getBiasReport(), []);
  const [ackState, setAckState] = useState<Record<string, { loading: boolean; error: string | null }>>({});

  const handleAcknowledge = async (signal: BiasSignal) => {
    if (!signal.id) return;
    setAckState((prev) => ({ ...prev, [signal.bias_code]: { loading: true, error: null } }));
    try {
      await acknowledgeBiasEvent(signal.id);
      bias.reload();
    } catch (err) {
      const message = err instanceof ApiError ? err.message : "확인 처리에 실패했습니다.";
      setAckState((prev) => ({ ...prev, [signal.bias_code]: { loading: false, error: message } }));
      return;
    }
    setAckState((prev) => ({ ...prev, [signal.bias_code]: { loading: false, error: null } }));
  };

  const biases = bias.data?.biases ?? [];
  const topCodes = bias.data?.top_signals ?? [];
  const topSignals = topCodes
    .map((code) => biases.find((b) => b.bias_code === code))
    .filter((b): b is BiasSignal => b !== undefined);
  const otherSignals = biases.filter((b) => !topCodes.includes(b.bias_code));

  return (
    <div className="stack">
      <h1>마이</h1>

      <div className="card stack">
        <h2 style={{ margin: 0 }}>성장 리포트 — 관찰된 거래 패턴</h2>
        <div className="banner banner-info" role="note">
          이 리포트는 의학적 진단이나 심리 평가가 아닙니다. 지금까지의 거래·일지
          기록에서 통계적으로 관찰된 패턴을 보여드릴 뿐, 옳고 그름이나 매수·매도
          시점을 지시하지 않습니다. 어떻게 해석하고 활용할지는 전적으로 본인의
          판단입니다.
        </div>

        {bias.loading && <LoadingBlock label="편향 리포트를 불러오는 중입니다..." />}
        {bias.error && <ErrorBlock message={bias.error} onRetry={bias.reload} />}

        {bias.data && (
          <>
            {topSignals.length > 0 ? (
              <div className="stack">
                <h3 style={{ margin: 0, fontSize: 15 }}>지금 살펴보면 좋을 신호</h3>
                {topSignals.map((s) => (
                  <BiasCard
                    key={s.bias_code}
                    signal={s}
                    onAcknowledge={handleAcknowledge}
                    acknowledging={ackState[s.bias_code]?.loading ?? false}
                    ackError={ackState[s.bias_code]?.error ?? null}
                  />
                ))}
              </div>
            ) : (
              <EmptyBlock message="아직 뚜렷하게 관찰된 거래 패턴이 없습니다." />
            )}

            {otherSignals.length > 0 && (
              <details>
                <summary style={{ cursor: "pointer", fontSize: 14 }}>
                  나머지 {otherSignals.length}개 항목 더 보기
                </summary>
                <div className="stack" style={{ marginTop: 12 }}>
                  {otherSignals.map((s) => (
                    <BiasCard
                      key={s.bias_code}
                      signal={s}
                      onAcknowledge={handleAcknowledge}
                      acknowledging={ackState[s.bias_code]?.loading ?? false}
                      ackError={ackState[s.bias_code]?.error ?? null}
                    />
                  ))}
                </div>
              </details>
            )}
          </>
        )}
      </div>

      <div className="card stack">
        <Link href="/journal" className="btn btn-block">
          내 투자일지 보기
        </Link>
        <Link href="/badges" className="btn btn-block">
          내 배지 보기
        </Link>
        <button className="btn btn-block" onClick={logout} type="button">
          로그아웃
        </button>
      </div>
    </div>
  );
}
