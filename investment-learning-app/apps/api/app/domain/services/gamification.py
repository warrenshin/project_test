"""XP 산정 규칙. 명세서 6.3 참고.

XP는 항상 서버가 계산하고, 손익·거래횟수가 아니라 학습·복기 등 '좋은 과정'에만
지급한다. 단순 반복으로 악용하지 못하도록 일일 상한을 둔다.
"""

from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session as DbSession

from app.domain.learning import XpLedger

XP_LESSON_COMPLETED = 10
XP_QUIZ_PASSED = 15
XP_DAILY_CAP = 100


def already_awarded(db: DbSession, user_id: UUID, reason: str, reference_id: UUID) -> bool:
    return (
        db.query(XpLedger)
        .filter(XpLedger.user_id == user_id, XpLedger.reason == reason, XpLedger.reference_id == reference_id)
        .first()
        is not None
    )


def today_xp_total(db: DbSession, user_id: UUID) -> int:
    today = datetime.now(timezone.utc).date()
    total = (
        db.query(func.coalesce(func.sum(XpLedger.amount), 0))
        .filter(XpLedger.user_id == user_id, func.date(XpLedger.awarded_at) == today)
        .scalar()
    )
    return int(total)


def award_xp(db: DbSession, user_id: UUID, amount: int, reason: str, reference_id: UUID) -> int:
    """일일 상한 내에서 XP를 지급하고 실제 지급량을 반환한다. 동일 reference_id에는 한 번만 지급한다."""
    if already_awarded(db, user_id, reason, reference_id):
        return 0

    remaining = max(0, XP_DAILY_CAP - today_xp_total(db, user_id))
    awarded = min(amount, remaining)
    if awarded <= 0:
        return 0

    db.add(
        XpLedger(
            user_id=user_id,
            amount=awarded,
            reason=reason,
            reference_id=reference_id,
            awarded_at=datetime.now(timezone.utc),
        )
    )
    return awarded


def current_streak_days(db: DbSession, user_id: UUID) -> int:
    """오늘 또는 어제부터 거슬러 올라가며 XP가 지급된 연속 일수를 센다."""
    rows = (
        db.query(func.date(XpLedger.awarded_at).label("d"))
        .filter(XpLedger.user_id == user_id)
        .distinct()
        .order_by(func.date(XpLedger.awarded_at).desc())
        .all()
    )
    active_dates = {row.d for row in rows}
    if not active_dates:
        return 0

    today = datetime.now(timezone.utc).date()
    cursor = today if today in active_dates else today - timedelta(days=1)
    if cursor not in active_dates:
        return 0

    streak = 0
    while cursor in active_dates:
        streak += 1
        cursor = cursor - timedelta(days=1)
    return streak
