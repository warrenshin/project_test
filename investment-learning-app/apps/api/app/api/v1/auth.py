"""계정·인증·동의. 명세서 6.1, 9.2 참고.

JWT access/refresh 토큰, refresh-token 회전, 다중 기기 세션(원격 로그아웃 대비 DB 기록),
약관 동의 감사로그, 만 14세 미만 가입 제한을 구현한다.
"""

import uuid
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DbSession

from app.api.v1.auth_schemas import (
    LoginRequest,
    MIN_SIGNUP_AGE_YEARS,
    RefreshRequest,
    SignupRequest,
    TokenResponse,
)
from app.core.config import get_settings
from app.core.db import get_db
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


def _issue_tokens(db: DbSession, user: User) -> TokenResponse:
    access_token = create_access_token(str(user.id))
    refresh_token, session_id = create_refresh_token(str(user.id))
    now = datetime.now(timezone.utc)
    db.add(
        UserSession(
            id=session_id,
            user_id=user.id,
            refresh_token_hash=hash_token(refresh_token),
            issued_at=now,
            expires_at=now + timedelta(days=30),
        )
    )
    db.commit()
    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


@router.post("/signup", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def signup(payload: SignupRequest, db: DbSession = Depends(get_db)):
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

    return _issue_tokens(db, user)


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: DbSession = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email, User.deleted_at.is_(None)).first()
    if user is None or user.password_hash is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="이메일 또는 비밀번호가 올바르지 않습니다.")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="비활성화된 계정입니다.")

    return _issue_tokens(db, user)


@router.post("/refresh", response_model=TokenResponse)
def refresh(payload: RefreshRequest, db: DbSession = Depends(get_db)):
    try:
        token_payload = decode_token(payload.refresh_token, expected_type="refresh")
    except ValueError:
        raise HTTPException(status_code=401, detail="유효하지 않은 refresh token입니다.")

    session_id = token_payload["jti"]
    user_session = db.query(UserSession).filter(UserSession.id == session_id).first()
    if user_session is None:
        raise HTTPException(status_code=401, detail="세션을 찾을 수 없습니다.")

    now = datetime.now(timezone.utc)
    if user_session.revoked_at is not None:
        # 이미 회전되어 폐기된 토큰의 재사용 시도: 탈취 가능성으로 보고 전체 세션을 폐기한다.
        db.query(UserSession).filter(
            UserSession.user_id == user_session.user_id, UserSession.revoked_at.is_(None)
        ).update({"revoked_at": now})
        db.commit()
        raise HTTPException(status_code=401, detail="이미 폐기된 세션입니다. 다시 로그인해주세요.")

    if user_session.expires_at < now or hash_token(payload.refresh_token) != user_session.refresh_token_hash:
        raise HTTPException(status_code=401, detail="만료되었거나 위조된 refresh token입니다.")

    user = db.query(User).filter(User.id == user_session.user_id, User.deleted_at.is_(None)).first()
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="사용할 수 없는 계정입니다.")

    new_access_token = create_access_token(str(user.id))
    new_refresh_token, new_session_id = create_refresh_token(str(user.id))
    db.add(
        UserSession(
            id=new_session_id,
            user_id=user.id,
            device_id=user_session.device_id,
            refresh_token_hash=hash_token(new_refresh_token),
            issued_at=now,
            expires_at=now + timedelta(days=30),
        )
    )
    user_session.revoked_at = now
    user_session.replaced_by_session_id = new_session_id
    db.commit()

    return TokenResponse(access_token=new_access_token, refresh_token=new_refresh_token)
