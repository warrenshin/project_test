"""7일 학습 챌린지·과정 중심 배지 도메인 모델.

핵심 원칙: 이 챌린지는 수익률이나 거래횟수를 보상 기준으로 쓰지 않는다 — 강의
완료, 퀴즈 이해도, 거래 전/후 일지, 반대 근거, 손실 제한 조건 같은 "좋은 과정"만
보상한다. 완료 여부·XP·배지는 항상 서버가 계산하며, 클라이언트가 직접 지정할
수 없다.

버전 관리: Challenge.version은 챌린지 정의(Day·미션 구성) 전체의 버전이다.
UserChallenge.challenge_version은 시작 시점의 Challenge.version을 스냅샷으로
저장해, 이후 관리자가 챌린지 정의를 바꿔도 이미 시작한 사용자의 여정이 조용히
바뀌지 않게 한다. BadgeDefinition.version과 UserBadge.badge_version도 같은
원칙이다 — 배지 조건이 바뀌어도 이미 획득한 기록은 그대로 남는다.

동시성: UserMissionProgress(user_challenge_id, mission_id)와
UserBadge(user_id, badge_definition_id)에 각각 unique 제약을 걸어, 이것이
"같은 미션/배지는 정확히 한 번만 완료·지급된다"는 사실을 DB 수준에서 보장하는
최종 방어선이다 — check-then-insert만으로는 동시 요청의 중복 지급을 막을 수
없다(services/challenge.py의 verify_mission/award_badges가 SAVEPOINT로
이 제약 위반을 잡아 안전하게 수렴시킨다).
"""

from datetime import date, datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

CONTENT_DRAFT = "DRAFT"
CONTENT_PUBLISHED = "PUBLISHED"
CONTENT_ARCHIVED = "ARCHIVED"

USER_CHALLENGE_ACTIVE = "ACTIVE"
USER_CHALLENGE_COMPLETED = "COMPLETED"
# NOT_STARTED은 저장된 상태가 아니다 — 해당 (user, challenge)의 UserChallenge
# 행이 아예 없다는 뜻이다. EXPIRED도 저장하지 않는다 — 배경 작업(cron) 없이도
# 항상 정확하도록, 조회 시점에 시작일+유예기간을 기준으로 계산한다
# (services/challenge.py의 effective_status 참고). DB 컬럼은 두 사건
# (시작 -> ACTIVE, Day7 완료 -> COMPLETED)만 기록한다.

DAY_LOCKED = "LOCKED"
DAY_AVAILABLE = "AVAILABLE"
DAY_IN_PROGRESS = "IN_PROGRESS"
DAY_COMPLETED = "COMPLETED"
# 위 4개도 저장되지 않는다 — LOCKED/AVAILABLE/IN_PROGRESS/COMPLETED는 매 조회마다
# (완료된 미션 수, 오늘 날짜, day_number)로부터 계산한다(서버만 계산, 클라이언트가
# 상태를 직접 지정할 수 없다는 요구사항을 코드로 강제).


class Challenge(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "challenges"

    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    title: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    total_days: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=CONTENT_DRAFT)


class ChallengeDay(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "challenge_days"
    __table_args__ = (UniqueConstraint("challenge_id", "day_number", name="uq_challenge_days_challenge_day"),)

    challenge_id: Mapped[str] = mapped_column(UUID(as_uuid=True), ForeignKey("challenges.id"), nullable=False)
    day_number: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)


class ChallengeMission(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """미션 하나. mission_type이 services/challenge.py의 검증 함수를 고르고,
    config(JSONB)가 그 검증에 필요한 파라미터(예: lesson_id, quiz_id, 정답)를
    담는다 — 새 미션 유형을 데이터로 추가할 수 있게 하되, 실제 근거 검증 로직
    자체는 항상 서버 코드에 있다(config가 "통과 여부"를 직접 결정하지 않는다)."""

    __tablename__ = "challenge_missions"
    __table_args__ = (UniqueConstraint("challenge_day_id", "code", name="uq_challenge_missions_day_code"),)

    challenge_day_id: Mapped[str] = mapped_column(UUID(as_uuid=True), ForeignKey("challenge_days.id"), nullable=False)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    mission_type: Mapped[str] = mapped_column(String(48), nullable=False)
    config: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    xp_amount: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_required: Mapped[bool] = mapped_column(nullable=False, default=True)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class UserChallenge(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "user_challenges"
    __table_args__ = (UniqueConstraint("user_id", "challenge_id", name="uq_user_challenges_user_challenge"),)

    user_id: Mapped[str] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    challenge_id: Mapped[str] = mapped_column(UUID(as_uuid=True), ForeignKey("challenges.id"), nullable=False)
    # 시작 시점의 Challenge.version 스냅샷 — 이후 챌린지 정의가 바뀌어도 이미
    # 시작한 사용자의 Day/미션 구성은 시작할 때 그대로 유지된다.
    challenge_version: Mapped[int] = mapped_column(Integer, nullable=False)
    # MVP 정책: 시작 시 Profile.timezone을 스냅샷으로 고정한다. 이후 사용자가
    # 프로필 timezone을 바꿔도 이미 시작한 챌린지의 Day 경계는 바뀌지 않는다.
    timezone: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=USER_CHALLENGE_ACTIVE)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # 사용자 timezone 기준 시작 "날짜" — 이후 매 요청마다 현재 시각을 이
    # timezone으로 변환해 날짜 차이를 구해 현재 Day를 판단한다(서버 시간이
    # 아니라 사용자 timezone 기준).
    started_date_local: Mapped[date] = mapped_column(nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class UserChallengeDay(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Day별 진행 기록. status는 저장하지 않고 조회 시점에 계산한다(모듈
    docstring 참고) — 여기 저장하는 것은 "실제로 언제 이용 가능해졌는지/
    완료했는지"라는 사실(evidence)뿐이다."""

    __tablename__ = "user_challenge_days"
    __table_args__ = (UniqueConstraint("user_challenge_id", "day_number", name="uq_user_challenge_days_uc_day"),)

    user_challenge_id: Mapped[str] = mapped_column(UUID(as_uuid=True), ForeignKey("user_challenges.id"), nullable=False)
    day_number: Mapped[int] = mapped_column(Integer, nullable=False)
    first_available_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class UserMissionProgress(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """미션 완료 근거. 이 행이 존재한다는 것 자체가 "이 미션은 완료됐다"는
    뜻이다(진행 중이라는 중간 상태를 별도로 두지 않는다 — 검증은 원자적으로
    통과/실패한다). unique 제약이 동일 미션 중복 완료·중복 XP 지급을 막는
    최종 방어선이다."""

    __tablename__ = "user_mission_progress"
    __table_args__ = (
        UniqueConstraint("user_challenge_id", "challenge_mission_id", name="uq_ump_user_challenge_mission"),
    )

    user_challenge_id: Mapped[str] = mapped_column(UUID(as_uuid=True), ForeignKey("user_challenges.id"), nullable=False)
    challenge_mission_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True), ForeignKey("challenge_missions.id"), nullable=False
    )
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # 이 완료를 뒷받침하는 실제 DB 객체(예: LessonProgress/QuizAttempt/
    # JournalEntry/AiMessage)의 종류와 id. 사용자 입력 자체가 근거인 미션(목표
    # 텍스트 등)은 evidence_id가 없고 evidence_payload에 입력값을 담는다.
    evidence_type: Mapped[str] = mapped_column(String(48), nullable=False)
    evidence_id: Mapped[str | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    evidence_payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    xp_awarded: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class BadgeDefinition(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "badge_definitions"

    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    title: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # services/challenge.py의 BADGE_CONDITION_EVALUATORS 딕셔너리에서 이
    # 문자열로 실제 평가 함수를 고른다 — 조건 자체(무엇을 만족해야 하는지)는
    # 항상 서버 코드에 있고, condition_config는 파라미터만 담는다.
    condition_type: Mapped[str] = mapped_column(String(48), nullable=False)
    condition_config: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=CONTENT_DRAFT)


class UserBadge(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "user_badges"
    __table_args__ = (UniqueConstraint("user_id", "badge_definition_id", name="uq_user_badges_user_badge"),)

    user_id: Mapped[str] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    badge_definition_id: Mapped[str] = mapped_column(UUID(as_uuid=True), ForeignKey("badge_definitions.id"), nullable=False)
    # 획득 시점의 BadgeDefinition.version 스냅샷 — 이후 조건이 바뀌어도 이미
    # 획득한 배지가 "그때 그 조건으로 받았다"는 기록은 보존된다.
    badge_version: Mapped[int] = mapped_column(Integer, nullable=False)
    earned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    evidence_type: Mapped[str] = mapped_column(String(48), nullable=False)
    evidence_id: Mapped[str | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    # "SYSTEM"(자동 평가) 또는 수동 발급한 관리자의 식별자. 이번 범위에는 이
    # 코드베이스에 admin 권한 체계가 아직 없어 수동 발급 API는 구현하지
    # 않는다(감사에서 별도 보고) — 필드만 미리 마련해 둔다.
    awarded_by: Mapped[str] = mapped_column(String(64), nullable=False, default="SYSTEM")
