"""투자일지·과정 점수·편향 리포트. 명세서 6장 7절, 9.2 참고.

거래 전/후 일지, 원문 버전 보존, 규칙 기반 process_score (7.3),
행동편향 탐지 (7.4)를 구현한다.
"""

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session as DbSession

from app.api.v1.journal_schemas import (
    BiasObservation,
    BiasReportResponse,
    CoachingSourceResponse,
    JournalCoachingResponse,
    JournalResponse,
    JournalUpdateRequest,
    PostTradeReviewRequest,
    PreTradeJournalCreateRequest,
)
from app.core.db import get_db
from app.core.deps import get_current_user
from app.domain.journal import JournalEntry, JournalVersion
from app.domain.market import Instrument
from app.domain.portfolio import Portfolio
from app.domain.services import ai_coach, coaching, execution
from app.domain.user import User

router = APIRouter()


def _get_owned_journal(db: DbSession, journal_id: UUID, current_user: User) -> JournalEntry:
    journal = db.query(JournalEntry).filter(JournalEntry.id == journal_id, JournalEntry.user_id == current_user.id).first()
    if journal is None:
        raise HTTPException(status_code=404, detail="투자일지를 찾을 수 없습니다.")
    return journal


def _snapshot_version(db: DbSession, journal: JournalEntry, author_type: str = "USER") -> None:
    """수정 전 현재 상태를 별도 버전으로 보존한다 (7.1: 최초 작성내용은 항상 별도 버전으로 보존)."""
    snapshot = {
        c.name: (str(getattr(journal, c.name)) if getattr(journal, c.name) is not None else None)
        for c in JournalEntry.__table__.columns
    }
    db.add(JournalVersion(journal_id=journal.id, author_type=author_type, content_snapshot=snapshot))


@router.post("/journals/pre-trade", response_model=JournalResponse, status_code=201)
def create_pre_trade_journal(
    payload: PreTradeJournalCreateRequest,
    db: DbSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    portfolio = db.query(Portfolio).filter(Portfolio.id == payload.portfolio_id).first()
    if portfolio is None or portfolio.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="포트폴리오를 찾을 수 없습니다.")

    instrument = db.query(Instrument).filter(Instrument.id == payload.instrument_id).first()
    if instrument is None:
        raise HTTPException(status_code=404, detail="종목을 찾을 수 없습니다.")

    bar = execution.get_latest_bar(db, instrument.id)
    market_snapshot = None
    if bar is not None:
        market_snapshot = {
            "close": str(bar.close),
            "as_of": bar.as_of.isoformat(),
            "source": bar.source,
            "delay_seconds": bar.delay_seconds,
        }

    journal = JournalEntry(
        user_id=current_user.id,
        portfolio_id=portfolio.id,
        instrument_id=instrument.id,
        order_id=payload.order_id,
        thesis=payload.thesis,
        supporting_evidence=payload.supporting_evidence,
        counter_evidence=payload.counter_evidence,
        expected_holding_period=payload.expected_holding_period,
        entry_condition=payload.entry_condition,
        target_condition=payload.target_condition,
        stop_loss_condition=payload.stop_loss_condition,
        planned_amount=payload.planned_amount,
        planned_weight_pct=payload.planned_weight_pct,
        confidence_level=payload.confidence_level,
        reference_links=payload.reference_links,
        market_data_snapshot=market_snapshot,
    )
    score, breakdown = coaching.compute_process_score(journal)
    journal.process_score = score
    journal.process_score_breakdown = breakdown

    db.add(journal)
    db.commit()
    db.refresh(journal)
    return JournalResponse.model_validate(journal, from_attributes=True)


@router.get("/me/journals", response_model=list[JournalResponse])
def list_my_journals(db: DbSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    """일지 목록 조회. 명세서 9.2에 명시적 목록은 없지만, 프런트엔드 일지 화면에 필요하다."""
    journals = (
        db.query(JournalEntry)
        .filter(JournalEntry.user_id == current_user.id)
        .order_by(JournalEntry.created_at.desc())
        .all()
    )
    return [JournalResponse.model_validate(j, from_attributes=True) for j in journals]


@router.get("/journals/{journal_id}", response_model=JournalResponse)
def get_journal(journal_id: UUID, db: DbSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    """일지 단건 조회. 명세서 9.2에 명시적 엔드포인트는 없지만, 프런트엔드 일지 화면에 필요하다."""
    journal = _get_owned_journal(db, journal_id, current_user)
    return JournalResponse.model_validate(journal, from_attributes=True)


@router.patch("/journals/{journal_id}", response_model=JournalResponse)
def update_journal(
    journal_id: UUID,
    payload: JournalUpdateRequest,
    db: DbSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    journal = _get_owned_journal(db, journal_id, current_user)
    _snapshot_version(db, journal, author_type="USER")

    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(journal, field, value)

    score, breakdown = coaching.compute_process_score(journal)
    journal.process_score = score
    journal.process_score_breakdown = breakdown

    db.commit()
    db.refresh(journal)
    return JournalResponse.model_validate(journal, from_attributes=True)


@router.post("/journals/{journal_id}/post-trade", response_model=JournalResponse)
def create_post_trade_review(
    journal_id: UUID,
    payload: PostTradeReviewRequest,
    db: DbSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    journal = _get_owned_journal(db, journal_id, current_user)
    _snapshot_version(db, journal, author_type="USER")

    journal.actual_entry_at = payload.actual_entry_at
    journal.actual_exit_at = payload.actual_exit_at
    journal.followed_plan = payload.followed_plan
    journal.plan_change_reason = payload.plan_change_reason
    journal.expectation_gap = payload.expectation_gap
    journal.luck_contribution = payload.luck_contribution
    journal.behavior_to_repeat = payload.behavior_to_repeat
    journal.behavior_to_change = payload.behavior_to_change
    journal.emotion_tags = payload.emotion_tags

    score, breakdown = coaching.compute_process_score(journal)
    journal.process_score = score
    journal.process_score_breakdown = breakdown

    db.commit()
    db.refresh(journal)
    return JournalResponse.model_validate(journal, from_attributes=True)


@router.get("/journals/{journal_id}/coaching", response_model=JournalCoachingResponse)
def get_journal_coaching(
    journal_id: UUID, db: DbSession = Depends(get_db), current_user: User = Depends(get_current_user)
):
    journal = _get_owned_journal(db, journal_id, current_user)
    answer = ai_coach.generate_coach_answer(
        db,
        current_user.id,
        question="이 투자일지의 과정 점수와 개선할 점을 설명해줘.",
        journal_id=journal.id,
    )
    return JournalCoachingResponse(
        process_score=journal.process_score,
        process_score_breakdown=journal.process_score_breakdown,
        content=answer.content,
        model=answer.model,
        prompt_version=answer.prompt_version,
        sources=[CoachingSourceResponse(**s) for s in answer.sources],
        degraded=answer.degraded,
    )


@router.get("/me/bias-report", response_model=BiasReportResponse)
def get_bias_report(db: DbSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    observations = coaching.detect_biases(db, current_user.id)
    return BiasReportResponse(observations=[BiasObservation(**o) for o in observations])
