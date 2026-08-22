"""7일 학습 챌린지 서비스 — Day/timezone 판단, 미션 근거 검증, XP·배지 지급.

중요한 설계 원칙:
1. 완료 여부·XP·배지는 항상 이 파일의 함수가 서버에서 계산한다. API 계층은
   클라이언트가 보낸 값을 신뢰하지 않고 이 함수들의 반환값만 사용한다.
2. 미션 완료(UserMissionProgress)와 배지 획득(UserBadge)의 중복 방지는 각각
   DB unique 제약이 최종 방어선이다 — SAVEPOINT 안에서 삽입을 시도하고
   IntegrityError를 잡아 "이미 완료됨"으로 수렴시킨다(Instrument 동시성 수정과
   같은 패턴, app/domain/services/market_data.py의 upsert_instrument 참고).
3. LESSON_COMPLETE/QUIZ_PASS는 챌린지 시작 전에 이미 끝냈어도 인정한다(같은
   이해를 다시 확인시키는 것은 불필요한 마찰이다). 그 외 "이번에 실제로
   행동했는지"를 확인하는 미션(일지 작성, 주문 미리보기 연결, 복기, AI 코칭
   확인)은 챌린지 시작 시각 이후에 생성된 증거만 인정한다 — 챌린지 시작 전의
   오래된 일지 하나로 여러 Day를 즉시 완료해버리는 것을 막는다.
"""

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DbSession

from app.domain.ai import AiConversation, AiMessage
from app.domain.challenge import (
    USER_CHALLENGE_ACTIVE,
    USER_CHALLENGE_COMPLETED,
    BadgeDefinition,
    Challenge,
    ChallengeDay,
    ChallengeMission,
    UserBadge,
    UserChallenge,
    UserChallengeDay,
    UserMissionProgress,
)
from app.domain.journal import JournalEntry
from app.domain.learning import LessonProgress, QuizAttempt
from app.domain.market import Instrument
from app.domain.portfolio import Portfolio, Position
from app.domain.services import coaching, execution, gamification

DEFAULT_TIMEZONE = "Asia/Seoul"
EXPIRY_GRACE_DAYS = 14  # 마지막 Day 이후 이만큼 더 지나도 완료 못 하면 조회 시 EXPIRED로 표시(저장은 안 함)
CHALLENGE_COMPLETE_BONUS_XP = 50
XP_REASON_MISSION = "CHALLENGE_MISSION"
XP_REASON_COMPLETE = "CHALLENGE_COMPLETE"

# "이번에 실제로 행동했는지"를 확인해야 하는 미션 유형 — 챌린지 시작 이후 생성된
# 증거만 인정한다. LESSON_COMPLETE/QUIZ_PASS/PORTFOLIO_CONCENTRATION_REVIEW/
# BIAS_REVIEW는 여기 없다(전자 둘은 이전 완료도 인정, 후자 둘은 매번 그 자리에서
# 새로 계산되므로 "오래된 증거 재사용" 자체가 성립하지 않는다).
_WINDOW_RESTRICTED_EVIDENCE_TYPES = {"JournalEntry", "AiMessage"}


class ChallengeError(Exception):
    """사용자에게 보여줄 수 있는 챌린지 서비스 오류의 베이스."""


class ChallengeNotFoundError(ChallengeError):
    pass


class AlreadyStartedError(ChallengeError):
    pass


class NotStartedError(ChallengeError):
    pass


class DayLockedError(ChallengeError):
    pass


class InvalidTimezoneError(ChallengeError):
    pass


# --- timezone / day 판단 ---


def _zone(tz_name: str) -> ZoneInfo:
    try:
        return ZoneInfo(tz_name)
    except ZoneInfoNotFoundError as exc:
        raise InvalidTimezoneError(f"알 수 없는 timezone입니다: {tz_name}") from exc


def validate_timezone(tz_name: str) -> str:
    _zone(tz_name)  # 유효성만 확인 — DST 유무와 무관하게 zoneinfo가 변환을 책임진다.
    return tz_name


def local_date(now_utc: datetime, tz_name: str) -> date:
    """UTC 시각을 사용자 timezone으로 변환한 "그 날짜". DST 전환이 있는
    timezone도 zoneinfo가 올바르게 처리한다 — 서버 시간이 아니라 이 값으로
    Day 경계를 판단한다."""
    return now_utc.astimezone(_zone(tz_name)).date()


def current_day_number(user_challenge: UserChallenge, now_utc: datetime | None = None) -> int:
    """오늘이 이 챌린지의 며칠째인지(1부터 시작). total_days를 넘지 않게
    clamp한다 — 그 이상의 Day는 애초에 존재하지 않는다."""
    now_utc = now_utc or datetime.now(timezone.utc)
    today_local = local_date(now_utc, user_challenge.timezone)
    elapsed = (today_local - user_challenge.started_date_local).days
    day_number = elapsed + 1
    return max(1, day_number)


def effective_status(user_challenge: UserChallenge, total_days: int, now_utc: datetime | None = None) -> str:
    """DB에는 ACTIVE/COMPLETED만 저장한다(모듈 docstring 참고). EXPIRED는
    배경 작업 없이 조회 시점에 계산한다."""
    if user_challenge.status == USER_CHALLENGE_COMPLETED:
        return USER_CHALLENGE_COMPLETED
    now_utc = now_utc or datetime.now(timezone.utc)
    today_local = local_date(now_utc, user_challenge.timezone)
    days_since_start = (today_local - user_challenge.started_date_local).days
    if days_since_start > (total_days - 1) + EXPIRY_GRACE_DAYS:
        return "EXPIRED"
    return USER_CHALLENGE_ACTIVE


def day_status(
    day_number: int,
    current_day: int,
    completed_at: datetime | None,
    has_any_progress: bool,
) -> str:
    if day_number > current_day:
        return "LOCKED"
    if completed_at is not None:
        return "COMPLETED"
    if has_any_progress:
        return "IN_PROGRESS"
    return "AVAILABLE"


# --- 챌린지 시작·조회 ---


def get_published_challenge_by_code(db: DbSession, code: str) -> Challenge:
    challenge = db.query(Challenge).filter(Challenge.code == code, Challenge.status == "PUBLISHED").first()
    if challenge is None:
        raise ChallengeNotFoundError(f"챌린지를 찾을 수 없습니다: {code}")
    return challenge


def get_user_challenge_or_none(db: DbSession, user_id: UUID, challenge_id: UUID) -> UserChallenge | None:
    return (
        db.query(UserChallenge)
        .filter(UserChallenge.user_id == user_id, UserChallenge.challenge_id == challenge_id)
        .first()
    )


def start_challenge(db: DbSession, user_id: UUID, challenge_id: UUID, timezone_name: str) -> UserChallenge:
    """이미 시작한 적이 있으면 AlreadyStartedError. (user_id, challenge_id)
    unique 제약이 동시 요청에서도 중복 시작을 막는 최종 방어선이다."""
    challenge = db.query(Challenge).filter(Challenge.id == challenge_id).first()
    if challenge is None:
        raise ChallengeNotFoundError("챌린지를 찾을 수 없습니다.")

    validate_timezone(timezone_name)
    now = datetime.now(timezone.utc)
    user_challenge = UserChallenge(
        user_id=user_id,
        challenge_id=challenge_id,
        challenge_version=challenge.version,
        timezone=timezone_name,
        status=USER_CHALLENGE_ACTIVE,
        started_at=now,
        started_date_local=local_date(now, timezone_name),
    )
    db.add(user_challenge)
    try:
        with db.begin_nested():
            db.flush()
    except IntegrityError as exc:
        db.rollback()
        existing = get_user_challenge_or_none(db, user_id, challenge_id)
        if existing is None:
            raise
        raise AlreadyStartedError("이미 시작한 챌린지입니다.") from exc

    for day_number in range(1, challenge.total_days + 1):
        db.add(UserChallengeDay(user_challenge_id=user_challenge.id, day_number=day_number))
    return user_challenge


# --- 미션 근거 검증 ---


@dataclass
class VerificationResult:
    ok: bool
    reason: str | None = None
    evidence_type: str = "NONE"
    evidence_id: UUID | None = None
    evidence_payload: dict | None = None
    extra: dict = field(default_factory=dict)


def _own_journal_or_none(db: DbSession, user_id: UUID, journal_id) -> JournalEntry | None:
    return db.query(JournalEntry).filter(JournalEntry.id == journal_id, JournalEntry.user_id == user_id).first()


def _verify_lesson_complete(db, user_id, user_challenge, mission, payload) -> VerificationResult:
    lesson_id = mission.config.get("lesson_id")
    progress = (
        db.query(LessonProgress)
        .filter(LessonProgress.user_id == user_id, LessonProgress.lesson_id == lesson_id, LessonProgress.status == "COMPLETED")
        .first()
    )
    if progress is None:
        return VerificationResult(ok=False, reason="아직 이 강의를 완료하지 않았습니다.")
    return VerificationResult(ok=True, evidence_type="LessonProgress", evidence_id=progress.id)


def _verify_quiz_pass(db, user_id, user_challenge, mission, payload) -> VerificationResult:
    quiz_id = mission.config.get("quiz_id")
    attempt = (
        db.query(QuizAttempt)
        .filter(QuizAttempt.user_id == user_id, QuizAttempt.quiz_id == quiz_id, QuizAttempt.passed.is_(True))
        .order_by(QuizAttempt.attempted_at.desc())
        .first()
    )
    if attempt is None:
        return VerificationResult(ok=False, reason="아직 이 퀴즈를 통과하지 못했습니다.")
    return VerificationResult(ok=True, evidence_type="QuizAttempt", evidence_id=attempt.id)


def _verify_goal_note(db, user_id, user_challenge, mission, payload) -> VerificationResult:
    note = (payload or {}).get("note", "")
    min_length = int(mission.config.get("min_length", 5))
    if not isinstance(note, str) or len(note.strip()) < min_length:
        return VerificationResult(ok=False, reason=f"{min_length}자 이상 입력해야 합니다.")
    return VerificationResult(ok=True, evidence_type="USER_INPUT", evidence_payload={"note": note.strip()})


def _run_preview(db, user_id, portfolio_id, instrument_id, side, order_type, quantity, limit_price):
    from app.core.config import get_settings

    settings = get_settings()
    portfolio = db.query(Portfolio).filter(Portfolio.id == portfolio_id, Portfolio.user_id == user_id).first()
    if portfolio is None:
        return None, "본인 소유 포트폴리오가 아닙니다."
    instrument = db.query(Instrument).filter(Instrument.id == instrument_id).first()
    if instrument is None:
        return None, "종목을 찾을 수 없습니다."
    try:
        quote = execution.build_quote(
            db, portfolio, instrument, side, order_type, Decimal(str(quantity)),
            Decimal(str(limit_price)) if limit_price is not None else None,
            settings.market_data_staleness_threshold_seconds,
        )
    except execution.ExecutionError as exc:
        return None, str(exc)
    return quote, None


def _verify_order_preview(db, user_id, user_challenge, mission, payload) -> VerificationResult:
    payload = payload or {}
    required = ["portfolio_id", "instrument_id", "side", "order_type", "quantity"]
    if any(k not in payload for k in required):
        return VerificationResult(ok=False, reason="주문 미리보기에 필요한 정보가 부족합니다.")
    quote, error = _run_preview(
        db, user_id, payload["portfolio_id"], payload["instrument_id"], payload["side"], payload["order_type"],
        payload["quantity"], payload.get("limit_price"),
    )
    if quote is None:
        return VerificationResult(ok=False, reason=error)
    return VerificationResult(
        ok=True,
        evidence_type="ORDER_PREVIEW_COMPUTED",
        evidence_payload={"instrument_id": str(payload["instrument_id"])},
        extra={
            "reference_price": str(quote.reference_price),
            "estimated_fill_price": str(quote.fill_price),
            "estimated_cash_impact": str(quote.cash_impact_portfolio_ccy),
        },
    )


def _within_challenge_window(user_challenge: UserChallenge, created_at: datetime) -> bool:
    return created_at >= user_challenge.started_at


_PRE_TRADE_FIELDS = ("thesis", "counter_evidence", "stop_loss_condition")


def _pre_trade_journal_complete(journal: JournalEntry) -> bool:
    if not journal.thesis or not journal.stop_loss_condition:
        return False
    if not journal.counter_evidence or len(journal.counter_evidence) == 0:
        return False
    return True


def _verify_journal_pre_trade(db, user_id, user_challenge, mission, payload) -> VerificationResult:
    journal_id = (payload or {}).get("journal_id")
    journal = _own_journal_or_none(db, user_id, journal_id) if journal_id else None
    if journal is None:
        return VerificationResult(ok=False, reason="본인 소유의 거래 전 일지를 찾을 수 없습니다.")
    if not _within_challenge_window(user_challenge, journal.created_at):
        return VerificationResult(ok=False, reason="챌린지 시작 이후에 작성한 일지여야 합니다.")
    if not _pre_trade_journal_complete(journal):
        return VerificationResult(ok=False, reason="매수 근거·반대 근거·손실 제한 조건을 모두 작성해야 합니다.")
    return VerificationResult(ok=True, evidence_type="JournalEntry", evidence_id=journal.id)


def _portfolio_concentration_snapshot(db: DbSession, portfolio: Portfolio) -> dict:
    from app.domain.constants import BAR_INTERVAL_DAILY

    cash = execution.get_cash_balance(db, portfolio.id, portfolio.base_currency)
    positions = db.query(Position).filter(Position.portfolio_id == portfolio.id, Position.quantity > 0).all()
    total = cash
    weights: dict[str, str] = {}
    values: dict[str, Decimal] = {}
    for position in positions:
        instrument = db.query(Instrument).filter(Instrument.id == position.instrument_id).first()
        if instrument is None:
            continue
        bar = execution.get_latest_bar(db, position.instrument_id, interval=BAR_INTERVAL_DAILY)
        if bar is None:
            continue
        fx_rate = execution.get_fx_mid_rate(db, instrument.currency, portfolio.base_currency)
        if fx_rate is None:
            continue
        value = Decimal(bar.close) * Decimal(position.quantity) * fx_rate
        values[instrument.ticker] = value
        total += value
    if total > 0:
        for ticker, value in values.items():
            weights[ticker] = str((value / total * 100).quantize(Decimal("0.01")))
    return {"total_assets": str(total), "position_weights_pct": weights}


def _verify_portfolio_concentration_review(db, user_id, user_challenge, mission, payload) -> VerificationResult:
    portfolio = db.query(Portfolio).filter(Portfolio.user_id == user_id).first()
    if portfolio is None:
        return VerificationResult(ok=False, reason="포트폴리오를 찾을 수 없습니다.")
    snapshot = _portfolio_concentration_snapshot(db, portfolio)
    return VerificationResult(ok=True, evidence_type="PORTFOLIO_CONCENTRATION_COMPUTED", extra=snapshot)


def _verify_scenario_choice(db, user_id, user_challenge, mission, payload) -> VerificationResult:
    choice = (payload or {}).get("choice")
    correct = mission.config.get("correct_choice")
    if choice is None:
        return VerificationResult(ok=False, reason="선택지를 골라야 합니다.")
    if choice != correct:
        return VerificationResult(
            ok=False, reason="다시 생각해보세요.", extra={"explanation": mission.config.get("explanation", "")}
        )
    return VerificationResult(ok=True, evidence_type="USER_INPUT", evidence_payload={"choice": choice})


def _verify_order_preview_linked_journal(db, user_id, user_challenge, mission, payload) -> VerificationResult:
    payload = payload or {}
    journal_id = payload.get("journal_id")
    journal = _own_journal_or_none(db, user_id, journal_id) if journal_id else None
    if journal is None:
        return VerificationResult(ok=False, reason="본인 소유의 거래 전 일지를 찾을 수 없습니다.")
    if not _within_challenge_window(user_challenge, journal.created_at):
        return VerificationResult(ok=False, reason="챌린지 시작 이후에 작성한 일지여야 합니다.")
    if not _pre_trade_journal_complete(journal):
        return VerificationResult(ok=False, reason="유효한 거래 전 일지가 아닙니다.")

    portfolio = db.query(Portfolio).filter(Portfolio.user_id == user_id).first()
    if portfolio is None:
        return VerificationResult(ok=False, reason="포트폴리오를 찾을 수 없습니다.")
    quote, error = _run_preview(
        db, user_id, str(portfolio.id), str(journal.instrument_id), payload.get("side", "BUY"),
        payload.get("order_type", "MARKET"), payload.get("quantity", "1"), payload.get("limit_price"),
    )
    if quote is None:
        return VerificationResult(ok=False, reason=error)
    return VerificationResult(
        ok=True,
        evidence_type="JournalEntry",
        evidence_id=journal.id,
        evidence_payload={"preview_computed": True},
        extra={"estimated_cash_impact": str(quote.cash_impact_portfolio_ccy)},
    )


def _verify_disclosure_ack(db, user_id, user_challenge, mission, payload) -> VerificationResult:
    if not (payload or {}).get("acknowledged"):
        return VerificationResult(ok=False, reason="가상자금·모의투자 고지를 확인해야 합니다.")
    return VerificationResult(ok=True, evidence_type="USER_INPUT", evidence_payload={"acknowledged": True})


def _verify_bias_review(db, user_id, user_challenge, mission, payload) -> VerificationResult:
    observations = coaching.detect_biases(db, user_id)
    return VerificationResult(ok=True, evidence_type="BIAS_REPORT_COMPUTED", extra={"observations": observations})


def _verify_coaching_confirm(db, user_id, user_challenge, mission, payload) -> VerificationResult:
    message = (
        db.query(AiMessage)
        .join(AiConversation, AiMessage.conversation_id == AiConversation.id)
        .filter(
            AiConversation.user_id == user_id,
            AiMessage.role == "ASSISTANT",
            AiMessage.created_at >= user_challenge.started_at,
        )
        .order_by(AiMessage.created_at.desc())
        .first()
    )
    if message is None:
        return VerificationResult(ok=False, reason="AI 코칭 확인 기록이 없습니다.")
    return VerificationResult(ok=True, evidence_type="AiMessage", evidence_id=message.id)


def _verify_post_trade_review(db, user_id, user_challenge, mission, payload) -> VerificationResult:
    journal_id = (payload or {}).get("journal_id")
    journal = _own_journal_or_none(db, user_id, journal_id) if journal_id else None
    if journal is None:
        return VerificationResult(ok=False, reason="본인 소유의 일지를 찾을 수 없습니다.")
    if not _within_challenge_window(user_challenge, journal.created_at):
        return VerificationResult(ok=False, reason="챌린지 시작 이후에 작성한 일지여야 합니다.")
    if journal.followed_plan is None:
        return VerificationResult(ok=False, reason="계획 준수 여부를 기록해야 합니다.")
    reflection_fields = [journal.expectation_gap, journal.behavior_to_repeat, journal.behavior_to_change, journal.luck_contribution]
    if sum(1 for f in reflection_fields if f) < 2:
        return VerificationResult(ok=False, reason="거래 후 복기 내용을 더 채워야 합니다.")
    return VerificationResult(ok=True, evidence_type="JournalEntry", evidence_id=journal.id)


def _verify_process_score_check(db, user_id, user_challenge, mission, payload) -> VerificationResult:
    journal_id = (payload or {}).get("journal_id")
    journal = _own_journal_or_none(db, user_id, journal_id) if journal_id else None
    if journal is None:
        return VerificationResult(ok=False, reason="본인 소유의 일지를 찾을 수 없습니다.")
    if journal.process_score is None:
        return VerificationResult(ok=False, reason="아직 과정 점수가 계산되지 않았습니다.")
    return VerificationResult(
        ok=True, evidence_type="JournalEntry", evidence_id=journal.id, extra={"process_score": str(journal.process_score)}
    )


_MISSION_VERIFIERS = {
    "LESSON_COMPLETE": _verify_lesson_complete,
    "QUIZ_PASS": _verify_quiz_pass,
    "GOAL_NOTE": _verify_goal_note,
    "ORDER_PREVIEW": _verify_order_preview,
    "JOURNAL_PRE_TRADE": _verify_journal_pre_trade,
    "PORTFOLIO_CONCENTRATION_REVIEW": _verify_portfolio_concentration_review,
    "SCENARIO_CHOICE": _verify_scenario_choice,
    "ORDER_PREVIEW_LINKED_JOURNAL": _verify_order_preview_linked_journal,
    "DISCLOSURE_ACK": _verify_disclosure_ack,
    "BIAS_REVIEW": _verify_bias_review,
    "COACHING_CONFIRM": _verify_coaching_confirm,
    "POST_TRADE_REVIEW": _verify_post_trade_review,
    "PROCESS_SCORE_CHECK": _verify_process_score_check,
}


@dataclass
class MissionVerifyOutcome:
    already_completed: bool
    result: VerificationResult
    progress: UserMissionProgress | None
    xp_awarded: int
    day_completed: bool
    challenge_completed: bool
    newly_awarded_badges: list[UserBadge] = field(default_factory=list)


def verify_mission(
    db: DbSession, user_id: UUID, user_challenge: UserChallenge, mission: ChallengeMission,
    challenge_day: ChallengeDay, payload: dict | None,
) -> MissionVerifyOutcome:
    existing = (
        db.query(UserMissionProgress)
        .filter(UserMissionProgress.user_challenge_id == user_challenge.id, UserMissionProgress.challenge_mission_id == mission.id)
        .first()
    )
    if existing is not None:
        # 이미 완료된 미션의 재검증은 idempotent하다 — 다시 채점하거나 XP를
        # 더 지급하지 않고 기존 결과를 그대로 돌려준다.
        return MissionVerifyOutcome(
            already_completed=True,
            result=VerificationResult(ok=True, evidence_type=existing.evidence_type, evidence_id=existing.evidence_id),
            progress=existing, xp_awarded=0, day_completed=False,
            challenge_completed=user_challenge.completed_at is not None,
        )

    today = current_day_number(user_challenge)
    if challenge_day.day_number > today:
        raise DayLockedError(f"Day {challenge_day.day_number}는 아직 잠겨 있습니다(현재 Day {today}).")

    verifier = _MISSION_VERIFIERS.get(mission.mission_type)
    if verifier is None:
        return MissionVerifyOutcome(
            already_completed=False, result=VerificationResult(ok=False, reason="지원하지 않는 미션 유형입니다."),
            progress=None, xp_awarded=0, day_completed=False, challenge_completed=False,
        )

    result = verifier(db, user_id, user_challenge, mission, payload)
    if not result.ok:
        return MissionVerifyOutcome(
            already_completed=False, result=result, progress=None, xp_awarded=0,
            day_completed=False, challenge_completed=False,
        )

    now = datetime.now(timezone.utc)
    progress = UserMissionProgress(
        user_challenge_id=user_challenge.id, challenge_mission_id=mission.id, completed_at=now,
        evidence_type=result.evidence_type, evidence_id=result.evidence_id, evidence_payload=result.evidence_payload,
        xp_awarded=0,
    )
    db.add(progress)
    try:
        with db.begin_nested():
            db.flush()
    except IntegrityError:
        db.rollback()
        existing = (
            db.query(UserMissionProgress)
            .filter(UserMissionProgress.user_challenge_id == user_challenge.id, UserMissionProgress.challenge_mission_id == mission.id)
            .first()
        )
        return MissionVerifyOutcome(
            already_completed=True, result=result, progress=existing, xp_awarded=0, day_completed=False,
            challenge_completed=user_challenge.completed_at is not None,
        )

    xp_awarded = gamification.award_xp(db, user_id, mission.xp_amount, XP_REASON_MISSION, mission.id)
    progress.xp_awarded = xp_awarded

    day_completed, challenge_completed = _mark_day_and_challenge_progress(db, user_id, user_challenge, challenge_day)
    # 배지 조건은 day/challenge 완료 여부와 무관하게 미션 하나만으로도 충족될 수
    # 있으므로(예: 첫걸음 배지는 Day1 미션 하나만 봄) 매 성공적인 검증 뒤에 평가한다.
    newly_awarded = evaluate_and_award_badges(db, user_id)

    return MissionVerifyOutcome(
        already_completed=False, result=result, progress=progress, xp_awarded=xp_awarded,
        day_completed=day_completed, challenge_completed=challenge_completed, newly_awarded_badges=newly_awarded,
    )


def _all_required_missions_completed(db: DbSession, user_challenge: UserChallenge) -> bool:
    """이 챌린지 전체(모든 Day)의 필수 미션이 이 user_challenge에서 다 끝났는지
    확인한다. 마지막 Day의 미션만 몰아서 끝내고 앞선 Day를 건너뛴 상태로
    "7일 완주"가 되는 것을 막기 위한 전역 체크다."""
    required_mission_ids = {
        m.id for m in db.query(ChallengeMission.id).join(
            ChallengeDay, ChallengeMission.challenge_day_id == ChallengeDay.id
        ).filter(ChallengeDay.challenge_id == user_challenge.challenge_id, ChallengeMission.is_required.is_(True))
    }
    if not required_mission_ids:
        return False
    completed_mission_ids = {
        p.challenge_mission_id for p in db.query(UserMissionProgress.challenge_mission_id).filter(
            UserMissionProgress.user_challenge_id == user_challenge.id,
            UserMissionProgress.challenge_mission_id.in_(required_mission_ids),
        )
    }
    return required_mission_ids.issubset(completed_mission_ids)


def _mark_day_and_challenge_progress(
    db: DbSession, user_id: UUID, user_challenge: UserChallenge, challenge_day: ChallengeDay
) -> tuple[bool, bool]:
    required_mission_ids = {
        m.id for m in db.query(ChallengeMission).filter(
            ChallengeMission.challenge_day_id == challenge_day.id, ChallengeMission.is_required.is_(True)
        )
    }
    completed_mission_ids = {
        p.challenge_mission_id for p in db.query(UserMissionProgress).filter(
            UserMissionProgress.user_challenge_id == user_challenge.id,
            UserMissionProgress.challenge_mission_id.in_(required_mission_ids),
        )
    }
    day_completed = required_mission_ids.issubset(completed_mission_ids) and len(required_mission_ids) > 0
    now = datetime.now(timezone.utc)

    user_day = (
        db.query(UserChallengeDay)
        .filter(UserChallengeDay.user_challenge_id == user_challenge.id, UserChallengeDay.day_number == challenge_day.day_number)
        .first()
    )
    if user_day is not None and user_day.completed_at is None and day_completed:
        user_day.completed_at = now

    challenge_completed = False
    if day_completed and _all_required_missions_completed(db, user_challenge):
        # 이 챌린지의 모든 Day에 걸친 필수 미션이 전부 끝났다 — 특정 Day
        # 번호가 아니라 "필수 미션 전체 완료"를 기준으로 삼는다. Day를
        # 건너뛰고 마지막 Day만 몰아서 끝내는 것으로는 완주 처리되지
        # 않게 하기 위함이다. compare-and-swap으로 완료 처리는 정확히
        # 한 번만 일어나게 한다(동시 요청 두 개가 동시에 "마지막 미션"을
        # 완료해도 보너스 XP·배지가 두 번 지급되지 않는다).
        result = (
            db.query(UserChallenge)
            .filter(UserChallenge.id == user_challenge.id, UserChallenge.completed_at.is_(None))
            .update({"completed_at": now, "status": USER_CHALLENGE_COMPLETED})
        )
        if result:
            db.flush()
            gamification.award_xp(db, user_id, CHALLENGE_COMPLETE_BONUS_XP, XP_REASON_COMPLETE, user_challenge.id)
            challenge_completed = True
            db.refresh(user_challenge)
    return day_completed, challenge_completed


# --- 배지 ---


def _badge_first_lesson_complete(db, user_id, config) -> tuple[bool, str, UUID | None]:
    row = (
        db.query(LessonProgress)
        .filter(LessonProgress.user_id == user_id, LessonProgress.status == "COMPLETED")
        .order_by(LessonProgress.completed_at.asc())
        .first()
    )
    return (row is not None, "LessonProgress", row.id if row else None)


def _badge_journal_field_present(db, user_id, config) -> tuple[bool, str, UUID | None]:
    field_name = config["field"]
    query = db.query(JournalEntry).filter(JournalEntry.user_id == user_id)
    if config.get("require_list_nonempty"):
        row = next((j for j in query.all() if getattr(j, field_name) and len(getattr(j, field_name)) > 0), None)
    elif config.get("require_true"):
        row = query.filter(getattr(JournalEntry, field_name).is_(True)).first()
    else:
        row = query.filter(getattr(JournalEntry, field_name).isnot(None)).first()
    return (row is not None, "JournalEntry", row.id if row else None)


def _badge_three_distinct_learning_days(db, user_id, config) -> tuple[bool, str, UUID | None]:
    rows = (
        db.query(func.date(LessonProgress.completed_at).label("d"))
        .filter(LessonProgress.user_id == user_id, LessonProgress.completed_at.isnot(None))
        .distinct()
        .all()
    )
    ok = len(rows) >= 3
    return (ok, "LessonProgress", None)


def _badge_seven_day_challenge_complete(db, user_id, config) -> tuple[bool, str, UUID | None]:
    challenge = db.query(Challenge).filter(Challenge.code == config["challenge_code"]).first()
    if challenge is None:
        return (False, "UserChallenge", None)
    row = (
        db.query(UserChallenge)
        .filter(UserChallenge.user_id == user_id, UserChallenge.challenge_id == challenge.id, UserChallenge.completed_at.isnot(None))
        .first()
    )
    return (row is not None, "UserChallenge", row.id if row else None)


def _badge_mission_type_completed(db, user_id, config) -> tuple[bool, str, UUID | None]:
    query = db.query(UserMissionProgress).join(
        ChallengeMission, UserMissionProgress.challenge_mission_id == ChallengeMission.id
    ).join(UserChallenge, UserMissionProgress.user_challenge_id == UserChallenge.id).filter(UserChallenge.user_id == user_id)
    if config.get("mission_type"):
        query = query.filter(ChallengeMission.mission_type == config["mission_type"])
    if config.get("mission_code"):
        query = query.filter(ChallengeMission.code == config["mission_code"])
    row = query.first()
    return (row is not None, "UserMissionProgress", row.id if row else None)


_BADGE_EVALUATORS = {
    "FIRST_LESSON_COMPLETE": _badge_first_lesson_complete,
    "JOURNAL_FIELD_PRESENT": _badge_journal_field_present,
    "THREE_DISTINCT_LEARNING_DAYS": _badge_three_distinct_learning_days,
    "SEVEN_DAY_CHALLENGE_COMPLETE": _badge_seven_day_challenge_complete,
    "MISSION_TYPE_COMPLETED": _badge_mission_type_completed,
}


def evaluate_and_award_badges(db: DbSession, user_id: UUID) -> list[UserBadge]:
    """조건을 만족하는 아직 못 받은 배지를 평가해 지급한다. 이미 받은 배지는
    다시 평가하지 않는다(중복 지급 방지 + 조건이 나중에 바뀌어도 이미 받은
    배지에 영향 없음)."""
    already_earned_ids = {b.badge_definition_id for b in db.query(UserBadge).filter(UserBadge.user_id == user_id)}
    candidates = db.query(BadgeDefinition).filter(BadgeDefinition.status == "PUBLISHED")

    newly_awarded: list[UserBadge] = []
    for badge in candidates:
        if badge.id in already_earned_ids:
            continue
        evaluator = _BADGE_EVALUATORS.get(badge.condition_type)
        if evaluator is None:
            continue
        ok, evidence_type, evidence_id = evaluator(db, user_id, badge.condition_config)
        if not ok:
            continue

        user_badge = UserBadge(
            user_id=user_id, badge_definition_id=badge.id, badge_version=badge.version,
            earned_at=datetime.now(timezone.utc), evidence_type=evidence_type, evidence_id=evidence_id,
            awarded_by="SYSTEM",
        )
        db.add(user_badge)
        try:
            with db.begin_nested():
                db.flush()
        except IntegrityError:
            db.rollback()
            continue
        newly_awarded.append(user_badge)
    return newly_awarded
