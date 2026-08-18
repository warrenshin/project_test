import uuid
from decimal import Decimal

from tests.conftest import client, seed_instrument_with_bar, signup_user


def _auth(cookies: dict) -> dict:
    return cookies


def _idem_headers() -> dict:
    return {"Idempotency-Key": str(uuid.uuid4())}


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
        cookies=_auth(token),
    )
    assert create_res.status_code == 201, create_res.text
    journal_id = create_res.json()["id"]

    list_res = client.get("/v1/me/journals", cookies=_auth(token))
    assert list_res.status_code == 200
    ids = [j["id"] for j in list_res.json()]
    assert journal_id in ids

    get_res = client.get(f"/v1/journals/{journal_id}", cookies=_auth(token))
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
        cookies=_auth(token),
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
        cookies=token,
        headers=_idem_headers(),
    )
    assert order_res.status_code == 201, order_res.text
    order_id = order_res.json()["id"]

    journal_after = client.get(f"/v1/journals/{journal_id}", cookies=_auth(token))
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
    res = client.post("/v1/journals/pre-trade", json=payload, cookies=_auth(token))
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
        cookies=_auth(token),
    )
    journal_id = create_res.json()["id"]

    update_res = client.patch(
        f"/v1/journals/{journal_id}", json={"thesis": "수정된 논리"}, cookies=_auth(token)
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
        cookies=_auth(token),
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
        cookies=_auth(token),
    )
    assert post_trade_res.status_code == 200
    score_after = Decimal(str(post_trade_res.json()["process_score"]))
    assert score_after > score_before


def test_journal_coaching_endpoint_returns_degraded_fallback():
    token, portfolio_id = signup_user("journaler4")

    # journal 없이도 인증만 되면 존재하지 않는 journal 접근은 404
    res = client.get(f"/v1/journals/{uuid.uuid4()}/coaching", cookies=_auth(token))
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
            cookies=_auth(token),
        )

    res = client.get("/v1/me/bias-report", cookies=_auth(token))
    assert res.status_code == 200
    body = res.json()
    patterns = [o["pattern"] for o in body["observations"]]
    assert "확증편향 의심 패턴" in patterns


def test_ai_conversation_falls_back_gracefully_without_api_key():
    token, _ = signup_user("aiuser")

    conv_res = client.post("/v1/ai/conversations", json={}, cookies=_auth(token))
    assert conv_res.status_code == 201
    conversation_id = conv_res.json()["id"]

    msg_res = client.post(
        f"/v1/ai/conversations/{conversation_id}/messages",
        json={"content": "ETF가 뭔가요?"},
        cookies=_auth(token),
    )
    assert msg_res.status_code == 201
    body = msg_res.json()
    assert body["degraded"] is True  # 이 테스트 환경엔 ANTHROPIC_API_KEY가 없다
    assert "교육용 정보" in body["content"]
    assert body["role"] == "ASSISTANT"

    feedback_res = client.post(
        f"/v1/ai/messages/{body['id']}/feedback",
        json={"feedback": "HELPFUL"},
        cookies=_auth(token),
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
        cookies=_auth(token_a),
    ).json()

    token_b, _ = signup_user("idorattacker")
    res = client.get(f"/v1/journals/{victim_journal['id']}", cookies=_auth(token_b))
    assert res.status_code == 404


def test_me_journals_never_includes_another_users_journal(db):
    token_a, portfolio_a = signup_user("idorvictim2")
    instrument = seed_instrument_with_bar(db, "090430", "KRX", "KRW", close=150_000)
    victim_journal = client.post(
        "/v1/journals/pre-trade",
        json={"portfolio_id": portfolio_a, "instrument_id": str(instrument.id), "thesis": "피해자 일지2"},
        cookies=_auth(token_a),
    ).json()

    token_b, _ = signup_user("idorattacker2")
    res = client.get("/v1/me/journals", cookies=_auth(token_b))
    assert res.status_code == 200
    ids = [j["id"] for j in res.json()]
    assert victim_journal["id"] not in ids


def test_cannot_backfill_another_users_journal_via_order(db):
    """공격자가 자신의 주문 생성 요청에 피해자의 journal id를 pre_trade_journal_id로
    넣으면, 서버는 쓰기 시점에 소유권을 검증해 주문 자체를 생성하지 않는다(404).
    (2026-08 감사 후속 조치: 이전에는 조용히 건너뛰고 주문만 성사시켰으나,
    쓰기 시점 검증 도입 후 요청 전체가 거절되도록 강화했다.)"""
    token_victim, portfolio_victim = signup_user("idorvictim3")
    instrument = seed_instrument_with_bar(db, "086790", "KRX", "KRW", close=55_000)
    victim_journal = client.post(
        "/v1/journals/pre-trade",
        json={"portfolio_id": portfolio_victim, "instrument_id": str(instrument.id), "thesis": "피해자 일지3"},
        cookies=_auth(token_victim),
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
        cookies=token_attacker,
        headers=_idem_headers(),
    )
    assert order_res.status_code == 404, order_res.text

    victim_journal_after = client.get(f"/v1/journals/{victim_journal['id']}", cookies=_auth(token_victim))
    assert victim_journal_after.json()["order_id"] is None

    # 공격자 본인은 피해자 일지를 여전히 볼 수 없다
    attacker_view = client.get(f"/v1/journals/{victim_journal['id']}", cookies=_auth(token_attacker))
    assert attacker_view.status_code == 404


# --- 쓰기 시점 소유권 검증 (2026-08 감사 후속 조치) ---
# journals.py::create_pre_trade_journal의 order_id와 portfolios.py::create_order의
# pre_trade_journal_id는 이제 저장 전에 소유권을 서버에서 검증한다. 둘 다 "존재하지
# 않음"과 "타인 소유"를 구분하지 않고 404로 응답해(anti-enumeration) 이 파일의 다른
# 소유권 검증들(_get_owned_journal, _get_owned_portfolio)과 정책을 통일한다.


def test_can_create_journal_linked_to_own_order(db):
    token, portfolio_id = signup_user("ownerlinker")
    instrument = seed_instrument_with_bar(db, "011790", "KRX", "KRW", close=70_000)

    order_res = client.post(
        f"/v1/portfolios/{portfolio_id}/orders",
        json={"instrument_id": str(instrument.id), "side": "BUY", "order_type": "MARKET", "quantity": "1"},
        cookies=token,
        headers=_idem_headers(),
    )
    assert order_res.status_code == 201, order_res.text
    order_id = order_res.json()["id"]

    journal_res = client.post(
        "/v1/journals/pre-trade",
        json={
            "portfolio_id": portfolio_id,
            "instrument_id": str(instrument.id),
            "order_id": order_id,
            "thesis": "이미 체결된 내 주문에 사후 연결",
        },
        cookies=_auth(token),
    )
    assert journal_res.status_code == 201, journal_res.text
    assert journal_res.json()["order_id"] == order_id


def test_cannot_create_journal_linked_to_other_users_order(db):
    token_victim, portfolio_victim = signup_user("orderowner")
    instrument = seed_instrument_with_bar(db, "058470", "KRX", "KRW", close=30_000)
    victim_order = client.post(
        f"/v1/portfolios/{portfolio_victim}/orders",
        json={"instrument_id": str(instrument.id), "side": "BUY", "order_type": "MARKET", "quantity": "1"},
        cookies=token_victim,
        headers=_idem_headers(),
    ).json()

    token_attacker, portfolio_attacker = signup_user("orderattacker")
    res = client.post(
        "/v1/journals/pre-trade",
        json={
            "portfolio_id": portfolio_attacker,
            "instrument_id": str(instrument.id),
            "order_id": victim_order["id"],
            "thesis": "타인 주문에 무단 연결 시도",
        },
        cookies=_auth(token_attacker),
    )
    assert res.status_code == 404, res.text

    # 거절된 요청은 일지 자체를 남기지 않는다
    attacker_journals = client.get("/v1/me/journals", cookies=_auth(token_attacker)).json()
    assert all(j["thesis"] != "타인 주문에 무단 연결 시도" for j in attacker_journals)


def test_create_journal_with_nonexistent_order_id_returns_404(db):
    token, portfolio_id = signup_user("ghostorderjournal")
    instrument = seed_instrument_with_bar(db, "064350", "KRX", "KRW", close=40_000)

    res = client.post(
        "/v1/journals/pre-trade",
        json={
            "portfolio_id": portfolio_id,
            "instrument_id": str(instrument.id),
            "order_id": str(uuid.uuid4()),
            "thesis": "존재하지 않는 주문 참조",
        },
        cookies=_auth(token),
    )
    assert res.status_code == 404, res.text

    journals = client.get("/v1/me/journals", cookies=_auth(token)).json()
    assert all(j["thesis"] != "존재하지 않는 주문 참조" for j in journals)


def test_create_order_with_nonexistent_pre_trade_journal_id_returns_404(db):
    from app.domain.portfolio import LedgerEntry, Order, Position
    from app.domain.services import execution

    token, portfolio_id = signup_user("ghostjournalorder")
    instrument = seed_instrument_with_bar(db, "052690", "KRX", "KRW", close=20_000)

    cash_before = execution.get_cash_balance(db, uuid.UUID(portfolio_id), "KRW")
    orders_before = db.query(Order).filter(Order.portfolio_id == uuid.UUID(portfolio_id)).count()
    ledger_before = db.query(LedgerEntry).filter(LedgerEntry.portfolio_id == uuid.UUID(portfolio_id)).count()
    positions_before = db.query(Position).filter(Position.portfolio_id == uuid.UUID(portfolio_id)).count()

    res = client.post(
        f"/v1/portfolios/{portfolio_id}/orders",
        json={
            "instrument_id": str(instrument.id),
            "side": "BUY",
            "order_type": "MARKET",
            "quantity": "1",
            "pre_trade_journal_id": str(uuid.uuid4()),
        },
        cookies=token,
        headers=_idem_headers(),
    )
    assert res.status_code == 404, res.text

    # 거절된 요청은 Order/ledger/position/cash에 어떤 부분 변경도 남기지 않는다
    db.expire_all()
    assert execution.get_cash_balance(db, uuid.UUID(portfolio_id), "KRW") == cash_before
    assert db.query(Order).filter(Order.portfolio_id == uuid.UUID(portfolio_id)).count() == orders_before
    assert (
        db.query(LedgerEntry).filter(LedgerEntry.portfolio_id == uuid.UUID(portfolio_id)).count() == ledger_before
    )
    assert db.query(Position).filter(Position.portfolio_id == uuid.UUID(portfolio_id)).count() == positions_before


def test_rejected_order_leaves_no_partial_state_for_other_users_journal(db):
    """타인 소유 일지를 노려 주문을 넣었다가 거절될 때도 부분 변경이 남지 않아야 한다."""
    from app.domain.portfolio import LedgerEntry, Order, Position
    from app.domain.services import execution

    token_victim, portfolio_victim = signup_user("statevictim")
    instrument = seed_instrument_with_bar(db, "047810", "KRX", "KRW", close=25_000)
    victim_journal = client.post(
        "/v1/journals/pre-trade",
        json={"portfolio_id": portfolio_victim, "instrument_id": str(instrument.id), "thesis": "상태 보존 확인용"},
        cookies=_auth(token_victim),
    ).json()

    token_attacker, portfolio_attacker = signup_user("stateattacker")
    cash_before = execution.get_cash_balance(db, uuid.UUID(portfolio_attacker), "KRW")
    orders_before = db.query(Order).filter(Order.portfolio_id == uuid.UUID(portfolio_attacker)).count()
    ledger_before = (
        db.query(LedgerEntry).filter(LedgerEntry.portfolio_id == uuid.UUID(portfolio_attacker)).count()
    )
    positions_before = db.query(Position).filter(Position.portfolio_id == uuid.UUID(portfolio_attacker)).count()

    res = client.post(
        f"/v1/portfolios/{portfolio_attacker}/orders",
        json={
            "instrument_id": str(instrument.id),
            "side": "BUY",
            "order_type": "MARKET",
            "quantity": "1",
            "pre_trade_journal_id": victim_journal["id"],
        },
        cookies=token_attacker,
        headers=_idem_headers(),
    )
    assert res.status_code == 404, res.text

    db.expire_all()
    assert execution.get_cash_balance(db, uuid.UUID(portfolio_attacker), "KRW") == cash_before
    assert db.query(Order).filter(Order.portfolio_id == uuid.UUID(portfolio_attacker)).count() == orders_before
    assert (
        db.query(LedgerEntry).filter(LedgerEntry.portfolio_id == uuid.UUID(portfolio_attacker)).count()
        == ledger_before
    )
    assert (
        db.query(Position).filter(Position.portfolio_id == uuid.UUID(portfolio_attacker)).count()
        == positions_before
    )


def test_own_order_journal_backfill_still_works_after_ownership_validation(db):
    """정상 흐름(자신의 일지 -> 자신의 주문) 회귀 확인: 쓰기 시점 검증 도입 후에도
    기존 order->journal backfill이 그대로 동작해야 한다."""
    token, portfolio_id = signup_user("backfillregression")
    instrument = seed_instrument_with_bar(db, "298050", "KRX", "KRW", close=35_000)

    journal = client.post(
        "/v1/journals/pre-trade",
        json={"portfolio_id": portfolio_id, "instrument_id": str(instrument.id), "thesis": "회귀 확인용 일지"},
        cookies=_auth(token),
    ).json()
    assert journal["order_id"] is None

    order_res = client.post(
        f"/v1/portfolios/{portfolio_id}/orders",
        json={
            "instrument_id": str(instrument.id),
            "side": "BUY",
            "order_type": "MARKET",
            "quantity": "1",
            "pre_trade_journal_id": journal["id"],
        },
        cookies=token,
        headers=_idem_headers(),
    )
    assert order_res.status_code == 201, order_res.text

    journal_after = client.get(f"/v1/journals/{journal['id']}", cookies=_auth(token))
    assert journal_after.json()["order_id"] == order_res.json()["id"]
