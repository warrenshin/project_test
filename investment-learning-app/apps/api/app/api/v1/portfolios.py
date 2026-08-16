"""모의투자 계좌·주문·체결. 명세서 6.5, 6.6, 6.7, 9.2, 9.3 참고.

Phase 3에서 구현 예정: 원장(ledger) 기반 잔고, 시장가·지정가 주문,
idempotency-key 필수, 8단계 서버 검증 순서(9.3) 준수.
"""

from fastapi import APIRouter, HTTPException

router = APIRouter()

_NOT_IMPLEMENTED = "Phase 3에서 구현 예정 (docs/product-spec.md 6.5-6.7, 9.2-9.3)"


@router.get("/portfolios/{portfolio_id}")
def get_portfolio(portfolio_id: str):
    raise HTTPException(status_code=501, detail=_NOT_IMPLEMENTED)


@router.get("/portfolios/{portfolio_id}/positions")
def get_positions(portfolio_id: str):
    raise HTTPException(status_code=501, detail=_NOT_IMPLEMENTED)


@router.get("/portfolios/{portfolio_id}/performance")
def get_performance(portfolio_id: str):
    raise HTTPException(status_code=501, detail=_NOT_IMPLEMENTED)


@router.post("/portfolios/{portfolio_id}/orders/preview")
def preview_order(portfolio_id: str):
    raise HTTPException(status_code=501, detail=_NOT_IMPLEMENTED)


@router.post("/portfolios/{portfolio_id}/orders")
def create_order(portfolio_id: str):
    raise HTTPException(status_code=501, detail=_NOT_IMPLEMENTED)


@router.get("/orders/{order_id}")
def get_order(order_id: str):
    raise HTTPException(status_code=501, detail=_NOT_IMPLEMENTED)


@router.post("/orders/{order_id}/cancel")
def cancel_order(order_id: str):
    raise HTTPException(status_code=501, detail=_NOT_IMPLEMENTED)
