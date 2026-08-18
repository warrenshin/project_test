/** 명세서 6, 12.3: 모든 핵심 화면 특히 주문 관련 화면에서 가상자금·모의투자임을 항상 표시한다. */
export function VirtualFundsBanner({ compact = false }: { compact?: boolean }) {
  if (compact) {
    return <span className="badge badge-virtual">가상자금 · 모의투자</span>;
  }
  return (
    <div className="banner banner-info">
      이 앱의 모든 금액과 체결은 <strong>가상자금 기반 모의투자</strong>입니다. 실제 증권 주문이
      접수되지 않으며, 실제 자금이 이동하지 않습니다.
    </div>
  );
}
