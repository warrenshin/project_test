"""add fills.market_data_source

Revision ID: d5d5285c1108
Revises: 94b30d15c128
Create Date: 2026-08-21 22:30:00.000000

감사에서 확인된 gap: Fill에는 market_data_as_of는 있었지만 어느 공급자의
가격으로 체결했는지(market_data_source)는 없었다 — 주문 감사(audit) 시
"이 체결가가 어떤 시세 출처에서 왔는가"를 답할 수 없었다.

작은 additive migration으로 처리한다(Phase B 전체 provenance/ingestion
batch 작업과는 별개, 훨씬 작은 범위):
- nullable로 추가한다 — 기존 체결 행은 그 정보가 애초에 기록되지 않았으므로
  거짓으로 채우지 않고 null로 남긴다.
- 신규 체결부터는 app/domain/services/execution.py의 execute_order가
  ExecutionQuote.bar_source(주문 시점에 쓰인 bar.source)를 그대로 기록한다.
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'd5d5285c1108'
down_revision = '94b30d15c128'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("fills", sa.Column("market_data_source", sa.String(length=64), nullable=True))


def downgrade() -> None:
    op.drop_column("fills", "market_data_source")
