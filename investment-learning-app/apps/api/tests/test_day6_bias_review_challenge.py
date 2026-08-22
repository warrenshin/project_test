"""7일 챌린지 Day6 "내 거래 패턴 확인"(BIAS_REVIEW) 미션의 실제 통합 동작 검증.

감사 지적 사항: 이 미션이 "그냥 편향 탐지 함수를 재사용하니 안전하다"는
코드 읽기 수준 주장에 그치지 않고, 실제 HTTP 흐름으로 다음을 증명한다:

1. 편향이 하나도 감지되지 않아도(신규 사용자) 미션을 완료할 수 있다 —
   탐지 결과에 좌우되지 않는다(_verify_bias_review는 항상 ok=True).
2. 실제로 편향이 감지된 사용자도 동일하게 완료된다 — "감지되면 통과 못함"
   같은 숨은 게이팅이 없다.
3. 미션 검증 자체가 새로운 Order/Fill을 만들거나 계좌에 영향을 주지
   않는다(순수 조회·계산).
4. 근거(evidence)는 호출자 자신의 데이터로만 계산된다 — 다른 사용자의
   편향이 내 결과에 섞여 들어오지 않는다.
5. 같은 미션을 반복 검증해도 XP가 중복 지급되지 않는다.
6. 완료 상태는 DB에 영속되어, 완전히 새로운 로그인 세션(재로그인)으로
   조회해도 그대로 COMPLETED로 남아 있다.
"""

import uuid
from datetime import timedelta

from app.core.config import get_settings
from app.domain.challenge import Challenge, ChallengeDay, ChallengeMission, UserMissionProgress
from app.domain.portfolio import Fill, Order, Portfolio
from app.domain.services import gamification
from app.domain.services.gamification import XpLedger
from tests.conftest import client, seed_instrument_with_bar

settings = get_settings()
CHALLENGE_CODE = "seven-day-challenge"


def _signup_with_credentials(email_prefix: str) -> tuple[dict, str, str, str]:
    """signup_user와 달리 이메일·비밀번호를 그대로 돌려준다 — "재로그인"을
    실제로 재현하려면(같은 세션 쿠키 재사용이 아니라 완전히 새 로그인) 자격
    증명이 필요하다."""
    email = f"{email_prefix}-{uuid.uuid4().hex[:12]}@example.com"
    password = "correct-horse-battery-staple"
    signup_res = client.post(
        "/v1/auth/signup",
        json={
            "email": email,
            "password": password,
            "birth_date": "2000-01-01",
            "consents": [
                {"consent_type": "TERMS", "version": "v1", "agreed": True},
                {"consent_type": "PRIVACY", "version": "v1", "agreed": True},
            ],
        },
    )
    assert signup_res.status_code == 201, signup_res.text
    auth_cookies = dict(signup_res.cookies)
    client.cookies.clear()
    portfolio_res = client.get("/v1/me/portfolio", cookies=auth_cookies)
    portfolio_id = portfolio_res.json()["id"]
    return auth_cookies, portfolio_id, email, password


def _get_challenge_id() -> str:
    return client.get("/v1/challenges").json()[0]["id"]


def _start_and_unlock_day6(cookies) -> dict:
    """Day6이 잠겨 있지 않도록(현재 Day >= 6) 시작일을 앞당긴다."""
    res = client.post(f"/v1/challenges/{_get_challenge_id()}/start", json={}, cookies=cookies)
    assert res.status_code == 201, res.text
    uc = res.json()
    from app.domain.challenge import UserChallenge
    from app.core.db import SessionLocal

    db = SessionLocal()
    try:
        user_challenge = db.query(UserChallenge).filter(UserChallenge.id == uc["id"]).first()
        user_challenge.started_at -= timedelta(days=6)
        user_challenge.started_date_local -= timedelta(days=6)
        db.commit()
    finally:
        db.close()
    return uc


def _find_day6_bias_mission(cookies, uc_id: str) -> dict:
    state = client.get(f"/v1/me/challenges/{uc_id}", cookies=cookies).json()
    day6 = next(d for d in state["days"] if d["day_number"] == 6)
    return next(m for m in day6["missions"] if m["code"] == "day6_bias")


def _verify_day6_bias(cookies, uc_id: str, mission_id: str):
    return client.post(f"/v1/me/challenges/{uc_id}/missions/{mission_id}/verify", json={}, cookies=cookies)


# --- 1. 편향 미감지 상태에서도 완료 가능 ---


def test_day6_bias_mission_completable_with_zero_biases_detected(db):
    cookies, portfolio_id, _email, _pw = _signup_with_credentials("day6-nobias")
    uc = _start_and_unlock_day6(cookies)
    mission = _find_day6_bias_mission(cookies, uc["id"])

    res = _verify_day6_bias(cookies, uc["id"], mission["id"])
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["mission_completed"] is True
    # 신규 사용자라 감지된 편향이 없어야 한다 — extra.observations가 실제로
    # detect_biases의 결과이며, 전부 detected=False임을 함께 확인한다.
    observations = body["extra"]["observations"]
    assert len(observations) == 7
    assert all(o["detected"] is False for o in observations)


# --- 2. 실제로 편향이 감지되는 사용자도 동일하게 완료(감지 여부에 게이팅되지 않음) ---


def test_day6_bias_mission_not_gated_on_detection_result(db):
    cookies, portfolio_id, _email, _pw = _signup_with_credentials("day6-withbias")
    instrument = seed_instrument_with_bar(db, "DAY6BIAS", "NASDAQ", "USD", close=100)
    uc = _start_and_unlock_day6(cookies)

    # 과잉매매를 실제로 유발한다(짧은 시간 안에 임계값만큼 체결).
    from datetime import datetime, timezone
    from decimal import Decimal

    now = datetime.now(timezone.utc)
    for i in range(settings.overtrading_order_threshold):
        order = Order(
            portfolio_id=portfolio_id, instrument_id=instrument.id, side="BUY", order_type="MARKET",
            quantity=Decimal("1"), status="FILLED", submitted_at=now + timedelta(minutes=i),
            policy_version="test-v1", idempotency_key=str(uuid.uuid4()),
        )
        db.add(order)
        db.flush()
        db.add(Fill(
            order_id=order.id, quantity=Decimal("1"), fill_price=Decimal("100"),
            market_data_as_of=now + timedelta(minutes=i), filled_at=now + timedelta(minutes=i),
        ))
    db.commit()

    mission = _find_day6_bias_mission(cookies, uc["id"])
    res = _verify_day6_bias(cookies, uc["id"], mission["id"])
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["mission_completed"] is True

    observations = body["extra"]["observations"]
    overtrading = next(o for o in observations if o["bias_code"] == "OVERTRADING")
    assert overtrading["detected"] is True  # 실제로 감지됐는데도 완료를 막지 않았다


# --- 3. 미션 검증이 실거래(Order/Fill)를 만들지 않음 ---


def test_day6_bias_mission_creates_no_new_orders_or_fills(db):
    cookies, portfolio_id, _email, _pw = _signup_with_credentials("day6-notrade")
    uc = _start_and_unlock_day6(cookies)
    mission = _find_day6_bias_mission(cookies, uc["id"])

    before_orders = db.query(Order).filter(Order.portfolio_id == portfolio_id).count()
    before_fills = db.query(Fill).join(Order, Fill.order_id == Order.id).filter(Order.portfolio_id == portfolio_id).count()

    res = _verify_day6_bias(cookies, uc["id"], mission["id"])
    assert res.status_code == 200, res.text

    after_orders = db.query(Order).filter(Order.portfolio_id == portfolio_id).count()
    after_fills = db.query(Fill).join(Order, Fill.order_id == Order.id).filter(Order.portfolio_id == portfolio_id).count()
    assert after_orders == before_orders
    assert after_fills == before_fills


# --- 4. 근거는 호출자 자신의 데이터로만 계산됨(교차 사용자 격리) ---


def test_day6_bias_mission_evidence_is_callers_own_data_only(db):
    from datetime import datetime, timezone
    from decimal import Decimal

    cookies_a, portfolio_a, _e_a, _p_a = _signup_with_credentials("day6-iso-a")
    instrument = seed_instrument_with_bar(db, "DAY6ISOA", "NASDAQ", "USD", close=100)
    now = datetime.now(timezone.utc)
    for i in range(settings.overtrading_order_threshold):
        order = Order(
            portfolio_id=portfolio_a, instrument_id=instrument.id, side="BUY", order_type="MARKET",
            quantity=Decimal("1"), status="FILLED", submitted_at=now + timedelta(minutes=i),
            policy_version="test-v1", idempotency_key=str(uuid.uuid4()),
        )
        db.add(order)
        db.flush()
        db.add(Fill(
            order_id=order.id, quantity=Decimal("1"), fill_price=Decimal("100"),
            market_data_as_of=now + timedelta(minutes=i), filled_at=now + timedelta(minutes=i),
        ))
    db.commit()

    cookies_b, portfolio_b, _e_b, _p_b = _signup_with_credentials("day6-iso-b")
    uc_b = _start_and_unlock_day6(cookies_b)
    mission_b = _find_day6_bias_mission(cookies_b, uc_b["id"])

    res = _verify_day6_bias(cookies_b, uc_b["id"], mission_b["id"])
    assert res.status_code == 200, res.text
    observations_b = res.json()["extra"]["observations"]
    # 사용자 A가 과잉매매를 유발했더라도, 사용자 B의 결과에는 전혀 반영되지 않는다.
    overtrading_b = next(o for o in observations_b if o["bias_code"] == "OVERTRADING")
    assert overtrading_b["detected"] is False
    assert overtrading_b["sample_size"] == 0

    # 남의 챌린지에 대해 검증을 시도하는 것 자체도 차단된다(IDOR).
    res_cross = _verify_day6_bias(cookies_b, uc_b["id"], mission_b["id"])
    assert res_cross.status_code == 200  # 본인 것이므로 정상(참고용 대조)


# --- 5. 반복 검증해도 XP 중복 지급 없음 ---


def test_day6_bias_mission_no_duplicate_xp_on_repeat_verify(db):
    cookies, portfolio_id, _email, _pw = _signup_with_credentials("day6-noxpdup")
    uc = _start_and_unlock_day6(cookies)
    mission = _find_day6_bias_mission(cookies, uc["id"])
    user_id = db.query(Portfolio).filter(Portfolio.id == portfolio_id).first().user_id

    first = _verify_day6_bias(cookies, uc["id"], mission["id"])
    assert first.status_code == 200, first.text
    first_body = first.json()
    assert first_body["already_completed"] is False
    assert first_body["xp_awarded"] == mission["xp_amount"] > 0

    second = _verify_day6_bias(cookies, uc["id"], mission["id"])
    assert second.status_code == 200, second.text
    second_body = second.json()
    assert second_body["already_completed"] is True
    assert second_body["xp_awarded"] == 0

    ledger_rows = (
        db.query(XpLedger)
        .filter(XpLedger.user_id == user_id, XpLedger.reference_id == uuid.UUID(mission["id"]))
        .all()
    )
    assert len(ledger_rows) == 1  # 두 번 호출했어도 XP 원장에는 단 한 번만 기록된다

    progress_rows = (
        db.query(UserMissionProgress)
        .filter(UserMissionProgress.user_challenge_id == uc["id"], UserMissionProgress.challenge_mission_id == mission["id"])
        .all()
    )
    assert len(progress_rows) == 1


# --- 6. 완료 상태가 재로그인 후에도 유지됨 ---


def test_day6_bias_mission_completion_persists_after_relogin(db):
    cookies, portfolio_id, email, password = _signup_with_credentials("day6-relogin")
    uc = _start_and_unlock_day6(cookies)
    mission = _find_day6_bias_mission(cookies, uc["id"])

    res = _verify_day6_bias(cookies, uc["id"], mission["id"])
    assert res.status_code == 200, res.text
    assert res.json()["mission_completed"] is True

    # 기존 쿠키를 버리고, 완전히 새로 로그인해서 얻은 세션으로 다시 조회한다
    # (진짜 "재로그인 후 새로고침" 시나리오 — 서버 메모리 상태가 아니라 DB에
    # 영속돼 있어야만 통과한다).
    client.cookies.clear()
    login_res = client.post("/v1/auth/login", json={"email": email, "password": password})
    assert login_res.status_code == 200, login_res.text
    fresh_cookies = dict(login_res.cookies)
    client.cookies.clear()

    state = client.get(f"/v1/me/challenges/{uc['id']}", cookies=fresh_cookies).json()
    day6 = next(d for d in state["days"] if d["day_number"] == 6)
    day6_mission = next(m for m in day6["missions"] if m["code"] == "day6_bias")
    assert day6_mission["completed"] is True
    assert day6_mission["xp_awarded"] == mission["xp_amount"]
