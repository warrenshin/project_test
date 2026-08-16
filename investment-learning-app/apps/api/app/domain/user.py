"""계정·인증·동의 도메인 모델. 명세서 6.1, 8.1 참고.

- refresh-token 회전과 다중 기기 세션·원격 로그아웃을 지원하기 위해
  세션을 DB에 기록한다 (평문 토큰이 아닌 해시만 저장).
- 약관 버전과 동의시각은 Consent에 감사로그로 보존한다.
- 만 14세 미만 가입 제한(6.1 기본값)을 검증할 수 있도록 생년월일을 둔다.
"""

from datetime import date, datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class User(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    password_hash: Mapped[str | None] = mapped_column(String(256), nullable=True)
    auth_provider: Mapped[str] = mapped_column(String(16), nullable=False, default="EMAIL")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Profile(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "profiles"

    user_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), unique=True, nullable=False
    )
    display_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    birth_date: Mapped[date | None] = mapped_column(nullable=True)
    experience_level: Mapped[str | None] = mapped_column(String(16), nullable=True)
    interested_markets: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    interested_topics: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    daily_study_minutes: Mapped[int | None] = mapped_column(nullable=True)
    base_currency: Mapped[str] = mapped_column(String(3), nullable=False, default="KRW")
    locale: Mapped[str] = mapped_column(String(8), nullable=False, default="ko-KR")
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="Asia/Seoul")


class Consent(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "consents"

    user_id: Mapped[str] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    consent_type: Mapped[str] = mapped_column(String(32), nullable=False)  # TERMS/PRIVACY/MARKETING
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    agreed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    agreed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class Device(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "devices"

    user_id: Mapped[str] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    device_id: Mapped[str] = mapped_column(String(128), nullable=False)
    platform: Mapped[str | None] = mapped_column(String(16), nullable=True)
    push_token: Mapped[str | None] = mapped_column(String(256), nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Session(Base, UUIDPrimaryKeyMixin):
    """refresh-token 세션. 원격 로그아웃과 회전 이력을 위해 평문 대신 해시를 저장한다."""

    __tablename__ = "sessions"

    user_id: Mapped[str] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    device_id: Mapped[str | None] = mapped_column(UUID(as_uuid=True), ForeignKey("devices.id"), nullable=True)
    refresh_token_hash: Mapped[str] = mapped_column(String(256), nullable=False, unique=True)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    replaced_by_session_id: Mapped[str | None] = mapped_column(UUID(as_uuid=True), nullable=True)
