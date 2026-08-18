from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session as DbSession

from app.core.db import get_db
from app.core.security import decode_token
from app.domain.user import User

_bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    db: DbSession = Depends(get_db),
) -> User:
    if credentials is None:
        raise HTTPException(status_code=401, detail="인증이 필요합니다.")
    try:
        payload = decode_token(credentials.credentials, expected_type="access")
    except ValueError:
        raise HTTPException(status_code=401, detail="유효하지 않은 access token입니다.")

    user = db.query(User).filter(User.id == payload["sub"], User.deleted_at.is_(None)).first()
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="사용할 수 없는 계정입니다.")
    return user
