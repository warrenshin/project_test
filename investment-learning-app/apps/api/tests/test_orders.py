import uuid
from decimal import Decimal

from tests.conftest import client, seed_instrument_with_bar, signup_user


def _idem_headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "Idempotency-Key": str(uuid.uuid4()),
    }


def test_market_buy_cash_invariant_matches_preview(db):
    token, portfolio_id = signup_user("buyer")
    instrument = seed_instrument_with_bar(db, "005930", "KRX", "KRW", close=50_000)

    order_payload = {
        "instrument_id": str(instrument.id),
        "side": "BUY",
        "order_type": "MARKET",
        "quantity": "10",
    }
    headers = {"Authorization": f"Bearer {token}"}

    preview = client.post(
        f"/v1/portfolios/{portfolio_id}/orders/preview", json=order_payload, headers=headers
    ).json()
    assert preview["estimated_fillable"] is True

    cash_before = Decimal(
        str(client.get(f"/v1/portfolios/{portfolio_id}", headers=headers).json()["cash_balance"])
    )

    order_res = client.post(
        f"/v1/portfolios/{portfolio_id}/orders", json=order_payload, headers=_idem_headers(token)
    )
    assert order_res.status_code == 201, order_res.text
    assert order_res.json()["status"] == "FILLED"

    cash_after = Decimal(
        str(client.get(f"/v1/portfolios/{portfolio_id}", headers=headers).json()["cash_balance"])
    )

    delta = cash_after - cash_before
    expected = Decimal(str(preview["estimated_cash_impact"]))
    assert abs(delta - expected) < Decimal("0.01")
    assert delta < 0  # 매수 후 현금은 반드시 감소해야 한다


def test_market_sell_increases_cash_and_realizes_pnl(db):
    token, portfolio_id = signup_user("seller")
    instrument = seed_instrument_with_bar(db, "000660", "KRX", "KRW", close=100_000)
    headers = {"Authorization": f"Bearer {token}"}

    buy_payload = {
        "instrument_id": str(instrument.id),
        "side": "BUY",
        "order_type": "MARKET",
        "quantity": "5",
    }
    buy_res = client.post(
        f"/v1/portfolios/{portfolio_id}/orders", json=buy_payload, headers=_idem_headers(token)
    )
    assert buy_res.status_code == 201

    cash_before_sell = Decimal(
        str(client.get(f"/v1/portfolios/{portfolio_id}", headers=headers).json()["cash_balance"])
    )

    sell_payload = {
        "instrument_id": str(instrument.id),
        "side": "SELL",
        "order_type": "MARKET",
        "quantity": "5",
    }
    preview = client.post(
        f"/v1/portfolios/{portfolio_id}/orders/preview", json=sell_payload, headers=headers
    ).json()

    sell_res = client.post(
        f"/v1/portfolios/{portfolio_id}/orders", json=sell_payload, headers=_idem_headers(token)
    )
    assert sell_res.status_code == 201
    assert sell_res.json()["status"] == "FILLED"

    cash_after_sell = Decimal(
        str(client.get(f"/v1/portfolios/{portfolio_id}", headers=headers).json()["cash_balance"])
    )
    delta = cash_after_sell - cash_before_sell
    expected = Decimal(str(preview["estimated_cash_impact"]))
    assert abs(delta - expected) < Decimal("0.01")
    assert delta > 0  # 매도 후 현금은 반드시 증가해야 한다

    positions = client.get(f"/v1/portfolios/{portfolio_id}/positions", headers=headers).json()
    assert all(p["instrument_id"] != str(instrument.id) for p in positions if Decimal(str(p["quantity"])) > 0)


def test_cannot_sell_beyond_holdings(db):
    token, portfolio_id = signup_user("overseller")
    instrument = seed_instrument_with_bar(db, "035420", "KRX", "KRW", close=200_000)
    headers = {"Authorization": f"Bearer {token}"}

    sell_payload = {
        "instrument_id": str(instrument.id),
        "side": "SELL",
        "order_type": "MARKET",
        "quantity": "1",
    }
    res = client.post(
        f"/v1/portfolios/{portfolio_id}/orders", json=sell_payload, headers=_idem_headers(token)
    )
    assert res.status_code == 422


def test_cannot_buy_beyond_cash(db):
    token, portfolio_id = signup_user("brokebuyer")
    instrument = seed_instrument_with_bar(db, "051910", "KRX", "KRW", close=500_000)
    headers = {"Authorization": f"Bearer {token}"}

    buy_payload = {
        "instrument_id": str(instrument.id),
        "side": "BUY",
        "order_type": "MARKET",
        "quantity": "1000",  # 5억원 상당, 초기 가상현금(1천만원) 초과
    }
    res = client.post(
        f"/v1/portfolios/{portfolio_id}/orders", json=buy_payload, headers=_idem_headers(token)
    )
    assert res.status_code == 422


def test_duplicate_idempotency_key_does_not_double_execute(db):
    token, portfolio_id = signup_user("retrier")
    instrument = seed_instrument_with_bar(db, "207940", "KRX", "KRW", close=800_000)
    headers = {"Authorization": f"Bearer {token}"}
    idem_headers = _idem_headers(token)

    order_payload = {
        "instrument_id": str(instrument.id),
        "side": "BUY",
        "order_type": "MARKET",
        "quantity": "2",
    }

    first = client.post(f"/v1/portfolios/{portfolio_id}/orders", json=order_payload, headers=idem_headers)
    assert first.status_code == 201
    first_order_id = first.json()["id"]

    cash_after_first = client.get(f"/v1/portfolios/{portfolio_id}", headers=headers).json()["cash_balance"]

    second = client.post(f"/v1/portfolios/{portfolio_id}/orders", json=order_payload, headers=idem_headers)
    assert second.status_code == 201
    assert second.json()["id"] == first_order_id  # 새 주문이 아니라 기존 주문을 반환해야 한다

    cash_after_second = client.get(f"/v1/portfolios/{portfolio_id}", headers=headers).json()["cash_balance"]
    assert cash_after_first == cash_after_second  # 중복 실행으로 잔고가 다시 변하면 안 된다


def test_limit_order_not_immediately_fillable_stays_accepted_then_cancellable(db):
    token, portfolio_id = signup_user("limiter")
    instrument = seed_instrument_with_bar(db, "006400", "KRX", "KRW", close=100_000, low=98_000, high=102_000)
    headers = {"Authorization": f"Bearer {token}"}

    # 저가(98,000)보다 낮은 지정가로는 이 bar에서 체결될 수 없다
    order_payload = {
        "instrument_id": str(instrument.id),
        "side": "BUY",
        "order_type": "LIMIT",
        "quantity": "1",
        "limit_price": "90000",
    }
    cash_before = client.get(f"/v1/portfolios/{portfolio_id}", headers=headers).json()["cash_balance"]

    order_res = client.post(
        f"/v1/portfolios/{portfolio_id}/orders", json=order_payload, headers=_idem_headers(token)
    )
    assert order_res.status_code == 201
    order = order_res.json()
    assert order["status"] == "ACCEPTED"

    cash_after = client.get(f"/v1/portfolios/{portfolio_id}", headers=headers).json()["cash_balance"]
    assert cash_before == cash_after  # 미체결 상태에서는 현금이 움직이지 않는다

    cancel_res = client.post(f"/v1/orders/{order['id']}/cancel", headers=headers)
    assert cancel_res.status_code == 200
    assert cancel_res.json()["status"] == "CANCELLED"

    # 종료 상태 주문은 다시 취소할 수 없다
    second_cancel = client.post(f"/v1/orders/{order['id']}/cancel", headers=headers)
    assert second_cancel.status_code == 409


def test_cross_currency_buy_uses_seeded_fx_rate(db):
    token, portfolio_id = signup_user("usbuyer")
    instrument = seed_instrument_with_bar(db, "AAPL", "NASDAQ", "USD", close=200)
    headers = {"Authorization": f"Bearer {token}"}

    order_payload = {
        "instrument_id": str(instrument.id),
        "side": "BUY",
        "order_type": "MARKET",
        "quantity": "10",
    }
    preview = client.post(
        f"/v1/portfolios/{portfolio_id}/orders/preview", json=order_payload, headers=headers
    ).json()
    assert preview["fx_rate"] is not None
    assert preview["estimated_fillable"] is True

    order_res = client.post(
        f"/v1/portfolios/{portfolio_id}/orders", json=order_payload, headers=_idem_headers(token)
    )
    assert order_res.status_code == 201
    assert order_res.json()["status"] == "FILLED"
