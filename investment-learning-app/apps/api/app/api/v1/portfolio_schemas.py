from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

Side = Literal["BUY", "SELL"]
OrderType = Literal["MARKET", "LIMIT"]


class OrderCreateRequest(BaseModel):
    instrument_id: UUID
    side: Side
    order_type: OrderType
    quantity: Decimal = Field(gt=0)
    limit_price: Decimal | None = Field(default=None, gt=0)
    time_in_force: str = "DAY"
    pre_trade_journal_id: UUID | None = None

    @model_validator(mode="after")
    def limit_price_required_for_limit_orders(self) -> "OrderCreateRequest":
        if self.order_type == "LIMIT" and self.limit_price is None:
            raise ValueError("LIMIT 주문은 limit_price가 필요합니다.")
        return self


class OrderPreviewRequest(OrderCreateRequest):
    pass


class OrderPreviewResponse(BaseModel):
    reference_price: Decimal
    estimated_fill_price: Decimal
    estimated_fillable: bool
    notional: Decimal
    commission: Decimal
    tax: Decimal
    fx_rate: Decimal | None
    estimated_cash_impact: Decimal
    currency: str
    market_data_as_of: datetime
    warnings: list[str] = []


class OrderResponse(BaseModel):
    id: UUID
    portfolio_id: UUID
    instrument_id: UUID
    side: Side
    order_type: OrderType
    quantity: Decimal
    limit_price: Decimal | None
    status: str
    submitted_at: datetime
    policy_version: str
    warnings: list[str] = []

    model_config = {"from_attributes": True}


class PositionResponse(BaseModel):
    instrument_id: UUID
    ticker: str
    quantity: Decimal
    average_cost: Decimal
    last_price: Decimal | None
    market_value: Decimal | None
    unrealized_pnl: Decimal | None


class PortfolioResponse(BaseModel):
    id: UUID
    base_currency: str
    cash_balance: Decimal
    positions_market_value: Decimal
    total_assets: Decimal


class PerformanceResponse(BaseModel):
    base_currency: str
    cash_balance: Decimal
    positions_market_value: Decimal
    total_assets: Decimal
    total_deposited: Decimal
    simple_return_pct: Decimal | None
    realized_pnl: Decimal
    unrealized_pnl: Decimal
    total_commission: Decimal
    total_tax: Decimal
    note: str = "모의 성과이며 실제 투자 성과를 보장하지 않습니다."
