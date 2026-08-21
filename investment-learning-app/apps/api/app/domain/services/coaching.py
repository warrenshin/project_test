"""과정 점수(7.3)와 행동편향 탐지(7.4). 명세서 참고.

과정 점수는 규칙 기반으로만 계산한다 — AI는 이 점수의 근거를 설명할 뿐 값을
바꾸지 않는다(7.3, 7.5). 편향은 의학적 진단이 아니라 "관찰된 거래 패턴"으로만
표현한다(7.4 마지막 문단).
"""

from decimal import Decimal
from uuid import UUID

from sqlalchemy.orm import Session as DbSession

from app.core.config import get_settings
from app.domain.constants import BAR_INTERVAL_DAILY
from app.domain.journal import JournalEntry
from app.domain.market import Instrument
from app.domain.portfolio import Fill, Order, Portfolio, Position
from app.domain.services import execution

settings = get_settings()

PROCESS_SCORE_WEIGHTS = {
    "thesis_completeness": Decimal("0.20"),
    "counter_evidence": Decimal("0.15"),
    "risk_plan_quality": Decimal("0.25"),
    "sizing_discipline": Decimal("0.15"),
    "plan_adherence": Decimal("0.15"),
    "post_trade_reflection": Decimal("0.10"),
}

MAX_REASONABLE_WEIGHT_PCT = Decimal("20")


def _thesis_completeness(journal: JournalEntry) -> Decimal:
    fields = [
        journal.thesis,
        journal.supporting_evidence,
        journal.expected_holding_period,
        journal.entry_condition,
        journal.target_condition,
        journal.stop_loss_condition,
    ]
    present = sum(1 for f in fields if f)
    return Decimal(present) / Decimal(len(fields)) * 100


def _counter_evidence_score(journal: JournalEntry) -> Decimal:
    if journal.counter_evidence and len(journal.counter_evidence) > 0:
        return Decimal(100)
    return Decimal(0)


def _risk_plan_quality(journal: JournalEntry) -> Decimal:
    score = Decimal(0)
    if journal.stop_loss_condition:
        score += 50
    if journal.planned_weight_pct is not None:
        score += 50 if Decimal(journal.planned_weight_pct) <= MAX_REASONABLE_WEIGHT_PCT else 25
    return score


def _sizing_discipline(journal: JournalEntry) -> Decimal:
    if journal.planned_weight_pct is None:
        return Decimal(0)
    weight = Decimal(journal.planned_weight_pct)
    if weight <= 10:
        return Decimal(100)
    if weight <= 20:
        return Decimal(70)
    if weight <= 30:
        return Decimal(40)
    return Decimal(10)


def _plan_adherence(journal: JournalEntry) -> Decimal:
    if journal.followed_plan is None:
        return Decimal(0)
    return Decimal(100) if journal.followed_plan else Decimal(0)


def _post_trade_reflection(journal: JournalEntry) -> Decimal:
    fields = [
        journal.expectation_gap,
        journal.behavior_to_repeat,
        journal.behavior_to_change,
        journal.emotion_tags,
        journal.luck_contribution,
    ]
    present = sum(1 for f in fields if f)
    return Decimal(present) / Decimal(len(fields)) * 100


def compute_process_score(journal: JournalEntry) -> tuple[Decimal, dict]:
    breakdown = {
        "thesis_completeness": _thesis_completeness(journal),
        "counter_evidence": _counter_evidence_score(journal),
        "risk_plan_quality": _risk_plan_quality(journal),
        "sizing_discipline": _sizing_discipline(journal),
        "plan_adherence": _plan_adherence(journal),
        "post_trade_reflection": _post_trade_reflection(journal),
    }
    total = sum(breakdown[key] * PROCESS_SCORE_WEIGHTS[key] for key in breakdown)
    breakdown_out = {k: float(v) for k, v in breakdown.items()}
    return total.quantize(Decimal("0.01")), breakdown_out


def detect_biases(db: DbSession, user_id: UUID) -> list[dict]:
    """사용자의 일지·주문 데이터에서 관찰된 거래 패턴을 규칙 기반으로 탐지한다."""
    observations: list[dict] = []

    journals = (
        db.query(JournalEntry)
        .filter(JournalEntry.user_id == user_id, JournalEntry.thesis.isnot(None))
        .all()
    )
    if len(journals) >= 3:
        missing_counter = sum(1 for j in journals if not j.counter_evidence)
        ratio = missing_counter / len(journals)
        if ratio > 0.5:
            observations.append(
                {
                    "pattern": "확증편향 의심 패턴",
                    "description": (
                        f"최근 작성한 거래 전 일지 {len(journals)}건 중 {missing_counter}건에서 "
                        "반대 근거가 기록되지 않았습니다. 이는 진단이 아니라 관찰된 기록 패턴입니다."
                    ),
                    "coaching_direction": "다음 거래 전 일지에서는 반대 근거를 최소 1개 이상 작성해보세요.",
                }
            )

    portfolios = db.query(Portfolio).filter(Portfolio.user_id == user_id).all()
    for portfolio in portfolios:
        journal_ids_with_orders = {j.order_id: j for j in journals if j.order_id is not None}
        if not journal_ids_with_orders:
            continue
        orders = (
            db.query(Order)
            .filter(Order.portfolio_id == portfolio.id, Order.id.in_(journal_ids_with_orders.keys()))
            .all()
        )
        winners_holding: list[float] = []
        losers_holding: list[float] = []
        for order in orders:
            journal = journal_ids_with_orders.get(order.id)
            if journal is None or journal.actual_entry_at is None or journal.actual_exit_at is None:
                continue
            fill = db.query(Fill).filter(Fill.order_id == order.id).first()
            if fill is None or fill.realized_pnl is None:
                continue
            holding_hours = (journal.actual_exit_at - journal.actual_entry_at).total_seconds() / 3600
            if Decimal(fill.realized_pnl) >= 0:
                winners_holding.append(holding_hours)
            else:
                losers_holding.append(holding_hours)

        if len(winners_holding) >= 2 and len(losers_holding) >= 2:
            avg_winner = sum(winners_holding) / len(winners_holding)
            avg_loser = sum(losers_holding) / len(losers_holding)
            if avg_loser > avg_winner * 1.5 and avg_winner > 0:
                observations.append(
                    {
                        "pattern": "처분효과 의심 패턴",
                        "description": (
                            f"이익 실현 거래의 평균 보유기간은 약 {avg_winner:.1f}시간, 손실 거래의 평균 "
                            f"보유기간은 약 {avg_loser:.1f}시간으로 관찰됩니다. 이는 진단이 아니라 관찰된 "
                            "거래 패턴입니다."
                        ),
                        "coaching_direction": "계획한 손실 제한 조건과 실제 청산 시점을 비교해보세요.",
                    }
                )

    for portfolio in portfolios:
        cash = execution.get_cash_balance(db, portfolio.id, portfolio.base_currency)
        positions = db.query(Position).filter(Position.portfolio_id == portfolio.id, Position.quantity > 0).all()
        total_value = cash
        position_values: dict[str, Decimal] = {}
        for position in positions:
            instrument = db.query(Instrument).filter(Instrument.id == position.instrument_id).first()
            bar = execution.get_latest_bar(db, position.instrument_id, interval=BAR_INTERVAL_DAILY)
            if instrument is None or bar is None:
                continue
            fx_rate = execution.get_fx_mid_rate(db, instrument.currency, portfolio.base_currency)
            if fx_rate is None:
                continue
            value = Decimal(bar.close) * Decimal(position.quantity) * fx_rate
            position_values[instrument.ticker] = value
            total_value += value

        if total_value > 0:
            for ticker, value in position_values.items():
                weight_pct = value / total_value * 100
                if weight_pct > settings.concentration_warning_threshold_pct:
                    observations.append(
                        {
                            "pattern": "집중위험 의심 패턴",
                            "description": (
                                f"현재 {ticker} 비중이 약 {weight_pct:.1f}%로 권장 상한"
                                f"({settings.concentration_warning_threshold_pct}%)을 초과한 상태로 관찰됩니다."
                            ),
                            "coaching_direction": "분산투자가 위험에 미치는 영향을 학습 콘텐츠에서 확인해보세요.",
                        }
                    )

    return observations
