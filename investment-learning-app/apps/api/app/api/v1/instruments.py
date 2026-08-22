"""시장 데이터·종목. 명세서 6.4, 9.2 참고.

검색·상세·bars는 DB(instruments/bars)를 대상으로 동작한다. 실제 라이브 시세
수집은 `app/domain/services/market_data.py`에 구현되어 있지만, 이 개발 세션의
샌드박스에서는 아웃바운드가 차단되어 있어 지금 조회 가능한 데이터는 시드
마이그레이션의 샘플 값이다 — 응답의 `price_source`가 "seed-sample"이면 실거래
근거로 쓸 수 없는 데모 데이터라는 뜻이다.
"""

from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import case, func, or_
from sqlalchemy.orm import Session as DbSession

from app.api.v1.instrument_schemas import BarResponse, InstrumentDetail, InstrumentSummary
from app.core.db import get_db
from app.domain.constants import BAR_INTERVAL_DAILY
from app.domain.market import Bar, Instrument
from app.domain.services.execution import get_latest_bar
from app.domain.services.market_data import normalize_exchange

router = APIRouter()


@router.get("/instruments/search", response_model=list[InstrumentSummary])
def search_instruments(
    q: str = Query(default="", min_length=0, max_length=64),
    exchange: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    db: DbSession = Depends(get_db),
):
    query = db.query(Instrument).filter(Instrument.valid_to.is_(None))
    if exchange:
        query = query.filter(Instrument.exchange == normalize_exchange(exchange))

    order_columns = []
    stripped_q = q.strip()
    if stripped_q:
        normalized_q = stripped_q.upper()
        contains_pattern = f"%{stripped_q}%"
        prefix_pattern = f"{normalized_q}%"
        query = query.filter(or_(Instrument.ticker.ilike(contains_pattern), Instrument.name.ilike(contains_pattern)))
        # DB 종류에 따라 정렬 결과가 달라지지 않도록, "어느 정도로 일치하는가"를
        # 명시적인 순위 값으로 계산해 정렬 기준에 포함시킨다: ticker 정확히
        # 일치(0) > ticker로 시작(1) > 이름만 일치(2, 그 외 전부).
        match_rank = case(
            (func.upper(Instrument.ticker) == normalized_q, 0),
            (func.upper(Instrument.ticker).like(prefix_pattern), 1),
            else_=2,
        )
        order_columns.append(match_rank)

    # 동점일 때도 항상 같은 순서가 나오도록 exchange, ticker, 그리고 최종
    # tie-breaker로 id까지 명시한다 — DB가 보장하지 않는 "동점 행의 기본 순서"에
    # 의존하지 않는다.
    order_columns.extend([Instrument.exchange, Instrument.ticker, Instrument.id])
    instruments = query.order_by(*order_columns).limit(limit).all()
    return [InstrumentSummary.model_validate(i, from_attributes=True) for i in instruments]


def _to_detail(db: DbSession, instrument: Instrument) -> InstrumentDetail:
    bar = get_latest_bar(db, instrument.id, interval=BAR_INTERVAL_DAILY)
    return InstrumentDetail(
        id=instrument.id,
        ticker=instrument.ticker,
        exchange=instrument.exchange,
        currency=instrument.currency,
        name=instrument.name,
        industry=instrument.industry,
        is_tradable=instrument.is_tradable,
        last_price=Decimal(bar.close) if bar else None,
        price_as_of=bar.as_of if bar else None,
        price_source=bar.source if bar else None,
        delay_seconds=bar.delay_seconds if bar else None,
    )


@router.get("/instruments/{instrument_id}", response_model=InstrumentDetail)
def get_instrument(instrument_id: UUID, db: DbSession = Depends(get_db)):
    instrument = db.query(Instrument).filter(Instrument.id == instrument_id).first()
    if instrument is None:
        raise HTTPException(status_code=404, detail="종목을 찾을 수 없습니다.")
    return _to_detail(db, instrument)


@router.get("/instruments/{instrument_id}/bars", response_model=list[BarResponse])
def get_instrument_bars(
    instrument_id: UUID,
    interval: str = "1d",
    limit: int = Query(default=60, ge=1, le=500),
    db: DbSession = Depends(get_db),
):
    instrument = db.query(Instrument).filter(Instrument.id == instrument_id).first()
    if instrument is None:
        raise HTTPException(status_code=404, detail="종목을 찾을 수 없습니다.")

    bars = (
        db.query(Bar)
        .filter(Bar.instrument_id == instrument_id, Bar.interval == interval)
        .order_by(Bar.bar_start.desc())
        .limit(limit)
        .all()
    )
    return list(reversed(bars))


@router.get("/instruments/{instrument_id}/fundamentals")
def get_instrument_fundamentals(instrument_id: UUID):
    raise HTTPException(
        status_code=501,
        detail="Phase 3 확장에서 구현 예정 (docs/product-spec.md 6.4, 9.2) — fundamentals 데이터 소스 미정",
    )
