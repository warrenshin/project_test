from fastapi import Cookie, Depends, HTTPException
from sqlalchemy.orm import Session as DbSession

from app.core.config import get_settings
from app.core.db import get_db
from app.core.security import decode_token
from app.domain.user import User

settings = get_settings()


def get_current_user(
    db: DbSession = Depends(get_db),
    access_token: str | None = Cookie(default=None, alias=settings.access_cookie_name),
) -> User:
    """HttpOnly access 쿠키로만 인증한다(2026-08 localStorage 마이그레이션).

    이전에는 Authorization: Bearer 헤더도 지원했다. 그 경로는 access token을
    응답 JSON 본문으로 돌려주던 시절의 흔적이었는데, 토큰을 더 이상 본문으로
    내려주지 않으므로(HttpOnly 쿠키로만 전달) 정당한 클라이언트가 Bearer 헤더를
    채울 방법 자체가 없다 — 즉시 완전히 제거했고 단계적 폐지 계획은 필요 없다.
    """
    if access_token is None:
        raise HTTPException(status_code=401, detail="인증이 필요합니다.")
    try:
        payload = decode_token(access_token, expected_type="access")
    except ValueError:
        raise HTTPException(status_code=401, detail="인증이 필요합니다.")

    user = db.query(User).filter(User.id == payload["sub"], User.deleted_at.is_(None)).first()
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="인증이 필요합니다.")
    return user
