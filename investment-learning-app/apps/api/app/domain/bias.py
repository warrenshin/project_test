"""행동편향 탐지(7.4) 결과 저장. 재현성·규칙 버전 관리·중복 방지가 목적이다.

왜 필요한가: coaching.detect_biases()가 매 요청마다 그 자리에서 계산만 하고
아무것도 저장하지 않으면, "이 결과가 어떤 규칙 버전·임계값으로 나온
것인지"를 나중에 재구성할 수 없고, 같은 근거로 반복 호출해도 매번 새
결과처럼 보인다. 여기서는 그 최소한만 저장한다 — 전체 편향 이벤트
플랫폼(알림·타임라인·집계 대시보드 등)을 만들지 않는다.

원문 보존 금지: evidence_refs에는 order_id/journal_id 같은 참조 UUID만
담는다. thesis·counter_evidence 등 사용자가 쓴 자유 텍스트 원문은 여기에도,
evidence_summary에도 절대 넣지 않는다(진단이 아니라 "관찰된 신호"로만
표현한다는 원칙과 개인정보 최소화 원칙 둘 다 위반하게 된다).
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

DATA_SUFFICIENT = "SUFFICIENT"
DATA_INSUFFICIENT = "INSUFFICIENT"
DATA_MARKET_UNAVAILABLE = "MARKET_DATA_UNAVAILABLE"

SEVERITY_LOW = "LOW"
SEVERITY_MEDIUM = "MEDIUM"
SEVERITY_HIGH = "HIGH"


class BiasEvent(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """실제로 탐지된(= detected=True) 편향 신호 1건. 데이터 부족으로 판단하지
    못한 경우는 여기 저장하지 않는다 — 저장 대상은 "이번에 실제로 관찰된 신호"뿐이다.

    (user_id, bias_code, rule_version, evidence_fingerprint) unique 제약이
    핵심이다: 같은 근거(evidence_fingerprint = 근거 ID 집합의 해시)로 같은
    규칙 버전 하에 다시 분석해도 행이 중복되지 않는다. 규칙 버전을 올리면
    같은 근거라도 새 행이 생겨, 과거 규칙으로 낸 결과와 새 규칙으로 낸 결과가
    섞이지 않는다."""

    __tablename__ = "bias_events"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "bias_code", "rule_version", "evidence_fingerprint",
            name="uq_bias_events_user_code_version_fingerprint",
        ),
    )

    user_id: Mapped[str] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    bias_code: Mapped[str] = mapped_column(String(64), nullable=False)
    display_name: Mapped[str] = mapped_column(String(128), nullable=False)
    rule_version: Mapped[str] = mapped_column(String(16), nullable=False)
    # 이 분석을 만들어낸 시점의 실제 임계값 값 스냅샷(Settings 필드가 나중에
    # 바뀌어도 이 행이 어떤 값으로 판정됐는지 항상 재구성 가능하게 한다).
    threshold_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)
    window_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    window_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sample_size: Mapped[int] = mapped_column(nullable=False)
    minimum_sample_size: Mapped[int] = mapped_column(nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    evidence_strength: Mapped[Numeric] = mapped_column(Numeric(5, 2), nullable=False)
    evidence_summary: Mapped[str] = mapped_column(Text, nullable=False)
    # [{"type": "Order"|"Fill"|"JournalEntry"|..., "id": "<uuid>"}] — ID만, 본문 없음.
    evidence_refs: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    limitations: Mapped[str] = mapped_column(Text, nullable=False)
    self_check_questions: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    related_lesson_id: Mapped[str | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    # 근거 ID 집합 + bias_code + rule_version의 결정론적 해시(sha256 hex).
    # 재분석 시 완전히 같은 근거면 같은 값이 나온다 — 이걸로 중복을 막는다.
    evidence_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # 동의(agree)가 아니라 "교육 내용을 확인했다"는 의미다 — 편향 자체에
    # 동의/반박하는 기능이 아니다.
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
