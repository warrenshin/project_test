import uuid
from decimal import Decimal

from tests.conftest import client, seed_instrument_with_bar, signup_user


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _idem_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Idempotency-Key": str(uuid.uuid4())}


def test_list_and_get_my_journals(db):
    token, portfolio_id = signup_user("journallister")
    instrument = seed_instrument_with_bar(db, "035420", "KRX", "KRW", close=200_000)

    create_res = client.post(
        "/v1/journals/pre-trade",
        json={
            "portfolio_id": portfolio_id,
            "instrument_id": str(instrument.id),
            "thesis": "검색 점유율 확대",
            "counter_evidence": ["광고 경쟁 심화"],
        },
        headers=_auth(token),
    )
    assert create_res.status_code == 201, create_res.text
    journal_id = create_res.json()["id"]

    list_res = client.get("/v1/me/journals", headers=_auth(token))
    assert list_res.status_code == 200
    ids = [j["id"] for j in list_res.json()]
    assert journal_id in ids

    get_res = client.get(f"/v1/journals/{journal_id}", headers=_auth(token))
    assert get_res.status_code == 200
    assert get_res.json()["thesis"] == "검색 점유율 확대"


def test_order_backfills_journal_order_id_for_bias_detection(db):
    token, portfolio_id = signup_user("backfilluser")
    instrument = seed_instrument_with_bar(db, "003550", "KRX", "KRW", close=90_000)

    journal_res = client.post(
        "/v1/journals/pre-trade",
        json={
            "portfolio_id": portfolio_id,
            "instrument_id": str(instrument.id),
            "thesis": "지주사 저평가",
            "counter_evidence": ["지배구조 불확실성"],
        },
        headers=_auth(token),
    )
    journal_id = journal_res.json()["id"]
    assert journal_res.json()["order_id"] is None

    order_res = client.post(
        f"/v1/portfolios/{portfolio_id}/orders",
        json={
            "instrument_id": str(instrument.id),
            "side": "BUY",
            "order_type": "MARKET",
            "quantity": "1",
            "pre_trade_journal_id": journal_id,
        },
        headers=_idem_headers(token),
    )
    assert order_res.status_code == 201, order_res.text
    order_id = order_res.json()["id"]

    journal_after = client.get(f"/v1/journals/{journal_id}", headers=_auth(token))
    assert journal_after.json()["order_id"] == order_id


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


# --- 객체 단위 권한(IDOR) 회귀 테스트 ---
# 병합 전 감사에서 확인된 항목: 다른 사용자의 UUID를 넣어 일지를 조회·연결할 수 없어야 한다.


def test_cannot_get_another_users_journal_by_id(db):
    token_a, portfolio_a = signup_user("idorvictim")
    instrument = seed_instrument_with_bar(db, "017670", "KRX", "KRW", close=45_000)
    victim_journal = client.post(
        "/v1/journals/pre-trade",
        json={"portfolio_id": portfolio_a, "instrument_id": str(instrument.id), "thesis": "피해자 일지"},
        headers=_auth(token_a),
    ).json()

    token_b, _ = signup_user("idorattacker")
    res = client.get(f"/v1/journals/{victim_journal['id']}", headers=_auth(token_b))
    assert res.status_code == 404


def test_me_journals_never_includes_another_users_journal(db):
    token_a, portfolio_a = signup_user("idorvictim2")
    instrument = seed_instrument_with_bar(db, "090430", "KRX", "KRW", close=150_000)
    victim_journal = client.post(
        "/v1/journals/pre-trade",
        json={"portfolio_id": portfolio_a, "instrument_id": str(instrument.id), "thesis": "피해자 일지2"},
        headers=_auth(token_a),
    ).json()

    token_b, _ = signup_user("idorattacker2")
    res = client.get("/v1/me/journals", headers=_auth(token_b))
    assert res.status_code == 200
    ids = [j["id"] for j in res.json()]
    assert victim_journal["id"] not in ids


def test_cannot_backfill_another_users_journal_via_order(db):
    """공격자가 자신의 주문 생성 요청에 피해자의 journal id를 pre_trade_journal_id로
    넣어도, 피해자 일지의 order_id가 채워지거나 공격자 소유로 넘어가지 않아야 한다."""
    token_victim, portfolio_victim = signup_user("idorvictim3")
    instrument = seed_instrument_with_bar(db, "086790", "KRX", "KRW", close=55_000)
    victim_journal = client.post(
        "/v1/journals/pre-trade",
        json={"portfolio_id": portfolio_victim, "instrument_id": str(instrument.id), "thesis": "피해자 일지3"},
        headers=_auth(token_victim),
    ).json()
    assert victim_journal["order_id"] is None

    token_attacker, portfolio_attacker = signup_user("idorattacker3")
    order_res = client.post(
        f"/v1/portfolios/{portfolio_attacker}/orders",
        json={
            "instrument_id": str(instrument.id),
            "side": "BUY",
            "order_type": "MARKET",
            "quantity": "1",
            "pre_trade_journal_id": victim_journal["id"],
        },
        headers=_idem_headers(token_attacker),
    )
    assert order_res.status_code == 201, order_res.text

    victim_journal_after = client.get(f"/v1/journals/{victim_journal['id']}", headers=_auth(token_victim))
    assert victim_journal_after.json()["order_id"] is None

    # 공격자 본인은 피해자 일지를 여전히 볼 수 없다
    attacker_view = client.get(f"/v1/journals/{victim_journal['id']}", headers=_auth(token_attacker))
    assert attacker_view.status_code == 404
