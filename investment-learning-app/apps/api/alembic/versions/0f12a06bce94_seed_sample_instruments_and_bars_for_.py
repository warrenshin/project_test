"""seed sample instruments and bars for demo

Revision ID: 0f12a06bce94
Revises: 13b805fca4ca
Create Date: 2026-08-16 13:10:00.000000

명세서 6.4: 실제 시세 데이터는 공급자 계약 후 market-data-worker가 채운다.
이 seed는 개발·데모용 정적 샘플 값이며 (source='seed-sample'), 실거래 판단
근거로 쓸 수 없다. as_of는 마이그레이션 실행 시각으로 채워 최신성 검증을
통과하게 하되, 오래되면(예: 900초 이상) 주문 생성 시 거부되므로 데모를 새로
하려면 재적용이 필요할 수 있다.
"""
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

# revision identifiers, used by Alembic.
revision = '0f12a06bce94'
down_revision = '13b805fca4ca'
branch_labels = None
depends_on = None

instruments_table = sa.table(
    "instruments",
    sa.column("id", PG_UUID(as_uuid=True)),
    sa.column("ticker", sa.String),
    sa.column("exchange", sa.String),
    sa.column("currency", sa.String),
    sa.column("name", sa.String),
    sa.column("industry", sa.String),
    sa.column("is_tradable", sa.Boolean),
    sa.column("created_at", sa.DateTime(timezone=True)),
)

bars_table = sa.table(
    "bars",
    sa.column("id", PG_UUID(as_uuid=True)),
    sa.column("instrument_id", PG_UUID(as_uuid=True)),
    sa.column("interval", sa.String),
    sa.column("open", sa.Numeric),
    sa.column("high", sa.Numeric),
    sa.column("low", sa.Numeric),
    sa.column("close", sa.Numeric),
    sa.column("volume", sa.Numeric),
    sa.column("bar_start", sa.DateTime(timezone=True)),
    sa.column("source", sa.String),
    sa.column("as_of", sa.DateTime(timezone=True)),
    sa.column("delay_seconds", sa.Integer),
)

SAMPLE_INSTRUMENTS = [
    {"ticker": "005930", "exchange": "KRX", "currency": "KRW", "name": "삼성전자", "industry": "반도체", "base_close": Decimal("71000"), "quantize": Decimal("1")},
    {"ticker": "000660", "exchange": "KRX", "currency": "KRW", "name": "SK하이닉스", "industry": "반도체", "base_close": Decimal("182000"), "quantize": Decimal("1")},
    {"ticker": "AAPL", "exchange": "NASDAQ", "currency": "USD", "name": "Apple Inc.", "industry": "Technology", "base_close": Decimal("195.50"), "quantize": Decimal("0.01")},
    {"ticker": "MSFT", "exchange": "NASDAQ", "currency": "USD", "name": "Microsoft Corp.", "industry": "Technology", "base_close": Decimal("421.00"), "quantize": Decimal("0.01")},
]

DAILY_DELTAS = [Decimal("0.004"), Decimal("-0.002"), Decimal("0.003"), Decimal("-0.001"), Decimal("0.002")]


def _q(value: Decimal, quantize: Decimal) -> Decimal:
    return value.quantize(quantize, rounding=ROUND_HALF_UP)


def upgrade() -> None:
    now = datetime.now(timezone.utc)

    for spec in SAMPLE_INSTRUMENTS:
        instrument_id = uuid.uuid4()
        op.execute(
            instruments_table.insert().values(
                id=instrument_id,
                ticker=spec["ticker"],
                exchange=spec["exchange"],
                currency=spec["currency"],
                name=spec["name"],
                industry=spec["industry"],
                is_tradable=True,
                created_at=now,
            )
        )

        close = spec["base_close"]
        quantize = spec["quantize"]
        bar_rows = []
        for day_offset, delta in zip(range(len(DAILY_DELTAS), 0, -1), DAILY_DELTAS):
            open_price = close
            close = _q(close * (Decimal("1") + delta), quantize)
            high = _q(max(open_price, close) * Decimal("1.003"), quantize)
            low = _q(min(open_price, close) * Decimal("0.997"), quantize)
            bar_start = now - timedelta(days=day_offset)
            bar_rows.append(
                {
                    "id": uuid.uuid4(),
                    "instrument_id": instrument_id,
                    "interval": "1d",
                    "open": open_price,
                    "high": high,
                    "low": low,
                    "close": close,
                    "volume": Decimal("1000000"),
                    "bar_start": bar_start,
                    "source": "seed-sample",
                    "as_of": now,
                    "delay_seconds": 0,
                }
            )
        op.bulk_insert(bars_table, bar_rows)


def downgrade() -> None:
    op.execute(
        "DELETE FROM bars WHERE instrument_id IN "
        "(SELECT id FROM instruments WHERE ticker IN ('005930','000660','AAPL','MSFT'))"
    )
    op.execute("DELETE FROM instruments WHERE ticker IN ('005930','000660','AAPL','MSFT')")
