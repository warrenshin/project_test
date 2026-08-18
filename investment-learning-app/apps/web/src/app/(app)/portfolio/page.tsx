"use client";

import Link from "next/link";
import { getPerformance, getPositions } from "@/lib/api";
import { useAsync } from "@/lib/useAsync";
import { LoadingBlock, ErrorBlock, EmptyBlock } from "@/components/States";
import { VirtualFundsBanner } from "@/components/VirtualFundsBanner";
import { useAuth } from "@/lib/auth-context";

function PnlText({ value }: { value: string | null }) {
  if (value === null) return <span className="muted">-</span>;
  const num = Number(value);
  const sign = num > 0 ? "+" : num < 0 ? "" : "";
  const cls = num > 0 ? "pnl-gain" : num < 0 ? "pnl-loss" : "";
  return (
    <span className={cls}>
      {num > 0 ? "▲" : num < 0 ? "▼" : "-"} {sign}{num.toLocaleString()}
    </span>
  );
}

export default function PortfolioPage() {
  const { portfolio } = useAuth();
  const data = useAsync(
    () => (portfolio ? Promise.all([getPositions(portfolio.id), getPerformance(portfolio.id)]) : Promise.reject(new Error("no portfolio"))),
    [portfolio?.id]
  );

  if (!portfolio) return <LoadingBlock label="포트폴리오 정보를 불러오는 중입니다..." />;
  if (data.loading) return <LoadingBlock label="포트폴리오를 불러오는 중입니다..." />;
  if (data.error) return <ErrorBlock message={data.error} onRetry={data.reload} />;
  const [positions, performance] = data.data!;

  return (
    <div className="stack">
      <h1>포트폴리오</h1>
      <VirtualFundsBanner compact />

      <div className="card stack">
        <div className="row-between">
          <span className="muted">총 자산</span>
          <strong>{Number(performance.total_assets).toLocaleString()} {performance.base_currency}</strong>
        </div>
        <div className="row-between">
          <span className="muted">가상현금</span>
          <span>{Number(performance.cash_balance).toLocaleString()} {performance.base_currency}</span>
        </div>
        <div className="row-between">
          <span className="muted">평가금액</span>
          <span>{Number(performance.positions_market_value).toLocaleString()} {performance.base_currency}</span>
        </div>
        <div className="row-between">
          <span className="muted">누적 실현손익</span>
          <PnlText value={performance.realized_pnl} />
        </div>
        <div className="row-between">
          <span className="muted">평가손익</span>
          <PnlText value={performance.unrealized_pnl} />
        </div>
        {performance.simple_return_pct !== null && (
          <div className="row-between">
            <span className="muted">단순 수익률</span>
            <PnlText value={performance.simple_return_pct} />
          </div>
        )}
        <p className="muted" style={{ margin: 0 }}>{performance.note}</p>
      </div>

      <h2>보유 종목</h2>
      {positions.length === 0 ? (
        <EmptyBlock message="아직 보유 중인 종목이 없습니다. 종목을 검색해 모의 매수를 시작해보세요." />
      ) : (
        <div className="stack">
          {positions.map((p) => (
            <div key={p.instrument_id} className="card">
              <div className="row-between">
                <strong>{p.ticker}</strong>
                <Link href={`/order/${p.instrument_id}?side=SELL`} className="btn">
                  매도
                </Link>
              </div>
              <div className="row-between">
                <span className="muted">보유수량</span>
                <span>{Number(p.quantity).toLocaleString()}</span>
              </div>
              <div className="row-between">
                <span className="muted">평균단가</span>
                <span>{Number(p.average_cost).toLocaleString()}</span>
              </div>
              <div className="row-between">
                <span className="muted">평가금액</span>
                <span>{p.market_value ? Number(p.market_value).toLocaleString() : "-"}</span>
              </div>
              <div className="row-between">
                <span className="muted">평가손익</span>
                <PnlText value={p.unrealized_pnl} />
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
