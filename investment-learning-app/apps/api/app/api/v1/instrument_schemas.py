from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel


class InstrumentSummary(BaseModel):
    id: UUID
    ticker: str
    exchange: str
    currency: str
    name: str
    industry: str | None


class InstrumentDetail(InstrumentSummary):
    is_tradable: bool
    last_price: Decimal | None
    price_as_of: datetime | None
    price_source: str | None
    delay_seconds: int | None


class BarResponse(BaseModel):
    bar_start: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    source: str
    as_of: datetime
    delay_seconds: int
