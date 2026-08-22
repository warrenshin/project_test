"""시장 데이터 수집·정규화·검증. 명세서 6.4 참고.

Provider 추상화와 정규화·검증·upsert 로직을 이 모듈에 둔다 (Phase A: 시장
데이터 공급자 추상화). `MarketDataProvider`는 서로 다른 공급자(개발용/기술
검증용/향후 선정할 상용 공급자)를 같은 방식으로 다룰 수 있게 하는 최소
계약이다 — 한국·미국 시장에 서로 다른 공급자를 붙일 수 있고, 개발용과
운영용 공급자를 분리할 수 있도록 설계했다(구현 전 결정사항 1).

현재 구현체는 두 가지뿐이다:

- `DemoMarketDataProvider`: 외부 네트워크를 전혀 쓰지 않는다. 티커별로
  결정론적인(=항상 같은 입력에 같은 출력) 합성 일봉을 생성해, 실제 공급자
  없이도 수집→검증→upsert 파이프라인 전체를 재현·테스트할 수 있게 한다.
  `is_delayed=True`로 항상 표시되며 실거래 판단 근거가 될 수 없다.
- `StooqMarketDataProvider`: 무료 stooq.com CSV 엔드포인트 어댑터.
  **개발·기술검증용으로만 유지한다 — 상용 운영의 기본 공급자로 쓰지
  않는다.** 상업적 표시·재배포 권한을 공식 문서에서 확인하지 못했기
  때문이다(시장 데이터 공급자 조사 보고서 참고). 이 개발 세션의 샌드박스
  아웃바운드 정책이 금융 데이터 호스트를 차단하고 있어 라이브로 검증하지도
  못했다 — 실제 배포 환경에서 egress가 허용되더라도 반드시 운영 투입 전에
  재검증해야 한다 (services/market-data-worker/README.md 참고).

지금 API가 서빙하는 데이터는 이 로직이 아니라 시드 마이그레이션의 샘플
데이터다 (alembic/versions에서 'seed sample instruments' 참고). 선정된
상용 공급자 adapter는 Phase B에서, 라이선스·계약 조건이 확정된 뒤에만
추가한다 — 이번 Phase A에서는 구현하지 않는다.
"""

import csv
import hashlib
import io
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DbSession

from app.domain.constants import PRICE_STATUS_FRESH, PRICE_STATUS_STALE
from app.domain.market import Bar, Instrument

EXCHANGE_TO_STOOQ_SUFFIX = {
    "NASDAQ": "us",
    "NYSE": "us",
    "AMEX": "us",
    "KRX": "kr",
    "KOSPI": "kr",
    "KOSDAQ": "kr",
}


class MarketDataError(Exception):
    pass


class UnsupportedExchangeError(MarketDataError):
    pass


class ProviderFetchError(MarketDataError):
    pass


class InvalidBarDataError(MarketDataError):
    pass


class InvalidInstrumentIdentifierError(MarketDataError):
    pass


@dataclass
class RawBar:
    bar_start: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal


@dataclass
class ProviderHealth:
    """공급자가 지금 정상 응답하는지. 예외를 던지지 않고 항상 이 값을 반환한다
    — 호출측(장애 시나리오 판단 로직)이 try/except 없이 상태를 볼 수 있게."""

    ok: bool
    checked_at: datetime
    detail: str = ""


class MarketDataProvider(ABC):
    """공급자 추상화. 새 공급자를 추가할 때는 이 계약만 만족하면 되고, 호출
    측(수집 스크립트·서비스 계층)은 어떤 구현체인지 몰라도 된다."""

    name: str
    # 이 공급자가 원천적으로 지연 데이터만 제공하는지(실시간 여부와 무관하게
    # 항상 True로 취급해야 하면 True). 개별 bar의 실제 지연은 delay_seconds로.
    is_delayed: bool = True

    @abstractmethod
    def fetch_daily_bars(self, ticker: str, exchange: str) -> list[RawBar]: ...

    @abstractmethod
    def health_check(self) -> ProviderHealth: ...


class DemoMarketDataProvider(MarketDataProvider):
    """외부 네트워크를 쓰지 않는 개발·테스트 전용 공급자.

    같은 (ticker, exchange)에는 항상 같은 합성 데이터를 생성한다(티커 문자열의
    해시로 시드를 고정) — 여러 번 실행해도 재현 가능해 단위테스트에서 쓰기
    좋다. 실거래 판단 근거로 쓸 수 없으므로 upsert 시 source는 항상 "demo"로
    남는다.
    """

    name = "demo"
    is_delayed = True

    _DAYS = 5

    def _seed(self, ticker: str, exchange: str) -> int:
        digest = hashlib.sha256(f"{ticker.upper()}.{exchange.upper()}".encode()).digest()
        return int.from_bytes(digest[:4], "big")

    def fetch_daily_bars(self, ticker: str, exchange: str) -> list[RawBar]:
        seed = self._seed(ticker, exchange)
        # 시드값만으로 -0.6% ~ +0.6% 범위의 결정론적 일일 등락률을 만든다.
        base_price = Decimal(100 + seed % 900)
        close = base_price
        # 일 단위로 고정해야 같은 날 여러 번 호출해도 완전히 같은 결과가 나온다
        # (초 단위 datetime.now()를 쓰면 호출마다 bar_start가 미세하게 달라져
        # "결정론적"이라는 이 provider의 존재 이유가 깨진다).
        now = datetime.combine(datetime.now(timezone.utc).date(), datetime.min.time(), tzinfo=timezone.utc)
        bars: list[RawBar] = []
        for day_offset in range(self._DAYS, 0, -1):
            delta_bp = (seed >> (day_offset * 3)) % 121 - 60  # -60 ~ +60 (bp)
            open_price = close
            close = (close * (Decimal(10000 + delta_bp) / Decimal(10000))).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            high = max(open_price, close) * Decimal("1.003")
            low = min(open_price, close) * Decimal("0.997")
            bars.append(
                RawBar(
                    bar_start=now - timedelta(days=day_offset),
                    open=open_price,
                    high=high.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
                    low=low.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
                    close=close,
                    volume=Decimal(100000 + seed % 900000),
                )
            )
        return bars

    def health_check(self) -> ProviderHealth:
        return ProviderHealth(ok=True, checked_at=datetime.now(timezone.utc), detail="demo provider는 항상 사용 가능")


class StooqMarketDataProvider(MarketDataProvider):
    """무료 stooq.com CSV 엔드포인트 어댑터. 개발·기술검증용으로만 유지한다
    — 상업적 표시·재배포 권한을 확인하기 전에는 공개 서비스 데이터로 쓰지
    않는다. 라이브 미검증 — 위 모듈 docstring 참고."""

    name = "stooq"
    is_delayed = True
    BASE_URL = "https://stooq.com/q/d/l/"

    def _symbol(self, ticker: str, exchange: str) -> str:
        suffix = EXCHANGE_TO_STOOQ_SUFFIX.get(exchange.upper())
        if suffix is None:
            raise UnsupportedExchangeError(f"stooq가 지원하지 않는 거래소입니다: {exchange}")
        return f"{ticker.lower()}.{suffix}"

    def fetch_daily_bars(self, ticker: str, exchange: str) -> list[RawBar]:
        import httpx

        symbol = self._symbol(ticker, exchange)
        try:
            response = httpx.get(self.BASE_URL, params={"s": symbol, "i": "d"}, timeout=15)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ProviderFetchError(f"{self.name} 조회 실패 ({symbol}): {exc}") from exc
        return self._parse_csv(response.text)

    def _parse_csv(self, text: str) -> list[RawBar]:
        reader = csv.DictReader(io.StringIO(text))
        bars: list[RawBar] = []
        for row in reader:
            try:
                bar_date = datetime.strptime(row["Date"], "%Y-%m-%d").replace(tzinfo=timezone.utc)
                bars.append(
                    RawBar(
                        bar_start=bar_date,
                        open=Decimal(row["Open"]),
                        high=Decimal(row["High"]),
                        low=Decimal(row["Low"]),
                        close=Decimal(row["Close"]),
                        volume=Decimal(row["Volume"]),
                    )
                )
            except (KeyError, InvalidOperation, ValueError):
                continue  # 헤더 불일치·결측 행은 건너뛴다 (6.4: 결측 데이터 자동 검증)
        return bars

    def health_check(self) -> ProviderHealth:
        import httpx

        now = datetime.now(timezone.utc)
        try:
            response = httpx.get(self.BASE_URL, params={"s": "aapl.us", "i": "d"}, timeout=5)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            return ProviderHealth(ok=False, checked_at=now, detail=f"{self.name} 응답 실패: {exc}")
        return ProviderHealth(ok=True, checked_at=now)


# 하위 호환 별칭 — 기존 코드가 `StooqProvider`를 참조하던 곳이 있으면 계속 동작한다.
StooqProvider = StooqMarketDataProvider


def get_provider(name: str) -> MarketDataProvider:
    """설정값(예: MARKET_DATA_PROVIDER 환경변수)으로 공급자 구현체를 고른다.
    아직 선정된 상용 공급자가 없으므로 이 두 개뿐이다(Phase A)."""
    providers: dict[str, type[MarketDataProvider]] = {
        "demo": DemoMarketDataProvider,
        "stooq": StooqMarketDataProvider,
    }
    provider_cls = providers.get(name)
    if provider_cls is None:
        raise ValueError(f"알 수 없는 시장 데이터 공급자입니다: {name} (가능한 값: {', '.join(providers)})")
    return provider_cls()


def classify_price_freshness(as_of: datetime, staleness_threshold_seconds: int) -> str:
    """가격의 기준시각(as_of)이 임계값 안이면 FRESH, 벗어나면 STALE(경계값 900초는
    FRESH — age_seconds <= threshold).

    `execution.build_quote`(주문 경로)와 `market_data_service.get_price_point`
    (포트폴리오 조회 경로)가 이 판단을 각자 다시 구현하지 않고 여기서만 계산한다
    — 두 경로의 "오래됨" 기준이 은근슬쩍 어긋나는 것을 막는다. bar 자체가
    없는 경우(UNAVAILABLE)는 이 함수의 책임이 아니다 — 호출측이 먼저 판단한다.

    as_of가 미래 시각이거나 timezone-naive이면 ValueError를 던진다 — 둘 다
    신뢰할 수 없는 입력이다(공급자 응답 손상, 시계 어긋남, 정규화 누락).
    이를 조용히 "FRESH"로 계산하면(미래 시각은 age가 음수라 threshold 이하로
    나온다) 오히려 가장 못 믿을 데이터가 가장 신선한 데이터로 둔갑한다.
    호출측(build_quote/get_price_point)은 이 예외를 UNAVAILABLE/거부로
    변환한다 — 못 믿을 시각을 FRESH로 계산하는 것보다 안전하다.
    """
    if as_of.tzinfo is None:
        raise ValueError(f"as_of는 timezone-aware(UTC)여야 합니다: {as_of!r}")
    now = datetime.now(timezone.utc)
    age_seconds = (now - as_of).total_seconds()
    if age_seconds < 0:
        raise ValueError(f"as_of가 미래 시각입니다: {as_of.isoformat()} (현재: {now.isoformat()})")
    return PRICE_STATUS_FRESH if age_seconds <= staleness_threshold_seconds else PRICE_STATUS_STALE


def validate_bar(bar: RawBar) -> None:
    """명세서 6.4: 결측·이상치 데이터를 자동 검증한다."""
    if bar.open <= 0 or bar.high <= 0 or bar.low <= 0 or bar.close <= 0:
        raise InvalidBarDataError(f"가격은 0보다 커야 합니다: {bar}")
    if bar.high < bar.low:
        raise InvalidBarDataError(f"high가 low보다 작습니다: {bar}")
    if not (bar.low <= bar.open <= bar.high) or not (bar.low <= bar.close <= bar.high):
        raise InvalidBarDataError(f"open/close가 low-high 범위를 벗어났습니다: {bar}")
    if bar.volume < 0:
        raise InvalidBarDataError(f"거래량은 음수일 수 없습니다: {bar}")
    if bar.bar_start > datetime.now(timezone.utc) + timedelta(minutes=1):
        # 공급자 응답이 손상되었거나 시계가 어긋난 경우, 미래 시각의 가짜 bar가
        # "최신 bar"로 잘못 선택되는 것을 막는다(get_latest_bar는 bar_start
        # 내림차순 정렬에 의존한다).
        raise InvalidBarDataError(f"bar_start가 미래 시각입니다: {bar}")


def normalize_ticker(ticker: str) -> str:
    """seed/ingestion/API/테스트가 공통으로 써야 하는 정규화 규칙: 앞뒤 공백 제거 +
    대문자 통일. 이미 이 형태인 기존 값(예: "005930", "AAPL")은 그대로 유지된다 —
    기존 종목 ID를 바꾸지 않는다. 사용자 검색어나 provider 고유 심볼은 이 함수를
    거치지 않는다 — 내부 ticker 식별자에만 적용한다."""
    normalized = ticker.strip().upper()
    if not normalized:
        raise InvalidInstrumentIdentifierError("ticker는 빈 값일 수 없습니다.")
    return normalized


def normalize_exchange(exchange: str) -> str:
    """ticker와 동일한 정규화 규칙(공백 제거 + 대문자)을 exchange 코드에도 적용한다."""
    normalized = exchange.strip().upper()
    if not normalized:
        raise InvalidInstrumentIdentifierError("exchange는 빈 값일 수 없습니다.")
    return normalized


def get_active_instrument(db: DbSession, ticker: str, exchange: str) -> Instrument | None:
    ticker = normalize_ticker(ticker)
    exchange = normalize_exchange(exchange)
    return (
        db.query(Instrument)
        .filter(Instrument.ticker == ticker, Instrument.exchange == exchange, Instrument.valid_to.is_(None))
        .first()
    )


def upsert_instrument(
    db: DbSession,
    ticker: str,
    exchange: str,
    currency: str,
    name: str,
    industry: str | None = None,
    valid_from: date | None = None,
) -> Instrument:
    """(exchange, 정규화된 ticker)당 활성(valid_to IS NULL) 행이 하나만 존재하게 한다.

    "확인 후 삽입"(check-then-insert)만으로는 두 worker가 동시에 같은 종목을
    처음 수집할 때의 race condition을 막을 수 없다 — 두 세션 모두 "활성 행 없음"을
    보고 나서 둘 다 삽입을 시도할 수 있다. 그래서 DB의 partial unique index를
    최종 방어선으로 두고, 그 제약 위반(IntegrityError)을 여기서 잡아 방금 다른
    worker가 커밋한 행을 다시 조회해 그쪽을 갱신하는 것으로 안전하게 수렴시킨다.
    SAVEPOINT(begin_nested) 안에서만 삽입을 시도하므로, 충돌해도 이 함수 호출
    자체만 롤백되고 같은 세션의 다른 변경사항은 영향받지 않는다.
    """
    ticker = normalize_ticker(ticker)
    exchange = normalize_exchange(exchange)

    instrument = get_active_instrument(db, ticker, exchange)
    if instrument is not None:
        instrument.name = name
        instrument.currency = currency
        instrument.industry = industry
        return instrument

    instrument = Instrument(
        ticker=ticker,
        exchange=exchange,
        currency=currency,
        name=name,
        industry=industry,
        is_tradable=True,
        valid_from=valid_from,
    )
    db.add(instrument)
    try:
        with db.begin_nested():
            db.flush()
    except IntegrityError:
        # begin_nested()의 SAVEPOINT는 flush 실패 시 자동으로 그 지점까지
        # 롤백되지만, 세션 자체는 "flush 중 예외 발생" 상태로 남아 명시적
        # rollback() 전에는 어떤 쿼리도 거부한다(SQLAlchemy 특성). 여기서
        # rollback()을 호출해도 SAVEPOINT 범위 안에서만 되돌아가므로, 같은
        # 세션에 있는 다른 무관한 pending 변경사항은 영향받지 않는다.
        db.rollback()
        instrument = get_active_instrument(db, ticker, exchange)
        if instrument is None:
            # unique 제약이 이 (exchange, ticker) 조합과 무관한 다른 이유로
            # 실패했다는 뜻이다 — 조용히 삼키지 않고 그대로 올린다.
            raise
        instrument.name = name
        instrument.currency = currency
        instrument.industry = industry
    return instrument


def upsert_bars(
    db: DbSession, instrument: Instrument, raw_bars: list[RawBar], source: str, interval: str = "1d", delay_seconds: int = 0
) -> int:
    """유효성 검증을 통과한 bar만 반영한다. 이미 있는 (instrument, interval, bar_start)는 갱신한다.

    UNIQUE(instrument_id, interval, bar_start) 제약 덕분에 같은 데이터를 여러 번
    수집해도 행이 중복되지 않는다 (6.4 중복 데이터 방지, 6.5 idempotency 원칙과 동일 취지).
    """
    now = datetime.now(timezone.utc)
    written = 0
    for raw in raw_bars:
        try:
            validate_bar(raw)
        except InvalidBarDataError:
            continue  # 이상치는 건너뛰고 나머지는 계속 반영한다

        existing = (
            db.query(Bar)
            .filter(Bar.instrument_id == instrument.id, Bar.interval == interval, Bar.bar_start == raw.bar_start)
            .first()
        )
        if existing is not None:
            existing.open, existing.high, existing.low, existing.close, existing.volume = (
                raw.open,
                raw.high,
                raw.low,
                raw.close,
                raw.volume,
            )
            existing.source = source
            existing.as_of = now
            existing.delay_seconds = delay_seconds
        else:
            db.add(
                Bar(
                    instrument_id=instrument.id,
                    interval=interval,
                    open=raw.open,
                    high=raw.high,
                    low=raw.low,
                    close=raw.close,
                    volume=raw.volume,
                    bar_start=raw.bar_start,
                    source=source,
                    as_of=now,
                    delay_seconds=delay_seconds,
                )
            )
        written += 1
    return written
