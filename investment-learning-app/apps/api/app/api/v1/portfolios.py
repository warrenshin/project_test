"""모의투자 계좌·주문·체결. 명세서 6.5-6.7, 9.2, 9.3 참고.

서버 검증 순서는 9.3의 8단계를 따른다:
1. 사용자·포트폴리오 권한  2. 종목 거래 가능 여부  3. 주문 필드 검증(Pydantic)
4. 가상현금·보유수량  5. 중복 요청(Idempotency-Key)  6. 최신 데이터 상태
7. 주문 후 집중도 경고  8. 주문 이벤트 저장과 체결

비동기 체결 큐 워커(services/simulation-worker)가 아직 없어, 8단계의 "체결"은
이 요청 안에서 동기적으로 수행한다. LIMIT 주문이 즉시 체결 불가능하면 ACCEPTED
상태로 남으며, 새 시세가 들어올 때 재평가하는 것은 후속 작업이다.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DbSession

from app.api.v1.portfolio_schemas import (
    OrderCreateRequest,
    OrderPreviewRequest,
    OrderPreviewResponse,
    OrderResponse,
    PerformanceResponse,
    PortfolioResponse,
    PositionResponse,
)
from app.core.config import get_settings
from app.core.db import get_db
from app.core.deps import get_current_user
from app.domain.constants import (
    ORDER_ACCEPTED,
    ORDER_CANCELLED,
    ORDER_TERMINAL_STATUSES,
    PRICE_STATUS_FRESH,
    PRICE_STATUS_STALE,
    PRICE_STATUS_UNAVAILABLE,
)
from app.domain.journal import JournalEntry
from app.domain.market import Instrument
from app.domain.portfolio import Fill, LedgerEntry, Order, Portfolio, Position
from app.domain.services import execution
from app.domain.services.market_data_service import get_price_point
from app.domain.user import User

router = APIRouter()
settings = get_settings()


@dataclass
class _PositionEval:
    """포지션 하나를 한 번만 평가해 last_price/market_value/unrealized_pnl과
    Phase A 신선도 상태(FRESH/STALE/UNAVAILABLE)를 함께 담는다 — 여러 엔드포인트
    (positions/portfolio/performance)가 같은 평가를 반복하지 않게 한다."""

    position: Position
    instrument: Instrument | None
    last_price: Decimal | None
    market_value: Decimal | None
    unrealized_pnl: Decimal | None
    price_status: str
    price_as_of: datetime | None


def _evaluate_position(db: DbSession, portfolio: Portfolio, position: Position) -> _PositionEval:
    instrument = db.query(Instrument).filter(Instrument.id == position.instrument_id).first()
    if instrument is None:
        # 데이터 정합성상 있으면 안 되는 상태(포지션은 있는데 종목이 없음)지만,
        # 방어적으로 UNAVAILABLE로 처리하고 0원으로 계산하지 않는다.
        return _PositionEval(position, None, None, None, None, PRICE_STATUS_UNAVAILABLE, None)

    price_point = get_price_point(db, instrument.id, settings.market_data_staleness_threshold_seconds)
    if price_point.status == PRICE_STATUS_UNAVAILABLE:
        return _PositionEval(position, instrument, None, None, None, PRICE_STATUS_UNAVAILABLE, None)

    fx_rate = execution.get_fx_mid_rate(db, instrument.currency, portfolio.base_currency)
    if fx_rate is None:
        # 가격은 있지만 포트폴리오 통화로 환산할 환율이 없다 — 역시 평가 불가로
        # 취급한다(예전처럼 이 포지션을 조용히 목록에서 빼거나 합계에서만 빼고
        # 알리지 않던 것과 달리, price_status로 명확히 드러낸다).
        return _PositionEval(position, instrument, None, None, None, PRICE_STATUS_UNAVAILABLE, price_point.as_of)

    last_price = price_point.price * fx_rate
    market_value = last_price * Decimal(position.quantity)
    cost_basis = Decimal(position.average_cost) * fx_rate * Decimal(position.quantity)
    unrealized_pnl = market_value - cost_basis
    return _PositionEval(
        position, instrument, last_price, market_value, unrealized_pnl, price_point.status, price_point.as_of
    )


def _aggregate_market_data_status(evals: list[_PositionEval]) -> tuple[str, datetime | None, bool]:
    """여러 포지션의 신선도를 하나의 포트폴리오 수준 상태로 합친다.

    가장 나쁜 상태를 우선한다 — 하나라도 UNAVAILABLE이면 전체를 UNAVAILABLE로,
    그 다음으로 하나라도 STALE이면 STALE로 표시해 경고를 놓치지 않는다.
    """
    if not evals:
        return "EMPTY", None, False

    has_unavailable = any(e.price_status == PRICE_STATUS_UNAVAILABLE for e in evals)
    has_stale = any(e.price_status == PRICE_STATUS_STALE for e in evals)
    if has_unavailable:
        status = PRICE_STATUS_UNAVAILABLE
    elif has_stale:
        status = PRICE_STATUS_STALE
    else:
        status = PRICE_STATUS_FRESH

    as_ofs = [e.price_as_of for e in evals if e.price_as_of is not None]
    oldest_as_of = min(as_ofs) if as_ofs else None
    return status, oldest_as_of, has_unavailable


def _get_owned_portfolio(db: DbSession, portfolio_id: UUID, current_user: User) -> Portfolio:
    portfolio = db.query(Portfolio).filter(Portfolio.id == portfolio_id).first()
    if portfolio is None or portfolio.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="포트폴리오를 찾을 수 없습니다.")
    return portfolio


def _get_tradable_instrument(db: DbSession, instrument_id: UUID) -> Instrument:
    instrument = db.query(Instrument).filter(Instrument.id == instrument_id).first()
    if instrument is None:
        raise HTTPException(status_code=404, detail="종목을 찾을 수 없습니다.")
    if not instrument.is_tradable:
        raise HTTPException(status_code=422, detail="현재 거래할 수 없는 종목입니다.")
    return instrument


def _build_quote_or_422(db: DbSession, portfolio: Portfolio, instrument: Instrument, payload) -> execution.ExecutionQuote:
    try:
        return execution.build_quote(
            db,
            portfolio,
            instrument,
            payload.side,
            payload.order_type,
            payload.quantity,
            payload.limit_price,
            settings.market_data_staleness_threshold_seconds,
        )
    except execution.StaleMarketDataError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except (execution.NoMarketDataError, execution.UnsupportedMarketError, execution.FxRateUnavailableError) as exc:
        raise HTTPException(status_code=422, detail=str(exc))


def _to_order_response(order: Order) -> OrderResponse:
    return OrderResponse(
        id=order.id,
        portfolio_id=order.portfolio_id,
        instrument_id=order.instrument_id,
        side=order.side,
        order_type=order.order_type,
        quantity=order.quantity,
        limit_price=order.limit_price,
        status=order.status,
        submitted_at=order.submitted_at,
        policy_version=order.policy_version,
    )


def _evaluate_open_positions(
    db: DbSession, portfolio: Portfolio, exclude_instrument_id: UUID | None = None
) -> list[_PositionEval]:
    positions = db.query(Position).filter(Position.portfolio_id == portfolio.id, Position.quantity > 0).all()
    return [
        _evaluate_position(db, portfolio, position)
        for position in positions
        if exclude_instrument_id is None or position.instrument_id != exclude_instrument_id
    ]


def _positions_market_value_from_evals(evals: list[_PositionEval]) -> Decimal:
    """UNAVAILABLE 포지션은 합계에서 제외한다 — 0원으로 계산하지 않는다는 뜻이며,
    STALE 포지션은 참고값으로 그대로 합산한다(경고는 market_data_status가 맡는다)."""
    return sum((e.market_value for e in evals if e.market_value is not None), Decimal(0))


def _positions_market_value(db: DbSession, portfolio: Portfolio, exclude_instrument_id: UUID | None = None) -> Decimal:
    return _positions_market_value_from_evals(_evaluate_open_positions(db, portfolio, exclude_instrument_id))


def _concentration_warnings(
    db: DbSession, portfolio: Portfolio, instrument: Instrument, side: str, quantity: Decimal, quote: execution.ExecutionQuote
) -> list[str]:
    position = execution.get_position(db, portfolio.id, instrument.id)
    existing_qty = Decimal(position.quantity) if position is not None else Decimal(0)
    new_qty = existing_qty + quantity if side == "BUY" else existing_qty - quantity
    fx_rate = quote.fx_rate or Decimal(1)
    instrument_value = new_qty * quote.fill_price * fx_rate

    cash_after = execution.get_cash_balance(db, portfolio.id, portfolio.base_currency) + quote.cash_impact_portfolio_ccy
    other_positions_value = _positions_market_value(db, portfolio, exclude_instrument_id=instrument.id)
    total_after = cash_after + instrument_value + other_positions_value

    warnings: list[str] = []
    if total_after > 0:
        weight_pct = instrument_value / total_after * 100
        if weight_pct > settings.concentration_warning_threshold_pct:
            warnings.append(
                f"주문 체결 시 단일 종목 비중이 약 {weight_pct:.1f}%로 "
                f"권장 상한({settings.concentration_warning_threshold_pct}%)을 초과합니다."
            )
    return warnings


@router.get("/me/portfolio", response_model=PortfolioResponse)
def get_my_portfolio(db: DbSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    portfolio = db.query(Portfolio).filter(Portfolio.user_id == current_user.id).first()
    if portfolio is None:
        raise HTTPException(status_code=404, detail="포트폴리오가 없습니다.")
    return _portfolio_response(db, portfolio)


def _portfolio_response(db: DbSession, portfolio: Portfolio) -> PortfolioResponse:
    cash = execution.get_cash_balance(db, portfolio.id, portfolio.base_currency)
    evals = _evaluate_open_positions(db, portfolio)
    market_value = _positions_market_value_from_evals(evals)
    status, as_of, has_unavailable = _aggregate_market_data_status(evals)
    return PortfolioResponse(
        id=portfolio.id,
        base_currency=portfolio.base_currency,
        cash_balance=cash,
        positions_market_value=market_value,
        total_assets=cash + market_value,
        market_data_status=status,
        market_data_as_of=as_of,
        has_unavailable_positions=has_unavailable,
    )


@router.get("/portfolios/{portfolio_id}", response_model=PortfolioResponse)
def get_portfolio(portfolio_id: UUID, db: DbSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    portfolio = _get_owned_portfolio(db, portfolio_id, current_user)
    return _portfolio_response(db, portfolio)


@router.get("/portfolios/{portfolio_id}/positions", response_model=list[PositionResponse])
def get_positions(portfolio_id: UUID, db: DbSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    portfolio = _get_owned_portfolio(db, portfolio_id, current_user)
    evals = _evaluate_open_positions(db, portfolio)
    return [
        PositionResponse(
            instrument_id=e.position.instrument_id,
            ticker=e.instrument.ticker if e.instrument else "",
            quantity=e.position.quantity,
            average_cost=e.position.average_cost,
            last_price=e.last_price,
            market_value=e.market_value,
            unrealized_pnl=e.unrealized_pnl,
            price_status=e.price_status,
            price_as_of=e.price_as_of,
        )
        for e in evals
    ]


@router.get("/portfolios/{portfolio_id}/performance", response_model=PerformanceResponse)
def get_performance(portfolio_id: UUID, db: DbSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    portfolio = _get_owned_portfolio(db, portfolio_id, current_user)
    cash = execution.get_cash_balance(db, portfolio.id, portfolio.base_currency)
    evals = _evaluate_open_positions(db, portfolio)
    market_value = _positions_market_value_from_evals(evals)
    total_assets = cash + market_value
    status, as_of, has_unavailable = _aggregate_market_data_status(evals)

    deposits = (
        db.query(LedgerEntry)
        .filter(LedgerEntry.portfolio_id == portfolio.id, LedgerEntry.entry_type == "INITIAL_DEPOSIT")
        .all()
    )
    total_deposited = sum((Decimal(d.amount) for d in deposits), Decimal(0))

    fills = (
        db.query(Fill)
        .join(Order, Fill.order_id == Order.id)
        .filter(Order.portfolio_id == portfolio.id)
        .all()
    )
    realized_pnl = sum((Decimal(f.realized_pnl) for f in fills if f.realized_pnl is not None), Decimal(0))
    total_commission = sum((Decimal(f.commission) for f in fills), Decimal(0))
    total_tax = sum((Decimal(f.tax) for f in fills), Decimal(0))

    # UNAVAILABLE 포지션의 unrealized_pnl은 None이므로 애초에 0으로 합산되지
    # 않는다 — market_value와 동일한 원칙(0원·전액손실로 계산하지 않음).
    unrealized_pnl = sum((e.unrealized_pnl for e in evals if e.unrealized_pnl is not None), Decimal(0))

    simple_return_pct = None
    if total_deposited > 0:
        simple_return_pct = (total_assets - total_deposited) / total_deposited * 100

    return PerformanceResponse(
        base_currency=portfolio.base_currency,
        cash_balance=cash,
        positions_market_value=market_value,
        total_assets=total_assets,
        total_deposited=total_deposited,
        simple_return_pct=simple_return_pct,
        realized_pnl=realized_pnl,
        unrealized_pnl=unrealized_pnl,
        total_commission=total_commission,
        total_tax=total_tax,
        market_data_status=status,
        market_data_as_of=as_of,
        has_unavailable_positions=has_unavailable,
    )


@router.post("/portfolios/{portfolio_id}/orders/preview", response_model=OrderPreviewResponse)
def preview_order(
    portfolio_id: UUID,
    payload: OrderPreviewRequest,
    db: DbSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    portfolio = _get_owned_portfolio(db, portfolio_id, current_user)
    instrument = _get_tradable_instrument(db, payload.instrument_id)
    quote = _build_quote_or_422(db, portfolio, instrument, payload)
    warnings = _concentration_warnings(db, portfolio, instrument, payload.side, payload.quantity, quote)

    return OrderPreviewResponse(
        reference_price=quote.reference_price,
        estimated_fill_price=quote.fill_price,
        estimated_fillable=quote.fillable,
        notional=quote.notional_instrument_ccy,
        commission=quote.commission_instrument_ccy,
        tax=quote.tax_instrument_ccy,
        fx_rate=quote.fx_rate,
        estimated_cash_impact=quote.cash_impact_portfolio_ccy,
        currency=portfolio.base_currency,
        market_data_as_of=quote.bar_as_of,
        warnings=warnings,
    )


@router.post("/portfolios/{portfolio_id}/orders", response_model=OrderResponse, status_code=201)
def create_order(
    portfolio_id: UUID,
    payload: OrderCreateRequest,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    db: DbSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # 1. 사용자·포트폴리오 권한
    portfolio = _get_owned_portfolio(db, portfolio_id, current_user)

    # 다른 사용자 소유 일지를 자신의 주문에 연결하지 못하도록 쓰기 시점에 검증한다.
    # 존재하지 않는 경우와 동일하게 404로 응답해 소유 여부를 노출하지 않으며,
    # 검증에 실패하면 주문 자체를 생성하지 않는다.
    pre_trade_journal: JournalEntry | None = None
    if payload.pre_trade_journal_id is not None:
        pre_trade_journal = (
            db.query(JournalEntry)
            .filter(JournalEntry.id == payload.pre_trade_journal_id, JournalEntry.user_id == current_user.id)
            .first()
        )
        if pre_trade_journal is None:
            raise HTTPException(status_code=404, detail="투자일지를 찾을 수 없습니다.")

    # 5. 중복 요청: 같은 idempotency key면 새로 만들지 않고 기존 결과를 반환한다
    existing = (
        db.query(Order)
        .filter(Order.portfolio_id == portfolio.id, Order.idempotency_key == idempotency_key)
        .first()
    )
    if existing is not None:
        return _to_order_response(existing)

    # 2. 종목 거래 가능 여부 (장 상태·거래소 캘린더 검증은 market_sessions 데이터가
    #    필요한 후속 작업이다; MVP는 종목의 is_tradable 플래그만 확인한다)
    instrument = _get_tradable_instrument(db, payload.instrument_id)

    # 3. 주문 필드 검증은 Pydantic 스키마에서 수행됨 (수량>0, LIMIT은 limit_price 필수)

    # 6. 최신 데이터 상태 확인 + 체결가 견적 산출 (4번 현금검증에도 재사용)
    quote = _build_quote_or_422(db, portfolio, instrument, payload)

    # 4. 가상현금·보유수량 검증
    if payload.side == "BUY":
        cash = execution.get_cash_balance(db, portfolio.id, portfolio.base_currency)
        if cash + quote.cash_impact_portfolio_ccy < 0:
            raise HTTPException(status_code=422, detail="가상현금이 부족합니다.")
    else:
        position = execution.get_position(db, portfolio.id, instrument.id)
        if position is None or Decimal(position.quantity) < payload.quantity:
            raise HTTPException(status_code=422, detail="보유수량을 초과하여 매도할 수 없습니다.")

    # 7. 주문 후 집중도 경고 (차단하지 않고 경고만 반환)
    warnings = _concentration_warnings(db, portfolio, instrument, payload.side, payload.quantity, quote)

    # 8. 주문 이벤트 저장 + 체결
    order = Order(
        portfolio_id=portfolio.id,
        instrument_id=instrument.id,
        side=payload.side,
        order_type=payload.order_type,
        quantity=payload.quantity,
        limit_price=payload.limit_price,
        time_in_force=payload.time_in_force,
        status=ORDER_ACCEPTED,
        submitted_at=datetime.now(timezone.utc),
        policy_version=quote.policy_version,
        idempotency_key=idempotency_key,
        pre_trade_journal_id=payload.pre_trade_journal_id,
    )
    db.add(order)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        existing = (
            db.query(Order)
            .filter(Order.portfolio_id == portfolio.id, Order.idempotency_key == idempotency_key)
            .first()
        )
        if existing is not None:
            return _to_order_response(existing)
        raise HTTPException(status_code=409, detail="중복된 주문 요청입니다.")

    try:
        execution.execute_order(db, order, portfolio, instrument, quote)
    except execution.InsufficientHoldingsError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc))

    if pre_trade_journal is not None:
        # 일지 -> 주문 역참조를 채워야 처분효과 등 편향 탐지(coaching.detect_biases)가
        # 이 거래를 찾을 수 있다. 소유권은 함수 시작부에서 이미 검증했다.
        pre_trade_journal.order_id = order.id

    db.commit()
    db.refresh(order)
    response = _to_order_response(order)
    response.warnings = warnings
    return response


@router.get("/orders/{order_id}", response_model=OrderResponse)
def get_order(order_id: UUID, db: DbSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    order = db.query(Order).filter(Order.id == order_id).first()
    if order is None:
        raise HTTPException(status_code=404, detail="주문을 찾을 수 없습니다.")
    _get_owned_portfolio(db, order.portfolio_id, current_user)
    return _to_order_response(order)


@router.post("/orders/{order_id}/cancel", response_model=OrderResponse)
def cancel_order(order_id: UUID, db: DbSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    order = db.query(Order).filter(Order.id == order_id).first()
    if order is None:
        raise HTTPException(status_code=404, detail="주문을 찾을 수 없습니다.")
    _get_owned_portfolio(db, order.portfolio_id, current_user)

    if order.status in ORDER_TERMINAL_STATUSES:
        raise HTTPException(status_code=409, detail="이미 종료된 주문은 취소할 수 없습니다.")

    order.status = ORDER_CANCELLED
    db.commit()
    db.refresh(order)
    return _to_order_response(order)
