"""get_latest_bar가 interval을 명시적으로 요구하고, 서로 다른 interval의
bar가 섞여 "최신 bar"로 잘못 선택되지 않음을 검증한다.

배경: 기존 구현은 instrument_id + bar_start만으로 최신 bar를 골랐다. 현재는
"1d"만 쓰여 잠재(latent) 상태였지만, 다른 interval의 bar가 더 최근 시각을
가지면 그 bar가 잘못 선택될 수 있었다(주문 체결가·포트폴리오 평가 오염).
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.domain.market import Bar
from app.domain.services.execution import get_latest_bar
from tests.conftest import seed_instrument_with_bar


def _add_bar(db, instrument_id, interval: str, bar_start, as_of, close: str) -> Bar:
    bar = Bar(
        instrument_id=instrument_id,
        interval=interval,
        open=close,
        high=close,
        low=close,
        close=close,
        volume=100_000,
        bar_start=bar_start,
        source="test-seed",
        as_of=as_of,
        delay_seconds=0,
    )
    db.add(bar)
    db.commit()
    return bar


def test_get_latest_bar_only_returns_requested_interval(db):
    instrument = seed_instrument_with_bar(db, "INTVMIX1", "NASDAQ", "USD", close=100)
    now = datetime.now(timezone.utc)

    # 1m bar가 1d bar보다 훨씬 최근 시각이더라도, interval="1d"로 조회하면
    # 1m bar는 절대 선택되지 않는다 — 다른 interval로 대체(fallback)하지 않는다.
    _add_bar(db, instrument.id, "1m", bar_start=now, as_of=now, close="999")

    bar = get_latest_bar(db, instrument.id, interval="1d")
    assert bar is not None
    assert bar.interval == "1d"
    assert Decimal(bar.close) == Decimal("100")


def test_get_latest_bar_picks_most_recent_within_same_interval(db):
    instrument = seed_instrument_with_bar(db, "INTVMIX2", "NASDAQ", "USD", close=100)
    now = datetime.now(timezone.utc)

    _add_bar(db, instrument.id, "1d", bar_start=now + timedelta(days=1), as_of=now, close="150")

    bar = get_latest_bar(db, instrument.id, interval="1d")
    assert Decimal(bar.close) == Decimal("150")


def test_get_latest_bar_returns_none_when_requested_interval_missing(db):
    instrument = seed_instrument_with_bar(db, "INTVMIX3", "NASDAQ", "USD", close=100)
    # seed_instrument_with_bar는 "1d"만 만든다 — "1m"을 요청하면 없어야 한다.
    bar = get_latest_bar(db, instrument.id, interval="1m")
    assert bar is None


def test_get_latest_bar_rejects_unsupported_interval(db):
    instrument = seed_instrument_with_bar(db, "INTVMIX4", "NASDAQ", "USD", close=100)
    with pytest.raises(ValueError):
        get_latest_bar(db, instrument.id, interval="5m")


def test_order_uses_only_daily_bar_even_when_minute_bar_is_newer(db):
    """주문 체결 경로(execution.build_quote가 내부적으로 쓰는 get_latest_bar)가
    더 최근인 1m bar에 오염되지 않고 1d bar의 as_of로 신선도를 판단함을 확인한다."""
    instrument = seed_instrument_with_bar(db, "INTVMIX5", "NASDAQ", "USD", close=100)
    now = datetime.now(timezone.utc)
    stale_1m_as_of = now - timedelta(seconds=2000)  # 900초 임계값을 훨씬 넘김

    # 1m bar 쪽은 bar_start는 더 최근이지만 as_of는 오히려 더 오래됐다고 하자 —
    # interval 필터가 없다면 bar_start DESC 정렬로 이 bar가 선택될 수 있었다.
    _add_bar(db, instrument.id, "1m", bar_start=now, as_of=stale_1m_as_of, close="999")

    bar = get_latest_bar(db, instrument.id, interval="1d")
    assert bar.interval == "1d"
    # 1d bar의 as_of(방금 seed된 신선한 값)가 신선도 판단에 쓰인다 — 1m의 stale
    # as_of가 섞여 들어오지 않는다.
    assert (datetime.now(timezone.utc) - bar.as_of).total_seconds() < 900
