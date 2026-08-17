"use client";

import Link from "next/link";
import { use } from "react";
import { getInstrument, getInstrumentBars } from "@/lib/api";
import { useAsync } from "@/lib/useAsync";
import { LoadingBlock, ErrorBlock } from "@/components/States";
import { MarketDataBadge } from "@/components/MarketDataBadge";
import { VirtualFundsBanner } from "@/components/VirtualFundsBanner";

export default function InstrumentDetailPage({ params }: { params: Promise<{ instrumentId: string }> }) {
  const { instrumentId } = use(params);
  const data = useAsync(
    () => Promise.all([getInstrument(instrumentId), getInstrumentBars(instrumentId)]),
    [instrumentId]
  );

  if (data.loading) return <LoadingBlock label="종목 정보를 불러오는 중입니다..." />;
  if (data.error) return <ErrorBlock message={data.error} onRetry={data.reload} />;
  const [instrument, bars] = data.data!;

  return (
    <div className="stack">
      <Link href="/market" className="link-back">
        ← 종목 검색
      </Link>
      <h1>{instrument.name}</h1>
      <p className="muted">
        {instrument.ticker} · {instrument.exchange} · {instrument.currency}
        {instrument.industry ? ` · ${instrument.industry}` : ""}
      </p>

      <div className="card stack">
        <div className="row-between">
          <span className="muted">현재가</span>
          <strong>
            {instrument.last_price ? Number(instrument.last_price).toLocaleString() : "정보 없음"}{" "}
            {instrument.currency}
          </strong>
        </div>
        {instrument.price_as_of && (
          <MarketDataBadge
            asOf={instrument.price_as_of}
            source={instrument.price_source ?? "알 수 없음"}
            delaySeconds={instrument.delay_seconds ?? 0}
          />
        )}
        {!instrument.is_tradable && (
          <div className="banner banner-warning">이 종목은 현재 거래가 제한되어 있습니다.</div>
        )}
      </div>

      {bars.length > 0 && (
        <div className="card">
          <h2>최근 시세</h2>
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
              <thead>
                <tr style={{ textAlign: "right" }}>
                  <th style={{ textAlign: "left" }}>기준시각</th>
                  <th>종가</th>
                  <th>거래량</th>
                </tr>
              </thead>
              <tbody>
                {bars.slice(-10).reverse().map((bar, idx) => (
                  <tr key={idx}>
                    <td>{new Date(bar.bar_start).toLocaleDateString()}</td>
                    <td style={{ textAlign: "right" }}>{Number(bar.close).toLocaleString()}</td>
                    <td style={{ textAlign: "right" }}>{Number(bar.volume).toLocaleString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      <VirtualFundsBanner />

      {instrument.is_tradable && (
        <div className="card stack">
          <Link href={`/journal/new?instrumentId=${instrument.id}`} className="btn btn-primary btn-block">
            투자일지 작성 후 매수하기
          </Link>
          <Link href={`/order/${instrument.id}`} className="btn btn-block">
            투자일지 없이 바로 주문하기
          </Link>
        </div>
      )}
    </div>
  );
}
