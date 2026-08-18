import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.db import SessionLocal
from app.domain.market import Bar, Instrument
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
    db, ticker: str, exchange: str, currency: str, close: float, low: float | None = None, high: float | None = None
) -> Instrument:
    instrument = Instrument(
        ticker=ticker, exchange=exchange, currency=currency, name=ticker, is_tradable=True
    )
    db.add(instrument)
    db.flush()

    now = datetime.now(timezone.utc)
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
        as_of=now,
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
