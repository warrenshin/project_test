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


PriceStatus = Literal["FRESH", "STALE", "UNAVAILABLE"]


class PositionResponse(BaseModel):
    instrument_id: UUID
    ticker: str
    quantity: Decimal
    average_cost: Decimal
    last_price: Decimal | None
    market_value: Decimal | None
    unrealized_pnl: Decimal | None
    # Phase A: 이 포지션 가격의 신뢰도. UNAVAILABLE이면 last_price/market_value/
    # unrealized_pnl은 항상 null이다 — 0으로 계산되지 않았다는 뜻이지, 실제
    # 값이 0이라는 뜻이 아니다.
    price_status: PriceStatus
    price_as_of: datetime | None
    # 이 가격이 어디서 왔는지(예: "demo", "stooq", "seed-sample") — 사용자에게
    # 그대로 보여도 안전한 일반 식별자만 담는다(내부 예외 메시지·공급자 오류
    # 상세는 담지 않는다). UNAVAILABLE이면 null.
    price_source: str | None
    # price_as_of로부터 지금까지 흐른 시간(초, UTC 기준). UNAVAILABLE이면 null.
    price_age_seconds: int | None


class PortfolioResponse(BaseModel):
    id: UUID
    base_currency: str
    cash_balance: Decimal
    positions_market_value: Decimal
    total_assets: Decimal
    # Phase A: 보유 종목 중 하나라도 UNAVAILABLE이면 "UNAVAILABLE", 그 외 하나라도
    # STALE이면 "STALE", 전부 FRESH면 "FRESH", 보유 종목이 없으면 "EMPTY".
    # UNAVAILABLE 종목은 positions_market_value/total_assets 합계에서 제외된다
    # (0원으로 계산하지 않는다) — has_unavailable_positions로 그 사실을 알린다.
    market_data_status: Literal["FRESH", "STALE", "UNAVAILABLE", "EMPTY"]
    market_data_as_of: datetime | None
    has_unavailable_positions: bool
    # 몇 종목이 문제인지 — 프런트가 종목별 배지를 일일이 세지 않아도 바로 보여줄
    # 수 있다. positions 응답의 price_status 배지 개수와 항상 일치해야 한다.
    stale_position_count: int
    unavailable_position_count: int


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
    market_data_status: Literal["FRESH", "STALE", "UNAVAILABLE", "EMPTY"]
    market_data_as_of: datetime | None
    has_unavailable_positions: bool
    stale_position_count: int
    unavailable_position_count: int
    # Phase A: UNAVAILABLE 포지션이 하나라도 있으면 False. simple_return_pct는
    # total_assets(일부 종목 제외)와 total_deposited(전액 포함)를 나누어 계산하므로,
    # 이 값이 False일 때는 simple_return_pct가 null로 내려간다 — 실제로는 불완전한
    # 값을 완전한 수익률처럼 보이게 하지 않기 위함이다.
    performance_complete: bool
    note: str = "모의 성과이며 실제 투자 성과를 보장하지 않습니다."
