"""비밀번호 해싱과 JWT 발급·검증. 명세서 6.1, 12.1 참고.

- 비밀번호는 Argon2id로 해싱한다 (12.1).
- access token은 짧은 수명의 JWT, refresh token은 별도 수명의 JWT로 발급하고
  DB의 세션 레코드(app.domain.user.Session)와 대조해 회전·폐기를 관리한다.
"""

import hashlib
import uuid
from datetime import datetime, timedelta, timezone
from typing import Literal

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import get_settings

_pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")

settings = get_settings()


def hash_password(password: str) -> str:
    return _pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return _pwd_context.verify(password, password_hash)


def hash_token(token: str) -> str:
    """refresh token 원문을 DB에 저장하지 않기 위한 조회용 해시(무결성 대조용)."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_access_token(user_id: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "type": "access",
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_expire_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_refresh_token(user_id: str, session_id: str | None = None) -> tuple[str, str]:
    """(token, session_id) 반환. session_id는 세션 회전·폐기 조회에 사용한다."""
    session_id = session_id or str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "type": "refresh",
        "jti": session_id,
        "iat": now,
        "exp": now + timedelta(days=settings.refresh_token_expire_days),
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return token, session_id


def decode_token(token: str, expected_type: Literal["access", "refresh"]) -> dict:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except JWTError as exc:
        raise ValueError("invalid_token") from exc
    if payload.get("type") != expected_type:
        raise ValueError("unexpected_token_type")
    return payload
