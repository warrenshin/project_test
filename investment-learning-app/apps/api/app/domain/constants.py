"""도메인 전반에서 쓰는 상수. 매직 스트링을 한 곳에 모은다."""

ACCOUNT_CASH = "CASH"

ENTRY_INITIAL_DEPOSIT = "INITIAL_DEPOSIT"
ENTRY_BUY_TRADE = "BUY_TRADE"
ENTRY_SELL_TRADE = "SELL_TRADE"

# 주문 상태 머신 (6.6)
ORDER_CREATED = "CREATED"
ORDER_VALIDATED = "VALIDATED"
ORDER_ACCEPTED = "ACCEPTED"
ORDER_PARTIALLY_FILLED = "PARTIALLY_FILLED"
ORDER_FILLED = "FILLED"
ORDER_CANCELLED = "CANCELLED"
ORDER_EXPIRED = "EXPIRED"
ORDER_VALIDATION_FAILED = "VALIDATION_FAILED"
ORDER_REJECTED = "REJECTED"

ORDER_TERMINAL_STATUSES = {
    ORDER_FILLED,
    ORDER_CANCELLED,
    ORDER_EXPIRED,
    ORDER_VALIDATION_FAILED,
    ORDER_REJECTED,
}

EXCHANGE_MARKET_MAP = {
    "KRX": "KR",
    "KOSPI": "KR",
    "KOSDAQ": "KR",
    "NASDAQ": "US",
    "NYSE": "US",
    "AMEX": "US",
}

FEE_POLICY_VERSION = "v1"

# 시세 신선도 상태 (Phase A: MarketDataService.get_price_point가 판단).
# FRESH: 임계값 이내의 최신 bar. STALE: bar는 있지만 임계값을 넘겨 오래됨 —
# 주문은 차단하되 포트폴리오에는 참고값으로 표시한다. UNAVAILABLE: bar 자체가
# 없거나(한 번도 수집 안 됨) 환율 등 평가에 필요한 값이 없어 가격을 산출할 수
# 없음 — 0원이나 손실로 계산하지 않고 "확인 불가"로 표시한다.
PRICE_STATUS_FRESH = "FRESH"
PRICE_STATUS_STALE = "STALE"
PRICE_STATUS_UNAVAILABLE = "UNAVAILABLE"

# bars.interval에 저장 가능한 값의 전체 집합("1d, 1m 등" — Bar 모델 주석 참고).
# Phase A는 이 중 일봉("1d")만 실제로 수집·사용한다. get_latest_bar 호출자는
# 반드시 interval을 명시해야 하며(기본값 없음), 다른 interval의 bar가 조용히
# 섞여 들어가는 것을 막는다. 이 집합에 없는 값(오타·미지원 주기)은 명확히
# 거절한다 — "유효하지만 데이터가 없음"과 "애초에 잘못된 값"을 구분한다.
BAR_INTERVAL_DAILY = "1d"
BAR_INTERVAL_MINUTE = "1m"
SUPPORTED_BAR_INTERVALS = {BAR_INTERVAL_DAILY, BAR_INTERVAL_MINUTE}
