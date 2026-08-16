"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";
import { ApiError, createPreTradeJournal, getInstrument } from "@/lib/api";
import { useAsync } from "@/lib/useAsync";
import { LoadingBlock, ErrorBlock } from "@/components/States";
import { useAuth } from "@/lib/auth-context";

export default function NewJournalPage() {
  const searchParams = useSearchParams();
  const instrumentId = searchParams.get("instrumentId") ?? "";
  const router = useRouter();
  const { portfolio } = useAuth();

  const instrument = useAsync(() => getInstrument(instrumentId), [instrumentId]);

  const [thesis, setThesis] = useState("");
  const [supportingEvidence, setSupportingEvidence] = useState("");
  const [counterEvidence, setCounterEvidence] = useState("");
  const [entryCondition, setEntryCondition] = useState("");
  const [targetCondition, setTargetCondition] = useState("");
  const [stopLossCondition, setStopLossCondition] = useState("");
  const [plannedWeightPct, setPlannedWeightPct] = useState("");
  const [confidenceLevel, setConfidenceLevel] = useState("3");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!instrumentId) {
    return (
      <div className="stack">
        <h1>투자일지 작성</h1>
        <ErrorBlock message="종목이 지정되지 않았습니다. 종목 상세 화면에서 다시 시도해주세요." />
        <Link href="/market" className="btn btn-block">
          종목 검색으로 이동
        </Link>
      </div>
    );
  }

  if (instrument.loading) return <LoadingBlock label="종목 정보를 불러오는 중입니다..." />;
  if (instrument.error) return <ErrorBlock message={instrument.error} onRetry={instrument.reload} />;
  const inst = instrument.data!;

  const splitLines = (text: string) =>
    text
      .split("\n")
      .map((l) => l.trim())
      .filter((l) => l.length > 0);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!portfolio) return;
    setSubmitting(true);
    setError(null);
    try {
      const journal = await createPreTradeJournal({
        portfolio_id: portfolio.id,
        instrument_id: instrumentId,
        thesis,
        supporting_evidence: splitLines(supportingEvidence).slice(0, 3),
        counter_evidence: splitLines(counterEvidence),
        entry_condition: entryCondition || undefined,
        target_condition: targetCondition || undefined,
        stop_loss_condition: stopLossCondition || undefined,
        planned_weight_pct: plannedWeightPct || undefined,
        confidence_level: Number(confidenceLevel),
      });
      router.push(`/order/${instrumentId}?journalId=${journal.id}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "투자일지 저장 중 오류가 발생했습니다.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="stack">
      <Link href={`/market/${instrumentId}`} className="link-back">
        ← {inst.name}
      </Link>
      <h1>거래 전 투자일지</h1>
      <p className="muted">
        매수 전에 투자 논리를 기록하면 체결 후 과정 점수와 AI 코칭에 반영됩니다. 반대 근거를
        포함할수록 확증편향 관찰 위험이 낮아집니다.
      </p>

      <form className="card stack" onSubmit={handleSubmit}>
        <div className="field">
          <label htmlFor="thesis">투자 논리 (필수)</label>
          <textarea
            id="thesis"
            required
            minLength={1}
            rows={3}
            value={thesis}
            onChange={(e) => setThesis(e.target.value)}
            placeholder="왜 이 종목을 매수하려고 하나요?"
          />
        </div>
        <div className="field">
          <label htmlFor="supporting">근거 (한 줄에 하나씩, 최대 3개)</label>
          <textarea
            id="supporting"
            rows={2}
            value={supportingEvidence}
            onChange={(e) => setSupportingEvidence(e.target.value)}
            placeholder="예: 실적 개선 기대"
          />
        </div>
        <div className="field">
          <label htmlFor="counter">반대 근거 (한 줄에 하나씩)</label>
          <textarea
            id="counter"
            rows={2}
            value={counterEvidence}
            onChange={(e) => setCounterEvidence(e.target.value)}
            placeholder="예: 업황 둔화 우려"
          />
        </div>
        <div className="field">
          <label htmlFor="entry">진입 조건</label>
          <input id="entry" value={entryCondition} onChange={(e) => setEntryCondition(e.target.value)} />
        </div>
        <div className="field">
          <label htmlFor="target">목표 조건</label>
          <input id="target" value={targetCondition} onChange={(e) => setTargetCondition(e.target.value)} />
        </div>
        <div className="field">
          <label htmlFor="stop">손절 조건</label>
          <input id="stop" value={stopLossCondition} onChange={(e) => setStopLossCondition(e.target.value)} />
        </div>
        <div className="field">
          <label htmlFor="weight">계획 비중 (%)</label>
          <input
            id="weight"
            type="number"
            min={0}
            max={100}
            step="0.1"
            value={plannedWeightPct}
            onChange={(e) => setPlannedWeightPct(e.target.value)}
          />
        </div>
        <div className="field">
          <label htmlFor="confidence">확신 수준 (1~5)</label>
          <select id="confidence" value={confidenceLevel} onChange={(e) => setConfidenceLevel(e.target.value)}>
            {[1, 2, 3, 4, 5].map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </select>
        </div>

        {error && <ErrorBlock message={error} />}
        <button className="btn btn-primary btn-block" type="submit" disabled={submitting || !thesis.trim()}>
          {submitting ? "저장 중..." : "일지 저장하고 주문으로 이동"}
        </button>
      </form>
    </div>
  );
}
