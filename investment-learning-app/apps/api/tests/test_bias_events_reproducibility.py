"""행동편향 7종 공통 요구사항: 규칙 버전·임계값 스냅샷 재현성, 중복 방지,
여러 편향 동시 발생 시 결정론적 정렬, evidence에 원문 미포함, acknowledge
API의 소유권 검증. 개별 편향의 positive/negative/boundary 케이스는
tests/test_behavioral_bias_seven_types.py, tests/test_journal_and_ai.py를
참고 — 이 파일은 "7종 공통"으로 요구된 부분만 다룬다.
"""

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.core.config import get_settings
from app.domain.bias import BiasEvent
from app.domain.journal import JournalEntry
from app.domain.portfolio import Fill, Order, Portfolio
from app.domain.services import coaching
from tests.conftest import client, seed_instrument_with_bar, signup_user

settings = get_settings()


def _make_filled_buy_order(db, portfolio_id, instrument_id, fill_price, filled_at) -> Order:
    order = Order(
        portfolio_id=portfolio_id, instrument_id=instrument_id, side="BUY", order_type="MARKET",
        quantity=Decimal("1"), status="FILLED", submitted_at=filled_at,
        policy_version="test-v1", idempotency_key=str(uuid.uuid4()),
    )
    db.add(order)
    db.flush()
    db.add(
        Fill(
            order_id=order.id, quantity=Decimal("1"), fill_price=Decimal(str(fill_price)),
            market_data_as_of=filled_at, filled_at=filled_at,
        )
    )
    db.commit()
    return order


def test_bias_report_requires_auth():
    res = client.get("/v1/me/bias-report")
    assert res.status_code == 401


def test_fresh_user_all_seven_biases_returned_as_insufficient(db):
    """편향 이력이 전혀 없는 신규 사용자도 7종 전체가 응답에 나와야 하고,
    전부 감지되지 않은(또는 데이터 부족) 상태여야 한다 — 조용히 목록이
    비어버리면 안 된다."""
    cookies, _ = signup_user("bias-fresh")
    res = client.get("/v1/me/bias-report", cookies=cookies)
    assert res.status_code == 200
    body = res.json()
    assert len(body["biases"]) == 7
    codes = {b["bias_code"] for b in body["biases"]}
    assert codes == {
        "CONFIRMATION_BIAS", "DISPOSITION_EFFECT", "CONCENTRATION_RISK",
        "CHASING_RALLY", "LOSS_AVERSION", "AVERAGING_DOWN", "OVERTRADING",
    }
    assert all(not b["detected"] for b in body["biases"])
    assert all(b["data_sufficiency"] in ("SUFFICIENT", "INSUFFICIENT", "MARKET_DATA_UNAVAILABLE") for b in body["biases"])
    assert body["observations"] == []


def test_bias_event_persists_rule_version_and_threshold_snapshot(db):
    cookies, portfolio_id = signup_user("bias-repro")
    instrument = seed_instrument_with_bar(db, "REPRO1", "NASDAQ", "USD", close=100)
    now = datetime.now(timezone.utc)
    for i in range(settings.overtrading_order_threshold):
        _make_filled_buy_order(db, portfolio_id, instrument.id, fill_price=100, filled_at=now + timedelta(minutes=i))

    portfolio = db.query(Portfolio).filter(Portfolio.id == portfolio_id).first()
    coaching.detect_biases(db, portfolio.user_id)
    db.commit()

    event = db.query(BiasEvent).filter(
        BiasEvent.user_id == portfolio.user_id, BiasEvent.bias_code == "OVERTRADING"
    ).first()
    assert event is not None
    assert event.rule_version == coaching.BIAS_RULE_VERSIONS["OVERTRADING"]
    assert event.threshold_snapshot == {
        "window_hours": settings.overtrading_window_hours,
        "order_threshold": settings.overtrading_order_threshold,
    }
    assert event.detected_at is not None
    assert event.evidence_fingerprint  # 비어있지 않음


def test_rerunning_analysis_with_same_evidence_does_not_duplicate(db):
    """동일 근거로 여러 번 분석해도(예: bias-report를 여러 번 조회) BiasEvent
    행이 중복 생성되지 않는다 — 재분석의 멱등성."""
    cookies, portfolio_id = signup_user("bias-idempotent")
    instrument = seed_instrument_with_bar(db, "REPRO2", "NASDAQ", "USD", close=100)
    now = datetime.now(timezone.utc)
    for i in range(settings.overtrading_order_threshold):
        _make_filled_buy_order(db, portfolio_id, instrument.id, fill_price=100, filled_at=now + timedelta(minutes=i))

    portfolio = db.query(Portfolio).filter(Portfolio.id == portfolio_id).first()
    for _ in range(3):
        client.get("/v1/me/bias-report", cookies=cookies)

    count = db.query(BiasEvent).filter(
        BiasEvent.user_id == portfolio.user_id, BiasEvent.bias_code == "OVERTRADING"
    ).count()
    assert count == 1


def test_rule_version_bump_creates_new_event_without_touching_old_one(db, monkeypatch):
    """규칙 버전을 올리면 같은 근거라도 새 행이 생기고, 이전 버전으로 이미
    저장된 행은 그대로 남아 있어야 한다(과거 분석 결과 보존)."""
    cookies, portfolio_id = signup_user("bias-ruleversion")
    instrument = seed_instrument_with_bar(db, "REPRO3", "NASDAQ", "USD", close=100)
    now = datetime.now(timezone.utc)
    for i in range(settings.overtrading_order_threshold):
        _make_filled_buy_order(db, portfolio_id, instrument.id, fill_price=100, filled_at=now + timedelta(minutes=i))

    portfolio = db.query(Portfolio).filter(Portfolio.id == portfolio_id).first()
    coaching.detect_biases(db, portfolio.user_id)
    db.commit()
    v1_event = db.query(BiasEvent).filter(
        BiasEvent.user_id == portfolio.user_id, BiasEvent.bias_code == "OVERTRADING"
    ).first()
    assert v1_event.rule_version == "v1"

    monkeypatch.setitem(coaching.BIAS_RULE_VERSIONS, "OVERTRADING", "v2")
    coaching.detect_biases(db, portfolio.user_id)
    db.commit()

    events = db.query(BiasEvent).filter(
        BiasEvent.user_id == portfolio.user_id, BiasEvent.bias_code == "OVERTRADING"
    ).order_by(BiasEvent.rule_version).all()
    assert [e.rule_version for e in events] == ["v1", "v2"]
    # v1 행은 그대로 보존된다(내용이 바뀌지 않음).
    assert events[0].id == v1_event.id
    assert events[0].detected_at == v1_event.detected_at


def test_multiple_biases_detected_are_sorted_deterministically_with_top_three(db):
    """여러 편향이 동시에 감지될 때 응답 순서가 결정론적이어야 하고(같은
    입력이면 항상 같은 순서), 상위 3개가 top_signals로 표시돼야 한다."""
    cookies, portfolio_id = signup_user("bias-multi")
    portfolio = db.query(Portfolio).filter(Portfolio.id == portfolio_id).first()

    # 확증편향: 반대 근거 없는 일지 3건 이상.
    for i in range(4):
        client.post(
            "/v1/journals/pre-trade",
            json={
                "portfolio_id": portfolio_id,
                "instrument_id": str(seed_instrument_with_bar(db, f"MULTI{i}", "NASDAQ", "USD", close=100).id),
                "thesis": f"논리 {i}", "counter_evidence": [],
            },
            cookies=cookies,
        )

    # 과잉매매: 짧은 시간 안에 다수 체결.
    instrument = seed_instrument_with_bar(db, "MULTIOT", "NASDAQ", "USD", close=100)
    now = datetime.now(timezone.utc)
    for i in range(settings.overtrading_order_threshold):
        _make_filled_buy_order(db, portfolio_id, instrument.id, fill_price=100, filled_at=now + timedelta(minutes=i))

    res1 = client.get("/v1/me/bias-report", cookies=cookies)
    res2 = client.get("/v1/me/bias-report", cookies=cookies)
    assert res1.status_code == 200 and res2.status_code == 200
    body1, body2 = res1.json(), res2.json()

    detected_codes_1 = [b["bias_code"] for b in body1["biases"] if b["detected"]]
    detected_codes_2 = [b["bias_code"] for b in body2["biases"] if b["detected"]]
    assert set(detected_codes_1) >= {"CONFIRMATION_BIAS", "OVERTRADING"}
    assert detected_codes_1 == detected_codes_2  # 재조회해도 순서가 같다(결정론적)
    assert [b["bias_code"] for b in body1["biases"]] == [b["bias_code"] for b in body2["biases"]]
    assert len(body1["top_signals"]) <= 3
    assert body1["top_signals"] == detected_codes_1[:3]
    # 감지된 항목이 감지 안 된 항목보다 항상 앞에 온다.
    detected_flags = [b["detected"] for b in body1["biases"]]
    assert detected_flags == sorted(detected_flags, reverse=True)


def test_evidence_never_contains_raw_journal_text(db):
    """evidence_summary·description 등 어디에도 사용자가 쓴 일지 원문이 그대로
    노출되면 안 된다 — 전부 계산된 수치·상태 문구만 담아야 한다."""
    cookies, portfolio_id = signup_user("bias-noleak")
    marker = "이것은-절대-노출되면-안되는-일지-원문-마커-XYZ123"
    for i in range(4):
        client.post(
            "/v1/journals/pre-trade",
            json={
                "portfolio_id": portfolio_id,
                "instrument_id": str(seed_instrument_with_bar(db, f"NOLEAK{i}", "NASDAQ", "USD", close=100).id),
                "thesis": marker, "counter_evidence": [],
            },
            cookies=cookies,
        )
    res = client.get("/v1/me/bias-report", cookies=cookies)
    raw_body = res.text
    assert marker not in raw_body


def test_acknowledge_bias_event_success_and_is_education_confirmation(db):
    cookies, portfolio_id = signup_user("bias-ack")
    instrument = seed_instrument_with_bar(db, "ACK1", "NASDAQ", "USD", close=100)
    now = datetime.now(timezone.utc)
    for i in range(settings.overtrading_order_threshold):
        _make_filled_buy_order(db, portfolio_id, instrument.id, fill_price=100, filled_at=now + timedelta(minutes=i))

    report = client.get("/v1/me/bias-report", cookies=cookies).json()
    overtrading = next(b for b in report["biases"] if b["bias_code"] == "OVERTRADING")
    assert overtrading["detected"] is True
    assert overtrading["id"] is not None
    assert overtrading["acknowledged_at"] is None

    ack_res = client.post(f"/v1/me/bias-events/{overtrading['id']}/acknowledge", cookies=cookies)
    assert ack_res.status_code == 200, ack_res.text
    assert ack_res.json()["bias_code"] == "OVERTRADING"
    assert ack_res.json()["acknowledged_at"] is not None

    report_after = client.get("/v1/me/bias-report", cookies=cookies).json()
    overtrading_after = next(b for b in report_after["biases"] if b["bias_code"] == "OVERTRADING")
    assert overtrading_after["acknowledged_at"] is not None

    # 다시 확인해도(재요청) 에러 없이 같은 시각을 유지한다(멱등).
    ack_again = client.post(f"/v1/me/bias-events/{overtrading['id']}/acknowledge", cookies=cookies)
    assert ack_again.status_code == 200
    assert ack_again.json()["acknowledged_at"] == ack_res.json()["acknowledged_at"]


def test_acknowledge_bias_event_blocks_other_users_event(db):
    cookies_a, portfolio_id_a = signup_user("bias-ack-owner")
    cookies_b, _ = signup_user("bias-ack-intruder")
    instrument = seed_instrument_with_bar(db, "ACK2", "NASDAQ", "USD", close=100)
    now = datetime.now(timezone.utc)
    for i in range(settings.overtrading_order_threshold):
        _make_filled_buy_order(db, portfolio_id_a, instrument.id, fill_price=100, filled_at=now + timedelta(minutes=i))

    report = client.get("/v1/me/bias-report", cookies=cookies_a).json()
    overtrading = next(b for b in report["biases"] if b["bias_code"] == "OVERTRADING")

    res = client.post(f"/v1/me/bias-events/{overtrading['id']}/acknowledge", cookies=cookies_b)
    assert res.status_code == 404


def test_acknowledge_nonexistent_bias_event_returns_404():
    cookies, _ = signup_user("bias-ack-missing")
    res = client.post(f"/v1/me/bias-events/{uuid.uuid4()}/acknowledge", cookies=cookies)
    assert res.status_code == 404


def test_acknowledge_requires_auth():
    res = client.post(f"/v1/me/bias-events/{uuid.uuid4()}/acknowledge")
    assert res.status_code == 401
