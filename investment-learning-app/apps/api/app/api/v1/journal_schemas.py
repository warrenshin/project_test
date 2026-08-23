from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field


class PreTradeJournalCreateRequest(BaseModel):
    portfolio_id: UUID
    instrument_id: UUID
    order_id: UUID | None = None
    thesis: str = Field(min_length=1)
    supporting_evidence: list[str] = Field(default_factory=list, max_length=3)
    counter_evidence: list[str] = Field(default_factory=list)
    expected_holding_period: str | None = None
    entry_condition: str | None = None
    target_condition: str | None = None
    stop_loss_condition: str | None = None
    planned_amount: Decimal | None = None
    planned_weight_pct: Decimal | None = Field(default=None, ge=0, le=100)
    confidence_level: int | None = Field(default=None, ge=1, le=5)
    reference_links: list[str] = Field(default_factory=list)


class JournalUpdateRequest(BaseModel):
    thesis: str | None = None
    supporting_evidence: list[str] | None = None
    counter_evidence: list[str] | None = None
    expected_holding_period: str | None = None
    entry_condition: str | None = None
    target_condition: str | None = None
    stop_loss_condition: str | None = None
    planned_amount: Decimal | None = None
    planned_weight_pct: Decimal | None = Field(default=None, ge=0, le=100)
    confidence_level: int | None = Field(default=None, ge=1, le=5)
    reference_links: list[str] | None = None


class PostTradeReviewRequest(BaseModel):
    actual_entry_at: datetime | None = None
    actual_exit_at: datetime | None = None
    followed_plan: bool
    plan_change_reason: str | None = None
    expectation_gap: str | None = None
    luck_contribution: str | None = None
    behavior_to_repeat: str | None = None
    behavior_to_change: str | None = None
    emotion_tags: list[str] = Field(default_factory=list)


class JournalResponse(BaseModel):
    id: UUID
    portfolio_id: UUID
    instrument_id: UUID
    order_id: UUID | None
    thesis: str | None
    supporting_evidence: list | None
    counter_evidence: list | None
    expected_holding_period: str | None
    entry_condition: str | None
    target_condition: str | None
    stop_loss_condition: str | None
    planned_amount: Decimal | None
    planned_weight_pct: Decimal | None
    confidence_level: int | None
    reference_links: list | None
    market_data_snapshot: dict | None
    actual_entry_at: datetime | None
    actual_exit_at: datetime | None
    followed_plan: bool | None
    expectation_gap: str | None
    behavior_to_repeat: str | None
    behavior_to_change: str | None
    emotion_tags: list | None
    process_score: Decimal | None
    process_score_breakdown: dict | None

    model_config = {"from_attributes": True}


class BiasObservation(BaseModel):
    """하위 호환 필드 — 기존 클라이언트가 쓰던 3개 필드 그대로다. 실제로
    감지된(감지 안 됨/데이터 부족 제외) 패턴만 담는다."""

    pattern: str
    description: str
    coaching_direction: str


class BiasSignalResponse(BaseModel):
    """7종 편향 전체(감지 여부 무관)를 담는 확장 필드. 클라이언트가
    severity·bias_code 등을 직접 지정할 수 없다 — 전부 서버 계산 값이다."""

    id: UUID | None
    bias_code: str
    display_name: str
    rule_version: str
    detected: bool
    severity: str | None
    evidence_strength: float | None
    sample_size: int
    minimum_sample_size: int
    data_sufficiency: str
    window_start: datetime | None
    window_end: datetime | None
    description: str
    coaching_direction: str
    evidence_summary: str
    limitations: str
    self_check_questions: list[str]
    related_lesson_id: UUID | None
    detected_at: datetime | None
    acknowledged_at: datetime | None


class BiasReportResponse(BaseModel):
    observations: list[BiasObservation]
    biases: list[BiasSignalResponse]
    top_signals: list[str] = Field(default_factory=list)
    note: str = "행동편향은 의학적 진단이 아니라 관찰된 거래 패턴입니다."


class BiasAcknowledgeResponse(BaseModel):
    id: UUID
    bias_code: str
    acknowledged_at: datetime


class CoachingSourceResponse(BaseModel):
    type: str
    id: str | None
    title: str
    as_of: str | None
    source: str
    delay_seconds: int | None = None


class JournalCoachingResponse(BaseModel):
    process_score: Decimal | None
    process_score_breakdown: dict | None
    content: str
    model: str
    prompt_version: str
    sources: list[CoachingSourceResponse]
    degraded: bool
