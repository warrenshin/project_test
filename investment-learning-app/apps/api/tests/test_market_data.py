"""Phase A: 시장 데이터 파서·검증·업서트·공급자 추상화 단위테스트.

이전까지 app/domain/services/market_data.py는 단위테스트가 0건이었다
(validate_bar/upsert_instrument/upsert_bars/StooqProvider._parse_csv 전부
미검증). 이 파일이 그 공백을 메운다. 실제 네트워크 호출은 어디에서도 하지
않는다 — health_check조차 httpx를 monkeypatch로 가로챈다.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.domain.constants import PRICE_STATUS_FRESH, PRICE_STATUS_STALE, PRICE_STATUS_UNAVAILABLE
from app.domain.services.market_data import (
    DemoMarketDataProvider,
    InvalidBarDataError,
    RawBar,
    StooqMarketDataProvider,
    UnsupportedExchangeError,
    classify_price_freshness,
    get_active_instrument,
    get_provider,
    upsert_bars,
    upsert_instrument,
    validate_bar,
)
from app.domain.services.market_data_service import get_price_point
from tests.conftest import seed_instrument_with_bar


def _valid_bar(**overrides) -> RawBar:
    defaults = dict(
        bar_start=datetime.now(timezone.utc) - timedelta(days=1),
        open=Decimal("100"),
        high=Decimal("105"),
        low=Decimal("95"),
        close=Decimal("102"),
        volume=Decimal("1000"),
    )
    defaults.update(overrides)
    return RawBar(**defaults)


# --- validate_bar ---


def test_validate_bar_accepts_normal_bar():
    validate_bar(_valid_bar())  # 예외가 없어야 정상


@pytest.mark.parametrize(
    "field,value",
    [("open", Decimal("0")), ("high", Decimal("-1")), ("low", Decimal("0")), ("close", Decimal("-5"))],
)
def test_validate_bar_rejects_non_positive_price(field, value):
    with pytest.raises(InvalidBarDataError):
        validate_bar(_valid_bar(**{field: value}))


def test_validate_bar_rejects_high_less_than_low():
    with pytest.raises(InvalidBarDataError):
        validate_bar(_valid_bar(high=Decimal("90"), low=Decimal("95")))


def test_validate_bar_rejects_open_outside_low_high_range():
    with pytest.raises(InvalidBarDataError):
        validate_bar(_valid_bar(open=Decimal("200"), low=Decimal("95"), high=Decimal("105")))


def test_validate_bar_rejects_close_outside_low_high_range():
    with pytest.raises(InvalidBarDataError):
        validate_bar(_valid_bar(close=Decimal("1"), low=Decimal("95"), high=Decimal("105")))


def test_validate_bar_rejects_negative_volume():
    with pytest.raises(InvalidBarDataError):
        validate_bar(_valid_bar(volume=Decimal("-1")))


def test_validate_bar_rejects_future_bar_start():
    with pytest.raises(InvalidBarDataError):
        validate_bar(_valid_bar(bar_start=datetime.now(timezone.utc) + timedelta(days=1)))


# --- upsert_instrument / upsert_bars (멱등성) ---


def test_upsert_instrument_reactivates_existing_active_instrument(db):
    first = upsert_instrument(db, "TESTU1", "NASDAQ", "USD", "Test Co")
    db.commit()

    second = upsert_instrument(db, "TESTU1", "NASDAQ", "USD", "Test Co (updated name)")
    db.commit()

    assert first.id == second.id  # 새 행을 만들지 않고 기존 행을 갱신
    assert second.name == "Test Co (updated name)"
    assert get_active_instrument(db, "TESTU1", "NASDAQ").id == first.id


def test_upsert_bars_does_not_duplicate_on_rerun(db):
    instrument = upsert_instrument(db, "TESTU2", "NASDAQ", "USD", "Test Co 2")
    db.commit()

    bar = _valid_bar()
    written_first = upsert_bars(db, instrument, [bar], source="test")
    db.commit()
    written_second = upsert_bars(db, instrument, [bar], source="test")
    db.commit()

    assert written_first == 1
    assert written_second == 1  # 갱신으로 처리되지만 여전히 "반영된 개수"는 1
    from app.domain.market import Bar

    rows = db.query(Bar).filter(Bar.instrument_id == instrument.id, Bar.bar_start == bar.bar_start).all()
    assert len(rows) == 1  # 중복 행 없음(UNIQUE(instrument_id, interval, bar_start))


def test_upsert_bars_skips_invalid_bars_but_keeps_valid_ones(db):
    instrument = upsert_instrument(db, "TESTU3", "NASDAQ", "USD", "Test Co 3")
    db.commit()

    good = _valid_bar(bar_start=datetime.now(timezone.utc) - timedelta(days=2))
    bad = _valid_bar(bar_start=datetime.now(timezone.utc) - timedelta(days=1), high=Decimal("1"), low=Decimal("95"))

    written = upsert_bars(db, instrument, [good, bad], source="test")
    db.commit()

    assert written == 1


# --- DemoMarketDataProvider ---


def test_demo_provider_is_deterministic_for_same_ticker():
    provider = DemoMarketDataProvider()
    bars_a = provider.fetch_daily_bars("005930", "KRX")
    bars_b = provider.fetch_daily_bars("005930", "KRX")
    assert bars_a == bars_b


def test_demo_provider_varies_by_ticker():
    provider = DemoMarketDataProvider()
    assert provider.fetch_daily_bars("005930", "KRX") != provider.fetch_daily_bars("AAPL", "NASDAQ")


def test_demo_provider_bars_pass_validation():
    provider = DemoMarketDataProvider()
    for bar in provider.fetch_daily_bars("AAPL", "NASDAQ"):
        validate_bar(bar)  # 예외 없어야 정상


def test_demo_provider_health_check_always_ok():
    health = DemoMarketDataProvider().health_check()
    assert health.ok is True


# --- StooqMarketDataProvider ---


def test_stooq_symbol_mapping_for_kr_and_us_exchanges():
    provider = StooqMarketDataProvider()
    assert provider._symbol("005930", "KRX") == "005930.kr"
    assert provider._symbol("AAPL", "NASDAQ") == "aapl.us"


def test_stooq_symbol_mapping_rejects_unsupported_exchange():
    provider = StooqMarketDataProvider()
    with pytest.raises(UnsupportedExchangeError):
        provider._symbol("XYZ", "LSE")


def test_stooq_parse_csv_skips_malformed_rows_but_keeps_valid_ones():
    provider = StooqMarketDataProvider()
    csv_text = (
        "Date,Open,High,Low,Close,Volume\n"
        "2026-08-18,100,105,95,102,1000\n"
        "not-a-date,100,105,95,102,1000\n"  # 헤더 불일치/파싱 실패 -> 건너뜀
        "2026-08-19,101,106,96,103,\n"  # Volume 결측 -> Decimal('') 실패 -> 건너뜀
    )
    bars = provider._parse_csv(csv_text)
    assert len(bars) == 1
    assert bars[0].close == Decimal("102")


def test_stooq_health_check_reports_failure_without_raising(monkeypatch):
    import httpx

    def _raise(*args, **kwargs):
        raise httpx.ConnectError("network blocked")

    monkeypatch.setattr(httpx, "get", _raise)
    health = StooqMarketDataProvider().health_check()
    assert health.ok is False
    assert "network blocked" in health.detail


# --- get_provider factory ---


def test_get_provider_returns_expected_types():
    assert isinstance(get_provider("demo"), DemoMarketDataProvider)
    assert isinstance(get_provider("stooq"), StooqMarketDataProvider)


def test_get_provider_rejects_unknown_name():
    with pytest.raises(ValueError):
        get_provider("nope")


# --- classify_price_freshness / get_price_point (FRESH/STALE/UNAVAILABLE) ---


def test_classify_price_freshness_fresh_within_threshold():
    as_of = datetime.now(timezone.utc) - timedelta(seconds=10)
    assert classify_price_freshness(as_of, staleness_threshold_seconds=900) == PRICE_STATUS_FRESH


def test_classify_price_freshness_stale_beyond_threshold():
    as_of = datetime.now(timezone.utc) - timedelta(seconds=1000)
    assert classify_price_freshness(as_of, staleness_threshold_seconds=900) == PRICE_STATUS_STALE


def test_get_price_point_unavailable_when_no_bar_ever(db):
    instrument = upsert_instrument(db, "TESTU4", "NASDAQ", "USD", "Test Co 4")
    db.commit()

    point = get_price_point(db, instrument.id, staleness_threshold_seconds=900)
    assert point.status == PRICE_STATUS_UNAVAILABLE
    assert point.price is None  # 0이 아니라 None — 호출측이 0으로 오인하지 않게


# --- production 안전장치: Stooq는 production 기본 공급자로 쓸 수 없다 ---


def test_production_rejects_stooq_as_market_data_provider():
    from pydantic import ValidationError

    from app.core.config import Settings

    try:
        Settings(
            environment="production",
            cookie_secure=True,
            jwt_secret="a-real-secret",
            market_data_provider="stooq",
        )
        assert False, "production + MARKET_DATA_PROVIDER=stooq는 반드시 실패해야 한다"
    except ValidationError as exc:
        assert "MARKET_DATA_PROVIDER" in str(exc)

    # demo는 production에서도 허용된다(선정된 상용 공급자가 생기기 전까지의 기본값)
    prod_settings = Settings(
        environment="production", cookie_secure=True, jwt_secret="a-real-secret", market_data_provider="demo"
    )
    assert prod_settings.market_data_provider == "demo"


def test_get_price_point_fresh_and_stale(db):
    fresh_instrument = seed_instrument_with_bar(db, "TESTF1", "NASDAQ", "USD", close=100)
    stale_instrument = seed_instrument_with_bar(
        db, "TESTF2", "NASDAQ", "USD", close=100, as_of=datetime.now(timezone.utc) - timedelta(seconds=1000)
    )

    fresh_point = get_price_point(db, fresh_instrument.id, staleness_threshold_seconds=900)
    stale_point = get_price_point(db, stale_instrument.id, staleness_threshold_seconds=900)

    assert fresh_point.status == PRICE_STATUS_FRESH
    assert stale_point.status == PRICE_STATUS_STALE
    assert stale_point.price == Decimal("100")  # STALE이어도 값 자체는 그대로 반환(호출측이 참고값으로 쓸 수 있게)
