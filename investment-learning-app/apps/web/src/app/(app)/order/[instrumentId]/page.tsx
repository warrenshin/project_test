"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { use, useState } from "react";
import { ApiError, createOrder, getInstrument, previewOrder } from "@/lib/api";
import { useAsync } from "@/lib/useAsync";
import { LoadingBlock, ErrorBlock } from "@/components/States";
import { VirtualFundsBanner } from "@/components/VirtualFundsBanner";
import { useAuth } from "@/lib/auth-context";
import type { OrderPreviewResponse } from "@/lib/types";

export default function OrderTicketPage({ params }: { params: Promise<{ instrumentId: string }> }) {
  const { instrumentId } = use(params);
  const searchParams = useSearchParams();
  const journalId = searchParams.get("journalId") ?? undefined;
  const initialSide = searchParams.get("side") === "SELL" ? "SELL" : "BUY";
  const router = useRouter();
  const { portfolio, refreshPortfolio } = useAuth();

  const instrument = useAsync(() => getInstrument(instrumentId), [instrumentId]);

  const [side, setSide] = useState<"BUY" | "SELL">(initialSide);
  const [quantity, setQuantity] = useState("1");
  const [preview, setPreview] = useState<OrderPreviewResponse | null>(null);
  const [previewing, setPreviewing] = useState(false);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  if (instrument.loading) return <LoadingBlock label="종목 정보를 불러오는 중입니다..." />;
  if (instrument.error) return <ErrorBlock message={instrument.error} onRetry={instrument.reload} />;
  const inst = instrument.data!;

  const quantityNumber = Number(quantity);
  const canPreview = portfolio && quantityNumber > 0;

  async function handlePreview() {
    if (!portfolio) return;
    setPreviewing(true);
    setPreviewError(null);
    setPreview(null);
    try {
      const res = await previewOrder(portfolio.id, {
        instrument_id: instrumentId,
        side,
        order_type: "MARKET",
        quantity,
      });
      setPreview(res);
    } catch (err) {
      setPreviewError(err instanceof ApiError ? err.message : "주문 미리보기 중 오류가 발생했습니다.");
    } finally {
      setPreviewing(false);
    }
  }

  async function handleSubmit() {
    if (!portfolio) return;
    setSubmitting(true);
    setSubmitError(null);
    try {
      const order = await createOrder(
        portfolio.id,
        {
          instrument_id: instrumentId,
          side,
          order_type: "MARKET",
          quantity,
          pre_trade_journal_id: journalId,
        },
        crypto.randomUUID()
      );
      await refreshPortfolio();
      if (journalId) {
        router.push(`/journal/${journalId}?orderConfirmed=1`);
      } else {
        router.push(`/portfolio?orderId=${order.id}`);
      }
    } catch (err) {
      setSubmitError(err instanceof ApiError ? err.message : "주문 처리 중 오류가 발생했습니다.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="stack">
      <Link href={`/market/${instrumentId}`} className="link-back">
        ← {inst.name}
      </Link>
      <h1>모의 주문</h1>
      <VirtualFundsBanner />
      {journalId && (
        <div className="banner banner-info">이 주문은 작성한 투자일지와 연결되어 체결 후 복기·코칭에 사용됩니다.</div>
      )}

      <div className="card stack">
        <div className="row-between">
          <span className="muted">종목</span>
          <strong>{inst.name} ({inst.ticker})</strong>
        </div>
        <div className="row-between">
          <span className="muted">현재가</span>
          <span>{inst.last_price ? Number(inst.last_price).toLocaleString() : "정보 없음"} {inst.currency}</span>
        </div>

        <div className="field">
          <label>매매 구분</label>
          <div className="row">
            <button
              type="button"
              className={`btn ${side === "BUY" ? "btn-primary" : ""}`}
              onClick={() => { setSide("BUY"); setPreview(null); }}
            >
              매수
            </button>
            <button
              type="button"
              className={`btn ${side === "SELL" ? "btn-primary" : ""}`}
              onClick={() => { setSide("SELL"); setPreview(null); }}
            >
              매도
            </button>
          </div>
        </div>

        <div className="field">
          <label htmlFor="quantity">수량 (시장가 주문)</label>
          <input
            id="quantity"
            type="number"
            min="0"
            step="1"
            value={quantity}
            onChange={(e) => { setQuantity(e.target.value); setPreview(null); }}
          />
        </div>

        <button className="btn btn-block" onClick={handlePreview} disabled={!canPreview || previewing} type="button">
          {previewing ? "미리보기 계산 중..." : "주문 미리보기"}
        </button>
        {previewError && <ErrorBlock message={previewError} onRetry={handlePreview} />}

        {preview && (
          <div className="stack">
            <div className="row-between">
              <span className="muted">예상 체결가</span>
              <span>{Number(preview.estimated_fill_price).toLocaleString()} {preview.currency}</span>
            </div>
            <div className="row-between">
              <span className="muted">수수료</span>
              <span>{Number(preview.commission).toLocaleString()} {preview.currency}</span>
            </div>
            <div className="row-between">
              <span className="muted">세금</span>
              <span>{Number(preview.tax).toLocaleString()} {preview.currency}</span>
            </div>
            <div className="row-between">
              <span className="muted">예상 현금 변동</span>
              <strong>{Number(preview.estimated_cash_impact).toLocaleString()} {preview.currency}</strong>
            </div>
            {!preview.estimated_fillable && (
              <div className="banner banner-warning">현재 조건으로는 체결이 어려울 수 있습니다.</div>
            )}
            {preview.warnings.map((w, i) => (
              <div key={i} className="banner banner-warning">{w}</div>
            ))}

            <button className="btn btn-primary btn-block" onClick={handleSubmit} disabled={submitting} type="button">
              {submitting ? "주문 처리 중..." : `가상자금으로 ${side === "BUY" ? "매수" : "매도"} 확정`}
            </button>
            {submitError && <ErrorBlock message={submitError} />}
          </div>
        )}
      </div>
    </div>
  );
}
