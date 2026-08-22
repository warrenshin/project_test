"""Phase A: 포트폴리오 FRESH/STALE/UNAVAILABLE 표시, 주문 stale 차단 검증.

구현 전 결정사항(2. 시세 정책)을 그대로 코드로 옮긴 것을 확인한다:
- 허용시간을 넘긴 시세로는 주문이 체결되지 않는다(기존 동작 유지).
- 포트폴리오는 stale 가격을 참고값으로 표시하되 상태·기준시각을 함께 준다.
- unavailable 가격은 0원이나 손실로 계산되지 않는다(합계에서 제외, 목록에는 남음).
"""

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from tests.conftest import client, seed_instrument_with_bar, signup_user

STALE_AS_OF = datetime.now(timezone.utc) - timedelta(seconds=1000)  # 기본 임계값 900초를 넘김


def _idem_headers() -> dict:
    return {"Idempotency-Key": str(uuid.uuid4())}


def _buy(cookies, portfolio_id, instrument_id, quantity="1"):
    payload = {"instrument_id": str(instrument_id), "side": "BUY", "order_type": "MARKET", "quantity": quantity}
    res = client.post(f"/v1/portfolios/{portfolio_id}/orders", json=payload, cookies=cookies, headers=_idem_headers())
    assert res.status_code == 201, res.text
    return res.json()


def test_position_status_fresh_when_bar_is_recent(db):
    cookies, portfolio_id = signup_user("mdstatus-fresh")
    instrument = seed_instrument_with_bar(db, "TESTMF1", "NASDAQ", "USD", close=100)
    _buy(cookies, portfolio_id, instrument.id)

    positions = client.get(f"/v1/portfolios/{portfolio_id}/positions", cookies=cookies).json()
    position = next(p for p in positions if p["instrument_id"] == str(instrument.id))
    assert position["price_status"] == "FRESH"
    assert position["last_price"] is not None
    assert position["market_value"] is not None
    assert position["price_source"] == "test-seed"
    assert position["price_age_seconds"] is not None
    assert 0 <= position["price_age_seconds"] < 900

    portfolio = client.get(f"/v1/portfolios/{portfolio_id}", cookies=cookies).json()
    assert portfolio["market_data_status"] == "FRESH"
    assert portfolio["has_unavailable_positions"] is False
    assert portfolio["market_data_as_of"] is not None
    assert portfolio["stale_position_count"] == 0
    assert portfolio["unavailable_position_count"] == 0


def test_position_status_stale_is_shown_as_reference_value_and_included_in_total(db):
    cookies, portfolio_id = signup_user("mdstatus-stale")
    instrument = seed_instrument_with_bar(db, "TESTMF2", "NASDAQ", "USD", close=100, as_of=STALE_AS_OF)

    # 매수 시점에는 신선한 시세가 필요하므로, 먼저 신선한 bar로 매수한 뒤
    # bar를 오래된 것으로 되돌려 "이미 보유한 포지션의 시세가 나중에 stale해짐"을
    # 재현한다 — 실제 서비스에서 벌어질 시나리오와 같다.
    from app.domain.market import Bar

    bar = db.query(Bar).filter(Bar.instrument_id == instrument.id).first()
    bar.as_of = datetime.now(timezone.utc)
    db.commit()
    _buy(cookies, portfolio_id, instrument.id)

    bar = db.query(Bar).filter(Bar.instrument_id == instrument.id).first()
    bar.as_of = STALE_AS_OF
    db.commit()

    positions = client.get(f"/v1/portfolios/{portfolio_id}/positions", cookies=cookies).json()
    position = next(p for p in positions if p["instrument_id"] == str(instrument.id))
    assert position["price_status"] == "STALE"
    assert position["last_price"] is not None  # 참고값으로는 여전히 보여준다
    assert position["market_value"] is not None
    assert position["price_source"] == "test-seed"
    assert position["price_age_seconds"] >= 1000  # STALE_AS_OF만큼 오래됨

    portfolio = client.get(f"/v1/portfolios/{portfolio_id}", cookies=cookies).json()
    assert portfolio["market_data_status"] == "STALE"
    # STALE은 UNAVAILABLE이 아니므로 합계에 포함된다(0으로 계산되는 것과는 다름).
    assert Decimal(str(portfolio["positions_market_value"])) > 0
    assert portfolio["has_unavailable_positions"] is False
    assert portfolio["stale_position_count"] == 1
    assert portfolio["unavailable_position_count"] == 0


def test_position_status_unavailable_excluded_from_total_but_not_zero(db):
    cookies, portfolio_id = signup_user("mdstatus-unavail")
    instrument = seed_instrument_with_bar(db, "TESTMF3", "NASDAQ", "USD", close=100)
    _buy(cookies, portfolio_id, instrument.id)

    # 매수 후 이 종목의 시세 자체가 사라진 상황을 재현한다(공급자 장애 등).
    from app.domain.market import Bar

    db.query(Bar).filter(Bar.instrument_id == instrument.id).delete()
    db.commit()

    positions = client.get(f"/v1/portfolios/{portfolio_id}/positions", cookies=cookies).json()
    position = next(p for p in positions if p["instrument_id"] == str(instrument.id))
    # 목록에서 조용히 사라지지 않는다 — 여전히 존재하되 값이 명확히 "확인 불가".
    assert position["price_status"] == "UNAVAILABLE"
    assert position["last_price"] is None
    assert position["market_value"] is None
    assert position["unrealized_pnl"] is None
    assert position["price_source"] is None
    assert position["price_age_seconds"] is None

    portfolio = client.get(f"/v1/portfolios/{portfolio_id}", cookies=cookies).json()
    assert portfolio["market_data_status"] == "UNAVAILABLE"
    assert portfolio["has_unavailable_positions"] is True
    assert portfolio["stale_position_count"] == 0
    assert portfolio["unavailable_position_count"] == 1
    # 이 종목의 가치가 0원으로 잡혀 총자산이 깎이지 않는다 — 그냥 평가액 계산에서
    # 빠질 뿐, 실제로 있던 현금(초기 가상현금 - 매수 비용)은 total_assets에
    # 그대로 남아 있어야 한다.
    assert Decimal(str(portfolio["total_assets"])) > 0

    performance = client.get(f"/v1/portfolios/{portfolio_id}/performance", cookies=cookies).json()
    assert performance["market_data_status"] == "UNAVAILABLE"
    assert performance["has_unavailable_positions"] is True
    assert performance["stale_position_count"] == 0
    assert performance["unavailable_position_count"] == 1
    # simple_return_pct는 total_assets(일부 종목 제외한 불완전한 값)를
    # total_deposited(항상 완전한 값)로 나누므로, UNAVAILABLE 포지션이 있을 때
    # 이 값을 그대로 노출하면 완전한 수익률처럼 보이는 왜곡이 생긴다 — null이어야 한다.
    assert performance["performance_complete"] is False
    assert performance["simple_return_pct"] is None


def test_portfolio_counts_match_number_of_badges_in_positions_list(db):
    """stale_position_count/unavailable_position_count는 positions 응답에서
    사용자가 직접 price_status 배지를 세었을 때 나오는 개수와 항상 일치해야
    한다 — 두 응답이 서로 다른 숫자를 말하면 신뢰할 수 없는 API가 된다."""
    cookies, portfolio_id = signup_user("mdstatus-counts")
    fresh = seed_instrument_with_bar(db, "TESTMFC1", "NASDAQ", "USD", close=100)
    stale = seed_instrument_with_bar(db, "TESTMFC2", "NASDAQ", "USD", close=100)
    unavail = seed_instrument_with_bar(db, "TESTMFC3", "NASDAQ", "USD", close=100)

    from app.domain.market import Bar

    for inst in (stale, unavail):
        bar = db.query(Bar).filter(Bar.instrument_id == inst.id).first()
        bar.as_of = datetime.now(timezone.utc)
        db.commit()

    for inst in (fresh, stale, unavail):
        _buy(cookies, portfolio_id, inst.id)

    db.query(Bar).filter(Bar.instrument_id == stale.id).update({"as_of": STALE_AS_OF})
    db.query(Bar).filter(Bar.instrument_id == unavail.id).delete()
    db.commit()

    positions = client.get(f"/v1/portfolios/{portfolio_id}/positions", cookies=cookies).json()
    counted_stale = sum(1 for p in positions if p["price_status"] == "STALE")
    counted_unavailable = sum(1 for p in positions if p["price_status"] == "UNAVAILABLE")
    assert counted_stale == 1
    assert counted_unavailable == 1

    portfolio = client.get(f"/v1/portfolios/{portfolio_id}", cookies=cookies).json()
    assert portfolio["stale_position_count"] == counted_stale
    assert portfolio["unavailable_position_count"] == counted_unavailable

    performance = client.get(f"/v1/portfolios/{portfolio_id}/performance", cookies=cookies).json()
    assert performance["stale_position_count"] == counted_stale
    assert performance["unavailable_position_count"] == counted_unavailable


def test_performance_complete_true_when_only_fresh_and_stale(db):
    cookies, portfolio_id = signup_user("mdstatus-perfcomplete")
    fresh = seed_instrument_with_bar(db, "TESTMF6", "NASDAQ", "USD", close=100)
    stale = seed_instrument_with_bar(db, "TESTMF7", "NASDAQ", "USD", close=100)
    _buy(cookies, portfolio_id, fresh.id)

    from app.domain.market import Bar

    bar = db.query(Bar).filter(Bar.instrument_id == stale.id).first()
    bar.as_of = datetime.now(timezone.utc)
    db.commit()
    _buy(cookies, portfolio_id, stale.id)

    bar = db.query(Bar).filter(Bar.instrument_id == stale.id).first()
    bar.as_of = STALE_AS_OF
    db.commit()

    performance = client.get(f"/v1/portfolios/{portfolio_id}/performance", cookies=cookies).json()
    # STALE만 있고 UNAVAILABLE은 없으므로 total_assets는 여전히 완전한 값이다 —
    # simple_return_pct를 그대로 노출해도 왜곡되지 않는다.
    assert performance["market_data_status"] == "STALE"
    assert performance["has_unavailable_positions"] is False
    assert performance["performance_complete"] is True
    assert performance["simple_return_pct"] is not None


def test_empty_portfolio_market_data_status_is_empty():
    cookies, portfolio_id = signup_user("mdstatus-empty")
    portfolio = client.get(f"/v1/portfolios/{portfolio_id}", cookies=cookies).json()
    assert portfolio["market_data_status"] == "EMPTY"
    assert portfolio["has_unavailable_positions"] is False
    assert portfolio["market_data_as_of"] is None


def test_order_still_blocked_when_price_is_stale(db):
    cookies, portfolio_id = signup_user("mdstatus-order-stale")
    instrument = seed_instrument_with_bar(db, "TESTMF4", "NASDAQ", "USD", close=100, as_of=STALE_AS_OF)

    payload = {"instrument_id": str(instrument.id), "side": "BUY", "order_type": "MARKET", "quantity": "1"}
    res = client.post(f"/v1/portfolios/{portfolio_id}/orders", json=payload, cookies=cookies, headers=_idem_headers())
    assert res.status_code == 409, res.text


def test_order_blocked_when_no_price_available(db):
    cookies, portfolio_id = signup_user("mdstatus-order-unavail")
    instrument = seed_instrument_with_bar(db, "TESTMF5", "NASDAQ", "USD", close=100)
    from app.domain.market import Bar

    db.query(Bar).filter(Bar.instrument_id == instrument.id).delete()
    db.commit()

    payload = {"instrument_id": str(instrument.id), "side": "BUY", "order_type": "MARKET", "quantity": "1"}
    res = client.post(f"/v1/portfolios/{portfolio_id}/orders", json=payload, cookies=cookies, headers=_idem_headers())
    assert res.status_code == 422, res.text
