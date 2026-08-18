"""계정·인증·동의. 명세서 6.1, 9.2 참고.

JWT access/refresh 토큰, refresh-token 회전, 다중 기기 세션(원격 로그아웃 대비 DB 기록),
약관 동의 감사로그, 만 14세 미만 가입 제한을 구현한다.

2026-08: 토큰을 응답 JSON 본문으로 내려주던 방식에서 HttpOnly Secure 쿠키로
전환했다(localStorage/JS가 토큰을 읽을 수 있으면 XSS 한 번으로 계정을 통째로
탈취당할 수 있다는 것이 계기). 회전·재사용 탐지 로직 자체는 그대로이고, 토큰을
어디에 담아 보내는지만 바뀌었다.
"""

import uuid
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DbSession

from app.api.v1.auth_schemas import LoginRequest, MIN_SIGNUP_AGE_YEARS, SignupRequest, UserResponse
from app.core.config import get_settings
from app.core.cookies import clear_auth_cookies, set_auth_cookies
from app.core.db import get_db
from app.core.deps import get_current_user
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    hash_token,
    verify_password,
)
from app.domain.constants import ACCOUNT_CASH, ENTRY_INITIAL_DEPOSIT
from app.domain.portfolio import LedgerEntry, Portfolio
from app.domain.user import Consent, Profile, Session as UserSession, User

router = APIRouter()
settings = get_settings()


def _create_portfolio_with_initial_cash(db: DbSession, user: User) -> Portfolio:
    """가입 시 모의투자 포트폴리오와 최초 가상현금을 원장에 기록한다 (6.5, 8.3).

    잔고는 별도 필드가 아니라 ledger_entries에서 계산하므로, 최초 지급도 이벤트로
    남긴다.
    """
    portfolio = Portfolio(user_id=user.id, base_currency=settings.default_base_currency)
    db.add(portfolio)
    db.flush()

    db.add(
        LedgerEntry(
            portfolio_id=portfolio.id,
            event_id=uuid.uuid4(),
            account_code=ACCOUNT_CASH,
            currency=settings.default_base_currency,
            amount=settings.default_virtual_cash_krw,
            entry_type=ENTRY_INITIAL_DEPOSIT,
            occurred_at=datetime.now(timezone.utc),
        )
    )
    return portfolio


def _age_years(birth_date: date, as_of: date) -> int:
    return as_of.year - birth_date.year - ((as_of.month, as_of.day) < (birth_date.month, birth_date.day))


def _issue_tokens(db: DbSession, response: Response, user: User) -> None:
    """access/refresh 토큰을 발급해 세션을 기록하고 HttpOnly 쿠키로만 내려준다.

    응답 JSON 본문에는 토큰을 절대 포함하지 않는다 — 호출부는 이 함수 뒤에
    UserResponse 등 토큰이 없는 값만 반환해야 한다.
    """
    access_token = create_access_token(str(user.id))
    refresh_token, session_id = create_refresh_token(str(user.id))
    now = datetime.now(timezone.utc)
    db.add(
        UserSession(
            id=session_id,
            user_id=user.id,
            refresh_token_hash=hash_token(refresh_token),
            issued_at=now,
            expires_at=now + timedelta(days=settings.refresh_token_expire_days),
        )
    )
    db.commit()
    set_auth_cookies(response, access_token, refresh_token)


@router.post("/signup", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def signup(payload: SignupRequest, response: Response, db: DbSession = Depends(get_db)):
    if _age_years(payload.birth_date, datetime.now(timezone.utc).date()) < MIN_SIGNUP_AGE_YEARS:
        raise HTTPException(status_code=422, detail="만 14세 미만은 가입할 수 없습니다.")

    user = User(email=payload.email, password_hash=hash_password(payload.password))
    db.add(user)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="이미 가입된 이메일입니다.")

    db.add(Profile(user_id=user.id, birth_date=payload.birth_date, base_currency=settings.default_base_currency))
    agreed_at = datetime.now(timezone.utc)
    for consent in payload.consents:
        db.add(
            Consent(
                user_id=user.id,
                consent_type=consent.consent_type,
                version=consent.version,
                agreed=consent.agreed,
                agreed_at=agreed_at,
            )
        )
    _create_portfolio_with_initial_cash(db, user)
    db.commit()

    _issue_tokens(db, response, user)
    return UserResponse(id=user.id, email=user.email)


@router.post("/login", response_model=UserResponse)
def login(payload: LoginRequest, response: Response, db: DbSession = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email, User.deleted_at.is_(None)).first()
    if user is None or user.password_hash is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="이메일 또는 비밀번호가 올바르지 않습니다.")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="비활성화된 계정입니다.")

    _issue_tokens(db, response, user)
    return UserResponse(id=user.id, email=user.email)


@router.get("/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user)):
    """현재 인증 상태 확인용. 프런트엔드가 마운트 시 이 엔드포인트로만 로그인 여부를 판단한다."""
    return UserResponse(id=current_user.id, email=current_user.email)


@router.post("/refresh", status_code=status.HTTP_204_NO_CONTENT)
def refresh(
    response: Response,
    db: DbSession = Depends(get_db),
    refresh_token: str | None = Cookie(default=None, alias=settings.refresh_cookie_name),
):
    if refresh_token is None:
        raise HTTPException(status_code=401, detail="인증이 필요합니다.")
    try:
        token_payload = decode_token(refresh_token, expected_type="refresh")
    except ValueError:
        raise HTTPException(status_code=401, detail="인증이 필요합니다.")

    session_id = token_payload["jti"]
    user_session = db.query(UserSession).filter(UserSession.id == session_id).first()
    if user_session is None:
        raise HTTPException(status_code=401, detail="인증이 필요합니다.")

    now = datetime.now(timezone.utc)
    if user_session.revoked_at is not None:
        # 이미 회전되어 폐기된 토큰의 재사용 시도: 탈취 가능성으로 보고 전체 세션을 폐기한다.
        db.query(UserSession).filter(
            UserSession.user_id == user_session.user_id, UserSession.revoked_at.is_(None)
        ).update({"revoked_at": now})
        db.commit()
        clear_auth_cookies(response)
        raise HTTPException(status_code=401, detail="인증이 필요합니다.")

    if user_session.expires_at < now or hash_token(refresh_token) != user_session.refresh_token_hash:
        clear_auth_cookies(response)
        raise HTTPException(status_code=401, detail="인증이 필요합니다.")

    user = db.query(User).filter(User.id == user_session.user_id, User.deleted_at.is_(None)).first()
    if user is None or not user.is_active:
        clear_auth_cookies(response)
        raise HTTPException(status_code=401, detail="인증이 필요합니다.")

    new_access_token = create_access_token(str(user.id))
    new_refresh_token, new_session_id = create_refresh_token(str(user.id))
    db.add(
        UserSession(
            id=new_session_id,
            user_id=user.id,
            device_id=user_session.device_id,
            refresh_token_hash=hash_token(new_refresh_token),
            issued_at=now,
            expires_at=now + timedelta(days=settings.refresh_token_expire_days),
        )
    )
    user_session.revoked_at = now
    user_session.replaced_by_session_id = new_session_id
    db.commit()

    set_auth_cookies(response, new_access_token, new_refresh_token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    response: Response,
    db: DbSession = Depends(get_db),
    refresh_token: str | None = Cookie(default=None, alias=settings.refresh_cookie_name),
):
    """서버 세션(refresh token)을 폐기하고 인증 쿠키를 지운다.

    쿠키가 없거나 이미 무효해도 정상 종료(204)로 처리한다 — 로그아웃은 "로그인
    상태가 아니게 만드는" 멱등 연산이라 이미 그 상태여도 에러가 아니다.
    """
    if refresh_token is not None:
        try:
            token_payload = decode_token(refresh_token, expected_type="refresh")
        except ValueError:
            token_payload = None
        if token_payload is not None:
            db.query(UserSession).filter(
                UserSession.id == token_payload["jti"], UserSession.revoked_at.is_(None)
            ).update({"revoked_at": datetime.now(timezone.utc)})
            db.commit()

    clear_auth_cookies(response)
