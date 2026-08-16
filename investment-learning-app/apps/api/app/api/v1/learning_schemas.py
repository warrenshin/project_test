from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel


class LessonSummary(BaseModel):
    id: UUID
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


class LessonProgressResponse(BaseModel):
    status: str
    completed_at: datetime | None


class LessonDetailResponse(BaseModel):
    id: UUID
    title: str
    learning_objective: str | None
    estimated_minutes: int
    source: str | None
    reviewed_by: str | None
    content_blocks: list[ContentBlockResponse]
    quiz: QuizSummary | None
    progress: LessonProgressResponse | None


class LessonProgressUpdateRequest(BaseModel):
    status: Literal["IN_PROGRESS", "COMPLETED"]
    last_content_block_id: UUID | None = None


class LessonProgressUpdateResponse(BaseModel):
    status: str
    completed_at: datetime | None
    xp_awarded: int


class QuizAttemptRequest(BaseModel):
    answers: dict[UUID, list[UUID]]


class QuestionResult(BaseModel):
    question_id: UUID
    correct: bool
    explanation: str | None


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
