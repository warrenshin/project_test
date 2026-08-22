"""seed seven-day challenge, challenge cards, and badges

Revision ID: cb3cb7383a73
Revises: 937dbb491085
Create Date: 2026-08-22 07:05:00.000000

멱등 seed: 이미 존재하는 challenge code/lesson title/badge code는 건너뛰고
없는 것만 만든다 — 이 migration이(또는 이 안의 로직을 재사용하는 스크립트가)
두 번 실행돼도 중복이 생기지 않는다.

콘텐츠 재사용 원칙: Day 1은 기존 1강("투자는 무엇인가")과 그 퀴즈를 그대로
쓴다. 콘텐츠가 없는 Day(2/4/6)는 새 강의를 길게 만드는 대신, 기존 Lesson/
Quiz 모델을 그대로 써서 아주 짧은 "챌린지 전용 교육카드"를 만든다(수 분 내
읽을 분량, 문항 2개짜리 퀴즈) — Lesson이 이미 source/reviewed_by/reviewed_at/
status로 출처·검수 상태를 관리할 수 있으므로 새 모델을 만들 필요가 없었다.

원칙(반드시 지킬 것): 어떤 미션·배지도 수익률·거래횟수·투자금액·특정 종목
매수를 조건으로 하지 않는다 — 전부 학습 완료, 퀴즈 이해도, 일지 작성 완성도,
과정 준수 여부만 본다.
"""
import uuid
from datetime import date, datetime, timezone

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID

# revision identifiers, used by Alembic.
revision = 'cb3cb7383a73'
down_revision = '937dbb491085'
branch_labels = None
depends_on = None

modules_t = sa.table(
    "modules", sa.column("id", PG_UUID), sa.column("course_id", PG_UUID), sa.column("title", sa.String),
    sa.column("order_index", sa.Integer), sa.column("status", sa.String), sa.column("created_at", sa.DateTime(timezone=True)),
)
lessons_t = sa.table(
    "lessons", sa.column("id", PG_UUID), sa.column("module_id", PG_UUID), sa.column("title", sa.String),
    sa.column("learning_objective", sa.Text), sa.column("estimated_minutes", sa.Integer),
    sa.column("order_index", sa.Integer), sa.column("status", sa.String), sa.column("source", sa.String),
    sa.column("reviewed_by", sa.String), sa.column("reviewed_at", sa.Date), sa.column("created_at", sa.DateTime(timezone=True)),
)
content_blocks_t = sa.table(
    "content_blocks", sa.column("id", PG_UUID), sa.column("lesson_id", PG_UUID), sa.column("block_type", sa.String),
    sa.column("content", sa.Text), sa.column("order_index", sa.Integer),
)
quizzes_t = sa.table(
    "quizzes", sa.column("id", PG_UUID), sa.column("lesson_id", PG_UUID), sa.column("title", sa.String),
    sa.column("pass_score_pct", sa.Numeric),
)
questions_t = sa.table(
    "questions", sa.column("id", PG_UUID), sa.column("quiz_id", PG_UUID), sa.column("prompt", sa.Text),
    sa.column("question_type", sa.String), sa.column("explanation", sa.Text), sa.column("order_index", sa.Integer),
)
choices_t = sa.table(
    "choices", sa.column("id", PG_UUID), sa.column("question_id", PG_UUID), sa.column("label", sa.Text),
    sa.column("is_correct", sa.Boolean), sa.column("order_index", sa.Integer),
)
challenges_t = sa.table(
    "challenges", sa.column("id", PG_UUID), sa.column("code", sa.String), sa.column("version", sa.Integer),
    sa.column("title", sa.String), sa.column("description", sa.Text), sa.column("total_days", sa.Integer),
    sa.column("status", sa.String), sa.column("created_at", sa.DateTime(timezone=True)),
)
challenge_days_t = sa.table(
    "challenge_days", sa.column("id", PG_UUID), sa.column("challenge_id", PG_UUID), sa.column("day_number", sa.Integer),
    sa.column("title", sa.String), sa.column("description", sa.Text), sa.column("created_at", sa.DateTime(timezone=True)),
)
challenge_missions_t = sa.table(
    "challenge_missions", sa.column("id", PG_UUID), sa.column("challenge_day_id", PG_UUID), sa.column("code", sa.String),
    sa.column("title", sa.String), sa.column("description", sa.Text), sa.column("mission_type", sa.String),
    sa.column("config", JSONB), sa.column("xp_amount", sa.Integer), sa.column("is_required", sa.Boolean),
    sa.column("order_index", sa.Integer), sa.column("created_at", sa.DateTime(timezone=True)),
)
badge_definitions_t = sa.table(
    "badge_definitions", sa.column("id", PG_UUID), sa.column("code", sa.String), sa.column("version", sa.Integer),
    sa.column("title", sa.String), sa.column("description", sa.Text), sa.column("condition_type", sa.String),
    sa.column("condition_config", JSONB), sa.column("status", sa.String), sa.column("created_at", sa.DateTime(timezone=True)),
)

CHALLENGE_CODE = "seven-day-challenge"

CARD_LESSONS = [
    {
        "title": "주문 방식: 시장가와 지정가",
        "objective": "시장가 주문과 지정가 주문의 차이를 설명할 수 있다.",
        "body": (
            "시장가 주문은 지금 시장에 나와 있는 가격으로 즉시 체결을 시도하는 주문입니다. 빠르게 "
            "체결되지만 실제 체결 가격이 예상과 다소 달라질 수 있습니다. 지정가 주문은 내가 원하는 "
            "가격을 미리 정해두고, 시장 가격이 그 조건을 만족할 때만 체결되는 주문입니다. 원하는 "
            "가격을 지킬 수 있지만, 그 가격에 도달하지 않으면 체결되지 않을 수 있습니다."
        ),
        "example": (
            "예: 현재가가 10,000원일 때 시장가 매수는 지금 즉시 사겠다는 뜻이고, 9,500원 지정가 "
            "매수는 가격이 9,500원 이하로 내려와야만 사겠다는 뜻입니다."
        ),
        "summary": "시장가=속도 우선, 지정가=가격 우선. 무엇을 더 중요하게 여기는지에 따라 선택합니다.",
        "questions": [
            {
                "prompt": "즉시 체결을 우선하고 싶을 때 적합한 주문 방식은?",
                "choices": [("시장가 주문", True), ("지정가 주문", False)],
                "explanation": "시장가 주문은 현재 시장 가격으로 즉시 체결을 시도합니다.",
            },
            {
                "prompt": "내가 원하는 가격 조건이 충족될 때만 체결되길 원한다면?",
                "choices": [("시장가 주문", False), ("지정가 주문", True)],
                "explanation": "지정가 주문은 지정한 가격 조건을 만족해야 체결됩니다.",
            },
        ],
    },
    {
        "title": "분산과 집중위험",
        "objective": "분산투자가 위험을 줄이는 원리와 집중위험의 의미를 설명할 수 있다.",
        "body": (
            "한 종목에 자산을 몰아넣으면, 그 종목에 안 좋은 일이 생겼을 때 전체 자산이 크게 흔들릴 "
            "수 있습니다. 여러 종목·자산에 나누어 담으면 한 종목의 부진이 전체에 미치는 영향을 "
            "줄일 수 있는데, 이를 분산투자라고 합니다. 반대로 특정 종목의 비중이 과도하게 높은 "
            "상태를 집중위험이라고 부릅니다."
        ),
        "example": "예: 자산의 90%를 한 종목에 담았다면, 그 종목이 크게 하락할 때 전체 자산도 크게 하락합니다.",
        "summary": "분산은 위험을 없애는 것이 아니라 한 곳에 쏠린 위험을 줄이는 방법입니다.",
        "questions": [
            {
                "prompt": "한 종목에 자산의 대부분을 담은 상태를 무엇이라고 부르나요?",
                "choices": [("집중위험", True), ("분산투자", False)],
                "explanation": "특정 종목·자산 비중이 지나치게 높은 상태를 집중위험이라고 합니다.",
            },
            {
                "prompt": "분산투자의 주된 목적은 무엇인가요?",
                "choices": [("특정 종목의 부진이 전체 자산에 미치는 영향을 줄이는 것", True), ("반드시 더 높은 수익을 내는 것", False)],
                "explanation": "분산투자는 위험을 줄이는 방법이지, 수익을 보장하는 방법이 아닙니다.",
            },
        ],
    },
    {
        "title": "행동편향 살펴보기",
        "objective": "확증편향과 처분효과의 의미를 설명하고, 자신의 거래 기록에서 관찰될 수 있는 신호를 안다.",
        "body": (
            "확증편향은 내 생각을 뒷받침하는 근거만 찾고 반대 근거는 무시하는 경향입니다. 처분효과는 "
            "이익 난 종목은 빨리 팔고 손실 난 종목은 오래 들고 있으려는 경향입니다. 이런 경향은 "
            "누구에게나 있을 수 있으며, 이를 안다는 것 자체가 더 나은 판단의 출발점입니다."
        ),
        "example": "예: 매수 전 일지에 반대 근거를 한 번도 적지 않았다면 확증편향 신호일 수 있습니다.",
        "summary": "편향은 진단이 아니라 관찰된 패턴입니다 — 알아차리는 것이 첫걸음입니다.",
        "questions": [
            {
                "prompt": "내 생각을 뒷받침하는 근거만 찾고 반대 근거를 무시하는 경향은?",
                "choices": [("확증편향", True), ("처분효과", False)],
                "explanation": "확증편향은 자신의 판단을 지지하는 정보만 선택적으로 받아들이는 경향입니다.",
            },
            {
                "prompt": "이익 종목은 빨리 팔고 손실 종목은 오래 보유하려는 경향은?",
                "choices": [("확증편향", False), ("처분효과", True)],
                "explanation": "처분효과는 손실 확정을 피하려는 심리에서 비롯된 경향입니다.",
            },
        ],
    },
]


def _lesson_exists(conn, title: str) -> bool:
    return conn.execute(sa.text("SELECT 1 FROM lessons WHERE title = :t"), {"t": title}).first() is not None


def _seed_card_lessons(conn, now) -> dict[str, dict[str, uuid.UUID]]:
    """반환값: {lesson_title: {"lesson_id":.., "quiz_id":..}} — 없는 카드만 새로 만든다."""
    course_row = conn.execute(
        sa.text("SELECT id FROM courses WHERE title = '투자 시작하기'")
    ).first()
    if course_row is None:
        raise RuntimeError("기준 course('투자 시작하기')를 찾을 수 없습니다 — 이전 migration이 먼저 적용돼야 합니다.")
    course_id = course_row[0]

    module_row = conn.execute(
        sa.text("SELECT id FROM modules WHERE course_id = :cid AND title = '보충: 7일 챌린지 카드'"),
        {"cid": course_id},
    ).first()
    if module_row is None:
        module_id = uuid.uuid4()
        conn.execute(
            modules_t.insert().values(
                id=module_id, course_id=course_id, title="보충: 7일 챌린지 카드", order_index=1,
                status="PUBLISHED", created_at=now,
            )
        )
    else:
        module_id = module_row[0]

    result: dict[str, dict[str, uuid.UUID]] = {}
    for index, card in enumerate(CARD_LESSONS):
        existing = conn.execute(
            sa.text("SELECT l.id, q.id FROM lessons l JOIN quizzes q ON q.lesson_id = l.id WHERE l.title = :t"),
            {"t": card["title"]},
        ).first()
        if existing is not None:
            result[card["title"]] = {"lesson_id": existing[0], "quiz_id": existing[1]}
            continue

        lesson_id = uuid.uuid4()
        conn.execute(
            lessons_t.insert().values(
                id=lesson_id, module_id=module_id, title=card["title"], learning_objective=card["objective"],
                estimated_minutes=2, order_index=index, status="PUBLISHED",
                source="7일 챌린지 콘텐츠 v1 (내부 검수)", reviewed_by="challenge-content-team",
                reviewed_at=date(2026, 8, 22), created_at=now,
            )
        )
        for block_index, (block_type, content) in enumerate(
            [("OBJECTIVE", card["objective"]), ("BODY", card["body"]), ("EXAMPLE", card["example"]), ("SUMMARY", card["summary"])]
        ):
            conn.execute(
                content_blocks_t.insert().values(
                    id=uuid.uuid4(), lesson_id=lesson_id, block_type=block_type, content=content, order_index=block_index,
                )
            )

        quiz_id = uuid.uuid4()
        conn.execute(
            quizzes_t.insert().values(id=quiz_id, lesson_id=lesson_id, title=f"{card['title']} 이해 확인", pass_score_pct=70)
        )
        for q_index, question in enumerate(card["questions"]):
            question_id = uuid.uuid4()
            conn.execute(
                questions_t.insert().values(
                    id=question_id, quiz_id=quiz_id, prompt=question["prompt"], question_type="SINGLE_CHOICE",
                    explanation=question["explanation"], order_index=q_index,
                )
            )
            for c_index, (label, is_correct) in enumerate(question["choices"]):
                conn.execute(
                    choices_t.insert().values(
                        id=uuid.uuid4(), question_id=question_id, label=label, is_correct=is_correct, order_index=c_index,
                    )
                )
        result[card["title"]] = {"lesson_id": lesson_id, "quiz_id": quiz_id}
    return result


def _mission(day_id, code, title, mission_type, config, xp, order_index, description=None, is_required=True):
    return {
        "id": uuid.uuid4(), "challenge_day_id": day_id, "code": code, "title": title, "description": description,
        "mission_type": mission_type, "config": config, "xp_amount": xp, "is_required": is_required,
        "order_index": order_index,
    }


def upgrade() -> None:
    conn = op.get_bind()
    now = datetime.now(timezone.utc)

    if conn.execute(sa.text("SELECT 1 FROM challenges WHERE code = :c"), {"c": CHALLENGE_CODE}).first() is not None:
        return  # 멱등: 이미 시드돼 있으면 아무것도 하지 않는다.

    card_ids = _seed_card_lessons(conn, now)

    day1_lesson = conn.execute(sa.text("SELECT id FROM lessons WHERE title = '투자는 무엇인가'")).first()
    if day1_lesson is None:
        raise RuntimeError("기준 강의('투자는 무엇인가')를 찾을 수 없습니다.")
    day1_lesson_id = day1_lesson[0]
    day1_quiz_id = conn.execute(sa.text("SELECT id FROM quizzes WHERE lesson_id = :lid"), {"lid": day1_lesson_id}).first()[0]

    challenge_id = uuid.uuid4()
    conn.execute(
        challenges_t.insert().values(
            id=challenge_id, code=CHALLENGE_CODE, version=1, title="7일 투자 학습 챌린지",
            description=(
                "수익률이나 거래 횟수가 아니라, 학습·투자 전 계획·반대 근거·손실 제한·복기 같은 "
                "'좋은 과정'을 7일에 걸쳐 익히는 초보자용 프로그램입니다."
            ),
            total_days=7, status="PUBLISHED", created_at=now,
        )
    )

    days = [
        (1, "투자와 위험", "투자와 저축의 차이, 위험의 의미를 이해합니다."),
        (2, "주문 방식 이해", "시장가·지정가 주문의 차이를 이해하고 가상 주문을 미리보기합니다."),
        (3, "투자 논리 작성", "종목을 고르고 매수 근거·반대 근거·손실 제한 조건을 담은 거래 전 일지를 씁니다."),
        (4, "분산과 집중위험", "분산투자와 집중위험을 이해하고 내 포트폴리오의 집중도를 확인합니다."),
        (5, "모의투자 실습", "거래 전 일지와 연결된 가상 주문을 미리보기하고 비용을 확인합니다."),
        (6, "행동편향", "확증편향·처분효과를 이해하고 내 거래에서 관찰되는 패턴을 확인합니다."),
        (7, "복기와 계획", "거래 후 복기를 쓰고 과정 점수를 확인한 뒤 다음 주 개선행동을 정합니다."),
    ]
    day_ids: dict[int, uuid.UUID] = {}
    for day_number, title, description in days:
        day_id = uuid.uuid4()
        day_ids[day_number] = day_id
        conn.execute(
            challenge_days_t.insert().values(
                id=day_id, challenge_id=challenge_id, day_number=day_number, title=title, description=description,
                created_at=now,
            )
        )

    order_lesson = card_ids["주문 방식: 시장가와 지정가"]
    diversification_lesson = card_ids["분산과 집중위험"]
    bias_lesson = card_ids["행동편향 살펴보기"]

    missions = [
        _mission(day_ids[1], "day1_lesson", "1강 학습: 투자는 무엇인가", "LESSON_COMPLETE",
                 {"lesson_id": str(day1_lesson_id)}, 10, 0),
        _mission(day_ids[1], "day1_quiz", "1강 퀴즈 통과", "QUIZ_PASS", {"quiz_id": str(day1_quiz_id)}, 15, 1),
        _mission(day_ids[1], "day1_goal", "이번 주 학습목표 정하기", "GOAL_NOTE", {"min_length": 5}, 10, 2,
                 description="이번 7일 동안 이루고 싶은 학습목표를 한 줄로 적어보세요."),

        _mission(day_ids[2], "day2_lesson", "주문 방식 카드 학습", "LESSON_COMPLETE",
                 {"lesson_id": str(order_lesson["lesson_id"])}, 10, 0),
        _mission(day_ids[2], "day2_quiz", "시장가·지정가 퀴즈 통과", "QUIZ_PASS",
                 {"quiz_id": str(order_lesson["quiz_id"])}, 15, 1),
        _mission(day_ids[2], "day2_preview", "가상 주문 미리보기", "ORDER_PREVIEW", {}, 15, 2,
                 description="실제 체결은 필요 없습니다 — 미리보기로 예상 비용만 확인하면 됩니다."),

        _mission(day_ids[3], "day3_journal", "거래 전 일지 완성", "JOURNAL_PRE_TRADE", {}, 25, 0,
                 description="종목 1개를 고르고 매수 근거, 반대 근거 최소 1개, 손실 제한 조건을 작성하세요."),

        _mission(day_ids[4], "day4_lesson", "분산과 집중위험 카드 학습", "LESSON_COMPLETE",
                 {"lesson_id": str(diversification_lesson["lesson_id"])}, 10, 0),
        _mission(day_ids[4], "day4_quiz", "분산투자 퀴즈 통과", "QUIZ_PASS",
                 {"quiz_id": str(diversification_lesson["quiz_id"])}, 15, 1),
        _mission(day_ids[4], "day4_concentration", "내 포트폴리오 집중도 확인", "PORTFOLIO_CONCENTRATION_REVIEW", {}, 10, 2,
                 description="추가 주문은 필요 없습니다 — 현재 보유 종목의 비중만 확인합니다."),
        _mission(day_ids[4], "day4_scenario", "분산투자 교육 시나리오", "SCENARIO_CHOICE",
                 {"correct_choice": "A", "options": {"A": "두 종목에 60/40으로 나눠 담는다", "B": "한 종목에 100% 담는다"},
                  "explanation": "여러 종목에 나누어 담는 쪽이 분산투자 원칙에 맞습니다."},
                 10, 3),

        _mission(day_ids[5], "day5_order_preview", "일지와 연결된 가상 주문 미리보기", "ORDER_PREVIEW_LINKED_JOURNAL", {}, 25, 0,
                 description="Day 3에서 작성한 거래 전 일지를 골라, 그 종목의 예상 비용을 미리 확인하세요."),
        _mission(day_ids[5], "day5_disclosure", "가상자금·모의투자 고지 확인", "DISCLOSURE_ACK", {}, 5, 1),

        _mission(day_ids[6], "day6_lesson", "행동편향 카드 학습", "LESSON_COMPLETE",
                 {"lesson_id": str(bias_lesson["lesson_id"])}, 10, 0),
        _mission(day_ids[6], "day6_quiz", "행동편향 퀴즈 통과", "QUIZ_PASS", {"quiz_id": str(bias_lesson["quiz_id"])}, 15, 1),
        _mission(day_ids[6], "day6_bias", "내 거래 패턴 확인", "BIAS_REVIEW", {}, 10, 2),
        _mission(day_ids[6], "day6_coaching", "AI 코칭 확인", "COACHING_CONFIRM", {}, 15, 3,
                 description="AI 코치에게 내 일지에 대한 설명을 한 번 물어보세요."),

        _mission(day_ids[7], "day7_review", "거래 후 복기 작성", "POST_TRADE_REVIEW", {}, 25, 0,
                 description="최초 판단과 실제 행동을 비교하며 복기를 작성하세요."),
        _mission(day_ids[7], "day7_score", "과정 점수 확인", "PROCESS_SCORE_CHECK", {}, 10, 1),
        _mission(day_ids[7], "day7_next_action", "다음 주 개선행동 선택", "GOAL_NOTE", {"min_length": 5}, 10, 2,
                 description="다음 주에 시도해볼 개선행동 1개를 적어보세요."),
    ]
    for mission in missions:
        conn.execute(challenge_missions_t.insert().values(**mission, created_at=now))

    badges = [
        ("first_step", "첫걸음", "첫 강의를 완료했습니다.", "FIRST_LESSON_COMPLETE", {}),
        ("principled_investor", "원칙 있는 투자자", "거래 전 일지를 완성했습니다.", "JOURNAL_FIELD_PRESENT",
         {"field": "thesis"}),
        ("other_side", "반대편의 시선", "반대 근거를 기록했습니다.", "JOURNAL_FIELD_PRESENT",
         {"field": "counter_evidence", "require_list_nonempty": True}),
        ("risk_management_intro", "위험관리 입문", "손실 제한 조건을 작성했습니다.", "JOURNAL_FIELD_PRESENT",
         {"field": "stop_loss_condition"}),
        ("power_of_review", "복기의 힘", "거래 후 복기를 완료했습니다.", "JOURNAL_FIELD_PRESENT",
         {"field": "followed_plan"}),
        ("steady_learner", "꾸준한 학습자", "서로 다른 3일 동안 학습을 완료했습니다.", "THREE_DISTINCT_LEARNING_DAYS", {}),
        ("seven_day_finisher", "7일 완주", "7일 챌린지를 완료했습니다.", "SEVEN_DAY_CHALLENGE_COMPLETE",
         {"challenge_code": CHALLENGE_CODE}),
        ("cost_check_habit", "비용 확인 습관", "주문 미리보기에서 예상 비용을 확인했습니다.", "MISSION_TYPE_COMPLETED",
         {"mission_type": "ORDER_PREVIEW"}),
        ("plan_adherence", "계획 준수", "사전 계획과 실제 행동이 일치했다고 기록했습니다.", "JOURNAL_FIELD_PRESENT",
         {"field": "followed_plan", "require_true": True}),
        ("balanced_portfolio", "균형 잡힌 포트폴리오", "분산투자 교육 미션을 완료했습니다.", "MISSION_TYPE_COMPLETED",
         {"mission_code": "day4_scenario"}),
    ]
    for code, title, description, condition_type, condition_config in badges:
        if conn.execute(sa.text("SELECT 1 FROM badge_definitions WHERE code = :c"), {"c": code}).first() is not None:
            continue
        conn.execute(
            badge_definitions_t.insert().values(
                id=uuid.uuid4(), code=code, version=1, title=title, description=description,
                condition_type=condition_type, condition_config=condition_config, status="PUBLISHED", created_at=now,
            )
        )


def downgrade() -> None:
    """이 migration이 심은 seed 행을 지운다.

    주의: 이 seed가 나간 뒤 실제로 챌린지를 시작·진행한 사용자가 있다면
    user_challenges/user_mission_progress/user_badges 등 자식 행이 이미
    생겼을 수 있다(테스트에서도 마찬가지 — 다른 테스트 파일이 이 챌린지로
    실제 진행 데이터를 만든 채로 이 downgrade가 실행될 수 있다). 부모 행
    (challenges/challenge_missions/badge_definitions/lessons/quizzes)을
    지우기 전에 그 자식 행부터 FK 안전 순서로 지워야 한다. 이 downgrade는
    seed 자체를 되돌리는 개발/테스트 도구이지, 운영에서 진행 중인 사용자
    데이터를 보존하며 부분 롤백하는 기능이 아니다 — 이 챌린지 하나를
    통째로 되돌릴 때만 쓴다.
    """
    badge_codes = (
        "'first_step','principled_investor','other_side','risk_management_intro','power_of_review',"
        "'steady_learner','seven_day_finisher','cost_check_habit','plan_adherence','balanced_portfolio'"
    )
    op.execute(sa.text(
        f"DELETE FROM user_mission_progress WHERE user_challenge_id IN "
        f"(SELECT id FROM user_challenges WHERE challenge_id IN "
        f"(SELECT id FROM challenges WHERE code = '{CHALLENGE_CODE}'))"
    ))
    op.execute(sa.text(
        f"DELETE FROM user_challenge_days WHERE user_challenge_id IN "
        f"(SELECT id FROM user_challenges WHERE challenge_id IN "
        f"(SELECT id FROM challenges WHERE code = '{CHALLENGE_CODE}'))"
    ))
    op.execute(sa.text(
        f"DELETE FROM user_challenges WHERE challenge_id IN "
        f"(SELECT id FROM challenges WHERE code = '{CHALLENGE_CODE}')"
    ))
    op.execute(sa.text(f"DELETE FROM user_badges WHERE badge_definition_id IN "
                        f"(SELECT id FROM badge_definitions WHERE code IN ({badge_codes}))"))
    op.execute(sa.text(f"DELETE FROM badge_definitions WHERE code IN ({badge_codes})"))
    op.execute(sa.text(f"DELETE FROM challenge_missions WHERE challenge_day_id IN "
                        f"(SELECT id FROM challenge_days WHERE challenge_id IN "
                        f"(SELECT id FROM challenges WHERE code = '{CHALLENGE_CODE}'))"))
    op.execute(sa.text(f"DELETE FROM challenge_days WHERE challenge_id IN "
                        f"(SELECT id FROM challenges WHERE code = '{CHALLENGE_CODE}')"))
    op.execute(sa.text(f"DELETE FROM challenges WHERE code = '{CHALLENGE_CODE}'"))
    card_titles = "('주문 방식: 시장가와 지정가','분산과 집중위험','행동편향 살펴보기')"
    op.execute(sa.text(
        f"DELETE FROM quiz_attempts WHERE quiz_id IN (SELECT id FROM quizzes WHERE lesson_id IN "
        f"(SELECT id FROM lessons WHERE title IN {card_titles}))"
    ))
    op.execute(sa.text(
        f"DELETE FROM lesson_progress WHERE lesson_id IN (SELECT id FROM lessons WHERE title IN {card_titles})"
    ))
    op.execute(sa.text(
        f"DELETE FROM choices WHERE question_id IN (SELECT id FROM questions WHERE quiz_id IN "
        f"(SELECT id FROM quizzes WHERE lesson_id IN (SELECT id FROM lessons WHERE title IN {card_titles})))"
    ))
    op.execute(sa.text(
        f"DELETE FROM questions WHERE quiz_id IN (SELECT id FROM quizzes WHERE lesson_id IN "
        f"(SELECT id FROM lessons WHERE title IN {card_titles}))"
    ))
    op.execute(sa.text(f"DELETE FROM quizzes WHERE lesson_id IN (SELECT id FROM lessons WHERE title IN {card_titles})"))
    op.execute(sa.text(f"DELETE FROM content_blocks WHERE lesson_id IN (SELECT id FROM lessons WHERE title IN {card_titles})"))
    op.execute(sa.text(f"DELETE FROM lessons WHERE title IN {card_titles}"))
    op.execute(sa.text("DELETE FROM modules WHERE title = '보충: 7일 챌린지 카드'"))
