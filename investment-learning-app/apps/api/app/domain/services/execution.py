"""모의 체결 엔진. 명세서 6.7 참고.

동기 방식(단일 요청 내 즉시 체결 판정)으로 구현한 MVP다. 실제로는
`services/simulation-worker`가 새 bar 도착 시마다 미체결 LIMIT 주문을 재평가해야
하지만, 그 비동기 워커는 아직 없다 (services/simulation-worker/README.md 참고).
따라서 이 버전은 "최신 bar 기준으로 즉시 체결 가능하면 체결, 아니면 ACCEPTED로
대기" 수준까지만 지원한다.

모든 금액 계산은 Decimal로 수행하며(8.3, float 금지), 체결 시점의 비용 정책
버전을 order.policy_version에 고정한다.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session as DbSession

from app.domain.constants import (
    ACCOUNT_CASH,
    BAR_INTERVAL_DAILY,
    ENTRY_BUY_TRADE,
    ENTRY_SELL_TRADE,
    EXCHANGE_MARKET_MAP,
    FEE_POLICY_VERSION,
    ORDER_ACCEPTED,
    ORDER_FILLED,
    PRICE_STATUS_FRESH,
    SUPPORTED_BAR_INTERVALS,
)
from app.domain.market import Bar, Instrument
from app.domain.policy import FeePolicy, FxRate
from app.domain.portfolio import Fill, LedgerEntry, Order, Portfolio, Position
from app.domain.services.market_data import classify_price_freshness


class ExecutionError(Exception):
    """체결 엔진에서 발생하는 사용자에게 보여줄 수 있는 오류의 베이스."""


class StaleMarketDataError(ExecutionError):
    pass


class NoMarketDataError(ExecutionError):
    pass


class UnsupportedMarketError(ExecutionError):
    pass


class FxRateUnavailableError(ExecutionError):
    pass


class InsufficientFundsError(ExecutionError):
    pass


class InsufficientHoldingsError(ExecutionError):
    pass


@dataclass
class ExecutionQuote:
    reference_price: Decimal
    fill_price: Decimal
    fillable: bool
    notional_instrument_ccy: Decimal
    commission_instrument_ccy: Decimal
    tax_instrument_ccy: Decimal
    fx_rate: Decimal | None
    cash_impact_portfolio_ccy: Decimal  # BUY: 음수(현금 감소), SELL: 양수(현금 증가)
    bar_as_of: datetime
    bar_source: str
    policy_version: str


def get_market(instrument: Instrument) -> str:
    market = EXCHANGE_MARKET_MAP.get(instrument.exchange.upper())
    if market is None:
        raise UnsupportedMarketError(f"지원하지 않는 거래소입니다: {instrument.exchange}")
    return market


def get_latest_bar(db: DbSession, instrument_id, *, interval: str) -> Bar | None:
    """지정한 interval의 최신 bar만 반환한다 — 기본값을 두지 않는다. 호출자가

    interval을 명시하지 않으면 서로 다른 주기(예: 1d/1m)의 bar가 bar_start만으로
    비교되어 더 최근 시각을 가진 다른 interval의 bar가 "최신 bar"로 잘못 선택될
    수 있다(주문 체결가·포트폴리오 평가가 오염되는 실제 위험). 요청한 interval의
    데이터가 없으면 다른 interval로 대체하지 않고 None을 반환한다.
    """
    if interval not in SUPPORTED_BAR_INTERVALS:
        raise ValueError(f"지원하지 않는 interval입니다: {interval!r}")
    return (
        db.query(Bar)
        .filter(Bar.instrument_id == instrument_id, Bar.interval == interval)
        .order_by(Bar.bar_start.desc())
        .first()
    )


def get_fee_policy(db: DbSession, market: str) -> FeePolicy:
    policy = (
        db.query(FeePolicy)
        .filter(FeePolicy.market == market, FeePolicy.version == FEE_POLICY_VERSION)
        .order_by(FeePolicy.effective_from.desc())
        .first()
    )
    if policy is None:
        raise UnsupportedMarketError(f"{market} 시장의 수수료 정책이 없습니다.")
    return policy


def _get_fx_rate_row(db: DbSession, from_ccy: str, to_ccy: str) -> tuple[Decimal, Decimal]:
    """from_ccy -> to_ccy 환산 시 사용할 (rate, spread_bps)를 반환한다."""
    direct = (
        db.query(FxRate)
        .filter(FxRate.base_currency == from_ccy, FxRate.quote_currency == to_ccy)
        .order_by(FxRate.as_of.desc())
        .first()
    )
    if direct is not None:
        return Decimal(direct.rate), Decimal(direct.spread_bps)

    inverse = (
        db.query(FxRate)
        .filter(FxRate.base_currency == to_ccy, FxRate.quote_currency == from_ccy)
        .order_by(FxRate.as_of.desc())
        .first()
    )
    if inverse is not None:
        return Decimal(1) / Decimal(inverse.rate), Decimal(inverse.spread_bps)

    raise FxRateUnavailableError(f"{from_ccy}->{to_ccy} 환율 데이터가 없습니다.")


def get_fx_mid_rate(db: DbSession, from_ccy: str, to_ccy: str) -> Decimal | None:
    """평가(마킹)용 중간 환율. 관측치가 없으면 None을 반환해 호출측이 값을 숨기게 한다 (6.8)."""
    if from_ccy == to_ccy:
        return Decimal(1)
    try:
        rate, _spread_bps = _get_fx_rate_row(db, from_ccy, to_ccy)
        return rate
    except FxRateUnavailableError:
        return None


def build_quote(
    db: DbSession,
    portfolio: Portfolio,
    instrument: Instrument,
    side: str,
    order_type: str,
    quantity: Decimal,
    limit_price: Decimal | None,
    staleness_threshold_seconds: int,
) -> ExecutionQuote:
    bar = get_latest_bar(db, instrument.id, interval=BAR_INTERVAL_DAILY)
    if bar is None:
        raise NoMarketDataError("해당 종목의 시세 데이터가 없습니다.")

    try:
        freshness = classify_price_freshness(bar.as_of, staleness_threshold_seconds)
    except ValueError as exc:
        # as_of가 미래 시각이거나 timezone-naive면 신뢰할 수 없는 시세다 —
        # STALE과 동일하게 주문을 거부한다(신뢰할 수 없는 시각을 FRESH로 보고
        # 체결하는 것보다 안전하다).
        raise StaleMarketDataError(f"시세 기준시각을 신뢰할 수 없습니다: {exc}") from exc

    if freshness != PRICE_STATUS_FRESH:
        raise StaleMarketDataError(
            f"시세가 오래되었습니다 (기준시각 {bar.as_of.isoformat()}). 주문을 거부합니다."
        )

    market = get_market(instrument)
    policy = get_fee_policy(db, market)

    reference_price = Decimal(bar.close)
    spread_cost = reference_price * Decimal(policy.spread_bps) / Decimal(10000)

    fillable = True
    if order_type == "MARKET":
        fill_price = reference_price + spread_cost if side == "BUY" else reference_price - spread_cost
    else:  # LIMIT — 보수적 체결 규칙 (6.7): bar 안 가격 순서를 알 수 없으므로 지정가로만 체결
        if side == "BUY":
            fillable = Decimal(bar.low) <= limit_price
        else:
            fillable = Decimal(bar.high) >= limit_price
        fill_price = limit_price

    notional = fill_price * quantity
    commission = max(notional * Decimal(policy.commission_bps) / Decimal(10000), Decimal(policy.min_commission))
    tax = notional * Decimal(policy.sell_tax_bps) / Decimal(10000) if side == "SELL" else Decimal(0)

    fx_rate: Decimal | None = None
    if instrument.currency == portfolio.base_currency:
        converted_notional, converted_commission, converted_tax = notional, commission, tax
    else:
        rate, fx_spread_bps = _get_fx_rate_row(db, instrument.currency, portfolio.base_currency)
        fx_spread = rate * fx_spread_bps / Decimal(10000)
        # 매수(외화 매입)는 불리한 방향(+spread), 매도 대금 환전은 불리한 방향(-spread)으로 적용한다.
        fx_rate = rate - fx_spread if side == "SELL" else rate + fx_spread
        converted_notional = notional * fx_rate
        converted_commission = commission * fx_rate
        converted_tax = tax * fx_rate

    cash_impact = (
        -(converted_notional + converted_commission)
        if side == "BUY"
        else (converted_notional - converted_commission - converted_tax)
    )

    return ExecutionQuote(
        reference_price=reference_price,
        fill_price=fill_price,
        fillable=fillable,
        notional_instrument_ccy=notional,
        commission_instrument_ccy=commission,
        tax_instrument_ccy=tax,
        fx_rate=fx_rate,
        cash_impact_portfolio_ccy=cash_impact,
        bar_as_of=bar.as_of,
        bar_source=bar.source,
        policy_version=f"{market}:{policy.version}",
    )


def get_cash_balance(db: DbSession, portfolio_id, currency: str) -> Decimal:
    total = (
        db.query(func.coalesce(func.sum(LedgerEntry.amount), 0))
        .filter(
            LedgerEntry.portfolio_id == portfolio_id,
            LedgerEntry.account_code == ACCOUNT_CASH,
            LedgerEntry.currency == currency,
        )
        .scalar()
    )
    return Decimal(total)


def get_position(db: DbSession, portfolio_id, instrument_id) -> Position | None:
    return (
        db.query(Position)
        .filter(Position.portfolio_id == portfolio_id, Position.instrument_id == instrument_id)
        .first()
    )


def execute_order(
    db: DbSession,
    order: Order,
    portfolio: Portfolio,
    instrument: Instrument,
    quote: ExecutionQuote,
) -> Fill | None:
    """quote가 fillable이면 체결을 원장·포지션에 반영하고 Fill을 반환한다.

    order.id를 ledger event_id로 사용해, 동일 주문이 실수로 재처리되어도
    UNIQUE(portfolio_id, event_id, account_code) 제약으로 중복 반영되지 않는다.
    """
    if not quote.fillable:
        order.status = ORDER_ACCEPTED
        return None

    existing_fill = db.query(Fill).filter(Fill.order_id == order.id).first()
    if existing_fill is not None:
        return existing_fill

    now = datetime.now(timezone.utc)
    quantity = Decimal(order.quantity)

    position = get_position(db, portfolio.id, instrument.id)
    realized_pnl: Decimal | None = None

    if order.side == "BUY":
        if position is None:
            position = Position(
                portfolio_id=portfolio.id,
                instrument_id=instrument.id,
                quantity=quantity,
                average_cost=quote.fill_price,
            )
            db.add(position)
        else:
            old_qty = Decimal(position.quantity)
            old_cost = Decimal(position.average_cost)
            new_qty = old_qty + quantity
            position.average_cost = (old_qty * old_cost + quantity * quote.fill_price) / new_qty
            position.quantity = new_qty
    else:  # SELL
        if position is None or Decimal(position.quantity) < quantity:
            raise InsufficientHoldingsError("보유수량을 초과하여 매도할 수 없습니다.")
        avg_cost = Decimal(position.average_cost)
        realized_pnl = (
            (quote.fill_price - avg_cost) * quantity
            - quote.commission_instrument_ccy
            - quote.tax_instrument_ccy
        )
        position.quantity = Decimal(position.quantity) - quantity
        if position.quantity == 0:
            position.average_cost = Decimal(0)

    fill = Fill(
        order_id=order.id,
        quantity=quantity,
        fill_price=quote.fill_price,
        commission=quote.commission_instrument_ccy,
        tax=quote.tax_instrument_ccy,
        slippage=Decimal(0),
        realized_pnl=realized_pnl,
        market_data_as_of=quote.bar_as_of,
        market_data_source=quote.bar_source,
        filled_at=now,
    )
    db.add(fill)

    db.add(
        LedgerEntry(
            portfolio_id=portfolio.id,
            event_id=order.id,
            account_code=ACCOUNT_CASH,
            currency=portfolio.base_currency,
            amount=quote.cash_impact_portfolio_ccy,
            entry_type=ENTRY_BUY_TRADE if order.side == "BUY" else ENTRY_SELL_TRADE,
            occurred_at=now,
        )
    )

    order.status = ORDER_FILLED
    order.policy_version = quote.policy_version
    return fill
