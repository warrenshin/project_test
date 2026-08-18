from tests.conftest import client


def test_search_by_ticker_and_name():
    by_ticker = client.get("/v1/instruments/search", params={"q": "005930"})
    assert by_ticker.status_code == 200
    tickers = [i["ticker"] for i in by_ticker.json()]
    assert "005930" in tickers

    by_name = client.get("/v1/instruments/search", params={"q": "삼성전자"})
    assert by_name.status_code == 200
    assert any(i["ticker"] == "005930" for i in by_name.json())


def test_search_filters_by_exchange():
    res = client.get("/v1/instruments/search", params={"q": "", "exchange": "NASDAQ"})
    assert res.status_code == 200
    assert all(i["exchange"] == "NASDAQ" for i in res.json())
    tickers = {i["ticker"] for i in res.json()}
    assert "AAPL" in tickers
    assert "005930" not in tickers


def test_instrument_detail_includes_price_and_source():
    search_res = client.get("/v1/instruments/search", params={"q": "AAPL"}).json()
    instrument_id = search_res[0]["id"]

    detail = client.get(f"/v1/instruments/{instrument_id}").json()
    assert detail["ticker"] == "AAPL"
    assert detail["last_price"] is not None
    assert detail["price_source"] == "seed-sample"
    assert detail["price_as_of"] is not None
    assert detail["delay_seconds"] is not None


def test_instrument_bars_are_chronological():
    search_res = client.get("/v1/instruments/search", params={"q": "MSFT"}).json()
    instrument_id = search_res[0]["id"]

    bars = client.get(f"/v1/instruments/{instrument_id}/bars").json()
    assert len(bars) >= 5
    starts = [b["bar_start"] for b in bars]
    assert starts == sorted(starts)  # 오름차순(과거 -> 최신)으로 반환되어야 한다
    for bar in bars:
        assert bar["low"] <= bar["open"] <= bar["high"]
        assert bar["low"] <= bar["close"] <= bar["high"]


def test_instrument_not_found():
    res = client.get("/v1/instruments/00000000-0000-0000-0000-000000000000")
    assert res.status_code == 404
