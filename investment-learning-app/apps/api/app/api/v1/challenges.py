"""7일 학습 챌린지·과정 중심 배지 API.

완료 여부·XP·배지는 전부 app/domain/services/challenge.py가 서버에서
계산한다 — 이 라우터는 소유권 검증과 응답 조립만 담당한다.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session as DbSession

from app.api.v1.challenge_schemas import (
    BadgeDefinitionResponse,
    ChallengeDaySummary,
    ChallengeDetailResponse,
    ChallengeSummary,
    MissionSummary,
    MissionVerifyRequest,
    MissionVerifyResponse,
    NewlyAwardedBadge,
    StartChallengeRequest,
    UserBadgeResponse,
    UserChallengeDayResponse,
    UserChallengeResponse,
    UserMissionResponse,
)
from app.core.db import get_db
from app.core.deps import get_current_user
from app.domain.challenge import (
    BadgeDefinition,
    Challenge,
    ChallengeDay,
    ChallengeMission,
    UserBadge,
    UserChallenge,
    UserChallengeDay,
    UserMissionProgress,
)
from app.domain.learning import Quiz
from app.domain.services import challenge as challenge_service
from app.domain.services import gamification
from app.domain.user import Profile, User

router = APIRouter()


# mission.config 전체를 노출하면 SCENARIO_CHOICE의 correct_choice 같은 정답
# 키가 그대로 클라이언트에 새어나간다. 미션 유형별로 화면 렌더링에 실제로
# 필요한, 정답을 드러내지 않는 키만 화이트리스트로 골라 담는다.
def _public_mission_config(db: DbSession, mission: ChallengeMission) -> dict:
    config = mission.config or {}
    if mission.mission_type == "LESSON_COMPLETE":
        return {"lesson_id": config.get("lesson_id")}
    if mission.mission_type == "QUIZ_PASS":
        # 퀴즈 화면은 강의 상세 화면(/learn/{lesson_id})에 포함돼 있으므로,
        # 프런트가 바로 딥링크할 수 있게 quiz의 소속 lesson_id도 함께 준다.
        quiz_id = config.get("quiz_id")
        lesson_id = None
        if quiz_id:
            quiz = db.query(Quiz).filter(Quiz.id == quiz_id).first()
            lesson_id = str(quiz.lesson_id) if quiz else None
        return {"quiz_id": quiz_id, "lesson_id": lesson_id}
    if mission.mission_type == "GOAL_NOTE":
        return {"min_length": config.get("min_length", 5)}
    if mission.mission_type == "SCENARIO_CHOICE":
        return {"options": config.get("options", {})}
    return {}


def _mission_summary(db: DbSession, mission: ChallengeMission) -> MissionSummary:
    return MissionSummary(
        id=mission.id, code=mission.code, title=mission.title, description=mission.description,
        mission_type=mission.mission_type, xp_amount=mission.xp_amount, is_required=mission.is_required,
        order_index=mission.order_index, public_config=_public_mission_config(db, mission),
    )


@router.get("/challenges", response_model=list[ChallengeSummary])
def list_challenges(db: DbSession = Depends(get_db)):
    challenges = db.query(Challenge).filter(Challenge.status == "PUBLISHED").all()
    return [
        ChallengeSummary(
            id=c.id, code=c.code, version=c.version, title=c.title, description=c.description, total_days=c.total_days
        )
        for c in challenges
    ]


def _get_published_challenge(db: DbSession, challenge_id: UUID) -> Challenge:
    challenge = db.query(Challenge).filter(Challenge.id == challenge_id, Challenge.status == "PUBLISHED").first()
    if challenge is None:
        raise HTTPException(status_code=404, detail="챌린지를 찾을 수 없습니다.")
    return challenge


@router.get("/challenges/{challenge_id}", response_model=ChallengeDetailResponse)
def get_challenge(challenge_id: UUID, db: DbSession = Depends(get_db)):
    challenge = _get_published_challenge(db, challenge_id)
    days = (
        db.query(ChallengeDay).filter(ChallengeDay.challenge_id == challenge.id).order_by(ChallengeDay.day_number).all()
    )
    day_summaries = []
    for day in days:
        missions = (
            db.query(ChallengeMission)
            .filter(ChallengeMission.challenge_day_id == day.id)
            .order_by(ChallengeMission.order_index)
            .all()
        )
        day_summaries.append(
            ChallengeDaySummary(
                day_number=day.day_number, title=day.title, description=day.description,
                missions=[_mission_summary(db, m) for m in missions],
            )
        )
    return ChallengeDetailResponse(
        id=challenge.id, code=challenge.code, version=challenge.version, title=challenge.title,
        description=challenge.description, total_days=challenge.total_days, days=day_summaries,
    )


def _build_user_challenge_response(db: DbSession, user_challenge: UserChallenge) -> UserChallengeResponse:
    challenge = db.query(Challenge).filter(Challenge.id == user_challenge.challenge_id).first()
    status = challenge_service.effective_status(user_challenge, challenge.total_days)
    current_day = challenge_service.current_day_number(user_challenge)

    user_days = {
        d.day_number: d
        for d in db.query(UserChallengeDay).filter(UserChallengeDay.user_challenge_id == user_challenge.id)
    }
    progress_by_mission = {
        p.challenge_mission_id: p
        for p in db.query(UserMissionProgress).filter(UserMissionProgress.user_challenge_id == user_challenge.id)
    }

    days_out: list[UserChallengeDayResponse] = []
    next_action: MissionSummary | None = None
    total_xp = 0
    for day in (
        db.query(ChallengeDay).filter(ChallengeDay.challenge_id == challenge.id).order_by(ChallengeDay.day_number)
    ):
        missions = (
            db.query(ChallengeMission)
            .filter(ChallengeMission.challenge_day_id == day.id)
            .order_by(ChallengeMission.order_index)
            .all()
        )
        mission_responses = []
        has_any_progress = False
        for mission in missions:
            progress = progress_by_mission.get(mission.id)
            if progress is not None:
                has_any_progress = True
                total_xp += progress.xp_awarded
            mission_responses.append(
                UserMissionResponse(
                    id=mission.id, code=mission.code, title=mission.title, description=mission.description,
                    mission_type=mission.mission_type, xp_amount=mission.xp_amount, is_required=mission.is_required,
                    order_index=mission.order_index, public_config=_public_mission_config(db, mission),
                    completed=progress is not None,
                    completed_at=progress.completed_at if progress else None,
                    xp_awarded=progress.xp_awarded if progress else None,
                )
            )
            if next_action is None and progress is None and mission.is_required and day.day_number <= current_day:
                next_action = _mission_summary(db, mission)

        user_day = user_days.get(day.day_number)
        day_status = challenge_service.day_status(
            day.day_number, current_day, user_day.completed_at if user_day else None, has_any_progress,
        )
        days_out.append(
            UserChallengeDayResponse(
                day_number=day.day_number, title=day.title, description=day.description, status=day_status,
                completed_at=user_day.completed_at if user_day else None, missions=mission_responses,
            )
        )

    return UserChallengeResponse(
        id=user_challenge.id, challenge_id=challenge.id, challenge_code=challenge.code, challenge_title=challenge.title,
        status=status, timezone=user_challenge.timezone, started_at=user_challenge.started_at,
        started_date_local=user_challenge.started_date_local, completed_at=user_challenge.completed_at,
        current_day=current_day, total_days=challenge.total_days, total_xp_earned=total_xp, days=days_out,
        next_action=next_action,
    )


@router.post("/challenges/{challenge_id}/start", response_model=UserChallengeResponse, status_code=201)
def start_challenge(
    challenge_id: UUID, payload: StartChallengeRequest, db: DbSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _get_published_challenge(db, challenge_id)

    timezone_name = payload.timezone
    if not timezone_name:
        profile = db.query(Profile).filter(Profile.user_id == current_user.id).first()
        timezone_name = profile.timezone if profile is not None else challenge_service.DEFAULT_TIMEZONE

    try:
        timezone_name = challenge_service.validate_timezone(timezone_name)
    except challenge_service.InvalidTimezoneError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    try:
        user_challenge = challenge_service.start_challenge(db, current_user.id, challenge_id, timezone_name)
    except challenge_service.AlreadyStartedError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    db.commit()
    return _build_user_challenge_response(db, user_challenge)


def _get_owned_user_challenge(db: DbSession, user_challenge_id: UUID, current_user: User) -> UserChallenge:
    user_challenge = db.query(UserChallenge).filter(UserChallenge.id == user_challenge_id).first()
    if user_challenge is None or user_challenge.user_id != current_user.id:
        # 존재 여부를 노출하지 않는다 — 다른 사용자의 챌린지인지, 애초에 없는지 구분하지 않는다(IDOR 방지).
        raise HTTPException(status_code=404, detail="챌린지를 찾을 수 없습니다.")
    return user_challenge


@router.get("/me/challenges/active", response_model=UserChallengeResponse)
def get_active_user_challenge(db: DbSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    user_challenge = (
        db.query(UserChallenge)
        .filter(UserChallenge.user_id == current_user.id, UserChallenge.completed_at.is_(None))
        .order_by(UserChallenge.started_at.desc())
        .first()
    )
    if user_challenge is None:
        raise HTTPException(status_code=404, detail="진행 중인 챌린지가 없습니다.")
    return _build_user_challenge_response(db, user_challenge)


@router.get("/me/challenges/{user_challenge_id}", response_model=UserChallengeResponse)
def get_user_challenge(
    user_challenge_id: UUID, db: DbSession = Depends(get_db), current_user: User = Depends(get_current_user)
):
    user_challenge = _get_owned_user_challenge(db, user_challenge_id, current_user)
    return _build_user_challenge_response(db, user_challenge)


@router.post(
    "/me/challenges/{user_challenge_id}/missions/{mission_id}/verify", response_model=MissionVerifyResponse
)
def verify_mission(
    user_challenge_id: UUID, mission_id: UUID, payload: MissionVerifyRequest,
    db: DbSession = Depends(get_db), current_user: User = Depends(get_current_user),
):
    user_challenge = _get_owned_user_challenge(db, user_challenge_id, current_user)
    mission = db.query(ChallengeMission).filter(ChallengeMission.id == mission_id).first()
    if mission is None:
        raise HTTPException(status_code=404, detail="미션을 찾을 수 없습니다.")
    challenge_day = db.query(ChallengeDay).filter(ChallengeDay.id == mission.challenge_day_id).first()
    if challenge_day is None or challenge_day.challenge_id != user_challenge.challenge_id:
        raise HTTPException(status_code=404, detail="미션을 찾을 수 없습니다.")

    payload_dict = payload.model_dump(exclude_none=True)
    for key in ("journal_id", "portfolio_id", "instrument_id"):
        if key in payload_dict:
            payload_dict[key] = str(payload_dict[key])

    try:
        outcome = challenge_service.verify_mission(db, current_user.id, user_challenge, mission, challenge_day, payload_dict)
    except challenge_service.DayLockedError as exc:
        raise HTTPException(status_code=423, detail=str(exc)) from exc

    db.commit()

    badge_definitions = {
        d.id: d
        for d in db.query(BadgeDefinition).filter(
            BadgeDefinition.id.in_([b.badge_definition_id for b in outcome.newly_awarded_badges])
        )
    } if outcome.newly_awarded_badges else {}

    return MissionVerifyResponse(
        mission_completed=outcome.result.ok, already_completed=outcome.already_completed,
        reason=outcome.result.reason, xp_awarded=outcome.xp_awarded,
        day_completed=outcome.day_completed, challenge_completed=outcome.challenge_completed,
        newly_awarded_badges=[
            NewlyAwardedBadge(
                code=badge_definitions[b.badge_definition_id].code,
                title=badge_definitions[b.badge_definition_id].title,
                description=badge_definitions[b.badge_definition_id].description,
            )
            for b in outcome.newly_awarded_badges
        ],
        extra=outcome.result.extra,
    )


@router.get("/badges", response_model=list[BadgeDefinitionResponse])
def list_badge_definitions(db: DbSession = Depends(get_db)):
    badges = db.query(BadgeDefinition).filter(BadgeDefinition.status == "PUBLISHED").all()
    return [
        BadgeDefinitionResponse(code=b.code, version=b.version, title=b.title, description=b.description)
        for b in badges
    ]


@router.get("/me/badges", response_model=list[UserBadgeResponse])
def list_my_badges(db: DbSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    # 챌린지 미션 완료 시점뿐 아니라 배지 목록을 조회할 때도 평가한다 — 챌린지
    # 밖에서(예: 기존 학습 화면에서) 조건을 만족했을 수 있기 때문이다.
    challenge_service.evaluate_and_award_badges(db, current_user.id)
    db.commit()

    rows = (
        db.query(UserBadge, BadgeDefinition)
        .join(BadgeDefinition, UserBadge.badge_definition_id == BadgeDefinition.id)
        .filter(UserBadge.user_id == current_user.id)
        .order_by(UserBadge.earned_at.desc())
        .all()
    )
    return [
        UserBadgeResponse(
            code=definition.code, title=definition.title, description=definition.description,
            earned_at=user_badge.earned_at, evidence_type=user_badge.evidence_type,
        )
        for user_badge, definition in rows
    ]
