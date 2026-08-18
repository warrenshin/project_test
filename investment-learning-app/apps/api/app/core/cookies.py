"""HttpOnly 인증 쿠키 설정/삭제 헬퍼.

access/refresh 토큰을 JSON 응답 본문이 아니라 Set-Cookie로만 전달한다(2026-08
localStorage -> HttpOnly 쿠키 마이그레이션). 쿠키 속성은 app.core.config.Settings에서
관리하며, 삭제 시에는 설정할 때와 정확히 동일한 속성(path/domain/samesite/secure)을
써야 브라우저가 실제로 쿠키를 지운다 — 속성이 조금이라도 다르면 별개의 쿠키로 취급되어
기존 쿠키가 남는다.
"""

from fastapi import Response

from app.core.config import get_settings

settings = get_settings()


def set_auth_cookies(response: Response, access_token: str, refresh_token: str) -> None:
    response.set_cookie(
        key=settings.access_cookie_name,
        value=access_token,
        max_age=settings.access_token_expire_minutes * 60,
        path=settings.access_cookie_path,
        domain=settings.cookie_domain,
        secure=settings.cookie_secure,
        httponly=True,
        samesite=settings.cookie_samesite,
    )
    response.set_cookie(
        key=settings.refresh_cookie_name,
        value=refresh_token,
        max_age=settings.refresh_token_expire_days * 24 * 60 * 60,
        path=settings.refresh_cookie_path,
        domain=settings.cookie_domain,
        secure=settings.cookie_secure,
        httponly=True,
        samesite=settings.cookie_samesite,
    )


def clear_auth_cookies(response: Response) -> None:
    response.delete_cookie(
        key=settings.access_cookie_name,
        path=settings.access_cookie_path,
        domain=settings.cookie_domain,
        secure=settings.cookie_secure,
        httponly=True,
        samesite=settings.cookie_samesite,
    )
    response.delete_cookie(
        key=settings.refresh_cookie_name,
        path=settings.refresh_cookie_path,
        domain=settings.cookie_domain,
        secure=settings.cookie_secure,
        httponly=True,
        samesite=settings.cookie_samesite,
    )
