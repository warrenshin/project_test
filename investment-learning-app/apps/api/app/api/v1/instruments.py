"""시장 데이터·종목. 명세서 6.4, 9.2 참고.

Phase 3에서 구현 예정: 종목 검색·상세·OHLCV, as_of/source/delay_seconds 필수 포함.
"""

from fastapi import APIRouter, HTTPException

router = APIRouter()

_NOT_IMPLEMENTED = "Phase 3에서 구현 예정 (docs/product-spec.md 6.4, 9.2)"


@router.get("/instruments/search")
def search_instruments(q: str = ""):
    raise HTTPException(status_code=501, detail=_NOT_IMPLEMENTED)


@router.get("/instruments/{instrument_id}")
def get_instrument(instrument_id: str):
    raise HTTPException(status_code=501, detail=_NOT_IMPLEMENTED)


@router.get("/instruments/{instrument_id}/bars")
def get_instrument_bars(instrument_id: str):
    raise HTTPException(status_code=501, detail=_NOT_IMPLEMENTED)
