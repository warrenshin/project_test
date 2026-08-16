"""AI 코치 대화 도메인 모델. 명세서 7.5-7.7, 8.1 참고.

답변마다 모델·프롬프트 버전·검색 문서 ID를 기록한다(7.7)는 원칙을 AiMessage에
직접 반영했다. retrieval_sources/model_runs/safety_events를 별도 테이블로 정규화하는
대신, 이번 범위에서는 AiMessage.sources/safety_flags에 JSONB로 기록한다 — 감사·리포트
요구가 커지면 별도 테이블로 분리한다.
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class AiConversation(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "ai_conversations"

    user_id: Mapped[str] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    journal_id: Mapped[str | None] = mapped_column(UUID(as_uuid=True), nullable=True)


class AiMessage(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "ai_messages"

    conversation_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ai_conversations.id"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)  # USER / ASSISTANT
    content: Mapped[str] = mapped_column(Text, nullable=False)

    # ASSISTANT 메시지에만 채워진다 (7.7: 모델·프롬프트버전·검색문서ID 기록)
    model: Mapped[str | None] = mapped_column(String(64), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    sources: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    safety_flags: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    degraded: Mapped[bool] = mapped_column(nullable=False, default=False)  # graceful degradation 경로 사용 여부

    user_feedback: Mapped[str | None] = mapped_column(String(16), nullable=True)  # HELPFUL / NOT_HELPFUL / REPORTED
    feedback_comment: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
