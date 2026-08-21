"""AI 투자교육 코치 파이프라인. 명세서 7.5-7.7 참고.

파이프라인(7.6): 의도·위험 분류 -> 허용된 데이터 검색 -> 정량·규칙 엔진 ->
LLM 설명 생성 -> 사실·인용·정책 검사 -> 답변·출처·기준시각 표시.

중요: 이 세션의 샌드박스에는 ANTHROPIC_API_KEY가 설정돼 있지 않아 실제 LLM 호출을
라이브로 검증하지 못했다. `settings.anthropic_api_key`가 비어 있거나 호출이
실패하면 규칙 기반 폴백 경로로 항상 graceful degradation한다(7.7 요구사항) — 이
폴백 경로는 이번 세션에서 실제로 테스트했다. 시스템 프롬프트 원본은
`content/prompts/v1-investment-coach.md`에 있으며, 이 파일의 SYSTEM_PROMPT
상수와 내용을 동기화해서 관리한다.
"""

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy import or_
from sqlalchemy.orm import Session as DbSession

from app.core.config import get_settings
from app.domain.constants import BAR_INTERVAL_DAILY
from app.domain.journal import JournalEntry
from app.domain.learning import CONTENT_PUBLISHED, Lesson
from app.domain.market import Instrument
from app.domain.portfolio import Portfolio
from app.domain.services import coaching, execution

settings = get_settings()

PROMPT_VERSION = settings.ai_coach_prompt_version

DISCLAIMER = "이 답변은 교육용 정보이며 투자 자문이 아닙니다. 과거·모의 성과는 미래 성과를 보장하지 않습니다."

SYSTEM_PROMPT = """당신은 초보 투자자를 위한 AI 투자교육 코치입니다. 이 앱은 가상자금으로만
모의투자를 연습하는 교육용 서비스이며, 사용자의 실제 자금을 다루지 않습니다.

반드시 지켜야 할 것:
- 투자 개념을 쉬운 말로 설명한다.
- 사용자의 논리(투자일지)에서 빠진 질문을 던진다.
- 찬성 근거와 반대 근거의 균형을 확인한다.
- 아래 "정량 데이터"로 제공된 수치만 사용한다. 제공되지 않은 시장 수치나 가격을
  임의로 만들어내지 않는다. 모르면 모른다고 말한다.
- 답변은 항상 다음 순서로 구성한다: (1) 짧은 결론 (2) 확인된 근거 (3) 반대 근거와
  불확실성 (4) 사용자가 스스로 확인할 질문 (5) 출처와 데이터 기준시각 (6) 교육용
  정보 고지.

절대 하지 말아야 할 것:
- "지금 사세요/파세요"와 같은 직접적인 매매 지시를 하지 않는다.
- 목표주가나 수익률을 보장하지 않는다.
- 사용자를 대신해 주문을 넣지 않는다.
- 행동편향을 의학적 진단으로 표현하지 않는다 — "관찰된 거래 패턴"으로만 표현한다.

한국어로, 초보자가 이해하기 쉽게, 확신에 찬 단정적 어조가 아니라 근거와 불확실성을
함께 제시하는 어조로 답한다."""

_POLICY_VIOLATION_PATTERNS = [
    re.compile(r"(지금|바로|당장)\s*(사세요|사라|매수하세요|매수하라)"),
    re.compile(r"(지금|바로|당장)\s*(파세요|팔아라|매도하세요|매도하라)"),
    re.compile(r"(반드시|무조건|확실히)\s*(오를|상승|수익)"),
    re.compile(r"(수익|원금)\s*(보장|보증)"),
]


class AiPolicyViolation(Exception):
    pass


def check_policy_violation(text: str) -> str | None:
    for pattern in _POLICY_VIOLATION_PATTERNS:
        if pattern.search(text):
            return pattern.pattern
    return None


@dataclass
class Source:
    type: str
    id: str | None
    title: str
    as_of: str | None
    source: str
    delay_seconds: int | None = None


@dataclass
class CoachAnswer:
    content: str
    model: str
    prompt_version: str
    sources: list[dict] = field(default_factory=list)
    degraded: bool = False
    safety_flags: dict | None = None


def _retrieve_lesson_sources(db: DbSession, question: str, limit: int = 3) -> list[Source]:
    words = [w for w in re.split(r"\s+", question) if len(w) >= 2][:5]
    if not words:
        return []
    conditions = [Lesson.title.ilike(f"%{w}%") for w in words]
    lessons = (
        db.query(Lesson)
        .filter(Lesson.status == CONTENT_PUBLISHED, or_(*conditions))
        .limit(limit)
        .all()
    )
    return [
        Source(
            type="lesson",
            id=str(lesson.id),
            title=lesson.title,
            as_of=(lesson.reviewed_at.isoformat() if lesson.reviewed_at else lesson.created_at.isoformat()),
            source=lesson.source or "investment-learning-app 강의 콘텐츠",
        )
        for lesson in lessons
    ]


def _build_quant_context(db: DbSession, user_id: UUID, journal: JournalEntry | None) -> tuple[str, list[Source]]:
    """정량·규칙 엔진 단계: LLM 산술을 신뢰하지 않고(7.7) 결정론적으로 계산된 값만 문맥으로 넘긴다."""
    lines: list[str] = []
    sources: list[Source] = []

    if journal is not None:
        score, breakdown = coaching.compute_process_score(journal)
        lines.append(f"연결된 투자일지 과정 점수: {score}점 (100점 만점)")
        lines.append(f"세부 항목: {breakdown}")
        if journal.thesis:
            lines.append(f"투자 아이디어: {journal.thesis}")
        if journal.counter_evidence:
            lines.append(f"기록된 반대 근거: {journal.counter_evidence}")
        else:
            lines.append("반대 근거가 기록되지 않았습니다.")

        instrument = db.query(Instrument).filter(Instrument.id == journal.instrument_id).first()
        if instrument is not None:
            bar = execution.get_latest_bar(db, instrument.id, interval=BAR_INTERVAL_DAILY)
            if bar is not None:
                lines.append(
                    f"{instrument.ticker}({instrument.name}) 최근가: {bar.close} {instrument.currency}, "
                    f"기준시각: {bar.as_of.isoformat()}, 출처: {bar.source}, 지연: {bar.delay_seconds}초"
                )
                sources.append(
                    Source(
                        type="market_bar",
                        id=str(instrument.id),
                        title=f"{instrument.ticker} 최근 시세",
                        as_of=bar.as_of.isoformat(),
                        source=bar.source,
                        delay_seconds=bar.delay_seconds,
                    )
                )

    bias_observations = coaching.detect_biases(db, user_id)
    if bias_observations:
        lines.append("관찰된 거래 패턴(진단이 아님):")
        for obs in bias_observations:
            lines.append(f"- {obs['pattern']}: {obs['description']}")
    else:
        lines.append("현재까지 뚜렷하게 관찰된 행동 패턴은 없습니다.")

    portfolio = db.query(Portfolio).filter(Portfolio.user_id == user_id).first()
    if portfolio is not None:
        cash = execution.get_cash_balance(db, portfolio.id, portfolio.base_currency)
        lines.append(f"현재 가상현금 잔고: {cash} {portfolio.base_currency} (모의투자, 실제 자금 아님)")

    return "\n".join(lines), sources


def _fallback_answer(quant_context: str, sources: list[Source], model_label: str) -> CoachAnswer:
    source_lines = (
        "\n".join(f"- {s.title} (출처: {s.source}, 기준시각: {s.as_of})" for s in sources)
        if sources
        else "- 관련 학습 콘텐츠를 찾지 못했습니다."
    )
    content = (
        "[규칙 기반 요약 — AI 설명 기능을 일시적으로 사용할 수 없어 자동 생성되었습니다]\n\n"
        "1. 짧은 결론: 지금은 계산된 데이터만 그대로 보여드립니다. 해석은 아래 정량 데이터를 "
        "직접 확인해주세요.\n\n"
        f"2. 확인된 근거:\n{quant_context}\n\n"
        "3. 반대 근거와 불확실성: 이 요약은 AI 설명 없이 자동 생성되어 맥락 해석이 제한적입니다. "
        "직접 판단할 때 반대 시나리오도 함께 고려하세요.\n\n"
        "4. 스스로 확인할 질문: 이 정량 데이터가 내 투자 논리와 일치하는가? 반대 근거를 "
        "충분히 검토했는가?\n\n"
        f"5. 출처와 기준시각:\n{source_lines}\n\n"
        f"6. 교육용 정보 고지: {DISCLAIMER}"
    )
    return CoachAnswer(
        content=content,
        model=model_label,
        prompt_version=PROMPT_VERSION,
        sources=[s.__dict__ for s in sources],
        degraded=True,
    )


def generate_coach_answer(
    db: DbSession,
    user_id: UUID,
    question: str,
    journal_id: UUID | None = None,
) -> CoachAnswer:
    journal = None
    if journal_id is not None:
        journal = db.query(JournalEntry).filter(JournalEntry.id == journal_id, JournalEntry.user_id == user_id).first()

    quant_context, quant_sources = _build_quant_context(db, user_id, journal)
    lesson_sources = _retrieve_lesson_sources(db, question)
    all_sources = quant_sources + lesson_sources

    model = settings.ai_coach_complex_model if journal is not None else settings.ai_coach_simple_model

    if not settings.anthropic_api_key:
        return _fallback_answer(quant_context, all_sources, model_label="rule-based-fallback")

    try:
        import anthropic

        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        source_lines = "\n".join(f"- {s.title} (출처: {s.source}, 기준시각: {s.as_of})" for s in all_sources)
        user_content = (
            f"[정량 데이터 — 이 수치만 근거로 사용하세요]\n{quant_context}\n\n"
            f"[검색된 학습 콘텐츠]\n{source_lines or '없음'}\n\n"
            f"[사용자 질문]\n{question}"
        )
        response = client.messages.create(
            model=model,
            max_tokens=1500,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_content}],
        )
        text = "".join(block.text for block in response.content if block.type == "text")

        violation = check_policy_violation(text)
        if violation:
            fallback = _fallback_answer(quant_context, all_sources, model_label=model)
            fallback.safety_flags = {"policy_violation_pattern": violation, "blocked_model_output": True}
            return fallback

        return CoachAnswer(
            content=text,
            model=model,
            prompt_version=PROMPT_VERSION,
            sources=[s.__dict__ for s in all_sources],
            degraded=False,
        )
    except Exception as exc:  # noqa: BLE001 - 모델 장애 시 규칙 기반으로 graceful degradation (7.7)
        fallback = _fallback_answer(quant_context, all_sources, model_label="rule-based-fallback")
        fallback.safety_flags = {"llm_error": str(exc)[:200]}
        return fallback
