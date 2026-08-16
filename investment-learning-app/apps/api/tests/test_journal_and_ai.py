import uuid
from decimal import Decimal

from tests.conftest import client, seed_instrument_with_bar, signup_user


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_pre_trade_journal_scores_low_without_counter_evidence(db):
    token, portfolio_id = signup_user("journaler1")
    instrument = seed_instrument_with_bar(db, "032830", "KRX", "KRW", close=60_000)

    payload = {
        "portfolio_id": portfolio_id,
        "instrument_id": str(instrument.id),
        "thesis": "실적 개선 기대",
        "supporting_evidence": ["매출 성장", "신제품 출시"],
        "counter_evidence": [],
        "planned_weight_pct": "5",
    }
    res = client.post("/v1/journals/pre-trade", json=payload, headers=_auth(token))
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["market_data_snapshot"]["close"] == "60000.00000000"
    assert body["process_score"] is not None
    # counter_evidence가 없으므로 그 항목(15% 가중치)에서 0점 처리된다
    assert body["process_score_breakdown"]["counter_evidence"] == 0.0


def test_journal_update_preserves_original_as_version(db):
    from app.domain.journal import JournalVersion

    token, portfolio_id = signup_user("journaler2")
    instrument = seed_instrument_with_bar(db, "010130", "KRX", "KRW", close=80_000)

    create_res = client.post(
        "/v1/journals/pre-trade",
        json={
            "portfolio_id": portfolio_id,
            "instrument_id": str(instrument.id),
            "thesis": "최초 논리",
            "counter_evidence": ["원자재 가격 상승 위험"],
        },
        headers=_auth(token),
    )
    journal_id = create_res.json()["id"]

    update_res = client.patch(
        f"/v1/journals/{journal_id}", json={"thesis": "수정된 논리"}, headers=_auth(token)
    )
    assert update_res.status_code == 200
    assert update_res.json()["thesis"] == "수정된 논리"

    versions = db.query(JournalVersion).filter(JournalVersion.journal_id == uuid.UUID(journal_id)).all()
    assert len(versions) == 1
    assert versions[0].content_snapshot["thesis"] == "최초 논리"


def test_post_trade_review_improves_process_score(db):
    token, portfolio_id = signup_user("journaler3")
    instrument = seed_instrument_with_bar(db, "011170", "KRX", "KRW", close=250_000)

    create_res = client.post(
        "/v1/journals/pre-trade",
        json={
            "portfolio_id": portfolio_id,
            "instrument_id": str(instrument.id),
            "thesis": "논리",
            "counter_evidence": ["위험 요인"],
            "entry_condition": "20일선 돌파",
            "target_condition": "+10%",
            "stop_loss_condition": "-5%",
            "expected_holding_period": "1개월",
            "planned_weight_pct": "8",
        },
        headers=_auth(token),
    )
    journal_id = create_res.json()["id"]
    score_before = Decimal(str(create_res.json()["process_score"]))

    post_trade_res = client.post(
        f"/v1/journals/{journal_id}/post-trade",
        json={
            "followed_plan": True,
            "expectation_gap": "예상보다 빨리 목표가 도달",
            "behavior_to_repeat": "분할 매수",
            "behavior_to_change": "성급한 매도",
            "emotion_tags": ["확신"],
        },
        headers=_auth(token),
    )
    assert post_trade_res.status_code == 200
    score_after = Decimal(str(post_trade_res.json()["process_score"]))
    assert score_after > score_before


def test_journal_coaching_endpoint_returns_degraded_fallback():
    token, portfolio_id = signup_user("journaler4")

    # journal 없이도 인증만 되면 존재하지 않는 journal 접근은 404
    res = client.get(f"/v1/journals/{uuid.uuid4()}/coaching", headers=_auth(token))
    assert res.status_code == 404


def test_bias_report_flags_missing_counter_evidence(db):
    token, portfolio_id = signup_user("biasuser")
    instrument = seed_instrument_with_bar(db, "005380", "KRX", "KRW", close=200_000)

    for i in range(3):
        client.post(
            "/v1/journals/pre-trade",
            json={
                "portfolio_id": portfolio_id,
                "instrument_id": str(instrument.id),
                "thesis": f"논리 {i}",
                "counter_evidence": [],
            },
            headers=_auth(token),
        )

    res = client.get("/v1/me/bias-report", headers=_auth(token))
    assert res.status_code == 200
    body = res.json()
    patterns = [o["pattern"] for o in body["observations"]]
    assert "확증편향 의심 패턴" in patterns


def test_ai_conversation_falls_back_gracefully_without_api_key():
    token, _ = signup_user("aiuser")

    conv_res = client.post("/v1/ai/conversations", json={}, headers=_auth(token))
    assert conv_res.status_code == 201
    conversation_id = conv_res.json()["id"]

    msg_res = client.post(
        f"/v1/ai/conversations/{conversation_id}/messages",
        json={"content": "ETF가 뭔가요?"},
        headers=_auth(token),
    )
    assert msg_res.status_code == 201
    body = msg_res.json()
    assert body["degraded"] is True  # 이 테스트 환경엔 ANTHROPIC_API_KEY가 없다
    assert "교육용 정보" in body["content"]
    assert body["role"] == "ASSISTANT"

    feedback_res = client.post(
        f"/v1/ai/messages/{body['id']}/feedback",
        json={"feedback": "HELPFUL"},
        headers=_auth(token),
    )
    assert feedback_res.status_code == 204


def test_ai_coach_policy_filter_blocks_direct_instruction_text():
    from app.domain.services.ai_coach import check_policy_violation

    assert check_policy_violation("지금 사세요, 확실히 오를 것입니다") is not None
    assert check_policy_violation("ETF는 여러 종목에 분산투자하는 상품입니다") is None
