"""시세 신선도 판단 (Phase A: stale valuation 안전성).

`execution.build_quote`(주문 경로)와 `api/v1/portfolios.py`(포트폴리오 조회
경로)가 "이 가격을 지금 써도 되는가"를 각자 다른 기준으로 판단하지 않도록,
판단 로직을 이 한 곳에 모은다. 두 경로 모두 같은 임계값
(`settings.market_data_staleness_threshold_seconds`)을 쓰되 판단 결과를
쓰는 방식만 다르다 — 주문은 STALE/UNAVAILABLE이면 거부하고, 포트폴리오는
STALE을 참고값으로 보여주되 UNAVAILABLE만 평가액 합계에서 제외한다.
"""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy.orm import Session as DbSession

from app.domain.constants import PRICE_STATUS_UNAVAILABLE
from app.domain.services.execution import get_latest_bar
from app.domain.services.market_data import classify_price_freshness


@dataclass
class PricePoint:
    """가격 + 그 가격을 신뢰해도 되는지에 대한 판단. `price`가 None이면
    `status`는 항상 UNAVAILABLE이다 — 호출측이 None을 0으로 오해해 손실처럼
    계산하지 않도록 status를 함께 반드시 확인하게 한다."""

    price: Decimal | None
    source: str | None
    as_of: datetime | None
    delay_seconds: int | None
    status: str  # PRICE_STATUS_*


def get_price_point(db: DbSession, instrument_id: UUID, staleness_threshold_seconds: int) -> PricePoint:
    bar = get_latest_bar(db, instrument_id)
    if bar is None:
        return PricePoint(price=None, source=None, as_of=None, delay_seconds=None, status=PRICE_STATUS_UNAVAILABLE)

    status = classify_price_freshness(bar.as_of, staleness_threshold_seconds)

    return PricePoint(
        price=Decimal(bar.close),
        source=bar.source,
        as_of=bar.as_of,
        delay_seconds=bar.delay_seconds,
        status=status,
    )
