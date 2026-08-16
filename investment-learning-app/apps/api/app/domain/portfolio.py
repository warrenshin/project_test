"""모의투자 원장 도메인 모델. 명세서 6.5-6.7, 8.2 참고.

핵심 원칙(21장 3항): 원장(ledger_entries)이 진실의 원천이며, 현재 잔고는
캐시일 뿐 ledger에서 항상 재구성 가능해야 한다. 모든 쓰기는 idempotency_key로
중복 실행을 방지한다.
"""

from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Portfolio(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "portfolios"

    user_id: Mapped[str] = mapped_column(UUID(as_uuid=True), nullable=False)
    base_currency: Mapped[str] = mapped_column(String(3), nullable=False, default="KRW")


class Order(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "orders"
    __table_args__ = (
        CheckConstraint("side IN ('BUY','SELL')", name="ck_orders_side"),
        CheckConstraint("order_type IN ('MARKET','LIMIT')", name="ck_orders_order_type"),
        CheckConstraint("quantity > 0", name="ck_orders_quantity_positive"),
        UniqueConstraint("portfolio_id", "idempotency_key", name="uq_orders_idempotency"),
    )

    portfolio_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True), ForeignKey("portfolios.id"), nullable=False
    )
    instrument_id: Mapped[str] = mapped_column(UUID(as_uuid=True), nullable=False)
    side: Mapped[str] = mapped_column(String(4), nullable=False)
    order_type: Mapped[str] = mapped_column(String(10), nullable=False)
    quantity: Mapped[Numeric] = mapped_column(Numeric(24, 8), nullable=False)
    limit_price: Mapped[Numeric | None] = mapped_column(Numeric(24, 8), nullable=True)
    time_in_force: Mapped[str] = mapped_column(String(8), nullable=False, default="DAY")
    # 상태 머신 (6.6): CREATED -> VALIDATED -> ACCEPTED -> PARTIALLY_FILLED -> FILLED
    #                                                     -> CANCELLED / EXPIRED
    # VALIDATION_FAILED / REJECTED는 종료 상태
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="CREATED")
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    policy_version: Mapped[str] = mapped_column(String(32), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    pre_trade_journal_id: Mapped[str | None] = mapped_column(UUID(as_uuid=True), nullable=True)


class Fill(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "fills"

    order_id: Mapped[str] = mapped_column(UUID(as_uuid=True), ForeignKey("orders.id"), nullable=False)
    quantity: Mapped[Numeric] = mapped_column(Numeric(24, 8), nullable=False)
    fill_price: Mapped[Numeric] = mapped_column(Numeric(24, 8), nullable=False)
    commission: Mapped[Numeric] = mapped_column(Numeric(24, 8), nullable=False, default=0)
    tax: Mapped[Numeric] = mapped_column(Numeric(24, 8), nullable=False, default=0)
    slippage: Mapped[Numeric] = mapped_column(Numeric(24, 8), nullable=False, default=0)
    realized_pnl: Mapped[Numeric | None] = mapped_column(Numeric(24, 8), nullable=True)
    market_data_as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    filled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class Position(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "positions"
    __table_args__ = (
        UniqueConstraint("portfolio_id", "instrument_id", name="uq_positions_portfolio_instrument"),
    )

    portfolio_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True), ForeignKey("portfolios.id"), nullable=False
    )
    instrument_id: Mapped[str] = mapped_column(UUID(as_uuid=True), nullable=False)
    quantity: Mapped[Numeric] = mapped_column(Numeric(24, 8), nullable=False, default=0)
    average_cost: Mapped[Numeric] = mapped_column(Numeric(24, 8), nullable=False, default=0)


class LedgerEntry(Base, UUIDPrimaryKeyMixin):
    """불변 원장. 모든 잔고 변경의 유일한 원본(single source of truth)."""

    __tablename__ = "ledger_entries"
    __table_args__ = (
        UniqueConstraint(
            "portfolio_id", "event_id", "account_code", name="uq_ledger_event_once"
        ),
    )

    portfolio_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True), ForeignKey("portfolios.id"), nullable=False
    )
    event_id: Mapped[str] = mapped_column(UUID(as_uuid=True), nullable=False)
    account_code: Mapped[str] = mapped_column(String(64), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    amount: Mapped[Numeric] = mapped_column(Numeric(24, 8), nullable=False)
    entry_type: Mapped[str] = mapped_column(String(32), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
