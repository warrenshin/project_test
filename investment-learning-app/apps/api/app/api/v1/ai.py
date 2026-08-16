"""AI 투자교육 코치. 명세서 7.5-7.7, 9.2 참고.

Phase 4에서 구현 예정: 의도 분류 → 검색(RAG) → 정량 규칙 엔진 → LLM 설명 →
사실/인용/정책 검사 → 출처 표시 파이프라인 (7.6).
직접 매매지시·수익보장·개인화 투자추천은 정책 필터에서 차단한다 (7.5).
"""

from fastapi import APIRouter, HTTPException

router = APIRouter()

_NOT_IMPLEMENTED = "Phase 4에서 구현 예정 (docs/product-spec.md 7.5-7.7, 9.2)"


@router.post("/conversations")
def create_conversation():
    raise HTTPException(status_code=501, detail=_NOT_IMPLEMENTED)


@router.post("/conversations/{conversation_id}/messages")
def send_message(conversation_id: str):
    raise HTTPException(status_code=501, detail=_NOT_IMPLEMENTED)


@router.post("/messages/{message_id}/feedback")
def send_message_feedback(message_id: str):
    raise HTTPException(status_code=501, detail=_NOT_IMPLEMENTED)
