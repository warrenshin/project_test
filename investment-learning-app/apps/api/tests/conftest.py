import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.db import SessionLocal
from app.domain.market import Bar, Instrument
from app.domain.services.market_data import upsert_instrument
from app.main import app

settings = get_settings()

# CSRF Origin 검증 미들웨어(app.core.csrf)를 통과하려면 상태 변경 요청(POST 등)에
# 허용된 Origin이 실려 있어야 한다. 모든 테스트가 이 client를 공유하므로 기본
# 헤더로 한 번만 설정한다(개별 테스트에서 매번 넣지 않아도 됨). CSRF 거부 자체를
# 검증하는 테스트는 이 기본값을 오버라이드해서 다른/누락된 Origin으로 호출한다.
client = TestClient(app, headers={"Origin": settings.cors_allowed_origins[0]})


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def seed_instrument_with_bar(
    db,
    ticker: str,
    exchange: str,
    currency: str,
    close: float,
    low: float | None = None,
    high: float | None = None,
    as_of: datetime | None = None,
) -> Instrument:
    """as_of를 명시하면 그 시각의 bar를 만든다 — 오래된(stale) 시세 시나리오를
    테스트할 때 쓴다(예: `datetime.now(timezone.utc) - timedelta(hours=1)`).

    upsert_instrument를 통해 만든다(직접 Instrument(...)를 생성하지 않는다) —
    같은 (ticker, exchange)로 이미 활성 종목이 있으면(예: 다른 테스트가 먼저
    만든 경우) 새로 만들지 않고 그 종목을 재사용한다. instruments에는
    (exchange, ticker) partial unique index가 있어, 매번 새로 INSERT하면
    두 번째 호출부터 제약 위반으로 실패한다."""
    instrument = upsert_instrument(db, ticker, exchange, currency, name=ticker)
    db.flush()

    # upsert_instrument는 (exchange, ticker)로 기존 활성 종목을 재사용하지만,
    # Bar는 그런 dedup이 없어 이 헬퍼를 여러 번(다른 프로세스 실행에서 DB를
    # 초기화하지 않고 재호출 등) 부르면 같은 instrument에 bar가 계속 쌓인다.
    # 그러면 테스트가 "방금 만든 그 bar"를 가정하고 `db.query(Bar)...first()`로
    # ORDER BY 없이 집는 순간, 실제 코드 경로(get_latest_bar, bar_start desc)가
    # 쓰는 bar와 테스트가 집은 bar가 서로 달라져 재현 불가능한 실패로 이어진다
    # (이 저장소에서 실제로 관찰된 flaky 원인). 항상 이 instrument+interval에는
    # bar가 정확히 하나만 있도록 기존 것을 지우고 새로 만든다.
    db.query(Bar).filter(Bar.instrument_id == instrument.id, Bar.interval == "1d").delete()

    now = datetime.now(timezone.utc)
    bar_as_of = as_of if as_of is not None else now
    bar = Bar(
        instrument_id=instrument.id,
        interval="1d",
        open=close,
        high=high if high is not None else close,
        low=low if low is not None else close,
        close=close,
        volume=100_000,
        bar_start=now,
        source="test-seed",
        as_of=bar_as_of,
        delay_seconds=0,
    )
    db.add(bar)
    db.commit()
    db.refresh(instrument)
    return instrument


def signup_user(email_prefix: str = "trader") -> tuple[dict, str]:
    """회원가입 후 (auth_cookies, portfolio_id)를 반환한다.

    2026-08 HttpOnly 쿠키 마이그레이션 이후 access/refresh token은 응답 JSON
    본문에 없다 — Set-Cookie로만 내려온다. 여러 사용자를 한 테스트에서 동시에
    다뤄야 하므로(IDOR 테스트 등), 공유 TestClient의 전역 쿠키jar에 맡기지 않고
    각 사용자의 쿠키를 dict로 뽑아 호출마다 명시적으로 cookies=...로 전달한다.
    signup 직후 공유 client의 쿠키jar는 즉시 비워 다음 테스트/사용자로 새지
    않게 한다.
    """
    email = f"{email_prefix}-{uuid.uuid4().hex[:12]}@example.com"
    signup_res = client.post(
        "/v1/auth/signup",
        json={
            "email": email,
            "password": "correct-horse-battery-staple",
            "birth_date": "2000-01-01",
            "consents": [
                {"consent_type": "TERMS", "version": "v1", "agreed": True},
                {"consent_type": "PRIVACY", "version": "v1", "agreed": True},
            ],
        },
    )
    assert signup_res.status_code == 201, signup_res.text
    assert "access_token" not in signup_res.json() and "refresh_token" not in signup_res.json()
    auth_cookies = dict(signup_res.cookies)
    client.cookies.clear()

    portfolio_res = client.get("/v1/me/portfolio", cookies=auth_cookies)
    assert portfolio_res.status_code == 200, portfolio_res.text
    portfolio_id = portfolio_res.json()["id"]

    return auth_cookies, portfolio_id
