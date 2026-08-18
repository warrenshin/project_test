"""seed default fee policies and placeholder fx rate

Revision ID: 2af91de317bb
Revises: 1c0aa76bf61d
Create Date: 2026-08-16 11:52:29.417611

명세서 6.7: 비용 정책은 시장·날짜별 버전으로 관리한다. FxRate는 아직
market-data-worker가 없어 seed 값을 사용한다 (ADR 0001) — 반드시 실제 환율
파이프라인으로 교체한 뒤 정식 출시해야 한다.
"""
import uuid
from datetime import date, datetime, timezone

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

# revision identifiers, used by Alembic.
revision = '2af91de317bb'
down_revision = '1c0aa76bf61d'
branch_labels = None
depends_on = None

fee_policies = sa.table(
    "fee_policies",
    sa.column("id", PG_UUID(as_uuid=True)),
    sa.column("market", sa.String),
    sa.column("version", sa.String),
    sa.column("commission_bps", sa.Numeric),
    sa.column("sell_tax_bps", sa.Numeric),
    sa.column("min_commission", sa.Numeric),
    sa.column("spread_bps", sa.Numeric),
    sa.column("effective_from", sa.Date),
    sa.column("created_at", sa.DateTime(timezone=True)),
)

fx_rates = sa.table(
    "fx_rates",
    sa.column("id", PG_UUID(as_uuid=True)),
    sa.column("base_currency", sa.String),
    sa.column("quote_currency", sa.String),
    sa.column("rate", sa.Numeric),
    sa.column("spread_bps", sa.Numeric),
    sa.column("source", sa.String),
    sa.column("as_of", sa.DateTime(timezone=True)),
)


def upgrade() -> None:
    now = datetime.now(timezone.utc)
    today = date.today()

    op.bulk_insert(
        fee_policies,
        [
            {
                "id": uuid.uuid4(),
                "market": "KR",
                "version": "v1",
                "commission_bps": 15,  # 0.015%, MVP 근사치
                "sell_tax_bps": 18,  # 매도 시 증권거래세 근사치 (코스피/코스닥 실제 세율 차이는 후속 정교화)
                "min_commission": 0,
                "spread_bps": 10,
                "effective_from": today,
                "created_at": now,
            },
            {
                "id": uuid.uuid4(),
                "market": "US",
                "version": "v1",
                "commission_bps": 0,  # 무료 수수료 브로커 가정, MVP 근사치
                "sell_tax_bps": 0,
                "min_commission": 0,
                "spread_bps": 5,
                "effective_from": today,
                "created_at": now,
            },
        ],
    )

    op.bulk_insert(
        fx_rates,
        [
            {
                "id": uuid.uuid4(),
                "base_currency": "USD",
                "quote_currency": "KRW",
                "rate": 1350.0,  # PLACEHOLDER: 실제 환율 파이프라인 연동 전까지 사용하는 seed 값
                "spread_bps": 20,
                "source": "seed-placeholder",
                "as_of": now,
            }
        ],
    )


def downgrade() -> None:
    op.execute("DELETE FROM fx_rates WHERE source = 'seed-placeholder'")
    op.execute("DELETE FROM fee_policies WHERE version = 'v1'")
