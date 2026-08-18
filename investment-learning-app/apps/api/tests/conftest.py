import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.core.db import SessionLocal
from app.domain.market import Bar, Instrument
from app.main import app

client = TestClient(app)


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


def signup_user(email_prefix: str = "trader") -> tuple[str, str]:
    """회원가입 후 (access_token, portfolio_id)를 반환한다."""
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
    access_token = signup_res.json()["access_token"]

    portfolio_res = client.get("/v1/me/portfolio", headers={"Authorization": f"Bearer {access_token}"})
    assert portfolio_res.status_code == 200, portfolio_res.text
    portfolio_id = portfolio_res.json()["id"]

    return access_token, portfolio_id
