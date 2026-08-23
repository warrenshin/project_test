"""행동편향 탐지(7.4) 나머지 4종: 추격매수·손실회피·물타기 집착·과잉매매.

확증편향·처분효과·집중위험 3종은 이미 tests/test_journal_and_ai.py에서
검증된다. 이 파일은 새로 추가한 4종만 다룬다 — 실제 체결 엔진(슬리피지·
수수료 등)에 의존하지 않도록 Order/Fill/Bar/JournalEntry를 직접 구성해
탐지 함수(coaching.detect_biases)를 순수 함수로서 검증한다. 전부 "진단"이
아니라 "관찰된 거래 패턴"으로만 표현되는지도 함께 확인한다.
"""

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.core.config import get_settings
from app.domain.journal import JournalEntry, JournalVersion
from app.domain.market import Bar
from app.domain.portfolio import Fill, Order
from app.domain.services import coaching
from tests.conftest import client, seed_instrument_with_bar, signup_user

settings = get_settings()


def _make_filled_buy_order(db, portfolio_id, instrument_id, fill_price, filled_at) -> Order:
    order = Order(
        portfolio_id=portfolio_id,
        instrument_id=instrument_id,
        side="BUY",
        order_type="MARKET",
        quantity=Decimal("1"),
        status="FILLED",
        submitted_at=filled_at,
        policy_version="test-v1",
        idempotency_key=str(uuid.uuid4()),
    )
    db.add(order)
    db.flush()
    db.add(
        Fill(
            order_id=order.id,
            quantity=Decimal("1"),
            fill_price=Decimal(str(fill_price)),
            market_data_as_of=filled_at,
            filled_at=filled_at,
        )
    )
    db.commit()
    return order


def _add_daily_bar(db, instrument_id, close, bar_start):
    db.add(
        Bar(
            instrument_id=instrument_id,
            interval="1d",
            open=close,
            high=close,
            low=close,
            close=close,
            volume=100_000,
            bar_start=bar_start,
            source="test-seed",
            as_of=bar_start,
            delay_seconds=0,
        )
    )
    db.commit()


def _assert_observed_not_diagnosed(observations: list[dict]) -> None:
    for o in observations:
        assert "진단" not in o["description"] or "진단이 아니" in o["description"]


# --- 추격매수 ---


def test_chasing_rally_detected_for_repeated_unplanned_buys_into_rally(db):
    cookies, portfolio_id = signup_user("bias-chase")
    # seed_instrument_with_bar 자체가 "지금" 시각에 bar 하나를 만들어버리므로
    # (급등 판단용 최신 bar로 잘못 집힐 수 있다), 그보다 뒤 시각에 급등 bar를
    # 둬서 확실히 가장 최근 bar가 되게 한다.
    instrument = seed_instrument_with_bar(db, "CHASE1", "NASDAQ", "USD", close=100)
    # seed 호출 이후 시각(baseline)은 seed가 만든 bar의 bar_start보다 항상
    # 뒤이므로, 미래 시각으로 밀어내지 않고도 "가장 최근 bar"로 만들 수
    # 있다(미래 as_of는 이제 신뢰 불가로 걸러지므로 절대 미래로 두면 안 된다).
    baseline = datetime.now(timezone.utc)
    rally_at = baseline

    # 5거래일 전 낮은 가격 -> 급등한 가격의 일봉을 만든다.
    _add_daily_bar(db, instrument.id, close=100, bar_start=baseline - timedelta(days=6))
    _add_daily_bar(db, instrument.id, close=120, bar_start=rally_at)

    # 진입 조건 없이(일지 자체가 없이) 두 번 매수한다.
    _make_filled_buy_order(db, portfolio_id, instrument.id, fill_price=120, filled_at=rally_at + timedelta(seconds=1))
    _make_filled_buy_order(
        db, portfolio_id, instrument.id, fill_price=121, filled_at=rally_at + timedelta(seconds=2)
    )

    from app.domain.portfolio import Portfolio

    portfolio = db.query(Portfolio).filter(Portfolio.id == portfolio_id).first()
    observations = coaching.detect_biases(db, portfolio.user_id)
    patterns = [o["pattern"] for o in observations if o["detected"]]
    assert "추격매수 의심 패턴" in patterns
    _assert_observed_not_diagnosed(observations)


def test_chasing_rally_not_flagged_when_entry_condition_recorded(db):
    cookies, portfolio_id = signup_user("bias-chase-planned")
    instrument = seed_instrument_with_bar(db, "CHASE2", "NASDAQ", "USD", close=100)
    baseline = datetime.now(timezone.utc)
    rally_at = baseline
    _add_daily_bar(db, instrument.id, close=100, bar_start=baseline - timedelta(days=6))
    _add_daily_bar(db, instrument.id, close=120, bar_start=rally_at)

    from app.domain.portfolio import Portfolio

    portfolio = db.query(Portfolio).filter(Portfolio.id == portfolio_id).first()

    for i in range(2):
        order = _make_filled_buy_order(
            db, portfolio_id, instrument.id, fill_price=120 + i, filled_at=rally_at + timedelta(seconds=i + 1)
        )
        db.add(
            JournalEntry(
                user_id=portfolio.user_id,
                portfolio_id=portfolio_id,
                instrument_id=instrument.id,
                order_id=order.id,
                thesis=f"진입 논리 {i}",
                entry_condition="20일선 지지 확인 후 진입",
                counter_evidence=["과열 우려"],
            )
        )
    db.commit()

    observations = coaching.detect_biases(db, portfolio.user_id)
    patterns = [o["pattern"] for o in observations if o["detected"]]
    assert "추격매수 의심 패턴" not in patterns


# --- 손실회피(손절 조건 반복 변경) ---


def test_loss_aversion_detected_when_stop_loss_repeatedly_revised(db):
    cookies, portfolio_id = signup_user("bias-lossaversion")
    instrument = seed_instrument_with_bar(db, "LOSSAV1", "NASDAQ", "USD", close=100)
    now = datetime.now(timezone.utc)

    from app.domain.portfolio import Portfolio

    portfolio = db.query(Portfolio).filter(Portfolio.id == portfolio_id).first()
    order = _make_filled_buy_order(db, portfolio_id, instrument.id, fill_price=100, filled_at=now)

    journal_res = client.post(
        "/v1/journals/pre-trade",
        json={
            "portfolio_id": portfolio_id, "instrument_id": str(instrument.id), "thesis": "논리",
            "counter_evidence": ["위험"], "stop_loss_condition": "-5%",
        },
        cookies=cookies,
    )
    journal_id = journal_res.json()["id"]
    db.query(JournalEntry).filter(JournalEntry.id == journal_id).update({"order_id": order.id})
    db.commit()

    # 손절 조건을 두 번 더 변경한다(체결과 연결된 상태에서 반복 변경).
    client.patch(f"/v1/journals/{journal_id}", json={"stop_loss_condition": "-10%"}, cookies=cookies)
    client.patch(f"/v1/journals/{journal_id}", json={"stop_loss_condition": "-20%"}, cookies=cookies)

    observations = coaching.detect_biases(db, portfolio.user_id)
    patterns = [o["pattern"] for o in observations if o["detected"]]
    assert "손실회피 의심 패턴" in patterns
    _assert_observed_not_diagnosed(observations)


def test_loss_aversion_not_flagged_for_single_unrevised_stop_loss(db):
    cookies, portfolio_id = signup_user("bias-lossaversion-ok")
    instrument = seed_instrument_with_bar(db, "LOSSAV2", "NASDAQ", "USD", close=100)
    now = datetime.now(timezone.utc)

    from app.domain.portfolio import Portfolio

    portfolio = db.query(Portfolio).filter(Portfolio.id == portfolio_id).first()
    order = _make_filled_buy_order(db, portfolio_id, instrument.id, fill_price=100, filled_at=now)

    journal_res = client.post(
        "/v1/journals/pre-trade",
        json={
            "portfolio_id": portfolio_id, "instrument_id": str(instrument.id), "thesis": "논리",
            "counter_evidence": ["위험"], "stop_loss_condition": "-5%",
        },
        cookies=cookies,
    )
    journal_id = journal_res.json()["id"]
    db.query(JournalEntry).filter(JournalEntry.id == journal_id).update({"order_id": order.id})
    db.commit()

    observations = coaching.detect_biases(db, portfolio.user_id)
    patterns = [o["pattern"] for o in observations if o["detected"]]
    assert "손실회피 의심 패턴" not in patterns


# --- 물타기 집착 ---


def test_averaging_down_detected_without_new_thesis(db):
    cookies, portfolio_id = signup_user("bias-avgdown")
    instrument = seed_instrument_with_bar(db, "AVGDN1", "NASDAQ", "USD", close=100)
    now = datetime.now(timezone.utc)

    from app.domain.portfolio import Portfolio

    portfolio = db.query(Portfolio).filter(Portfolio.id == portfolio_id).first()

    # 두 개의 서로 다른 종목에서 "더 싸진 가격에 추가매수 + 새 논리 없음" 패턴을 반복한다.
    for idx, ticker in enumerate(["AVGDN1", "AVGDN2"]):
        inst = instrument if ticker == "AVGDN1" else seed_instrument_with_bar(db, ticker, "NASDAQ", "USD", close=100)
        t0 = now + timedelta(hours=idx)
        _make_filled_buy_order(db, portfolio_id, inst.id, fill_price=100, filled_at=t0)
        _make_filled_buy_order(db, portfolio_id, inst.id, fill_price=90, filled_at=t0 + timedelta(minutes=10))

    observations = coaching.detect_biases(db, portfolio.user_id)
    patterns = [o["pattern"] for o in observations if o["detected"]]
    assert "물타기 집착 의심 패턴" in patterns
    _assert_observed_not_diagnosed(observations)


def test_averaging_down_not_flagged_when_new_thesis_recorded_between_buys(db):
    cookies, portfolio_id = signup_user("bias-avgdown-ok")
    instrument = seed_instrument_with_bar(db, "AVGDNOK", "NASDAQ", "USD", close=100)
    now = datetime.now(timezone.utc)

    from app.domain.portfolio import Portfolio

    portfolio = db.query(Portfolio).filter(Portfolio.id == portfolio_id).first()

    _make_filled_buy_order(db, portfolio_id, instrument.id, fill_price=100, filled_at=now)
    # 두 매수 사이에 새 투자 논리를 기록한다.
    client.post(
        "/v1/journals/pre-trade",
        json={
            "portfolio_id": portfolio_id, "instrument_id": str(instrument.id), "thesis": "저가 매수 재검증",
            "counter_evidence": ["추가 하락 위험"],
        },
        cookies=cookies,
    )
    _make_filled_buy_order(db, portfolio_id, instrument.id, fill_price=90, filled_at=now + timedelta(minutes=10))

    observations = coaching.detect_biases(db, portfolio.user_id)
    patterns = [o["pattern"] for o in observations if o["detected"]]
    assert "물타기 집착 의심 패턴" not in patterns


# --- 과잉매매 ---


def test_overtrading_detected_within_short_window(db):
    cookies, portfolio_id = signup_user("bias-overtrade")
    instrument = seed_instrument_with_bar(db, "OVERTR1", "NASDAQ", "USD", close=100)
    now = datetime.now(timezone.utc)

    from app.domain.portfolio import Portfolio

    portfolio = db.query(Portfolio).filter(Portfolio.id == portfolio_id).first()
    for i in range(settings.overtrading_order_threshold):
        _make_filled_buy_order(db, portfolio_id, instrument.id, fill_price=100, filled_at=now + timedelta(minutes=i))

    observations = coaching.detect_biases(db, portfolio.user_id)
    patterns = [o["pattern"] for o in observations if o["detected"]]
    assert "과잉매매 의심 패턴" in patterns
    _assert_observed_not_diagnosed(observations)


def test_overtrading_not_flagged_when_orders_spread_out(db):
    cookies, portfolio_id = signup_user("bias-overtrade-ok")
    instrument = seed_instrument_with_bar(db, "OVERTR2", "NASDAQ", "USD", close=100)
    now = datetime.now(timezone.utc)

    from app.domain.portfolio import Portfolio

    portfolio = db.query(Portfolio).filter(Portfolio.id == portfolio_id).first()
    for i in range(settings.overtrading_order_threshold):
        _make_filled_buy_order(
            db, portfolio_id, instrument.id, fill_price=100,
            filled_at=now + timedelta(hours=(settings.overtrading_window_hours + 1) * i),
        )

    observations = coaching.detect_biases(db, portfolio.user_id)
    patterns = [o["pattern"] for o in observations if o["detected"]]
    assert "과잉매매 의심 패턴" not in patterns


# --- API 통합 ---


def test_bias_report_endpoint_includes_new_pattern_types(db):
    cookies, portfolio_id = signup_user("bias-endpoint")
    instrument = seed_instrument_with_bar(db, "ENDPT1", "NASDAQ", "USD", close=100)
    now = datetime.now(timezone.utc)

    from app.domain.portfolio import Portfolio

    portfolio = db.query(Portfolio).filter(Portfolio.id == portfolio_id).first()
    for i in range(settings.overtrading_order_threshold):
        _make_filled_buy_order(db, portfolio_id, instrument.id, fill_price=100, filled_at=now + timedelta(minutes=i))

    res = client.get("/v1/me/bias-report", cookies=cookies)
    assert res.status_code == 200
    body = res.json()
    patterns = [o["pattern"] for o in body["observations"]]
    assert "과잉매매 의심 패턴" in patterns
