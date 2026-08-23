"""학습 엔진 도메인 모델. 명세서 6.2, 6.3, 8.1 참고.

계층: LearningPath > Course > Module > Lesson > (ContentBlock, Quiz>Question>Choice)

콘텐츠 작성·검수·게시 워크플로(6.2, 11.1)는 두 개의 독립된 필드로 나눠 표현한다
— 절대 서로를 대신하지 않는다:

- `status`(작성/게시 상태): DRAFT -> READY_FOR_REVIEW -> PUBLISHED (-> ARCHIVED).
  실제 공개 여부를 결정하는 유일한 게이트다 — API는 `status == PUBLISHED`인
  강의만 노출한다(그 외 전부 비공개).
- `review_status`(검수 상태): UNREVIEWED -> REVIEW_REQUIRED -> REVIEWED.
  콘텐츠 정확성이 사람에 의해 확인됐는지만 나타낸다. `review_status`가
  REVIEWED여도 `status`가 PUBLISHED가 아니면 여전히 비공개다 — 이 필드
  단독으로는 아무것도 노출시키지 않는다.

에이전트(자동화)가 새로 작성한 콘텐츠는 최대 READY_FOR_REVIEW까지만 시드한다.
REVIEWED·PUBLISHED로의 전환은 반드시 사람(운영자)이
`scripts/publish_lesson.py`를 통해 명시적으로 승인해야 한다 — 에이전트가
스스로의 산출물을 REVIEWED/PUBLISHED로 자기 승인하지 않는다는 원칙을
코드 수준에서 강제한다(그 스크립트가 검증하는 전제조건들 참고).

검수자·이전버전 복원 등 전체 CMS 워크플로는 관리자 웹(apps/admin-web)
작업과 함께 후속으로 확장한다 — 지금은 운영자 CLI(`scripts/publish_lesson.py`)
+ `lesson_review_audits` 감사기록으로 최소 승인 절차만 구현한다.
"""

from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

# --- status: 작성/게시 상태(공개 여부의 유일한 게이트) ---
CONTENT_DRAFT = "DRAFT"
CONTENT_READY_FOR_REVIEW = "READY_FOR_REVIEW"
CONTENT_PUBLISHED = "PUBLISHED"
CONTENT_ARCHIVED = "ARCHIVED"

# --- review_status: 검수 상태(공개 여부와 무관 — status가 별도로 PUBLISHED여야
# 실제로 노출된다) ---
REVIEW_UNREVIEWED = "UNREVIEWED"
REVIEW_REQUIRED = "REVIEW_REQUIRED"
REVIEW_REVIEWED = "REVIEWED"


class LearningPath(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "learning_paths"

    title: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    target_experience_level: Mapped[str | None] = mapped_column(String(16), nullable=True)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=CONTENT_PUBLISHED)


class Course(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "courses"

    learning_path_id: Mapped[str] = mapped_column(UUID(as_uuid=True), ForeignKey("learning_paths.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=CONTENT_PUBLISHED)


class Module(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "modules"

    course_id: Mapped[str] = mapped_column(UUID(as_uuid=True), ForeignKey("courses.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(128), nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=CONTENT_PUBLISHED)


class Lesson(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "lessons"
    __table_args__ = (
        # code는 신규(6강 이후) 강의부터 쓰는 안정적 식별자다 — UUID처럼 재생성 시
        # 바뀌지 않아 challenge_missions.config·문서·테스트에서 안전하게 참조할 수
        # 있다. 기존 1~5강·7일 챌린지 카드 강의는 code가 없다(NULL) — 부분 unique
        # index라 NULL은 제약 대상이 아니다(이 저장소의 Instrument ticker+exchange
        # unique index와 동일한 패턴).
        Index("uq_lessons_code", "code", unique=True, postgresql_where=text("code IS NOT NULL")),
    )

    module_id: Mapped[str] = mapped_column(UUID(as_uuid=True), ForeignKey("modules.id"), nullable=False)
    code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    title: Mapped[str] = mapped_column(String(128), nullable=False)
    learning_objective: Mapped[str | None] = mapped_column(Text, nullable=True)
    estimated_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=CONTENT_PUBLISHED)
    source: Mapped[str | None] = mapped_column(String(256), nullable=True)
    reviewed_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    reviewed_at: Mapped[date | None] = mapped_column(nullable=True)
    # 아래 5개는 6강 이후 콘텐츠부터 채운다(기존 1~5강·챌린지 카드 강의는 전부
    # NULL로 남는다 — 소급 채움 없이 하위호환). source_url/source_confirmed_at은
    # "기준일과 출처"를 콘텐츠 본문과 분리해 관리하기 위함이다(9.4강 원칙).
    source_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    source_confirmed_at: Mapped[date | None] = mapped_column(nullable=True)
    content_version: Mapped[str | None] = mapped_column(String(16), nullable=True)
    market_scope: Mapped[str | None] = mapped_column(String(32), nullable=True)  # 예: KR/US/GLOBAL
    review_status: Mapped[str | None] = mapped_column(String(16), nullable=True)


class LessonReviewAudit(Base, UUIDPrimaryKeyMixin):
    """`scripts/publish_lesson.py`가 강의를 REVIEWED/PUBLISHED로 승인할 때마다
    남기는 감사기록. (lesson_id, content_version, action) unique 제약이 같은
    콘텐츠 버전에 대한 동일 승인 액션의 재실행을 멱등하게 만든다 — 이 저장소
    전체에서 쓰는 SAVEPOINT + unique 제약 동시성 패턴과 동일하다."""

    __tablename__ = "lesson_review_audits"
    __table_args__ = (
        UniqueConstraint(
            "lesson_id", "content_version", "action", name="uq_lesson_review_audits_lesson_version_action"
        ),
    )

    lesson_id: Mapped[str] = mapped_column(UUID(as_uuid=True), ForeignKey("lessons.id"), nullable=False)
    lesson_code: Mapped[str] = mapped_column(String(64), nullable=False)
    content_version: Mapped[str] = mapped_column(String(16), nullable=False)
    action: Mapped[str] = mapped_column(String(16), nullable=False)  # 지금은 PUBLISHED만 씀
    reviewer: Mapped[str] = mapped_column(String(128), nullable=False)
    reviewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    note: Mapped[str] = mapped_column(Text, nullable=False)
    performed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ContentBlock(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "content_blocks"

    lesson_id: Mapped[str] = mapped_column(UUID(as_uuid=True), ForeignKey("lessons.id"), nullable=False)
    block_type: Mapped[str] = mapped_column(String(16), nullable=False)  # OBJECTIVE/BODY/EXAMPLE/SUMMARY
    content: Mapped[str] = mapped_column(Text, nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class Quiz(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "quizzes"

    lesson_id: Mapped[str] = mapped_column(UUID(as_uuid=True), ForeignKey("lessons.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(128), nullable=False)
    pass_score_pct: Mapped[Numeric] = mapped_column(Numeric(5, 2), nullable=False, default=70)
    # 문항 버전 표시용. 기존 QuizAttempt는 제출 시점의 score_pct/passed를 그대로
    # 저장하므로(다시 채점하지 않음), 이후 문항을 고쳐 이 버전을 올려도 과거
    # 응시 기록은 무효화되지 않는다.
    content_version: Mapped[str | None] = mapped_column(String(16), nullable=True)


class Question(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "questions"

    quiz_id: Mapped[str] = mapped_column(UUID(as_uuid=True), ForeignKey("quizzes.id"), nullable=False)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    question_type: Mapped[str] = mapped_column(String(16), nullable=False, default="SINGLE_CHOICE")
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class Choice(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "choices"

    question_id: Mapped[str] = mapped_column(UUID(as_uuid=True), ForeignKey("questions.id"), nullable=False)
    label: Mapped[str] = mapped_column(Text, nullable=False)
    is_correct: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # 오답별 설명(왜 이 선택지가 틀렸는지/맞았는지) — 채점 후 응답에만 노출한다.
    # 기존 1~5강 문항은 NULL로 남아 있어도 무방하다(질문 단위 explanation으로 대체).
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)


class LessonProgress(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "lesson_progress"
    __table_args__ = (UniqueConstraint("user_id", "lesson_id", name="uq_lesson_progress_user_lesson"),)

    user_id: Mapped[str] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    lesson_id: Mapped[str] = mapped_column(UUID(as_uuid=True), ForeignKey("lessons.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="IN_PROGRESS")
    last_content_block_id: Mapped[str | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class QuizAttempt(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "quiz_attempts"

    user_id: Mapped[str] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    quiz_id: Mapped[str] = mapped_column(UUID(as_uuid=True), ForeignKey("quizzes.id"), nullable=False)
    answers: Mapped[dict] = mapped_column(JSONB, nullable=False)  # {question_id: [choice_id, ...]}
    score_pct: Mapped[Numeric] = mapped_column(Numeric(5, 2), nullable=False)
    passed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    attempted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class XpLedger(Base, UUIDPrimaryKeyMixin):
    """XP는 서버가 규칙에 따라 계산해 여기에 기록한다 (6.3). 일일 상한 검증에 사용."""

    __tablename__ = "xp_ledger"

    user_id: Mapped[str] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(String(32), nullable=False)  # LESSON_COMPLETED / QUIZ_PASSED
    reference_id: Mapped[str] = mapped_column(UUID(as_uuid=True), nullable=False)
    awarded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
