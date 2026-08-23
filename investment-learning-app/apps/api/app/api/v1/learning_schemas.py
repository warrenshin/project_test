from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class LessonSummary(BaseModel):
    id: UUID
    code: str | None
    title: str
    estimated_minutes: int
    order_index: int


class ModuleSummary(BaseModel):
    id: UUID
    title: str
    order_index: int
    lessons: list[LessonSummary]


class CourseSummary(BaseModel):
    id: UUID
    title: str
    description: str | None
    order_index: int
    modules: list[ModuleSummary]


class LearningPathResponse(BaseModel):
    id: UUID
    title: str
    description: str | None
    target_experience_level: str | None
    courses: list[CourseSummary]


class ContentBlockResponse(BaseModel):
    block_type: str
    content: str
    order_index: int


class QuizSummary(BaseModel):
    id: UUID
    title: str
    question_count: int
    pass_score_pct: Decimal
    content_version: str | None


class LessonProgressResponse(BaseModel):
    status: str
    completed_at: datetime | None


class LessonDetailResponse(BaseModel):
    id: UUID
    code: str | None
    title: str
    learning_objective: str | None
    estimated_minutes: int
    source: str | None
    reviewed_by: str | None
    reviewed_at: date | None
    source_url: str | None
    source_confirmed_at: date | None
    content_version: str | None
    market_scope: str | None
    review_status: str | None
    content_blocks: list[ContentBlockResponse]
    quiz: QuizSummary | None
    progress: LessonProgressResponse | None
    disclosure: str = (
        "이 강의는 교육용 콘텐츠이며 특정 종목 매수·매도를 권유하거나 수익을 보장하지 않습니다. "
        "실제 투자 결정 전에는 최신 공식 자료를 직접 확인하세요."
    )


class QuizChoiceResponse(BaseModel):
    id: UUID
    label: str


class QuizQuestionResponse(BaseModel):
    id: UUID
    prompt: str
    question_type: str
    choices: list[QuizChoiceResponse]


class QuizDetailResponse(BaseModel):
    id: UUID
    title: str
    pass_score_pct: Decimal
    questions: list[QuizQuestionResponse]


class LessonProgressUpdateRequest(BaseModel):
    status: Literal["IN_PROGRESS", "COMPLETED"]
    last_content_block_id: UUID | None = None


class LessonProgressUpdateResponse(BaseModel):
    status: str
    completed_at: datetime | None
    xp_awarded: int


class QuizAttemptRequest(BaseModel):
    answers: dict[UUID, list[UUID]]


class ChoiceFeedback(BaseModel):
    """채점 후에만 노출한다(정답 전에는 QuizDetailResponse에 is_correct/explanation을 담지 않는다)."""

    choice_id: UUID
    label: str
    is_correct: bool
    explanation: str | None


class QuestionResult(BaseModel):
    question_id: UUID
    correct: bool
    explanation: str | None
    choice_feedback: list[ChoiceFeedback] = Field(default_factory=list)


class QuizAttemptResponse(BaseModel):
    score_pct: Decimal
    passed: bool
    xp_awarded: int
    results: list[QuestionResult]


class LearningSummaryResponse(BaseModel):
    total_xp: int
    lessons_completed: int
    quizzes_passed: int
    current_streak_days: int
    todays_xp: int
    daily_xp_cap: int
