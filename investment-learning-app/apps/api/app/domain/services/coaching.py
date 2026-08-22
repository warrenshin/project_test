"""과정 점수(7.3)와 행동편향 탐지(7.4, 7종 전부). 명세서 참고.

과정 점수는 규칙 기반으로만 계산한다 — AI는 이 점수의 근거를 설명할 뿐 값을
바꾸지 않는다(7.3, 7.5). 편향은 의학적 진단이 아니라 "관찰된 거래 패턴"으로만
표현한다(7.4 마지막 문단).

재현성·버전 관리 원칙: 각 편향 판정은 `BiasSignal`(순수 계산 결과)로 먼저
만들고, 실제로 detected=True인 것만 `app.domain.bias.BiasEvent`로 저장한다.
저장 시점의 실제 임계값(threshold_snapshot)과 규칙 버전(rule_version)을
같이 남겨, 나중에 Settings 값이 바뀌어도 "이 판정이 어떤 기준으로 나왔는지"를
그대로 재구성할 수 있게 한다. 같은 근거(evidence_fingerprint)로 같은 규칙
버전 하에 다시 분석해도 DB에는 중복 행이 생기지 않는다(unique 제약 +
SAVEPOINT 패턴, 이 저장소 전체에서 이미 쓰는 동시성 안전 패턴과 동일).
"""

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DbSession

from app.core.config import get_settings
from app.domain.bias import (
    DATA_INSUFFICIENT,
    DATA_MARKET_UNAVAILABLE,
    DATA_SUFFICIENT,
    SEVERITY_HIGH,
    SEVERITY_LOW,
    SEVERITY_MEDIUM,
    BiasEvent,
)
from app.domain.constants import BAR_INTERVAL_DAILY
from app.domain.journal import JournalEntry, JournalVersion
from app.domain.learning import Lesson
from app.domain.market import Bar, Instrument
from app.domain.portfolio import Fill, Order, Portfolio, Position
from app.domain.services import execution

settings = get_settings()

# 아래 상수들은 "관찰을 보고할 만큼 반복됐는지"를 가르는 표본 수 기준이다
# (예: 확증편향 탐지가 최소 3건의 일지를 요구하는 것과 같은 종류의 기준) —
# 이는 %/시간 같은 운영 임계치(app/core/config.py의 Settings)와는 성격이
# 달라 여기 모듈 상수로 둔다. 단 1회의 예외적 행동으로 패턴을 단정하지
# 않기 위함이다.
CHASING_RALLY_MIN_INSTANCES = 2
STOP_LOSS_REVISION_MIN_CHANGES = 2
AVERAGING_DOWN_MIN_INSTANCES = 2

# bias_code별 규칙 버전. 개별 편향의 판정 로직을 바꿀 때는 그 코드의 버전만
# 올린다 — 그러면 그 편향만 새 BiasEvent 행이 생기고, 다른 편향·과거에 이미
# 저장된 행은 전혀 건드리지 않는다.
BIAS_RULE_VERSIONS: dict[str, str] = {
    "CONFIRMATION_BIAS": "v1",
    "DISPOSITION_EFFECT": "v1",
    "CONCENTRATION_RISK": "v1",
    "CHASING_RALLY": "v1",
    "LOSS_AVERSION": "v1",
    "AVERAGING_DOWN": "v1",
    "OVERTRADING": "v1",
}

BIAS_DISPLAY_NAMES: dict[str, str] = {
    "CONFIRMATION_BIAS": "확증편향 의심 패턴",
    "DISPOSITION_EFFECT": "처분효과 의심 패턴",
    "CONCENTRATION_RISK": "집중위험 의심 패턴",
    "CHASING_RALLY": "추격매수 의심 패턴",
    "LOSS_AVERSION": "손실회피 의심 패턴",
    "AVERAGING_DOWN": "물타기 집착 의심 패턴",
    "OVERTRADING": "과잉매매 의심 패턴",
}

# 기존에 시드된 강의 중 실제로 있는 것만 연결한다(존재하지 않는 강의를
# 참조하지 않는다) — Day2/4/6 챌린지 카드로 만든 "행동편향 살펴보기",
# "분산과 집중위험"을 재사용한다.
BIAS_RELATED_LESSON_TITLE: dict[str, str] = {
    "CONFIRMATION_BIAS": "행동편향 살펴보기",
    "DISPOSITION_EFFECT": "행동편향 살펴보기",
    "CHASING_RALLY": "행동편향 살펴보기",
    "LOSS_AVERSION": "행동편향 살펴보기",
    "AVERAGING_DOWN": "행동편향 살펴보기",
    "OVERTRADING": "행동편향 살펴보기",
    "CONCENTRATION_RISK": "분산과 집중위험",
}

BIAS_SELF_CHECK_QUESTIONS: dict[str, list[str]] = {
    "CONFIRMATION_BIAS": [
        "이 매매를 반대할 만한 근거를 지금 하나 떠올릴 수 있나요?",
        "이 판단에 동의하지 않는 사람이 있다면 뭐라고 말할까요?",
    ],
    "DISPOSITION_EFFECT": [
        "이 종목을 오늘 처음 산다면 지금 가격에 다시 살 것 같나요?",
        "손실 종목을 오래 들고 있는 이유가 '팔면 손해가 확정돼서'는 아닌가요?",
    ],
    "CONCENTRATION_RISK": [
        "이 종목이 크게 하락하면 전체 자산에 얼마나 영향이 있나요?",
        "지금 비중을 처음부터 다시 정한다면 같은 비중을 고를까요?",
    ],
    "CHASING_RALLY": [
        "이미 오른 뒤에 사면서 '이번엔 다르다'고 생각하고 있지 않나요?",
        "이 매수를 하루 미룬다면 무엇이 달라지나요?",
    ],
    "LOSS_AVERSION": [
        "손절 조건을 바꾼 이유를 한 문장으로 설명할 수 있나요?",
        "조건을 바꾸지 않았다면 지금 어떤 상태일까요?",
    ],
    "AVERAGING_DOWN": [
        "가격이 떨어진 것 외에 새로 생긴 근거가 있나요?",
        "처음 예상과 다르게 흘러가고 있다는 신호는 없나요?",
    ],
    "OVERTRADING": [
        "이 중 학습이나 계획에 따른 거래는 몇 건인가요?",
        "지금 거래 속도를 늦춘다면 무엇을 잃게 되나요?",
    ],
}

BIAS_LIMITATIONS: dict[str, str] = {
    "CONFIRMATION_BIAS": "반대 근거 필드가 비어 있어도 실제로 고려했을 수 있습니다 — 기록 여부만 봅니다.",
    "DISPOSITION_EFFECT": "표본이 적어 우연일 수 있고, 시장 상황 차이는 반영하지 않습니다.",
    "CONCENTRATION_RISK": "가격 데이터가 지연·누락된 종목은 비중 계산에서 제외됩니다.",
    "CHASING_RALLY": "진입 조건 필드 작성 여부만 보며, 실제 계획의 질은 평가하지 않습니다.",
    "LOSS_AVERSION": "손절 조건이 자유 텍스트라 변경 방향(강화/완화)은 판단하지 않고 변경 횟수만 봅니다.",
    "AVERAGING_DOWN": "매도 이력은 평균단가 재구성에 반영하지 않은 단순 근사치입니다.",
    "OVERTRADING": "사용자 개인별 기준이 아니라 전체 사용자에게 동일하게 적용하는 고정 임계값(MVP 기준)입니다.",
}


@dataclass
class BiasSignal:
    """편향 하나에 대한 이번 분석 결과. detected=False여도 항상 만들어진다 —
    "이 편향은 확인했지만 신호가 없었다/판단할 데이터가 부족했다"를 명시적으로
    구분하기 위해서다(클라이언트가 침묵과 미확인을 혼동하지 않게)."""

    bias_code: str
    detected: bool
    data_sufficiency: str  # SUFFICIENT / INSUFFICIENT / MARKET_DATA_UNAVAILABLE
    sample_size: int
    minimum_sample_size: int
    window_start: datetime | None
    window_end: datetime | None
    severity: str | None
    evidence_strength: Decimal | None
    description: str
    coaching_direction: str
    evidence_refs: list[dict] = field(default_factory=list)
    threshold_snapshot: dict = field(default_factory=dict)


def _severity_from_ratio(ratio: Decimal) -> str:
    """탐지 임계값 대비 얼마나 초과했는지(ratio, 1.0=임계값과 동일)로 심각도
    등급을 정한다 — 전부 결정론적 규칙이며 여러 편향이 동시에 나올 때
    우선순위 정렬에도 그대로 쓴다."""
    if ratio >= Decimal("2"):
        return SEVERITY_HIGH
    if ratio >= Decimal("1.3"):
        return SEVERITY_MEDIUM
    return SEVERITY_LOW

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


def _is_trustworthy_bar(bar: Bar, as_of_limit: datetime) -> bool:
    """as_of가 timezone-naive거나 미래 시각이면 신뢰할 수 없는 bar다(공급자
    응답 손상·시계 어긋남과 동일한 취급 — market_data_service의 원칙과
    같다). 이런 bar는 가격 기반 편향 계산에 아예 쓰지 않는다."""
    return bar.as_of.tzinfo is not None and bar.as_of <= as_of_limit


def _price_gain_pct_before(db: DbSession, instrument_id, as_of: datetime, lookback_days: int) -> Decimal | None:
    """as_of 시점 이전(포함)의 신뢰 가능한 일봉 중 최근 lookback_days+1개를
    가져와 그 구간 시작 대비 끝 종가 변화율(%)을 계산한다. 신뢰 가능한
    일봉이 2개 미만이면(STALE/UNAVAILABLE·손상 데이터 포함) 판단할 수
    없으므로 None을 반환한다 — 억지로 0%로 취급하지 않는다."""
    now = datetime.now(timezone.utc)
    candidates = (
        db.query(Bar)
        .filter(Bar.instrument_id == instrument_id, Bar.interval == BAR_INTERVAL_DAILY, Bar.bar_start <= as_of)
        .order_by(Bar.bar_start.desc())
        .limit(lookback_days + 5)  # 신뢰 불가 bar가 섞여 있을 수 있어 여유를 두고 가져온다
        .all()
    )
    bars = [b for b in candidates if _is_trustworthy_bar(b, now)][: lookback_days + 1]
    if len(bars) < 2:
        return None
    latest_close = Decimal(bars[0].close)
    earliest_close = Decimal(bars[-1].close)
    if earliest_close <= 0:
        return None
    return (latest_close - earliest_close) / earliest_close * 100


def _detect_chasing_rally(db: DbSession, user_id: UUID, portfolios: list[Portfolio]) -> BiasSignal:
    """추격매수: 단기 급등 후 "진입 조건" 필드 없이 매수를 반복하는 패턴.
    상승 자체나 단 1회의 매수만으로는 절대 탐지하지 않는다 — 평가 가능한
    표본(usable_sample) 중 무계획 추격매수로 보이는 사례가 최소 2건 이상일
    때만 신호를 낸다."""
    journals_by_order_id = {
        j.order_id: j
        for j in db.query(JournalEntry).filter(JournalEntry.user_id == user_id, JournalEntry.order_id.isnot(None))
    }
    usable_sample = 0  # 신뢰 가능한 가격으로 실제 판단한 매수 건수
    instances = 0
    evidence_refs: list[dict] = []
    window_start: datetime | None = None
    window_end: datetime | None = None
    for portfolio in portfolios:
        fills_with_orders = (
            db.query(Fill, Order)
            .join(Order, Fill.order_id == Order.id)
            .filter(Order.portfolio_id == portfolio.id, Order.side == "BUY")
            .all()
        )
        for fill, order in fills_with_orders:
            gain = _price_gain_pct_before(db, order.instrument_id, fill.filled_at, settings.chasing_rally_lookback_days)
            if gain is None:
                continue  # 신뢰 가능한 가격 데이터가 부족해 이 건은 판단하지 않는다
            usable_sample += 1
            window_start = fill.filled_at if window_start is None else min(window_start, fill.filled_at)
            window_end = fill.filled_at if window_end is None else max(window_end, fill.filled_at)
            if gain < settings.chasing_rally_gain_threshold_pct:
                continue
            journal = journals_by_order_id.get(order.id)
            has_entry_plan = journal is not None and bool(journal.entry_condition)
            if not has_entry_plan:
                instances += 1
                evidence_refs.append({"type": "Order", "id": str(order.id)})
                evidence_refs.append({"type": "Fill", "id": str(fill.id)})

    threshold_snapshot = {
        "lookback_days": settings.chasing_rally_lookback_days,
        "gain_threshold_pct": settings.chasing_rally_gain_threshold_pct,
        "min_instances": CHASING_RALLY_MIN_INSTANCES,
    }
    if usable_sample == 0:
        return BiasSignal(
            bias_code="CHASING_RALLY", detected=False, data_sufficiency=DATA_MARKET_UNAVAILABLE,
            sample_size=0, minimum_sample_size=CHASING_RALLY_MIN_INSTANCES, window_start=None, window_end=None,
            severity=None, evidence_strength=None,
            description="가격 데이터를 신뢰할 수 있는 매수 사례가 없어 추격매수 여부를 판단할 수 없습니다.",
            coaching_direction="시세가 확인된 종목을 거래하면 다음부터 이 항목을 확인할 수 있습니다.",
            threshold_snapshot=threshold_snapshot,
        )
    detected = instances >= CHASING_RALLY_MIN_INSTANCES
    ratio = Decimal(instances) / Decimal(CHASING_RALLY_MIN_INSTANCES) if detected else None
    return BiasSignal(
        bias_code="CHASING_RALLY", detected=detected,
        data_sufficiency=DATA_SUFFICIENT if usable_sample >= CHASING_RALLY_MIN_INSTANCES else DATA_INSUFFICIENT,
        sample_size=usable_sample, minimum_sample_size=CHASING_RALLY_MIN_INSTANCES,
        window_start=window_start, window_end=window_end,
        severity=_severity_from_ratio(ratio) if detected else None,
        evidence_strength=(min(Decimal(100), Decimal(instances) * 20) if detected else None),
        description=(
            f"최근 {settings.chasing_rally_lookback_days}거래일 내 {settings.chasing_rally_gain_threshold_pct}% "
            f"이상 오른 종목을 진입 조건 없이 매수한 사례가 {instances}건 관찰됩니다."
            if detected
            else "진입 조건 없이 급등 종목을 반복 매수한 사례가 관찰되지 않았습니다."
        ),
        coaching_direction="매수 전 진입 조건과 대기 규칙을 먼저 일지에 작성해보세요.",
        evidence_refs=evidence_refs,
        threshold_snapshot=threshold_snapshot,
    )


def _detect_loss_aversion_stop_loss_revision(db: DbSession, user_id: UUID) -> BiasSignal:
    """손실회피: 손절 조건을 반복해서 변경하는 패턴(실제 체결과 연결된 일지에
    한함). stop_loss_condition은 자유 텍스트라 "하향" 방향까지 파싱하지
    않는다 — 값이 몇 번 바뀌었는지만 신호로 쓴다. `plan_change_reason`을
    기록해 변경 이유를 남긴 일지는 "정당한 재계획"으로 보고 제외한다 —
    이유 없이 조용히 반복해서 바꾸는 경우만 신호로 남긴다."""
    journals = (
        db.query(JournalEntry)
        .filter(JournalEntry.user_id == user_id, JournalEntry.order_id.isnot(None))
        .all()
    )
    evaluable = 0
    max_changes = 0
    evidence_refs: list[dict] = []
    window_start: datetime | None = None
    window_end: datetime | None = None
    for journal in journals:
        versions = (
            db.query(JournalVersion)
            .filter(JournalVersion.journal_id == journal.id)
            .order_by(JournalVersion.created_at.asc())
            .all()
        )
        if not versions:
            continue
        evaluable += 1
        window_start = journal.created_at if window_start is None else min(window_start, journal.created_at)
        window_end = journal.created_at if window_end is None else max(window_end, journal.created_at)
        if journal.plan_change_reason:
            continue  # 변경 이유를 기록했다면 "정당한 재계획"으로 보고 제외한다
        values = [v.content_snapshot.get("stop_loss_condition") for v in versions]
        values.append(str(journal.stop_loss_condition) if journal.stop_loss_condition is not None else None)
        changes = sum(1 for prev, curr in zip(values, values[1:]) if prev != curr)
        if changes > max_changes:
            max_changes = changes
            evidence_refs = [{"type": "JournalEntry", "id": str(journal.id)}]

    threshold_snapshot = {"min_changes": STOP_LOSS_REVISION_MIN_CHANGES}
    detected = max_changes >= STOP_LOSS_REVISION_MIN_CHANGES
    ratio = Decimal(max_changes) / Decimal(STOP_LOSS_REVISION_MIN_CHANGES) if detected else None
    return BiasSignal(
        bias_code="LOSS_AVERSION", detected=detected,
        data_sufficiency=DATA_SUFFICIENT if evaluable >= 1 else DATA_INSUFFICIENT,
        sample_size=evaluable, minimum_sample_size=1,
        window_start=window_start, window_end=window_end,
        severity=_severity_from_ratio(ratio) if detected else None,
        evidence_strength=(min(Decimal(100), Decimal(max_changes) * 25) if detected else None),
        description=(
            f"체결된 거래와 연결된 일지에서 손절 조건이 이유 기록 없이 {max_changes}회 변경된 사례가 "
            "관찰됩니다."
            if detected
            else "체결된 거래에서 손절 조건이 이유 없이 반복 변경된 사례가 관찰되지 않았습니다."
        ),
        coaching_direction="최초 정한 손실 제한 조건과 실제 변경 시점·이유를 비교해보세요.",
        evidence_refs=evidence_refs,
        threshold_snapshot=threshold_snapshot,
    )


def _running_average_cost_flags(fills_with_orders: list[tuple[Fill, Order]]) -> list[bool]:
    """시간순 BUY 체결 목록에 대해, 각 체결이 "그 이전까지의 가중평균 매입가보다
    낮은 가격"인지 여부를 순서대로 반환한다(첫 체결은 항상 False). 매도
    이력은 반영하지 않는 단순 근사치다(문서화된 한계 — BIAS_LIMITATIONS
    참고): 매수만으로 평단가를 근사하는 것으로 충분히 신호를 낼 수 있고,
    매도까지 반영하는 정확한 잔고 재구성은 이 신호의 목적에 비해 과하다."""
    flags: list[bool] = []
    total_qty = Decimal(0)
    total_cost = Decimal(0)
    for fill, _order in fills_with_orders:
        avg_cost_before = (total_cost / total_qty) if total_qty > 0 else None
        flags.append(avg_cost_before is not None and Decimal(fill.fill_price) < avg_cost_before)
        total_qty += Decimal(fill.quantity)
        total_cost += Decimal(fill.quantity) * Decimal(fill.fill_price)
    return flags


def _detect_averaging_down_without_new_thesis(
    db: DbSession, user_id: UUID, portfolios: list[Portfolio]
) -> BiasSignal:
    """물타기 집착: 그 시점까지의 평균 매입가보다 낮은 가격에 같은 종목을
    추가 매수하면서, 그 사이에 새 투자 논리(thesis)와 반대 근거
    (counter_evidence)를 모두 갖춘 일지를 기록하지 않은 패턴. 평균 매입가보다
    "높게" 산 추가매수는 애초에 물타기로 보지 않는다(직전 1건 가격이 아니라
    누적 평균과 비교 — 직전 체결가만 보면 평균보다는 낮지만 직전보다는 비싼
    추가매수를 놓친다)."""
    pairs_evaluated = 0
    instances = 0
    evidence_refs: list[dict] = []
    window_start: datetime | None = None
    window_end: datetime | None = None
    for portfolio in portfolios:
        fills_with_orders = (
            db.query(Fill, Order)
            .join(Order, Fill.order_id == Order.id)
            .filter(Order.portfolio_id == portfolio.id, Order.side == "BUY")
            .order_by(Fill.filled_at.asc())
            .all()
        )
        by_instrument: dict[str, list[tuple[Fill, Order]]] = {}
        for fill, order in fills_with_orders:
            by_instrument.setdefault(str(order.instrument_id), []).append((fill, order))

        for ordered in by_instrument.values():
            if len(ordered) < 2:
                continue
            below_avg_flags = _running_average_cost_flags(ordered)
            for idx in range(1, len(ordered)):
                if not below_avg_flags[idx]:
                    continue  # 평균 매입가보다 비싸게 샀다면 "물타기"로 보지 않는다
                pairs_evaluated += 1
                prev_fill, _prev_order = ordered[idx - 1]
                curr_fill, curr_order = ordered[idx]
                window_start = prev_fill.filled_at if window_start is None else min(window_start, prev_fill.filled_at)
                window_end = curr_fill.filled_at if window_end is None else max(window_end, curr_fill.filled_at)
                has_fresh_replan = (
                    db.query(JournalEntry)
                    .filter(
                        JournalEntry.user_id == user_id,
                        JournalEntry.instrument_id == curr_order.instrument_id,
                        JournalEntry.thesis.isnot(None),
                        JournalEntry.counter_evidence.isnot(None),
                        JournalEntry.created_at > prev_fill.filled_at,
                        JournalEntry.created_at <= curr_fill.filled_at,
                    )
                    .first()
                    is not None
                )
                if not has_fresh_replan:
                    instances += 1
                    evidence_refs.append({"type": "Fill", "id": str(curr_fill.id)})

    threshold_snapshot = {"min_instances": AVERAGING_DOWN_MIN_INSTANCES}
    detected = instances >= AVERAGING_DOWN_MIN_INSTANCES
    ratio = Decimal(instances) / Decimal(AVERAGING_DOWN_MIN_INSTANCES) if detected else None
    return BiasSignal(
        bias_code="AVERAGING_DOWN", detected=detected,
        data_sufficiency=DATA_SUFFICIENT if pairs_evaluated >= 1 else DATA_INSUFFICIENT,
        sample_size=pairs_evaluated, minimum_sample_size=1,
        window_start=window_start, window_end=window_end,
        severity=_severity_from_ratio(ratio) if detected else None,
        evidence_strength=(min(Decimal(100), Decimal(instances) * 25) if detected else None),
        description=(
            f"평균 매입가보다 낮은 가격에 같은 종목을 추가 매수하면서 투자 논리·반대 근거를 새로 "
            f"기록하지 않은 사례가 {instances}건 관찰됩니다."
            if detected
            else "평단가보다 낮은 가격에 추가 매수하며 논리를 갱신하지 않은 사례가 관찰되지 않았습니다."
        ),
        coaching_direction="추가 매수 전 최초 투자 논리가 여전히 유효한지, 반대 근거는 없는지 다시 검증해보세요.",
        evidence_refs=evidence_refs,
        threshold_snapshot=threshold_snapshot,
    )


def _detect_overtrading(db: DbSession, user_id: UUID, portfolios: list[Portfolio]) -> BiasSignal:
    """과잉매매: 짧은 시간 안에 "실제 체결" 빈도가 급증하는 패턴. 취소·거절
    등 체결되지 않은 주문은 세지 않는다(Fill이 있는 주문만) — 계획을 세우다
    취소한 것까지 "매매 폭주"로 잘못 셀 이유가 없다. 7일 챌린지의 주문
    미리보기 미션(Day2/5)은 실제 Order/Fill을 만들지 않으므로(미리보기만
    계산) 이 집계에 애초에 포함되지 않는다."""
    window = timedelta(hours=settings.overtrading_window_hours)
    filled_orders: list[tuple[datetime, Order]] = []
    for portfolio in portfolios:
        rows = (
            db.query(Fill.filled_at, Order)
            .join(Order, Fill.order_id == Order.id)
            .filter(Order.portfolio_id == portfolio.id)
            .all()
        )
        filled_orders.extend(rows)
    filled_orders.sort(key=lambda row: row[0])

    max_count = 0
    max_window_orders: list[Order] = []
    start = 0
    for end in range(len(filled_orders)):
        while filled_orders[end][0] - filled_orders[start][0] > window:
            start += 1
        count = end - start + 1
        if count > max_count:
            max_count = count
            max_window_orders = [o for _t, o in filled_orders[start : end + 1]]

    threshold_snapshot = {
        "window_hours": settings.overtrading_window_hours,
        "order_threshold": settings.overtrading_order_threshold,
    }
    sample_size = len(filled_orders)
    if sample_size == 0:
        return BiasSignal(
            bias_code="OVERTRADING", detected=False, data_sufficiency=DATA_INSUFFICIENT,
            sample_size=0, minimum_sample_size=1, window_start=None, window_end=None,
            severity=None, evidence_strength=None,
            description="체결된 주문이 없어 매매 빈도를 판단할 수 없습니다.",
            coaching_direction="거래를 시작하면 이 항목을 확인할 수 있습니다.",
            threshold_snapshot=threshold_snapshot,
        )
    detected = max_count >= settings.overtrading_order_threshold
    ratio = Decimal(max_count) / Decimal(settings.overtrading_order_threshold) if detected else None
    # 참고 정보: 이 burst 구간 주문 중 사전 일지와 연결되지 않은 비율 —
    # 새 판정 기준으로 쓰지는 않되(요구된 신호가 아님), 근거 요약에 덧붙여
    # "계획 없이 몰아친 정도"를 사람이 판단할 실마리로 남긴다.
    linkage_note = ""
    if detected and max_window_orders:
        unlinked = sum(1 for o in max_window_orders if o.pre_trade_journal_id is None)
        linkage_note = f" (그중 사전 일지와 연결되지 않은 주문 {unlinked}건)"
    return BiasSignal(
        bias_code="OVERTRADING", detected=detected,
        data_sufficiency=DATA_SUFFICIENT,
        sample_size=sample_size, minimum_sample_size=1,
        window_start=filled_orders[0][0], window_end=filled_orders[-1][0],
        severity=_severity_from_ratio(ratio) if detected else None,
        evidence_strength=(min(Decimal(100), ratio * 40) if detected and ratio is not None else None),
        description=(
            f"{settings.overtrading_window_hours}시간 이내에 {max_count}건의 체결이 발생한 구간이 "
            f"관찰됩니다{linkage_note}."
            if detected
            else "짧은 시간 안에 매매가 급증한 구간이 관찰되지 않았습니다."
        ),
        coaching_direction=f"{settings.overtrading_window_hours}시간 동안 신규 주문 없이 관찰·복기하는 과제를 시도해보세요.",
        evidence_refs=[{"type": "Order", "id": str(o.id)} for o in max_window_orders] if detected else [],
        threshold_snapshot=threshold_snapshot,
    )


def _detect_confirmation_bias(db: DbSession, user_id: UUID) -> BiasSignal:
    """확증편향: 거래 전 일지에 반대 근거를 기록하지 않는 비율이 높은 패턴."""
    journals = (
        db.query(JournalEntry)
        .filter(JournalEntry.user_id == user_id, JournalEntry.thesis.isnot(None))
        .all()
    )
    threshold_snapshot = {"min_sample": 3, "ratio_threshold": 0.5}
    sample_size = len(journals)
    if sample_size < 3:
        return BiasSignal(
            bias_code="CONFIRMATION_BIAS", detected=False, data_sufficiency=DATA_INSUFFICIENT,
            sample_size=sample_size, minimum_sample_size=3, window_start=None, window_end=None,
            severity=None, evidence_strength=None,
            description="거래 전 일지가 아직 충분하지 않아 판단할 수 없습니다.",
            coaching_direction="거래 전 일지를 몇 건 더 작성하면 이 항목을 확인할 수 있습니다.",
            threshold_snapshot=threshold_snapshot,
        )
    missing_counter = sum(1 for j in journals if not j.counter_evidence)
    ratio = Decimal(missing_counter) / Decimal(sample_size)
    detected = ratio > Decimal("0.5")
    window_start = min((j.created_at for j in journals), default=None)
    window_end = max((j.created_at for j in journals), default=None)
    return BiasSignal(
        bias_code="CONFIRMATION_BIAS", detected=detected, data_sufficiency=DATA_SUFFICIENT,
        sample_size=sample_size, minimum_sample_size=3, window_start=window_start, window_end=window_end,
        severity=_severity_from_ratio(ratio / Decimal("0.5")) if detected else None,
        evidence_strength=(ratio * 100) if detected else None,
        description=(
            f"최근 작성한 거래 전 일지 {sample_size}건 중 {missing_counter}건에서 반대 근거가 "
            "기록되지 않았습니다."
            if detected
            else f"최근 일지 {sample_size}건 중 반대 근거 미기록 비율은 특별히 높지 않습니다."
        ),
        coaching_direction="다음 거래 전 일지에서는 반대 근거를 최소 1개 이상 작성해보세요.",
        evidence_refs=[{"type": "JournalEntry", "id": str(j.id)} for j in journals if not j.counter_evidence],
        threshold_snapshot=threshold_snapshot,
    )


def _detect_disposition_effect(db: DbSession, user_id: UUID, portfolios: list[Portfolio]) -> BiasSignal:
    """처분효과: 이익 거래는 짧게, 손실 거래는 길게 보유하는 패턴."""
    journals = (
        db.query(JournalEntry)
        .filter(JournalEntry.user_id == user_id, JournalEntry.thesis.isnot(None))
        .all()
    )
    winners_holding: list[float] = []
    losers_holding: list[float] = []
    evidence_refs: list[dict] = []
    window_start: datetime | None = None
    window_end: datetime | None = None
    for portfolio in portfolios:
        journal_ids_with_orders = {j.order_id: j for j in journals if j.order_id is not None}
        if not journal_ids_with_orders:
            continue
        orders = (
            db.query(Order)
            .filter(Order.portfolio_id == portfolio.id, Order.id.in_(journal_ids_with_orders.keys()))
            .all()
        )
        for order in orders:
            journal = journal_ids_with_orders.get(order.id)
            if journal is None or journal.actual_entry_at is None or journal.actual_exit_at is None:
                continue
            fill = db.query(Fill).filter(Fill.order_id == order.id).first()
            if fill is None or fill.realized_pnl is None:
                continue
            holding_hours = (journal.actual_exit_at - journal.actual_entry_at).total_seconds() / 3600
            window_start = journal.actual_entry_at if window_start is None else min(window_start, journal.actual_entry_at)
            window_end = journal.actual_exit_at if window_end is None else max(window_end, journal.actual_exit_at)
            if Decimal(fill.realized_pnl) >= 0:
                winners_holding.append(holding_hours)
            else:
                losers_holding.append(holding_hours)
                evidence_refs.append({"type": "JournalEntry", "id": str(journal.id)})

    threshold_snapshot = {"min_winners": 2, "min_losers": 2, "ratio_threshold": 1.5}
    sample_size = len(winners_holding) + len(losers_holding)
    if len(winners_holding) < 2 or len(losers_holding) < 2:
        return BiasSignal(
            bias_code="DISPOSITION_EFFECT", detected=False, data_sufficiency=DATA_INSUFFICIENT,
            sample_size=sample_size, minimum_sample_size=4, window_start=window_start, window_end=window_end,
            severity=None, evidence_strength=None,
            description="완결된(진입·청산 모두 기록된) 이익·손실 거래가 아직 충분하지 않아 판단할 수 없습니다.",
            coaching_direction="거래 후 복기를 몇 건 더 남기면 이 항목을 확인할 수 있습니다.",
            threshold_snapshot=threshold_snapshot,
        )
    avg_winner = sum(winners_holding) / len(winners_holding)
    avg_loser = sum(losers_holding) / len(losers_holding)
    detected = avg_winner > 0 and avg_loser > avg_winner * 1.5
    ratio = Decimal(str(avg_loser / avg_winner)) if detected and avg_winner > 0 else None
    return BiasSignal(
        bias_code="DISPOSITION_EFFECT", detected=detected, data_sufficiency=DATA_SUFFICIENT,
        sample_size=sample_size, minimum_sample_size=4, window_start=window_start, window_end=window_end,
        severity=_severity_from_ratio(ratio / Decimal("1.5")) if detected and ratio else None,
        evidence_strength=(min(Decimal(100), ratio * 30) if detected and ratio else None),
        description=(
            f"이익 실현 거래의 평균 보유기간은 약 {avg_winner:.1f}시간, 손실 거래의 평균 보유기간은 약 "
            f"{avg_loser:.1f}시간으로 관찰됩니다."
            if detected
            else "이익·손실 거래의 평균 보유기간에 뚜렷한 차이가 관찰되지 않았습니다."
        ),
        coaching_direction="계획한 손실 제한 조건과 실제 청산 시점을 비교해보세요.",
        evidence_refs=evidence_refs if detected else [],
        threshold_snapshot=threshold_snapshot,
    )


def _detect_concentration_risk(db: DbSession, user_id: UUID, portfolios: list[Portfolio]) -> BiasSignal:
    """집중위험: 단일 종목 비중이 권장 상한을 넘는 패턴. 가격을 신뢰할 수
    없는(지연·누락) 종목은 비중 계산에서 제외한다 — 계산에 넣을 수 없다고
    "위험 없음"으로 단정하지 않고, 그 종목만큼은 판단 불가로 남긴다."""
    threshold_snapshot = {"warning_threshold_pct": settings.concentration_warning_threshold_pct}
    positions_considered = 0
    positions_skipped_stale = 0
    detected_ticker: str | None = None
    detected_weight: Decimal | None = None
    detected_position_id: UUID | None = None
    for portfolio in portfolios:
        cash = execution.get_cash_balance(db, portfolio.id, portfolio.base_currency)
        positions = db.query(Position).filter(Position.portfolio_id == portfolio.id, Position.quantity > 0).all()
        total_value = cash
        position_values: dict[str, tuple[Decimal, UUID, str]] = {}
        for position in positions:
            instrument = db.query(Instrument).filter(Instrument.id == position.instrument_id).first()
            bar = execution.get_latest_bar(db, position.instrument_id, interval=BAR_INTERVAL_DAILY)
            if instrument is None or bar is None or not _is_trustworthy_bar(bar, datetime.now(timezone.utc)):
                if instrument is not None and bar is not None:
                    positions_skipped_stale += 1
                continue
            fx_rate = execution.get_fx_mid_rate(db, instrument.currency, portfolio.base_currency)
            if fx_rate is None:
                continue
            value = Decimal(bar.close) * Decimal(position.quantity) * fx_rate
            position_values[instrument.ticker] = (value, position.id, instrument.ticker)
            total_value += value
            positions_considered += 1

        if total_value > 0:
            for ticker, (value, position_id, _t) in position_values.items():
                weight_pct = value / total_value * 100
                if weight_pct > settings.concentration_warning_threshold_pct:
                    if detected_weight is None or weight_pct > detected_weight:
                        detected_ticker, detected_weight, detected_position_id = ticker, weight_pct, position_id

    data_sufficiency = DATA_SUFFICIENT
    if positions_considered == 0:
        data_sufficiency = DATA_MARKET_UNAVAILABLE if positions_skipped_stale > 0 else DATA_INSUFFICIENT
    detected = detected_weight is not None
    ratio = (detected_weight / Decimal(settings.concentration_warning_threshold_pct)) if detected else None
    return BiasSignal(
        bias_code="CONCENTRATION_RISK", detected=detected, data_sufficiency=data_sufficiency,
        sample_size=positions_considered, minimum_sample_size=1, window_start=None, window_end=None,
        severity=_severity_from_ratio(ratio) if detected and ratio else None,
        evidence_strength=(min(Decimal(100), detected_weight)) if detected and detected_weight else None,
        description=(
            f"현재 {detected_ticker} 비중이 약 {detected_weight:.1f}%로 권장 상한"
            f"({settings.concentration_warning_threshold_pct}%)을 초과한 상태로 관찰됩니다."
            if detected
            else (
                "가격을 신뢰할 수 있는 보유 종목이 없어 집중도를 판단할 수 없습니다."
                if positions_considered == 0
                else "권장 상한을 넘는 비중의 보유 종목이 관찰되지 않았습니다."
            )
        ),
        coaching_direction="분산투자가 위험에 미치는 영향을 학습 콘텐츠에서 확인해보세요.",
        evidence_refs=[{"type": "Position", "id": str(detected_position_id)}] if detected_position_id else [],
        threshold_snapshot=threshold_snapshot,
    )


def _evidence_fingerprint(bias_code: str, rule_version: str, evidence_refs: list[dict]) -> str:
    """같은 근거(evidence_refs 집합)로 같은 규칙 버전 하에 다시 분석해도
    같은 값이 나오는 결정론적 해시. 참조 ID만 해시에 넣는다(원문 없음)."""
    normalized = sorted(f"{ref['type']}:{ref['id']}" for ref in evidence_refs)
    payload = json.dumps({"bias_code": bias_code, "rule_version": rule_version, "refs": normalized}, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _lesson_id_by_title(db: DbSession, title: str) -> UUID | None:
    row = db.query(Lesson.id).filter(Lesson.title == title).first()
    return row[0] if row else None


def _persist_bias_event(db: DbSession, user_id: UUID, signal: BiasSignal) -> BiasEvent | None:
    """detected=True인 신호만 저장한다. 중복 근거+동일 규칙 버전이면 새로
    삽입하지 않고 기존 행을 그대로 재사용한다(SAVEPOINT + unique 제약 —
    이 저장소 전체에서 쓰는 동시성 안전 패턴과 동일)."""
    if not signal.detected:
        return None
    rule_version = BIAS_RULE_VERSIONS[signal.bias_code]
    fingerprint = _evidence_fingerprint(signal.bias_code, rule_version, signal.evidence_refs)
    existing = (
        db.query(BiasEvent)
        .filter(
            BiasEvent.user_id == user_id, BiasEvent.bias_code == signal.bias_code,
            BiasEvent.rule_version == rule_version, BiasEvent.evidence_fingerprint == fingerprint,
        )
        .first()
    )
    if existing is not None:
        return existing

    event = BiasEvent(
        user_id=user_id, bias_code=signal.bias_code, display_name=BIAS_DISPLAY_NAMES[signal.bias_code],
        rule_version=rule_version, threshold_snapshot=signal.threshold_snapshot,
        window_start=signal.window_start, window_end=signal.window_end,
        sample_size=signal.sample_size, minimum_sample_size=signal.minimum_sample_size,
        severity=signal.severity or SEVERITY_LOW,
        evidence_strength=signal.evidence_strength if signal.evidence_strength is not None else Decimal(0),
        evidence_summary=signal.description, evidence_refs=signal.evidence_refs,
        limitations=BIAS_LIMITATIONS[signal.bias_code],
        self_check_questions=BIAS_SELF_CHECK_QUESTIONS[signal.bias_code],
        related_lesson_id=_lesson_id_by_title(db, BIAS_RELATED_LESSON_TITLE[signal.bias_code]),
        evidence_fingerprint=fingerprint, detected_at=datetime.now(timezone.utc),
    )
    db.add(event)
    try:
        with db.begin_nested():
            db.flush()
    except IntegrityError:
        db.rollback()
        return (
            db.query(BiasEvent)
            .filter(
                BiasEvent.user_id == user_id, BiasEvent.bias_code == signal.bias_code,
                BiasEvent.rule_version == rule_version, BiasEvent.evidence_fingerprint == fingerprint,
            )
            .first()
        )
    return event


_BIAS_SORT_SEVERITY_RANK = {SEVERITY_HIGH: 0, SEVERITY_MEDIUM: 1, SEVERITY_LOW: 2, None: 3}


def _bias_sort_key(signal: BiasSignal, persisted: BiasEvent | None):
    """여러 편향이 동시에 감지될 때의 결정론적 정렬 키: 심각도(높은 순) ->
    근거 강도(강한 순) -> 최근성(최근 순) -> bias_code(알파벳순, 최종
    동점 처리). detected=False인 항목은 항상 뒤로 밀린다."""
    detected_rank = 0 if signal.detected else 1
    severity_rank = _BIAS_SORT_SEVERITY_RANK.get(signal.severity, 3)
    strength = -(signal.evidence_strength or Decimal(0))
    detected_at = persisted.detected_at if persisted else None
    recency_key = -(detected_at.timestamp()) if detected_at else 0
    return (detected_rank, severity_rank, strength, recency_key, signal.bias_code)


def detect_biases(db: DbSession, user_id: UUID) -> list[dict]:
    """사용자의 일지·주문 데이터에서 7종 행동편향을 전부 평가한다. 실제로
    감지된(detected=True) 것만 BiasEvent로 저장하고, 응답에는 7종 전체를
    담는다(감지 안 됨/데이터 부족도 명시적으로 구분해서 보여주기 위해).
    정렬은 감지 여부 -> 심각도 -> 근거 강도 -> 최근성 -> bias_code 순으로
    항상 결정론적이다."""
    portfolios = db.query(Portfolio).filter(Portfolio.user_id == user_id).all()

    signals = [
        _detect_confirmation_bias(db, user_id),
        _detect_disposition_effect(db, user_id, portfolios),
        _detect_concentration_risk(db, user_id, portfolios),
        _detect_chasing_rally(db, user_id, portfolios),
        _detect_loss_aversion_stop_loss_revision(db, user_id),
        _detect_averaging_down_without_new_thesis(db, user_id, portfolios),
        _detect_overtrading(db, user_id, portfolios),
    ]

    persisted_by_code: dict[str, BiasEvent | None] = {
        s.bias_code: _persist_bias_event(db, user_id, s) for s in signals
    }
    signals.sort(key=lambda s: _bias_sort_key(s, persisted_by_code[s.bias_code]))

    lesson_id_cache: dict[str, UUID | None] = {}

    def _related_lesson_id(bias_code: str) -> UUID | None:
        title = BIAS_RELATED_LESSON_TITLE[bias_code]
        if title not in lesson_id_cache:
            lesson_id_cache[title] = _lesson_id_by_title(db, title)
        return lesson_id_cache[title]

    results = []
    for s in signals:
        event = persisted_by_code[s.bias_code]
        related_lesson_id = event.related_lesson_id if event else _related_lesson_id(s.bias_code)
        results.append(
            {
                "id": str(event.id) if event else None,
                "bias_code": s.bias_code,
                "display_name": BIAS_DISPLAY_NAMES[s.bias_code],
                "rule_version": BIAS_RULE_VERSIONS[s.bias_code],
                "detected": s.detected,
                "pattern": BIAS_DISPLAY_NAMES[s.bias_code],
                "data_sufficiency": s.data_sufficiency,
                "sample_size": s.sample_size,
                "minimum_sample_size": s.minimum_sample_size,
                "window_start": s.window_start,
                "window_end": s.window_end,
                "severity": s.severity,
                "evidence_strength": float(s.evidence_strength) if s.evidence_strength is not None else None,
                "description": s.description,
                "coaching_direction": s.coaching_direction,
                "evidence_summary": s.description,
                "limitations": BIAS_LIMITATIONS[s.bias_code],
                "self_check_questions": BIAS_SELF_CHECK_QUESTIONS[s.bias_code],
                "related_lesson_id": str(related_lesson_id) if related_lesson_id else None,
                "detected_at": event.detected_at if event else None,
                "acknowledged_at": event.acknowledged_at if event else None,
            }
        )
    return results
