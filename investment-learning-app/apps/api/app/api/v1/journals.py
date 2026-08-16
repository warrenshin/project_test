"""투자일지·과정 점수·편향 리포트. 명세서 6장 7절, 9.2 참고.

Phase 4에서 구현 예정: 거래 전/후 일지, 원문 버전 보존,
규칙 기반 process_score (7.3), 행동편향 탐지 (7.4).
"""

from fastapi import APIRouter, HTTPException

router = APIRouter()

_NOT_IMPLEMENTED = "Phase 4에서 구현 예정 (docs/product-spec.md 7장, 9.2)"


@router.post("/journals/pre-trade")
def create_pre_trade_journal():
    raise HTTPException(status_code=501, detail=_NOT_IMPLEMENTED)


@router.patch("/journals/{journal_id}")
def update_journal(journal_id: str):
    raise HTTPException(status_code=501, detail=_NOT_IMPLEMENTED)


@router.post("/journals/{journal_id}/post-trade")
def create_post_trade_review(journal_id: str):
    raise HTTPException(status_code=501, detail=_NOT_IMPLEMENTED)


@router.get("/journals/{journal_id}/coaching")
def get_journal_coaching(journal_id: str):
    raise HTTPException(status_code=501, detail=_NOT_IMPLEMENTED)


@router.get("/me/bias-report")
def get_bias_report():
    raise HTTPException(status_code=501, detail=_NOT_IMPLEMENTED)
