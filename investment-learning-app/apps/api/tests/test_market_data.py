"""Phase A: 시장 데이터 파서·검증·업서트·공급자 추상화 단위테스트.

이전까지 app/domain/services/market_data.py는 단위테스트가 0건이었다
(validate_bar/upsert_instrument/upsert_bars/StooqProvider._parse_csv 전부
미검증). 이 파일이 그 공백을 메운다. 실제 네트워크 호출은 어디에서도 하지
않는다 — health_check조차 httpx를 monkeypatch로 가로챈다.
"""

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.domain.constants import PRICE_STATUS_FRESH, PRICE_STATUS_STALE, PRICE_STATUS_UNAVAILABLE
from app.domain.services.market_data import (
    DemoMarketDataProvider,
    InvalidBarDataError,
    InvalidInstrumentIdentifierError,
    ProviderFetchError,
    RawBar,
    StooqMarketDataProvider,
    UnsupportedExchangeError,
    classify_price_freshness,
    get_active_instrument,
    get_provider,
    normalize_exchange,
    normalize_ticker,
    upsert_bars,
    upsert_instrument,
    validate_bar,
)
from app.domain.services.market_data_service import get_price_point
from tests.conftest import client, seed_instrument_with_bar, signup_user


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


def _bar_at(bar_start: datetime, close: Decimal) -> RawBar:
    """close 값을 감싸는 high/low를 함께 만들어 validate_bar를 항상 통과하게
    한다 — close만 바꾸고 high/low 기본값(95~105)을 그대로 두면 close가 그
    범위를 벗어나 upsert_bars가 조용히 건너뛰어 버린다."""
    return _valid_bar(bar_start=bar_start, open=close, high=close + Decimal("5"), low=close - Decimal("5"), close=close)


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


# --- ticker/exchange 정규화 ---


def test_normalize_ticker_trims_and_uppercases():
    assert normalize_ticker("  aapl  ") == "AAPL"
    assert normalize_ticker("005930") == "005930"  # 이미 정규화된 값은 그대로


def test_normalize_exchange_trims_and_uppercases():
    assert normalize_exchange(" nasdaq ") == "NASDAQ"


def test_normalize_ticker_rejects_empty():
    with pytest.raises(InvalidInstrumentIdentifierError):
        normalize_ticker("   ")


def test_normalize_exchange_rejects_empty():
    with pytest.raises(InvalidInstrumentIdentifierError):
        normalize_exchange("")


def test_upsert_instrument_normalizes_ticker_and_exchange_before_storing(db):
    instrument = upsert_instrument(db, "  msft  ", " nasdaq ", "USD", "Microsoft")
    db.commit()

    assert instrument.ticker == "MSFT"
    assert instrument.exchange == "NASDAQ"


def test_upsert_instrument_treats_case_and_whitespace_variants_as_same_instrument(db):
    first = upsert_instrument(db, "GOOGL", "NASDAQ", "USD", "Alphabet")
    db.commit()

    second = upsert_instrument(db, " googl ", "nasdaq", "USD", "Alphabet Inc.")
    db.commit()

    assert first.id == second.id


def test_upsert_instrument_race_condition_converges_to_single_row(db, monkeypatch):
    """두 worker(세션)가 동시에 같은 종목을 처음 만들려는 상황을 재현한다.

    check-then-insert만으로는 막을 수 없는 race condition이다: 두 세션 모두
    "활성 종목 없음"을 확인한 뒤 각자 삽입을 시도할 수 있다. DB의
    partial unique index(exchange, ticker WHERE valid_to IS NULL)가 최종
    방어선이 되어 뒤늦게 온 쪽의 삽입을 막고, upsert_instrument는 그 충돌을
    잡아 먼저 커밋된 행을 재조회해 갱신하는 것으로 안전하게 수렴해야 한다 —
    중복 행이 생기거나 예외가 그대로 새어나가면 안 된다.
    """
    from app.core.db import SessionLocal
    from app.domain.market import Instrument
    import app.domain.services.market_data as market_data_module

    session_b = SessionLocal()
    try:
        winner = upsert_instrument(session_b, "RACE1", "NASDAQ", "USD", "Race Co (B, 먼저 커밋)")
        session_b.commit()

        # session(=db fixture, "session A")은 자신의 확인 시점에는 활성 종목이
        # 없었다고 가정한다 — 실제로는 그 직후 session_b가 커밋을 마쳤지만
        # session A는 알 수 없다. get_active_instrument의 첫 호출만 None으로
        # 속여 이 상황을 결정론적으로 재현한다(두 번째 호출부터는 실제 동작).
        original = market_data_module.get_active_instrument
        call_count = {"n": 0}

        def fake_get_active_instrument(session, ticker, exchange):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return None
            return original(session, ticker, exchange)

        monkeypatch.setattr(market_data_module, "get_active_instrument", fake_get_active_instrument)

        loser_result = upsert_instrument(db, "RACE1", "NASDAQ", "USD", "Race Co (A, 뒤늦게 도착)")
        db.commit()

        assert loser_result.id == winner.id  # 중복 행이 생기지 않고 같은 행으로 수렴
        assert loser_result.name == "Race Co (A, 뒤늦게 도착)"  # 나중 갱신이 반영됨

        active_count = (
            db.query(Instrument)
            .filter(Instrument.ticker == "RACE1", Instrument.exchange == "NASDAQ", Instrument.valid_to.is_(None))
            .count()
        )
        assert active_count == 1
    finally:
        session_b.close()


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


# --- 900초 경계값 (고정 시각 사용 — 실행 시각에 따라 흔들리지 않는다) ---

_FIXED_NOW = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)


class _FixedDatetime(datetime):
    """datetime.now(tz)가 항상 _FIXED_NOW를 반환하게 한다. classify_price_freshness는
    모듈 안에서 `datetime.now(timezone.utc)`를 직접 호출하므로, 모듈이 참조하는
    `datetime` 이름 자체를 이 클래스로 바꿔치기해야 실제로 경계값을 고정할 수
    있다(단순히 as_of만 계산해서는 테스트 실행 시각과의 미세한 시간차 때문에
    경계 바로 위/아래로 흔들릴 수 있다)."""

    @classmethod
    def now(cls, tz=None):
        return _FIXED_NOW if tz is not None else _FIXED_NOW.replace(tzinfo=None)


@pytest.fixture
def frozen_now(monkeypatch):
    import app.domain.services.market_data as market_data_module

    monkeypatch.setattr(market_data_module, "datetime", _FixedDatetime)
    return _FIXED_NOW


def test_boundary_899_seconds_is_fresh(frozen_now):
    as_of = frozen_now - timedelta(seconds=899)
    assert classify_price_freshness(as_of, staleness_threshold_seconds=900) == PRICE_STATUS_FRESH


def test_boundary_exactly_900_seconds_is_fresh_per_current_policy(frozen_now):
    as_of = frozen_now - timedelta(seconds=900)
    assert classify_price_freshness(as_of, staleness_threshold_seconds=900) == PRICE_STATUS_FRESH


def test_boundary_901_seconds_is_stale(frozen_now):
    as_of = frozen_now - timedelta(seconds=901)
    assert classify_price_freshness(as_of, staleness_threshold_seconds=900) == PRICE_STATUS_STALE


def test_future_as_of_is_rejected_not_treated_as_fresh(frozen_now):
    """as_of가 미래 시각이면 age가 음수가 되어 자칫 "가장 신선한 값"으로
    잘못 계산될 수 있다 — 조용히 FRESH로 계산하지 않고 명확히 거절해야 한다."""
    as_of = frozen_now + timedelta(seconds=10)
    with pytest.raises(ValueError):
        classify_price_freshness(as_of, staleness_threshold_seconds=900)


def test_timezone_naive_as_of_is_rejected(frozen_now):
    naive_as_of = frozen_now.replace(tzinfo=None) - timedelta(seconds=10)
    with pytest.raises(ValueError):
        classify_price_freshness(naive_as_of, staleness_threshold_seconds=900)


def test_get_price_point_treats_future_as_of_as_unavailable_not_fresh(db):
    """bar.as_of가 (데이터 손상 등으로) 미래 시각이면, 포트폴리오 평가는 이를
    FRESH로 신뢰하지 않고 UNAVAILABLE로 처리해야 한다 — 0으로 계산되지도
    않고, 못 믿을 값을 정상 가격처럼 보여주지도 않는다."""
    instrument = seed_instrument_with_bar(db, "TESTFUT1", "NASDAQ", "USD", close=100)
    from app.domain.market import Bar

    bar = db.query(Bar).filter(Bar.instrument_id == instrument.id).first()
    bar.as_of = datetime.now(timezone.utc) + timedelta(minutes=10)
    db.commit()

    point = get_price_point(db, instrument.id, staleness_threshold_seconds=900)
    assert point.status == PRICE_STATUS_UNAVAILABLE
    assert point.price is None


def test_order_rejected_when_bar_as_of_is_future(db):
    """주문 경로도 미래 as_of를 STALE과 동일하게(신뢰 불가 -> 거부) 처리해야
    한다 — 조용히 체결시키면 안 된다."""
    instrument = seed_instrument_with_bar(db, "TESTFUT2", "NASDAQ", "USD", close=100)
    from app.domain.market import Bar

    bar = db.query(Bar).filter(Bar.instrument_id == instrument.id).first()
    bar.as_of = datetime.now(timezone.utc) + timedelta(minutes=10)
    db.commit()

    cookies, portfolio_id = signup_user("mdfuture-order")
    payload = {"instrument_id": str(instrument.id), "side": "BUY", "order_type": "MARKET", "quantity": "1"}
    res = client.post(
        f"/v1/portfolios/{portfolio_id}/orders", json=payload, cookies=cookies,
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert res.status_code == 409, res.text


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


# --- 공급자 전환 시 데이터 혼입 (item 11) ---
#
# 현재 DB 구조에는 ingestion_batch_id/수집 이력이 없다(감사에서 확인된 한계,
# Phase B로 이연). 그래서 여기서 검증 가능한 것은 "지금 실제로 구현된 upsert_bars
# 정책이 무엇인가"까지다: 같은 (instrument, interval, bar_start)를 다른 공급자로
# 재수집하면 예전 값을 보존하거나 공급자 우선순위를 따지지 않고 **마지막으로
# upsert_bars를 호출한 쪽이 무조건 이긴다**(last-write-wins, 호출 순서 기준으로는
# 결정론적이지만 "더 신뢰할 만한 공급자"를 우선하지는 않는다). 이 자체가 Phase B에서
# provenance/우선순위 정책이 필요하다는 근거이므로, 아래 테스트는 이 현재 정책을
# 있는 그대로 문서화하고 확인한다 — "더 나은 정책"을 구현하지는 않는다.


def test_reingesting_same_bar_with_different_provider_is_last_write_wins(db):
    instrument = upsert_instrument(db, "TESTSWITCH1", "NASDAQ", "USD", "Switch Co")
    db.commit()
    bar_start = datetime.now(timezone.utc) - timedelta(days=1)

    upsert_bars(db, instrument, [_bar_at(bar_start, Decimal("100"))], source="demo")
    db.commit()
    upsert_bars(db, instrument, [_bar_at(bar_start, Decimal("200"))], source="stooq")
    db.commit()

    from app.domain.market import Bar

    bar = db.query(Bar).filter(Bar.instrument_id == instrument.id, Bar.bar_start == bar_start).one()
    # 나중에 재수집한 stooq 값이 이긴다 — demo 값이 보존되지 않는다(현재 정책).
    assert bar.source == "stooq"
    assert bar.close == Decimal("200")


def test_reingesting_same_timestamp_order_determines_winner_not_provider_identity(db):
    """"stooq가 항상 이긴다" 같은 고정 우선순위가 있는 게 아니라, 정말로
    "마지막 호출"이 이긴다는 것을 반대 순서로도 확인한다 — 순서를 뒤집으면
    승자도 뒤집혀야 한다."""
    instrument = upsert_instrument(db, "TESTSWITCH2", "NASDAQ", "USD", "Switch Co 2")
    db.commit()
    bar_start = datetime.now(timezone.utc) - timedelta(days=1)

    upsert_bars(db, instrument, [_bar_at(bar_start, Decimal("300"))], source="stooq")
    db.commit()
    upsert_bars(db, instrument, [_bar_at(bar_start, Decimal("400"))], source="demo")
    db.commit()

    from app.domain.market import Bar

    bar = db.query(Bar).filter(Bar.instrument_id == instrument.id, Bar.bar_start == bar_start).one()
    assert bar.source == "demo"
    assert bar.close == Decimal("400")


def test_get_price_point_reflects_source_after_provider_switch(db):
    instrument = upsert_instrument(db, "TESTSWITCH3", "NASDAQ", "USD", "Switch Co 3")
    db.commit()
    bar_start = datetime.now(timezone.utc) - timedelta(days=1)

    upsert_bars(db, instrument, [_bar_at(bar_start, Decimal("100"))], source="demo")
    db.commit()
    point_before = get_price_point(db, instrument.id, staleness_threshold_seconds=900)
    assert point_before.source == "demo"

    upsert_bars(db, instrument, [_bar_at(bar_start, Decimal("150"))], source="stooq")
    db.commit()
    point_after = get_price_point(db, instrument.id, staleness_threshold_seconds=900)
    # 포트폴리오 평가 응답(PositionResponse.price_source로 그대로 노출됨)도
    # 공급자 전환 직후 새 source를 반영해야 한다 — 예전 공급자의 source가
    # 남아있으면 안 된다.
    assert point_after.source == "stooq"
    assert point_after.price == Decimal("150")


def test_stooq_fetch_failure_does_not_fall_back_to_demo(monkeypatch):
    """Stooq 조회가 실패하면(네트워크 오류 등) ProviderFetchError가 그대로
    올라와야 한다 — 어디에서도 이를 잡아 데모 데이터로 조용히 대체하지 않는다.
    get_provider("stooq")가 실제로 StooqMarketDataProvider를 돌려주는지도
    함께 확인해 "이름은 stooq인데 내부적으로 demo를 감춰서 쓰는" 일이 없음을
    보장한다."""
    import httpx

    def _raise(*args, **kwargs):
        raise httpx.ConnectError("network blocked")

    monkeypatch.setattr(httpx, "get", _raise)

    provider = get_provider("stooq")
    assert isinstance(provider, StooqMarketDataProvider)
    assert not isinstance(provider, DemoMarketDataProvider)

    with pytest.raises(ProviderFetchError):
        provider.fetch_daily_bars("AAPL", "NASDAQ")
