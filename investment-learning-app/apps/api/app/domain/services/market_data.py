"""시장 데이터 수집·정규화·검증. 명세서 6.4 참고.

Provider 추상화와 정규화·검증·upsert 로직만 이 모듈에 둔다. 실사용 가능한
`StooqProvider` 어댑터를 구현해뒀지만, 이 개발 세션의 샌드박스 아웃바운드
정책이 금융 데이터 호스트(stooq.com 등)를 차단하고 있어 **라이브로 검증하지
못했다**. 실제 배포 환경에서 egress가 허용되면 그대로 동작해야 하지만, 반드시
운영 투입 전에 재검증해야 한다 (services/market-data-worker/README.md 참고).

지금 당장 앱을 동작시키는 데이터는 이 로직이 아니라 시드 마이그레이션의
샘플 데이터다 (alembic/versions에서 'seed sample instruments' 참고).
"""

import csv
import io
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation

from sqlalchemy.orm import Session as DbSession

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


@dataclass
class RawBar:
    bar_start: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal


class MarketDataProvider(ABC):
    name: str

    @abstractmethod
    def fetch_daily_bars(self, ticker: str, exchange: str) -> list[RawBar]: ...


class StooqProvider(MarketDataProvider):
    """무료 stooq.com CSV 엔드포인트 어댑터. 미검증 — 위 모듈 docstring 참고."""

    name = "stooq"
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


def get_active_instrument(db: DbSession, ticker: str, exchange: str) -> Instrument | None:
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
    db.flush()
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
