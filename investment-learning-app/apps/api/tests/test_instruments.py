import uuid

from app.core.db import SessionLocal
from app.domain.services.market_data import upsert_instrument
from tests.conftest import client


def _seed_search_group(tag: str, specs: list[tuple[str, str, str]]) -> None:
    """(ticker, exchange, name) 목록을 만든다. 각 테스트가 고유한 tag로 만든
    ticker만 쓰므로, 다른 테스트나 시드 데이터와 검색 결과가 섞이지 않는다."""
    db = SessionLocal()
    try:
        for ticker, exchange, name in specs:
            upsert_instrument(db, ticker, exchange, "USD", name)
        db.commit()
    finally:
        db.close()


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


# --- 검색 결과 정렬의 결정론성 (item 7) ---


def test_search_ranks_exact_ticker_match_above_prefix_and_name_match():
    tag = uuid.uuid4().hex[:8].upper()
    exact = f"{tag}A"
    prefix_only = f"{tag}AX"
    name_only_ticker = f"{tag}ZZZ"
    _seed_search_group(
        tag,
        [
            (prefix_only, "NASDAQ", f"Prefix Co {tag}"),
            (name_only_ticker, "NASDAQ", f"{exact} Holdings {tag}"),
            (exact, "NASDAQ", f"Exact Co {tag}"),
        ],
    )

    res = client.get("/v1/instruments/search", params={"q": exact})
    assert res.status_code == 200
    tickers = [i["ticker"] for i in res.json()]
    # 정확히 일치 > prefix 일치 > 이름에만 등장 순으로 나와야 한다.
    assert tickers.index(exact) < tickers.index(prefix_only)
    assert tickers.index(prefix_only) < tickers.index(name_only_ticker)


def test_search_is_case_insensitive():
    tag = uuid.uuid4().hex[:8].upper()
    ticker = f"{tag}CASE"
    _seed_search_group(tag, [(ticker, "NASDAQ", f"Case Co {tag}")])

    res = client.get("/v1/instruments/search", params={"q": ticker.lower()})
    assert res.status_code == 200
    assert any(i["ticker"] == ticker for i in res.json())


def test_search_query_with_surrounding_whitespace_still_matches():
    tag = uuid.uuid4().hex[:8].upper()
    ticker = f"{tag}WS"
    _seed_search_group(tag, [(ticker, "NASDAQ", f"Whitespace Co {tag}")])

    res = client.get("/v1/instruments/search", params={"q": f"  {ticker}  "})
    assert res.status_code == 200
    assert any(i["ticker"] == ticker for i in res.json())


def test_search_breaks_ties_deterministically_by_exchange_then_ticker_then_id():
    tag = uuid.uuid4().hex[:8].upper()
    shared_name = f"Same Name Co {tag}"
    # 셋 다 이름만 일치(같은 순위)하므로 exchange -> ticker -> id 순으로만
    # 정렬되어야 한다.
    specs = [
        (f"{tag}C", "NYSE", shared_name),
        (f"{tag}B", "NASDAQ", shared_name),
        (f"{tag}A", "NASDAQ", shared_name),
    ]
    _seed_search_group(tag, specs)

    res = client.get("/v1/instruments/search", params={"q": tag})
    assert res.status_code == 200
    rows = [(i["exchange"], i["ticker"]) for i in res.json()]
    assert rows == [("NASDAQ", f"{tag}A"), ("NASDAQ", f"{tag}B"), ("NYSE", f"{tag}C")]


def test_search_returns_same_order_across_repeated_calls():
    tag = uuid.uuid4().hex[:8].upper()
    shared_name = f"Repeat Co {tag}"
    _seed_search_group(
        tag,
        [
            (f"{tag}C", "NYSE", shared_name),
            (f"{tag}B", "NASDAQ", shared_name),
            (f"{tag}A", "NASDAQ", shared_name),
        ],
    )

    first = client.get("/v1/instruments/search", params={"q": tag}).json()
    second = client.get("/v1/instruments/search", params={"q": tag}).json()
    third = client.get("/v1/instruments/search", params={"q": tag}).json()
    assert [i["id"] for i in first] == [i["id"] for i in second] == [i["id"] for i in third]
