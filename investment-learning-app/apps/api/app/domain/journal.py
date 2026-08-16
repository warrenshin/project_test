"""투자일지 도메인 모델. 명세서 7.1-7.3, 8.3 참고.

원문·AI 생성문·사용자 수정문을 각각 별도 버전으로 보존한다 (5.2 투자일지,
8.3). journal_entries는 최신 상태, journal_versions는 각 수정 시점의 스냅샷이다.
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class JournalEntry(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "journal_entries"

    portfolio_id: Mapped[str] = mapped_column(UUID(as_uuid=True), nullable=False)
    instrument_id: Mapped[str] = mapped_column(UUID(as_uuid=True), nullable=False)
    order_id: Mapped[str | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    # 거래 전 계획 (7.1)
    thesis: Mapped[str | None] = mapped_column(Text, nullable=True)
    supporting_evidence: Mapped[dict | None] = mapped_column(JSONB, nullable=True)  # 최대 3개
    counter_evidence: Mapped[dict | None] = mapped_column(JSONB, nullable=True)  # 최소 1개
    expected_holding_period: Mapped[str | None] = mapped_column(String(64), nullable=True)
    entry_condition: Mapped[str | None] = mapped_column(Text, nullable=True)
    target_condition: Mapped[str | None] = mapped_column(Text, nullable=True)
    stop_loss_condition: Mapped[str | None] = mapped_column(Text, nullable=True)
    planned_amount: Mapped[Numeric | None] = mapped_column(Numeric(24, 8), nullable=True)
    planned_weight_pct: Mapped[Numeric | None] = mapped_column(Numeric(6, 2), nullable=True)
    confidence_level: Mapped[int | None] = mapped_column(nullable=True)  # 1-5
    reference_links: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    market_data_snapshot: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # 거래 후 복기 (7.2)
    actual_entry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    actual_exit_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    followed_plan: Mapped[bool | None] = mapped_column(nullable=True)
    plan_change_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    expectation_gap: Mapped[str | None] = mapped_column(Text, nullable=True)
    luck_contribution: Mapped[str | None] = mapped_column(Text, nullable=True)
    behavior_to_repeat: Mapped[str | None] = mapped_column(Text, nullable=True)
    behavior_to_change: Mapped[str | None] = mapped_column(Text, nullable=True)
    emotion_tags: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # 과정 점수 (7.3) - 규칙 엔진 산출, AI는 설명만 하고 변경 불가
    process_score: Mapped[Numeric | None] = mapped_column(Numeric(5, 2), nullable=True)
    process_score_breakdown: Mapped[dict | None] = mapped_column(JSONB, nullable=True)


class JournalVersion(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """일지 수정 이력. 최초 작성본은 항상 별도 버전으로 보존한다."""

    __tablename__ = "journal_versions"

    journal_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True), ForeignKey("journal_entries.id"), nullable=False
    )
    author_type: Mapped[str] = mapped_column(String(16), nullable=False)  # USER / AI_SUGGESTION
    content_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)
    accepted_by_user: Mapped[bool | None] = mapped_column(nullable=True)
