"""AI 투자교육 코치. 명세서 7.5-7.7, 9.2 참고.

의도 분류 -> 검색(RAG) -> 정량 규칙 엔진 -> LLM 설명 -> 사실/인용/정책 검사 ->
출처 표시 파이프라인은 app/domain/services/ai_coach.py에 구현되어 있다.
직접 매매지시·수익보장·개인화 투자추천은 정책 필터에서 차단한다 (7.5).

이 세션에서는 ANTHROPIC_API_KEY가 없어 실제 LLM 응답 경로를 라이브로 검증하지
못했다 — graceful degradation 경로(규칙 기반 폴백)는 테스트로 검증했다.
"""

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session as DbSession

from app.api.v1.ai_schemas import (
    ConversationCreateRequest,
    ConversationResponse,
    MessageCreateRequest,
    MessageFeedbackRequest,
    MessageResponse,
    SourceResponse,
)
from app.core.db import get_db
from app.core.deps import get_current_user
from app.domain.ai import AiConversation, AiMessage
from app.domain.journal import JournalEntry
from app.domain.services import ai_coach
from app.domain.user import User

router = APIRouter()


@router.post("/conversations", response_model=ConversationResponse, status_code=201)
def create_conversation(
    payload: ConversationCreateRequest,
    db: DbSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if payload.journal_id is not None:
        journal = (
            db.query(JournalEntry)
            .filter(JournalEntry.id == payload.journal_id, JournalEntry.user_id == current_user.id)
            .first()
        )
        if journal is None:
            raise HTTPException(status_code=404, detail="투자일지를 찾을 수 없습니다.")

    conversation = AiConversation(user_id=current_user.id, journal_id=payload.journal_id)
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    return ConversationResponse(id=conversation.id, journal_id=conversation.journal_id)


def _get_owned_conversation(db: DbSession, conversation_id: UUID, current_user: User) -> AiConversation:
    conversation = (
        db.query(AiConversation)
        .filter(AiConversation.id == conversation_id, AiConversation.user_id == current_user.id)
        .first()
    )
    if conversation is None:
        raise HTTPException(status_code=404, detail="대화를 찾을 수 없습니다.")
    return conversation


@router.post("/conversations/{conversation_id}/messages", response_model=MessageResponse, status_code=201)
def send_message(
    conversation_id: UUID,
    payload: MessageCreateRequest,
    db: DbSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    conversation = _get_owned_conversation(db, conversation_id, current_user)

    now = datetime.now(timezone.utc)
    db.add(
        AiMessage(
            conversation_id=conversation.id, role="USER", content=payload.content, degraded=False, created_at=now
        )
    )

    answer = ai_coach.generate_coach_answer(
        db, current_user.id, question=payload.content, journal_id=conversation.journal_id
    )

    assistant_message = AiMessage(
        conversation_id=conversation.id,
        role="ASSISTANT",
        content=answer.content,
        model=answer.model,
        prompt_version=answer.prompt_version,
        sources=answer.sources,
        safety_flags=answer.safety_flags,
        degraded=answer.degraded,
        created_at=datetime.now(timezone.utc),
    )
    db.add(assistant_message)
    db.commit()
    db.refresh(assistant_message)

    return MessageResponse(
        id=assistant_message.id,
        role=assistant_message.role,
        content=assistant_message.content,
        model=assistant_message.model,
        prompt_version=assistant_message.prompt_version,
        sources=[SourceResponse(**s) for s in (assistant_message.sources or [])],
        degraded=assistant_message.degraded,
        created_at=assistant_message.created_at,
    )


@router.post("/messages/{message_id}/feedback", status_code=204)
def send_message_feedback(
    message_id: UUID,
    payload: MessageFeedbackRequest,
    db: DbSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    message = (
        db.query(AiMessage)
        .join(AiConversation, AiMessage.conversation_id == AiConversation.id)
        .filter(AiMessage.id == message_id, AiConversation.user_id == current_user.id)
        .first()
    )
    if message is None:
        raise HTTPException(status_code=404, detail="메시지를 찾을 수 없습니다.")

    message.user_feedback = payload.feedback
    message.feedback_comment = payload.comment
    db.commit()
