import uuid

from tests.conftest import client


def _signup_payload(email: str) -> dict:
    return {
        "email": email,
        "password": "correct-horse-battery-staple",
        "birth_date": "2000-01-01",
        "consents": [
            {"consent_type": "TERMS", "version": "v1", "agreed": True},
            {"consent_type": "PRIVACY", "version": "v1", "agreed": False},
            {"consent_type": "MARKETING", "version": "v1", "agreed": False},
        ],
    }


def _new_email() -> str:
    return f"user-{uuid.uuid4().hex[:12]}@example.com"


def test_signup_login_refresh_cycle():
    email = _new_email()
    payload = _signup_payload(email)
    payload["consents"][1]["agreed"] = True  # PRIVACY 필수 동의

    signup_res = client.post("/v1/auth/signup", json=payload)
    assert signup_res.status_code == 201, signup_res.text

    # 응답 JSON에는 절대 토큰이 없어야 한다 — HttpOnly Set-Cookie로만 전달된다.
    body = signup_res.json()
    assert "access_token" not in body and "refresh_token" not in body
    assert body["email"] == email

    auth_cookies = dict(signup_res.cookies)
    assert _access_cookie_name() in auth_cookies
    assert _refresh_cookie_name() in auth_cookies
    client.cookies.clear()

    # 이미 가입된 이메일은 거부
    dup_res = client.post("/v1/auth/signup", json=payload)
    assert dup_res.status_code == 409

    login_res = client.post("/v1/auth/login", json={"email": email, "password": "correct-horse-battery-staple"})
    assert login_res.status_code == 200
    assert "access_token" not in login_res.json() and "refresh_token" not in login_res.json()
    login_cookies = dict(login_res.cookies)
    client.cookies.clear()

    wrong_login_res = client.post("/v1/auth/login", json={"email": email, "password": "wrong-password"})
    assert wrong_login_res.status_code == 401

    refresh_res = client.post("/v1/auth/refresh", cookies=login_cookies)
    assert refresh_res.status_code == 204
    assert refresh_res.content == b""  # 본문에 아무 것도(토큰 포함) 담지 않는다
    refreshed_cookies = dict(refresh_res.cookies)
    client.cookies.clear()

    # refresh token은 회전된다 — 새 값이 이전 값과 달라야 한다. access token은
    # 같은 초에 재발급되면 (iat/exp가 초 단위라) 값이 우연히 같을 수 있어
    # 여기서는 비교하지 않는다 — 실제 보안 속성은 refresh token 회전이다.
    assert refreshed_cookies[_refresh_cookie_name()] != login_cookies[_refresh_cookie_name()]

    # 회전되어 폐기된 이전 refresh token 재사용은 거부되고, 새 토큰도 함께 무효화된다 (탈취 대응)
    reuse_res = client.post("/v1/auth/refresh", cookies=login_cookies)
    assert reuse_res.status_code == 401
    client.cookies.clear()

    reuse_new_res = client.post("/v1/auth/refresh", cookies=refreshed_cookies)
    assert reuse_new_res.status_code == 401
    client.cookies.clear()


def test_signup_rejects_underage():
    email = _new_email()
    payload = _signup_payload(email)
    payload["consents"][1]["agreed"] = True
    payload["birth_date"] = "2020-01-01"  # 6세

    res = client.post("/v1/auth/signup", json=payload)
    assert res.status_code == 422


def test_signup_rejects_missing_mandatory_consent():
    email = _new_email()
    payload = _signup_payload(email)
    payload["consents"] = [{"consent_type": "TERMS", "version": "v1", "agreed": True}]

    res = client.post("/v1/auth/signup", json=payload)
    assert res.status_code == 422


# --- HttpOnly 쿠키 인증 보안 테스트 (2026-08 localStorage -> 쿠키 마이그레이션) ---


def _signup_and_get_cookies(prefix: str) -> dict:
    email = f"{prefix}-{uuid.uuid4().hex[:12]}@example.com"
    payload = _signup_payload(email)
    payload["consents"][1]["agreed"] = True
    res = client.post("/v1/auth/signup", json=payload)
    assert res.status_code == 201, res.text
    cookies = dict(res.cookies)
    client.cookies.clear()
    return cookies


def _access_cookie_name() -> str:
    from app.core.config import get_settings

    return get_settings().access_cookie_name


def _refresh_cookie_name() -> str:
    from app.core.config import get_settings

    return get_settings().refresh_cookie_name


def test_login_response_sets_httponly_cookies():
    from app.core.config import get_settings

    settings = get_settings()
    email = _new_email()
    payload = _signup_payload(email)
    payload["consents"][1]["agreed"] = True
    client.post("/v1/auth/signup", json=payload)
    client.cookies.clear()

    res = client.post("/v1/auth/login", json={"email": email, "password": "correct-horse-battery-staple"})
    assert res.status_code == 200
    client.cookies.clear()

    set_cookie_headers = res.headers.get_list("set-cookie")
    access_header = next(h for h in set_cookie_headers if h.startswith(f"{settings.access_cookie_name}="))
    refresh_header = next(h for h in set_cookie_headers if h.startswith(f"{settings.refresh_cookie_name}="))
    assert "HttpOnly" in access_header
    assert "HttpOnly" in refresh_header
    # 개발 기본 설정(SameSite=Lax)이 실려 있는지도 함께 확인한다
    assert "samesite=lax" in access_header.lower()


def test_production_cookie_policy_requires_secure_and_valid_secret():
    from pydantic import ValidationError

    from app.core.config import Settings

    # production인데 Secure=false(개발 기본값 그대로)면 기동 자체를 막는다
    try:
        Settings(environment="production", cookie_secure=False, jwt_secret="a-real-secret")
        assert False, "production + cookie_secure=False는 반드시 실패해야 한다"
    except ValidationError as exc:
        assert "COOKIE_SECURE" in str(exc)

    # production인데 JWT_SECRET을 안 바꿨으면 그것도 막는다
    try:
        Settings(environment="production", cookie_secure=True, jwt_secret="change-me-in-env")
        assert False, "production + 기본 JWT_SECRET은 반드시 실패해야 한다"
    except ValidationError as exc:
        assert "JWT_SECRET" in str(exc)

    # 안전하게 채워졌다면 정상 기동된다
    prod_settings = Settings(environment="production", cookie_secure=True, jwt_secret="a-real-secret")
    assert prod_settings.cookie_secure is True


def test_production_cookies_carry_secure_flag():
    from fastapi import Response

    from app.core.config import Settings
    from app.core.cookies import set_auth_cookies

    prod_settings = Settings(environment="production", cookie_secure=True, jwt_secret="a-real-secret")

    import app.core.cookies as cookies_module

    original_settings = cookies_module.settings
    cookies_module.settings = prod_settings
    try:
        response = Response()
        set_auth_cookies(response, "fake-access", "fake-refresh")
        set_cookie_headers = response.headers.getlist("set-cookie")
    finally:
        cookies_module.settings = original_settings

    assert all("Secure" in h for h in set_cookie_headers)
    assert all("HttpOnly" in h for h in set_cookie_headers)


def test_no_tokens_in_any_auth_response_body():
    email = _new_email()
    payload = _signup_payload(email)
    payload["consents"][1]["agreed"] = True

    signup_res = client.post("/v1/auth/signup", json=payload)
    cookies = dict(signup_res.cookies)
    client.cookies.clear()
    assert "access_token" not in signup_res.text and "refresh_token" not in signup_res.text

    login_res = client.post("/v1/auth/login", json={"email": email, "password": "correct-horse-battery-staple"})
    login_cookies = dict(login_res.cookies)
    client.cookies.clear()
    assert "access_token" not in login_res.text and "refresh_token" not in login_res.text

    refresh_res = client.post("/v1/auth/refresh", cookies=login_cookies)
    client.cookies.clear()
    assert refresh_res.content == b""

    me_res = client.get("/v1/auth/me", cookies=cookies)
    assert "access_token" not in me_res.text and "refresh_token" not in me_res.text


def test_protected_api_without_cookie_returns_401():
    res = client.get("/v1/auth/me")
    assert res.status_code == 401
    res2 = client.get("/v1/me/portfolio")
    assert res2.status_code == 401


def test_valid_cookie_accesses_own_data():
    cookies = _signup_and_get_cookies("cookieowner")
    res = client.get("/v1/auth/me", cookies=cookies)
    assert res.status_code == 200
    assert "@" in res.json()["email"]

    portfolio_res = client.get("/v1/me/portfolio", cookies=cookies)
    assert portfolio_res.status_code == 200


def test_bearer_header_no_longer_authenticates():
    """예전 Authorization: Bearer 방식은 완전히 제거됐다 — 토큰을 응답 본문으로
    내려주지 않으므로 정당한 클라이언트가 Bearer 헤더를 채울 방법 자체가 없다."""
    res = client.get("/v1/auth/me", headers={"Authorization": "Bearer some-forged-or-copied-value"})
    assert res.status_code == 401


def test_logout_revokes_session_and_clears_cookies():
    """로그아웃은 (1) 서버의 refresh 세션을 즉시 폐기하고 (2) 브라우저의 쿠키를
    지우는 Set-Cookie를 내려준다. 실제 브라우저는 이 응답을 받는 순간 쿠키를
    비우므로 다음 요청부터는 쿠키 자체가 없어 401이 된다(이 흐름은 Playwright
    E2E에서 검증한다).

    알려진 제한사항: access token은 상태를 갖지 않는(stateless) 단기 JWT라서,
    로그아웃 이전에 이미 발급된 access token 원문을 그대로 복사해 재사용하면
    자연 만료 시각(기본 30분)까지는 서명 검증을 통과한다 — 이는 짧은 수명 +
    refresh 회전이라는 표준적인 JWT 설계의 알려진 트레이드오프이며, 매 요청마다
    DB를 조회하는 방식으로 바꾸지 않는 한(이번 범위 밖의 구조 변경) 피할 수 없다.
    refresh token은 그렇지 않다 — 아래에서 즉시 폐기됨을 검증한다.
    """
    cookies = _signup_and_get_cookies("logoutuser")

    ok_res = client.get("/v1/auth/me", cookies=cookies)
    assert ok_res.status_code == 200

    logout_res = client.post("/v1/auth/logout", cookies=cookies)
    assert logout_res.status_code == 204
    set_cookie_headers = logout_res.headers.get_list("set-cookie")
    # 삭제 쿠키는 설정할 때와 동일한 속성(path/samesite)으로 만료시켜야 브라우저가 실제로 지운다
    assert any(
        h.startswith(f"{_access_cookie_name()}=") and ("Max-Age=0" in h or "expired" in h.lower())
        for h in set_cookie_headers
    )
    assert any(
        h.startswith(f"{_refresh_cookie_name()}=") and ("Max-Age=0" in h or "expired" in h.lower())
        for h in set_cookie_headers
    )
    client.cookies.clear()

    # 서버 refresh 세션은 즉시 폐기된다 — 같은 refresh token으로는 더 이상 갱신할 수 없다
    refresh_after_logout = client.post("/v1/auth/refresh", cookies=cookies)
    assert refresh_after_logout.status_code == 401


def test_logout_is_idempotent_without_cookies():
    res = client.post("/v1/auth/logout")
    assert res.status_code == 204


def test_expired_access_token_refreshes_and_regains_access():
    from datetime import datetime, timedelta, timezone

    from jose import jwt

    from app.core.config import get_settings

    settings = get_settings()
    cookies = _signup_and_get_cookies("expiredaccess")

    # 만료된 access token을 직접 만들어 흉내낸다(30분 기다리지 않고 재현)
    expired_payload = {
        "sub": jwt.get_unverified_claims(cookies[settings.access_cookie_name])["sub"],
        "type": "access",
        "iat": datetime.now(timezone.utc) - timedelta(minutes=60),
        "exp": datetime.now(timezone.utc) - timedelta(minutes=30),
    }
    expired_access = jwt.encode(expired_payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    stale_cookies = {**cookies, settings.access_cookie_name: expired_access}

    denied = client.get("/v1/auth/me", cookies=stale_cookies)
    assert denied.status_code == 401

    # refresh token은 그대로 유효하므로 refresh 후 재시도하면 성공해야 한다
    refresh_res = client.post("/v1/auth/refresh", cookies=stale_cookies)
    assert refresh_res.status_code == 204
    new_cookies = dict(refresh_res.cookies)
    client.cookies.clear()

    retried = client.get("/v1/auth/me", cookies=new_cookies)
    assert retried.status_code == 200


# --- CSRF Origin 검증 ---


def test_state_changing_request_with_disallowed_origin_is_rejected():
    res = client.post(
        "/v1/auth/login",
        json={"email": "nobody@example.com", "password": "whatever"},
        headers={"Origin": "https://evil.example.com"},
    )
    assert res.status_code == 403


def test_state_changing_request_missing_origin_header_is_rejected():
    from fastapi.testclient import TestClient

    from app.main import app

    # conftest의 공유 client는 기본 Origin 헤더를 갖고 있으므로, 이 테스트만 Origin이
    # 전혀 없는 별도 TestClient로 직접 호출한다.
    bare_client = TestClient(app)
    res = bare_client.post("/v1/auth/login", json={"email": "nobody@example.com", "password": "whatever"})
    assert res.status_code == 403


def test_state_changing_request_with_allowed_origin_succeeds():
    from app.core.config import get_settings

    email = _new_email()
    payload = _signup_payload(email)
    payload["consents"][1]["agreed"] = True

    res = client.post(
        "/v1/auth/signup", json=payload, headers={"Origin": get_settings().cors_allowed_origins[0]}
    )
    assert res.status_code == 201
    client.cookies.clear()


def test_get_request_ignores_origin_check():
    res = client.get("/v1/auth/me", headers={"Origin": "https://evil.example.com"})
    # 인증이 없어 401이지 Origin 때문에 403이 되어서는 안 된다 — GET은 CSRF 검사 대상이 아니다
    assert res.status_code == 401
