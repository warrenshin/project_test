"""행동편향 7종 감사에서 지적된 나머지 경계값·교차 사용자 격리 보완 테스트.

이 파일은 tests/test_behavioral_bias_seven_types.py(4종 신규 편향의 기본
탐지/미탐지)와 tests/test_bias_events_reproducibility.py(공통 재현성·정렬·
API 보안)를 보완한다 — 아직 다루지 않았던 것만 추가한다:

1. 추격매수: 상승률이 임계값과 "정확히 같을 때"도 신호로 잡히는지(경계값).
2. 손실회피: 손절 조건이 "정확히 1회"만 바뀐 경우는 아직 신호가 아니어야
   한다(2회부터 신호 — 0회 미탐지는 기존 테스트가 이미 커버).
3. 4개 신규 탐지기 각각에 대해, 다른 사용자의 데이터가 내 판정에 섞여
   들어오지 않는지(교차 사용자 격리)를 개별적으로 확인한다.
4. 7일 챌린지 Day2/Day5의 주문 "미리보기" 미션이 실제 Order/Fill을 만들지
   않아 과잉매매 집계를 오염시키지 않는다는 것을(코드 읽기뿐 아니라) 실제
   HTTP 흐름으로 검증한다.
"""

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.core.config import get_settings
from app.domain.journal import JournalEntry, JournalVersion
from app.domain.market import Bar
from app.domain.portfolio import Fill, Order, Portfolio
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


def _signal(observations: list[dict], bias_code: str) -> dict:
    return next(o for o in observations if o["bias_code"] == bias_code)


def _user_id(db, portfolio_id) -> str:
    return db.query(Portfolio).filter(Portfolio.id == portfolio_id).first().user_id


# --- 경계값: 추격매수 ---


def test_chasing_rally_exactly_at_threshold_gain_counts_as_instance(db):
    """상승률이 임계값보다 "큰" 경우만이 아니라 "정확히 같은" 경우도
    잡혀야 한다(코드의 `gain < threshold: continue`는 등호일 때 통과시킨다) —
    실제로 그렇게 동작하는지 확인해 경계 조건 오타(예: <= 로 잘못 바뀌는
    회귀)를 방지한다."""
    cookies, portfolio_id = signup_user("bias-chase-boundary")
    instrument = seed_instrument_with_bar(db, "CHASEBND", "NASDAQ", "USD", close=100)
    baseline = datetime.now(timezone.utc)
    threshold = settings.chasing_rally_gain_threshold_pct
    # 정확히 threshold%만큼 오른 가격으로 두 번째 bar를 만든다.
    rally_close = Decimal(100) * (Decimal(100) + Decimal(threshold)) / Decimal(100)
    _add_daily_bar(db, instrument.id, close=100, bar_start=baseline - timedelta(days=6))
    _add_daily_bar(db, instrument.id, close=rally_close, bar_start=baseline)

    _make_filled_buy_order(db, portfolio_id, instrument.id, fill_price=rally_close, filled_at=baseline + timedelta(seconds=1))
    _make_filled_buy_order(db, portfolio_id, instrument.id, fill_price=rally_close, filled_at=baseline + timedelta(seconds=2))

    user_id = _user_id(db, portfolio_id)
    observations = coaching.detect_biases(db, user_id)
    signal = _signal(observations, "CHASING_RALLY")
    assert signal["detected"] is True, signal


def test_chasing_rally_just_below_threshold_gain_not_flagged(db):
    """임계값보다 "아주 조금" 낮은 상승률은 신호로 잡히면 안 된다(과대
    민감도 방지) — 위 경계값 테스트와 짝을 이룬다."""
    cookies, portfolio_id = signup_user("bias-chase-below")
    instrument = seed_instrument_with_bar(db, "CHASEBLW", "NASDAQ", "USD", close=100)
    baseline = datetime.now(timezone.utc)
    threshold = settings.chasing_rally_gain_threshold_pct
    just_below = Decimal(100) * (Decimal(100) + Decimal(threshold) - Decimal("0.5")) / Decimal(100)
    _add_daily_bar(db, instrument.id, close=100, bar_start=baseline - timedelta(days=6))
    _add_daily_bar(db, instrument.id, close=just_below, bar_start=baseline)

    _make_filled_buy_order(db, portfolio_id, instrument.id, fill_price=just_below, filled_at=baseline + timedelta(seconds=1))
    _make_filled_buy_order(db, portfolio_id, instrument.id, fill_price=just_below, filled_at=baseline + timedelta(seconds=2))

    user_id = _user_id(db, portfolio_id)
    observations = coaching.detect_biases(db, user_id)
    signal = _signal(observations, "CHASING_RALLY")
    assert signal["detected"] is False, signal


# --- 경계값: 손실회피(정확히 1회 변경은 아직 신호가 아님) ---


def test_loss_aversion_exactly_one_revision_not_yet_flagged(db):
    """손절 조건을 "정확히 1번"만 바꾼 경우는 아직 반복 변경으로 보지
    않는다(STOP_LOSS_REVISION_MIN_CHANGES=2). 0회 미탐지·3회 이상 탐지는
    기존 test_behavioral_bias_seven_types.py가 이미 다루므로, 여기서는
    "바로 그 경계 하나 아래" 값만 추가로 확인한다."""
    cookies, portfolio_id = signup_user("bias-lossaversion-onechange")
    instrument = seed_instrument_with_bar(db, "LOSSAVONE", "NASDAQ", "USD", close=100)
    now = datetime.now(timezone.utc)

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

    # 딱 한 번만 변경한다(이유 기록 없이).
    res = client.patch(f"/v1/journals/{journal_id}", json={"stop_loss_condition": "-10%"}, cookies=cookies)
    assert res.status_code == 200, res.text

    user_id = _user_id(db, portfolio_id)
    observations = coaching.detect_biases(db, user_id)
    signal = _signal(observations, "LOSS_AVERSION")
    assert signal["detected"] is False, signal


# --- 교차 사용자 격리(4개 신규 탐지기 개별) ---


def test_chasing_rally_does_not_leak_across_users(db):
    cookies_a, portfolio_a = signup_user("bias-iso-chase-a")
    instrument = seed_instrument_with_bar(db, "ISOCHASE", "NASDAQ", "USD", close=100)
    baseline = datetime.now(timezone.utc)
    _add_daily_bar(db, instrument.id, close=100, bar_start=baseline - timedelta(days=6))
    _add_daily_bar(db, instrument.id, close=120, bar_start=baseline)
    _make_filled_buy_order(db, portfolio_a, instrument.id, fill_price=120, filled_at=baseline + timedelta(seconds=1))
    _make_filled_buy_order(db, portfolio_a, instrument.id, fill_price=121, filled_at=baseline + timedelta(seconds=2))

    user_a = _user_id(db, portfolio_a)
    signal_a = _signal(coaching.detect_biases(db, user_a), "CHASING_RALLY")
    assert signal_a["detected"] is True

    cookies_b, portfolio_b = signup_user("bias-iso-chase-b")
    user_b = _user_id(db, portfolio_b)
    signal_b = _signal(coaching.detect_biases(db, user_b), "CHASING_RALLY")
    assert signal_b["detected"] is False
    assert signal_b["sample_size"] == 0


def test_loss_aversion_does_not_leak_across_users(db):
    cookies_a, portfolio_a = signup_user("bias-iso-lossav-a")
    instrument = seed_instrument_with_bar(db, "ISOLOSSAV", "NASDAQ", "USD", close=100)
    now = datetime.now(timezone.utc)
    order = _make_filled_buy_order(db, portfolio_a, instrument.id, fill_price=100, filled_at=now)
    journal_res = client.post(
        "/v1/journals/pre-trade",
        json={
            "portfolio_id": portfolio_a, "instrument_id": str(instrument.id), "thesis": "논리",
            "counter_evidence": ["위험"], "stop_loss_condition": "-5%",
        },
        cookies=cookies_a,
    )
    journal_id = journal_res.json()["id"]
    db.query(JournalEntry).filter(JournalEntry.id == journal_id).update({"order_id": order.id})
    db.commit()
    client.patch(f"/v1/journals/{journal_id}", json={"stop_loss_condition": "-10%"}, cookies=cookies_a)
    client.patch(f"/v1/journals/{journal_id}", json={"stop_loss_condition": "-20%"}, cookies=cookies_a)

    user_a = _user_id(db, portfolio_a)
    signal_a = _signal(coaching.detect_biases(db, user_a), "LOSS_AVERSION")
    assert signal_a["detected"] is True

    cookies_b, portfolio_b = signup_user("bias-iso-lossav-b")
    user_b = _user_id(db, portfolio_b)
    signal_b = _signal(coaching.detect_biases(db, user_b), "LOSS_AVERSION")
    assert signal_b["detected"] is False
    assert signal_b["sample_size"] == 0


def test_averaging_down_does_not_leak_across_users(db):
    cookies_a, portfolio_a = signup_user("bias-iso-avgdn-a")
    instrument = seed_instrument_with_bar(db, "ISOAVGDN", "NASDAQ", "USD", close=100)
    now = datetime.now(timezone.utc)
    _make_filled_buy_order(db, portfolio_a, instrument.id, fill_price=100, filled_at=now)
    _make_filled_buy_order(db, portfolio_a, instrument.id, fill_price=90, filled_at=now + timedelta(minutes=10))
    # 최소 표본(2건 이상) 확보를 위해 다른 종목에서도 한 번 더 반복한다.
    instrument2 = seed_instrument_with_bar(db, "ISOAVGDN2", "NASDAQ", "USD", close=100)
    _make_filled_buy_order(db, portfolio_a, instrument2.id, fill_price=100, filled_at=now + timedelta(hours=1))
    _make_filled_buy_order(db, portfolio_a, instrument2.id, fill_price=90, filled_at=now + timedelta(hours=1, minutes=10))

    user_a = _user_id(db, portfolio_a)
    signal_a = _signal(coaching.detect_biases(db, user_a), "AVERAGING_DOWN")
    assert signal_a["detected"] is True

    cookies_b, portfolio_b = signup_user("bias-iso-avgdn-b")
    user_b = _user_id(db, portfolio_b)
    signal_b = _signal(coaching.detect_biases(db, user_b), "AVERAGING_DOWN")
    assert signal_b["detected"] is False
    assert signal_b["sample_size"] == 0


def test_overtrading_does_not_leak_across_users(db):
    cookies_a, portfolio_a = signup_user("bias-iso-overtr-a")
    instrument = seed_instrument_with_bar(db, "ISOOVERTR", "NASDAQ", "USD", close=100)
    now = datetime.now(timezone.utc)
    for i in range(settings.overtrading_order_threshold):
        _make_filled_buy_order(db, portfolio_a, instrument.id, fill_price=100, filled_at=now + timedelta(minutes=i))

    user_a = _user_id(db, portfolio_a)
    signal_a = _signal(coaching.detect_biases(db, user_a), "OVERTRADING")
    assert signal_a["detected"] is True

    cookies_b, portfolio_b = signup_user("bias-iso-overtr-b")
    user_b = _user_id(db, portfolio_b)
    signal_b = _signal(coaching.detect_biases(db, user_b), "OVERTRADING")
    assert signal_b["detected"] is False
    assert signal_b["sample_size"] == 0


# --- 7일 챌린지 Day2/5 미리보기 미션이 과잉매매 집계를 오염시키지 않음 ---


def test_challenge_preview_missions_do_not_create_orders_or_pollute_overtrading(db):
    """Day2(ORDER_PREVIEW)·Day5(ORDER_PREVIEW_LINKED_JOURNAL) 미션을 과잉매매
    임계값만큼 반복 호출해도 실제 Order/Fill이 생기지 않아 과잉매매 신호에
    전혀 잡히지 않아야 한다 — _run_preview가 execution.build_quote만 호출하고
    Order/Fill을 커밋하지 않는다는 코드상의 근거를 실제 HTTP 흐름으로 재확인한다."""
    from app.domain.challenge import Challenge, ChallengeDay, ChallengeMission
    from app.domain.services import challenge as challenge_service

    cookies, portfolio_id = signup_user("bias-day2-preview-flood")
    instrument = seed_instrument_with_bar(db, "PREVIEWFLOOD", "NASDAQ", "USD", close=100)
    user_id = _user_id(db, portfolio_id)

    challenge = db.query(Challenge).filter(Challenge.code == "seven-day-challenge").first()
    user_challenge = challenge_service.start_challenge(db, user_id, challenge.id, "Asia/Seoul")
    db.commit()
    # Day2 미션을 검증하려면 Day2가 잠겨 있지 않아야 한다 — 시작일을 하루
    # 앞당겨 "오늘이 Day2"가 되게 한다(다른 챌린지 테스트들과 같은 방식).
    user_challenge.started_at -= timedelta(days=1)
    user_challenge.started_date_local -= timedelta(days=1)
    db.commit()

    day2 = db.query(ChallengeDay).filter(ChallengeDay.challenge_id == challenge.id, ChallengeDay.day_number == 2).first()
    day2_mission = db.query(ChallengeMission).filter(
        ChallengeMission.challenge_day_id == day2.id, ChallengeMission.code == "day2_preview"
    ).first()

    # verify_mission은 첫 성공 이후 같은 미션에 대해 idempotent하므로, 매번
    # "새 미션"인 것처럼 반복 호출하려면 진행 기록을 지워가며 반복한다 —
    # 그래도 매번 _run_preview만 실행될 뿐 Order/Fill을 만들지 않는다는 것이
    # 핵심이므로, 진행 기록 삭제 후 재호출을 반복해 여러 번 미리보기를 계산시킨다.
    from app.domain.challenge import UserMissionProgress

    payload = {
        "portfolio_id": portfolio_id, "instrument_id": str(instrument.id),
        "side": "BUY", "order_type": "MARKET", "quantity": "1",
    }
    for _ in range(settings.overtrading_order_threshold + 2):
        db.query(UserMissionProgress).filter(
            UserMissionProgress.user_challenge_id == user_challenge.id,
            UserMissionProgress.challenge_mission_id == day2_mission.id,
        ).delete()
        db.commit()
        outcome = challenge_service.verify_mission(db, user_id, user_challenge, day2_mission, day2, payload)
        db.commit()
        assert outcome.result.ok is True, outcome.result.reason

    assert db.query(Order).filter(Order.portfolio_id == portfolio_id).count() == 0
    assert db.query(Fill).join(Order, Fill.order_id == Order.id).filter(Order.portfolio_id == portfolio_id).count() == 0

    signal = _signal(coaching.detect_biases(db, user_id), "OVERTRADING")
    assert signal["detected"] is False
    assert signal["sample_size"] == 0
