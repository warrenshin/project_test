"""시장 데이터 도메인 모델. 명세서 6.4, 8.1 참고.

공급자 티커와 내부 instrument_id를 분리하고, 모든 가격에 as_of/source/delay_seconds를
저장한다는 원칙(6.4)을 반영한다.
"""

from datetime import date, datetime

from sqlalchemy import CHAR, Date, DateTime, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Instrument(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """ticker+exchange에 DB unique 제약을 걸지 않는다: 심볼이 재사용될 수 있어(8.3),
    상장폐지 후 같은 티커가 다른 종목에 배정될 수 있다. "현재 유효한" 종목 조회는
    valid_to IS NULL 조건으로 애플리케이션에서 판단한다 (services/market_data.py)."""

    __tablename__ = "instruments"

    ticker: Mapped[str] = mapped_column(String(32), nullable=False)
    exchange: Mapped[str] = mapped_column(String(16), nullable=False)
    currency: Mapped[str] = mapped_column(CHAR(3), nullable=False)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    industry: Mapped[str | None] = mapped_column(String(128), nullable=True)
    is_tradable: Mapped[bool] = mapped_column(default=True)
    # 심볼 재사용 대비: 유효기간을 명시한다 (8.3)
    valid_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    valid_to: Mapped[date | None] = mapped_column(Date, nullable=True)


class Bar(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "bars"
    __table_args__ = (
        UniqueConstraint("instrument_id", "interval", "bar_start", name="uq_bars_instrument_interval_start"),
    )

    instrument_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True), ForeignKey("instruments.id"), nullable=False
    )
    interval: Mapped[str] = mapped_column(String(8), nullable=False)  # 1d, 1m 등
    open: Mapped[Numeric] = mapped_column(Numeric(24, 8), nullable=False)
    high: Mapped[Numeric] = mapped_column(Numeric(24, 8), nullable=False)
    low: Mapped[Numeric] = mapped_column(Numeric(24, 8), nullable=False)
    close: Mapped[Numeric] = mapped_column(Numeric(24, 8), nullable=False)
    volume: Mapped[Numeric] = mapped_column(Numeric(24, 8), nullable=False)
    bar_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    delay_seconds: Mapped[int] = mapped_column(nullable=False, default=0)
