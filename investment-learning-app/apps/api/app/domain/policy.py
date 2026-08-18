"""비용 정책·환율. 명세서 6.7 비용, 8.1 fee_policies 참고.

비용 정책은 시장·상품·날짜별로 버전 관리하고, 체결 시점의 버전을 fills에 고정한다
(order.policy_version). FxRate는 아직 market-data-worker가 없어 seed 데이터로 대체한다
(ADR 0001 참고) — 실거래 수준 정확도가 필요하면 실시간 환율 파이프라인으로 교체해야 한다.
"""

from datetime import date, datetime

from sqlalchemy import CHAR, Date, DateTime, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class FeePolicy(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "fee_policies"
    __table_args__ = (UniqueConstraint("market", "version", name="uq_fee_policies_market_version"),)

    market: Mapped[str] = mapped_column(String(8), nullable=False)  # KR / US
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    commission_bps: Mapped[Numeric] = mapped_column(Numeric(10, 4), nullable=False)
    sell_tax_bps: Mapped[Numeric] = mapped_column(Numeric(10, 4), nullable=False, default=0)
    min_commission: Mapped[Numeric] = mapped_column(Numeric(24, 8), nullable=False, default=0)
    spread_bps: Mapped[Numeric] = mapped_column(Numeric(10, 4), nullable=False)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)


class FxRate(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "fx_rates"

    base_currency: Mapped[str] = mapped_column(CHAR(3), nullable=False)
    quote_currency: Mapped[str] = mapped_column(CHAR(3), nullable=False)
    rate: Mapped[Numeric] = mapped_column(Numeric(24, 8), nullable=False)
    spread_bps: Mapped[Numeric] = mapped_column(Numeric(10, 4), nullable=False, default=0)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
