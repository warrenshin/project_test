const STALE_THRESHOLD_SECONDS = 900; // 백엔드 market_data_staleness_threshold_seconds 기본값과 동일

function formatAsOf(asOf: string): string {
  const date = new Date(asOf);
  return date.toLocaleString("ko-KR", { hour12: false });
}

/** 명세서 12.3: 데이터 기준시각과 지연 여부를 항상 표시한다. */
export function MarketDataBadge({
  asOf,
  source,
  delaySeconds,
}: {
  asOf: string;
  source: string;
  delaySeconds: number;
}) {
  // 표시 시점 기준 경과 시간을 보여주는 배지이므로 렌더링 중 Date.now() 호출이 불가피하다.
  // eslint-disable-next-line react-hooks/purity
  const ageSeconds = (Date.now() - new Date(asOf).getTime()) / 1000;
  const isStale = ageSeconds > STALE_THRESHOLD_SECONDS || delaySeconds > 0;

  return (
    <div className="row" style={{ flexWrap: "wrap" }}>
      <span className={`badge ${isStale ? "badge-warning" : "badge-virtual"}`}>
        {isStale ? "시세 지연 가능" : "기준시각"}: {formatAsOf(asOf)}
      </span>
      <span className="muted">출처: {source}</span>
      {delaySeconds > 0 && <span className="muted">지연 {delaySeconds}초</span>}
    </div>
  );
}
