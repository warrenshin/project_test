from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel


class MissionSummary(BaseModel):
    id: UUID
    code: str
    title: str
    description: str | None
    mission_type: str
    xp_amount: int
    is_required: bool
    order_index: int
    # mission.config 전체는 절대 노출하지 않는다(예: SCENARIO_CHOICE의
    # correct_choice는 정답 키다). 미션 유형별로 화면에 꼭 필요한, 정답을
    # 드러내지 않는 필드만 서버가 골라서 담는다 — app/api/v1/challenges.py의
    # _public_mission_config 참고.
    public_config: dict[str, Any]


class ChallengeDaySummary(BaseModel):
    day_number: int
    title: str
    description: str | None
    missions: list[MissionSummary]


class ChallengeSummary(BaseModel):
    id: UUID
    code: str
    version: int
    title: str
    description: str | None
    total_days: int


class ChallengeDetailResponse(ChallengeSummary):
    days: list[ChallengeDaySummary]


class StartChallengeRequest(BaseModel):
    # 생략하면 Profile.timezone(기본 Asia/Seoul)을 쓴다. 시작 시점에 딱 한 번
    # 고정되며, 이후 프로필 timezone을 바꿔도 이 챌린지에는 영향이 없다.
    timezone: str | None = None


class UserMissionResponse(BaseModel):
    id: UUID
    code: str
    title: str
    description: str | None
    mission_type: str
    xp_amount: int
    is_required: bool
    order_index: int
    public_config: dict[str, Any]
    completed: bool
    completed_at: datetime | None
    xp_awarded: int | None


class UserChallengeDayResponse(BaseModel):
    day_number: int
    title: str
    description: str | None
    # 서버가 계산한 값이다: LOCKED/AVAILABLE/IN_PROGRESS/COMPLETED
    status: str
    completed_at: datetime | None
    missions: list[UserMissionResponse]


class UserChallengeResponse(BaseModel):
    id: UUID
    challenge_id: UUID
    challenge_code: str
    challenge_title: str
    # 서버가 계산한 값이다: ACTIVE/COMPLETED/EXPIRED
    status: str
    timezone: str
    started_at: datetime
    started_date_local: date
    completed_at: datetime | None
    current_day: int
    total_days: int
    total_xp_earned: int
    days: list[UserChallengeDayResponse]
    # 다음에 무엇을 하면 되는지 — 첫 미완료 필수 미션(있다면).
    next_action: MissionSummary | None


class MissionVerifyRequest(BaseModel):
    """미션 유형마다 필요한 필드가 다르므로 전부 선택적으로 둔다 — 서버가
    mission_type에 맞는 필드만 사용한다."""

    note: str | None = None
    choice: str | None = None
    acknowledged: bool | None = None
    journal_id: UUID | None = None
    portfolio_id: UUID | None = None
    instrument_id: UUID | None = None
    side: str | None = None
    order_type: str | None = None
    quantity: Decimal | None = None
    limit_price: Decimal | None = None


class NewlyAwardedBadge(BaseModel):
    code: str
    title: str
    description: str | None


class MissionVerifyResponse(BaseModel):
    mission_completed: bool
    already_completed: bool
    reason: str | None
    xp_awarded: int
    day_completed: bool
    challenge_completed: bool
    newly_awarded_badges: list[NewlyAwardedBadge]
    extra: dict[str, Any]


class BadgeDefinitionResponse(BaseModel):
    code: str
    version: int
    title: str
    description: str | None


class UserBadgeResponse(BaseModel):
    code: str
    title: str
    description: str | None
    earned_at: datetime
    evidence_type: str
