"use client";

import Link from "next/link";
import { getPerformance, getPositions } from "@/lib/api";
import { useAsync } from "@/lib/useAsync";
import { LoadingBlock, ErrorBlock, EmptyBlock } from "@/components/States";
import { VirtualFundsBanner } from "@/components/VirtualFundsBanner";
import { useAuth } from "@/lib/auth-context";
import type { PortfolioMarketDataStatus, PriceStatus } from "@/lib/types";

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

function formatAsOf(asOf: string | null): string {
  if (!asOf) return "";
  return new Date(asOf).toLocaleString("ko-KR", { hour12: false });
}

/** Phase A: 포트폴리오 수준 시세 신선도 경고. FRESH/EMPTY는 특별히 알릴 것이
 * 없어 아무것도 렌더링하지 않는다. */
function MarketDataStatusBanner({
  status,
  asOf,
  hasUnavailable,
}: {
  status: PortfolioMarketDataStatus;
  asOf: string | null;
  hasUnavailable: boolean;
}) {
  if (status === "FRESH" || status === "EMPTY") return null;

  if (status === "UNAVAILABLE") {
    return (
      <div className="banner banner-danger" role="alert">
        <strong>일부 종목의 시세를 확인할 수 없습니다.</strong>
        <p style={{ margin: "4px 0 0" }}>
          시세를 확인할 수 없는 종목은 평가금액·총자산 합계에 포함하지 않았습니다(0원으로 처리한 것이 아닙니다).
          아래 보유 종목 목록에서 &ldquo;시세 확인 불가&rdquo;로 표시된 종목을 확인하세요.
        </p>
      </div>
    );
  }

  // STALE
  return (
    <div className="banner banner-warning" role="status">
      <strong>일부 종목의 시세가 오래되었습니다.</strong>
      <p style={{ margin: "4px 0 0" }}>
        아래 평가금액은 최신 시세가 아닌 참고값입니다{asOf ? ` (기준시각: ${formatAsOf(asOf)})` : ""}.
        {hasUnavailable && " 일부 종목은 시세 확인 자체가 불가능해 합계에서 제외했습니다."}
      </p>
    </div>
  );
}

function PriceStatusBadge({ status }: { status: PriceStatus }) {
  if (status === "FRESH") return null;
  if (status === "UNAVAILABLE") {
    return <span className="badge badge-warning">시세 확인 불가</span>;
  }
  return <span className="badge badge-warning">시세 지연(참고값)</span>;
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
      <MarketDataStatusBanner
        status={performance.market_data_status}
        asOf={performance.market_data_as_of}
        hasUnavailable={performance.has_unavailable_positions}
      />

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
                <span className="row" style={{ gap: 8 }}>
                  <strong>{p.ticker}</strong>
                  <PriceStatusBadge status={p.price_status} />
                </span>
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
                <span>
                  {p.price_status === "UNAVAILABLE"
                    ? "시세 확인 불가"
                    : p.market_value
                      ? Number(p.market_value).toLocaleString()
                      : "-"}
                </span>
              </div>
              <div className="row-between">
                <span className="muted">평가손익</span>
                {p.price_status === "UNAVAILABLE" ? <span className="muted">확인 불가</span> : <PnlText value={p.unrealized_pnl} />}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
