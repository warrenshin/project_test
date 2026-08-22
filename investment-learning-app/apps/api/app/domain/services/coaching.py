"""과정 점수(7.3)와 행동편향 탐지(7.4). 명세서 참고.

과정 점수는 규칙 기반으로만 계산한다 — AI는 이 점수의 근거를 설명할 뿐 값을
바꾸지 않는다(7.3, 7.5). 편향은 의학적 진단이 아니라 "관찰된 거래 패턴"으로만
표현한다(7.4 마지막 문단).
"""

from datetime import timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy.orm import Session as DbSession

from app.core.config import get_settings
from app.domain.constants import BAR_INTERVAL_DAILY
from app.domain.journal import JournalEntry, JournalVersion
from app.domain.market import Bar, Instrument
from app.domain.portfolio import Fill, Order, Portfolio, Position
from app.domain.services import execution

settings = get_settings()

# 아래 세 상수는 "관찰을 보고할 만큼 반복됐는지"를 가르는 표본 수 기준이다
# (예: 확증편향 탐지가 최소 3건의 일지를 요구하는 것과 같은 종류의 기준) —
# 이는 %/시간 같은 운영 임계치(app/core/config.py의 Settings)와는 성격이
# 달라 여기 모듈 상수로 둔다. 단 1회의 예외적 행동으로 패턴을 단정하지
# 않기 위함이다.
CHASING_RALLY_MIN_INSTANCES = 2
STOP_LOSS_REVISION_MIN_CHANGES = 2
AVERAGING_DOWN_MIN_INSTANCES = 2

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


def _price_gain_pct_before(db: DbSession, instrument_id, as_of, lookback_days: int) -> Decimal | None:
    """as_of 시점 이전(포함)의 일봉 중 최근 lookback_days+1개를 가져와 그 구간
    시작 대비 끝 종가 변화율(%)을 계산한다. 일봉이 2개 미만이면 판단할 수
    없으므로 None을 반환한다(억지로 0%로 취급하지 않는다)."""
    bars = (
        db.query(Bar)
        .filter(Bar.instrument_id == instrument_id, Bar.interval == BAR_INTERVAL_DAILY, Bar.bar_start <= as_of)
        .order_by(Bar.bar_start.desc())
        .limit(lookback_days + 1)
        .all()
    )
    if len(bars) < 2:
        return None
    latest_close = Decimal(bars[0].close)
    earliest_close = Decimal(bars[-1].close)
    if earliest_close <= 0:
        return None
    return (latest_close - earliest_close) / earliest_close * 100


def _detect_chasing_rally(db: DbSession, user_id: UUID, portfolios: list[Portfolio]) -> dict | None:
    """추격매수: 단기 급등 후 진입 조건 없이 매수를 반복하는 패턴."""
    journals_by_order_id = {
        j.order_id: j
        for j in db.query(JournalEntry).filter(JournalEntry.user_id == user_id, JournalEntry.order_id.isnot(None))
    }
    instances = 0
    for portfolio in portfolios:
        fills_with_orders = (
            db.query(Fill, Order)
            .join(Order, Fill.order_id == Order.id)
            .filter(Order.portfolio_id == portfolio.id, Order.side == "BUY")
            .all()
        )
        for fill, order in fills_with_orders:
            gain = _price_gain_pct_before(db, order.instrument_id, fill.filled_at, settings.chasing_rally_lookback_days)
            if gain is None or gain < settings.chasing_rally_gain_threshold_pct:
                continue
            journal = journals_by_order_id.get(order.id)
            has_entry_plan = journal is not None and bool(journal.entry_condition)
            if not has_entry_plan:
                instances += 1

    if instances < CHASING_RALLY_MIN_INSTANCES:
        return None
    return {
        "pattern": "추격매수 의심 패턴",
        "description": (
            f"최근 {settings.chasing_rally_lookback_days}거래일 내 {settings.chasing_rally_gain_threshold_pct}% "
            f"이상 오른 종목을 진입 조건 없이 매수한 사례가 {instances}건 관찰됩니다. 이는 진단이 아니라 "
            "관찰된 거래 패턴입니다."
        ),
        "coaching_direction": "매수 전 진입 조건과 대기 규칙을 먼저 일지에 작성해보세요.",
    }


def _detect_loss_aversion_stop_loss_revision(db: DbSession, user_id: UUID) -> dict | None:
    """손실회피: 손절 조건을 반복해서 변경하는 패턴(실제 체결과 연결된 일지에 한함).

    stop_loss_condition은 자유 텍스트라 "하향" 방향까지 파싱하지 않는다 —
    대신 같은 일지에서 그 값이 구조적으로 몇 번 바뀌었는지를 관찰 신호로
    쓴다(반복 변경 자체가 신호다)."""
    journals = (
        db.query(JournalEntry)
        .filter(JournalEntry.user_id == user_id, JournalEntry.order_id.isnot(None))
        .all()
    )
    for journal in journals:
        versions = (
            db.query(JournalVersion)
            .filter(JournalVersion.journal_id == journal.id)
            .order_by(JournalVersion.created_at.asc())
            .all()
        )
        if not versions:
            continue
        values = [v.content_snapshot.get("stop_loss_condition") for v in versions]
        values.append(str(journal.stop_loss_condition) if journal.stop_loss_condition is not None else None)
        changes = sum(1 for prev, curr in zip(values, values[1:]) if prev != curr)
        if changes >= STOP_LOSS_REVISION_MIN_CHANGES:
            return {
                "pattern": "손실회피 의심 패턴",
                "description": (
                    f"체결된 거래와 연결된 일지에서 손절 조건이 {changes}회 변경된 사례가 관찰됩니다. "
                    "이는 진단이 아니라 관찰된 거래 패턴입니다."
                ),
                "coaching_direction": "최초 정한 손실 제한 조건과 실제 변경 시점·이유를 비교해보세요.",
            }
    return None


def _detect_averaging_down_without_new_thesis(
    db: DbSession, user_id: UUID, portfolios: list[Portfolio]
) -> dict | None:
    """물타기 집착: 이전 매수보다 더 낮은 가격에 같은 종목을 추가 매수하면서,
    그 사이에 새 투자 논리(일지)를 기록하지 않은 패턴."""
    instances = 0
    for portfolio in portfolios:
        fills_with_orders = (
            db.query(Fill, Order)
            .join(Order, Fill.order_id == Order.id)
            .filter(Order.portfolio_id == portfolio.id, Order.side == "BUY")
            .order_by(Fill.filled_at.asc())
            .all()
        )
        by_instrument: dict[str, list] = {}
        for fill, order in fills_with_orders:
            by_instrument.setdefault(str(order.instrument_id), []).append((fill, order))

        for ordered in by_instrument.values():
            for (prev_fill, _prev_order), (curr_fill, curr_order) in zip(ordered, ordered[1:]):
                if Decimal(curr_fill.fill_price) >= Decimal(prev_fill.fill_price):
                    continue  # 이전보다 비싸게 샀다면 "물타기"로 보지 않는다
                has_fresh_thesis = (
                    db.query(JournalEntry)
                    .filter(
                        JournalEntry.user_id == user_id,
                        JournalEntry.instrument_id == curr_order.instrument_id,
                        JournalEntry.thesis.isnot(None),
                        JournalEntry.created_at > prev_fill.filled_at,
                        JournalEntry.created_at <= curr_fill.filled_at,
                    )
                    .first()
                    is not None
                )
                if not has_fresh_thesis:
                    instances += 1

    if instances < AVERAGING_DOWN_MIN_INSTANCES:
        return None
    return {
        "pattern": "물타기 집착 의심 패턴",
        "description": (
            f"이전보다 낮은 가격에 같은 종목을 추가 매수하면서 투자 논리를 새로 기록하지 않은 사례가 "
            f"{instances}건 관찰됩니다. 이는 진단이 아니라 관찰된 거래 패턴입니다."
        ),
        "coaching_direction": "추가 매수 전 최초 투자 논리가 여전히 유효한지 다시 검증해보세요.",
    }


def _detect_overtrading(db: DbSession, user_id: UUID, portfolios: list[Portfolio]) -> dict | None:
    """과잉매매: 짧은 시간 안에 주문 빈도가 급증하는 패턴."""
    window = timedelta(hours=settings.overtrading_window_hours)
    submitted_times = []
    for portfolio in portfolios:
        submitted_times.extend(
            row[0] for row in db.query(Order.submitted_at).filter(Order.portfolio_id == portfolio.id)
        )
    submitted_times.sort()

    max_count = 0
    start = 0
    for end in range(len(submitted_times)):
        while submitted_times[end] - submitted_times[start] > window:
            start += 1
        max_count = max(max_count, end - start + 1)

    if max_count < settings.overtrading_order_threshold:
        return None
    return {
        "pattern": "과잉매매 의심 패턴",
        "description": (
            f"{settings.overtrading_window_hours}시간 이내에 {max_count}건의 주문이 발생한 구간이 "
            "관찰됩니다. 이는 진단이 아니라 관찰된 거래 패턴입니다."
        ),
        "coaching_direction": f"{settings.overtrading_window_hours}시간 동안 신규 주문 없이 관찰·복기하는 과제를 시도해보세요.",
    }


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

    for detector in (
        lambda: _detect_chasing_rally(db, user_id, portfolios),
        lambda: _detect_loss_aversion_stop_loss_revision(db, user_id),
        lambda: _detect_averaging_down_without_new_thesis(db, user_id, portfolios),
        lambda: _detect_overtrading(db, user_id, portfolios),
    ):
        observation = detector()
        if observation is not None:
            observations.append(observation)

    return observations
