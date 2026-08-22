"""인앱 알림(스텁). 실제 푸시(APNs/FCM 등) 연동은 이 범위 밖이다 — 여기서는
"지금 화면에 보여줄 것"만 매 조회 시점에 서버가 계산해서 돌려준다. 별도 알림
테이블이나 발송 큐를 두지 않는다: 상태(오늘 강의 미완료, 복기 대기 거래 등) 자체가
이미 서버에 있으므로, 그 상태를 읽어 그대로 알림 카드로 변환하면 충분하고, 이
편이 "실제 발송"이라는 오해를 만들지 않는다.

문구 원칙(반드시 지킬 것): 매수를 종용하거나("지금 매수하세요"), 조급함을
자극하거나("기회를 놓칩니다"), 손실 포지션에 추가 행동을 유도하거나, 시장
변동성을 이용해 다급함을 강조하는 표현을 쓰지 않는다. 전부 담담한 안내 문구다.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy.orm import Session as DbSession

from app.domain.challenge import UserBadge
from app.domain.journal import JournalEntry
from app.domain.services import challenge as challenge_service

BADGE_RECENCY_WINDOW = timedelta(hours=24)


@dataclass
class NotificationItem:
    type: str
    title: str
    body: str
    href: str


def _reviewable_trade_notification(db: DbSession, user_id: UUID) -> NotificationItem | None:
    journal = (
        db.query(JournalEntry)
        .filter(
            JournalEntry.user_id == user_id,
            JournalEntry.order_id.isnot(None),
            JournalEntry.followed_plan.is_(None),
        )
        .order_by(JournalEntry.actual_entry_at.desc())
        .first()
    )
    if journal is None:
        return None
    return NotificationItem(
        type="TRADE_REVIEW_DUE",
        title="복기를 기다리는 거래가 있어요",
        body="계획대로 진행됐는지 돌아보고 복기를 남겨보세요.",
        href=f"/journal/{journal.id}",
    )


_LESSON_LIKE_MISSION_TYPES = ("LESSON_COMPLETE", "QUIZ_PASS")


def _next_challenge_step_notification(db: DbSession, user_id: UUID) -> NotificationItem | None:
    """진행 중인 챌린지의 도달 가능한(잠기지 않은) Day 중 아직 완료하지 않은
    첫 필수 미션 하나를 알린다. 강의/퀴즈 미션이면 "오늘의 학습"으로, 그 외에는
    "챌린지 다음 단계"로 문구만 다르게 표시한다 — 같은 미션을 두 알림으로 중복
    표시하지 않는다."""
    user_challenge = (
        db.query(challenge_service.UserChallenge)
        .filter(
            challenge_service.UserChallenge.user_id == user_id,
            challenge_service.UserChallenge.completed_at.is_(None),
        )
        .order_by(challenge_service.UserChallenge.started_at.desc())
        .first()
    )
    if user_challenge is None:
        return None
    current_day = challenge_service.current_day_number(user_challenge)
    completed_ids = {
        p.challenge_mission_id
        for p in db.query(challenge_service.UserMissionProgress).filter(
            challenge_service.UserMissionProgress.user_challenge_id == user_challenge.id
        )
    }
    missions = (
        db.query(challenge_service.ChallengeMission)
        .join(
            challenge_service.ChallengeDay,
            challenge_service.ChallengeMission.challenge_day_id == challenge_service.ChallengeDay.id,
        )
        .filter(
            challenge_service.ChallengeDay.challenge_id == user_challenge.challenge_id,
            challenge_service.ChallengeDay.day_number <= current_day,
            challenge_service.ChallengeMission.is_required.is_(True),
        )
        .order_by(challenge_service.ChallengeDay.day_number, challenge_service.ChallengeMission.order_index)
        .all()
    )
    for m in missions:
        if m.id in completed_ids:
            continue
        if m.mission_type in _LESSON_LIKE_MISSION_TYPES:
            return NotificationItem(
                type="LESSON_DUE", title="오늘의 학습이 준비되어 있어요", body=m.title, href="/challenge"
            )
        return NotificationItem(
            type="CHALLENGE_STEP_DUE", title="챌린지 다음 단계가 남아있어요", body=m.title, href="/challenge"
        )
    return None


def _recent_badge_notifications(db: DbSession, user_id: UUID) -> list[NotificationItem]:
    cutoff = datetime.now(timezone.utc) - BADGE_RECENCY_WINDOW
    rows = (
        db.query(UserBadge, challenge_service.BadgeDefinition)
        .join(challenge_service.BadgeDefinition, UserBadge.badge_definition_id == challenge_service.BadgeDefinition.id)
        .filter(UserBadge.user_id == user_id, UserBadge.earned_at >= cutoff)
        .order_by(UserBadge.earned_at.desc())
        .all()
    )
    return [
        NotificationItem(
            type="BADGE_EARNED",
            title="새 배지를 획득했어요",
            body=definition.title,
            href="/badges",
        )
        for _, definition in rows
    ]


def get_notifications(db: DbSession, user_id: UUID) -> list[NotificationItem]:
    """이번 조회 시점 기준으로 보여줄 인앱 알림을 계산한다. 순서: 배지 획득(가장
    긍정적인 소식) → 챌린지 다음 단계(오늘의 학습 포함) → 복기 대기 거래."""
    items: list[NotificationItem] = []
    items.extend(_recent_badge_notifications(db, user_id))
    next_step = _next_challenge_step_notification(db, user_id)
    if next_step:
        items.append(next_step)
    trade = _reviewable_trade_notification(db, user_id)
    if trade:
        items.append(trade)
    return items
