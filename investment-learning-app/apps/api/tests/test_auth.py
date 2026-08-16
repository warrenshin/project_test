import uuid

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _signup_payload(email: str) -> dict:
    return {
        "email": email,
        "password": "correct-horse-battery-staple",
        "birth_date": "2000-01-01",
        "consents": [
            {"consent_type": "TERMS", "version": "v1", "agreed": True},
            {"consent_type": "PRIVACY", "version": "v1", "agreed": True},
            {"consent_type": "MARKETING", "version": "v1", "agreed": False},
        ],
    }


def test_signup_login_refresh_cycle():
    email = f"user-{uuid.uuid4().hex[:12]}@example.com"

    signup_res = client.post("/v1/auth/signup", json=_signup_payload(email))
    assert signup_res.status_code == 201, signup_res.text
    tokens = signup_res.json()
    assert tokens["access_token"] and tokens["refresh_token"]

    # 이미 가입된 이메일은 거부
    dup_res = client.post("/v1/auth/signup", json=_signup_payload(email))
    assert dup_res.status_code == 409

    login_res = client.post(
        "/v1/auth/login", json={"email": email, "password": "correct-horse-battery-staple"}
    )
    assert login_res.status_code == 200
    login_tokens = login_res.json()

    wrong_login_res = client.post(
        "/v1/auth/login", json={"email": email, "password": "wrong-password"}
    )
    assert wrong_login_res.status_code == 401

    refresh_res = client.post(
        "/v1/auth/refresh", json={"refresh_token": login_tokens["refresh_token"]}
    )
    assert refresh_res.status_code == 200
    refreshed_tokens = refresh_res.json()
    assert refreshed_tokens["refresh_token"] != login_tokens["refresh_token"]

    # 회전되어 폐기된 이전 refresh token 재사용은 거부되고, 새 토큰도 함께 무효화된다 (탈취 대응)
    reuse_res = client.post(
        "/v1/auth/refresh", json={"refresh_token": login_tokens["refresh_token"]}
    )
    assert reuse_res.status_code == 401

    reuse_new_res = client.post(
        "/v1/auth/refresh", json={"refresh_token": refreshed_tokens["refresh_token"]}
    )
    assert reuse_new_res.status_code == 401


def test_signup_rejects_underage():
    email = f"user-{uuid.uuid4().hex[:12]}@example.com"
    payload = _signup_payload(email)
    payload["birth_date"] = "2020-01-01"  # 6세

    res = client.post("/v1/auth/signup", json=payload)
    assert res.status_code == 422


def test_signup_rejects_missing_mandatory_consent():
    email = f"user-{uuid.uuid4().hex[:12]}@example.com"
    payload = _signup_payload(email)
    payload["consents"] = [{"consent_type": "TERMS", "version": "v1", "agreed": True}]

    res = client.post("/v1/auth/signup", json=payload)
    assert res.status_code == 422
