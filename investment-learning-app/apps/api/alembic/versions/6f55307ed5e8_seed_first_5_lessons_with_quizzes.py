"""seed first 5 lessons with quizzes

Revision ID: 6f55307ed5e8
Revises: 580cc4a7ebab
Create Date: 2026-08-16 14:00:00.000000

부록 B "첫 30개 강의 권장 목차"의 1~5강을 시드한다. 나머지 25강은 콘텐츠
제작 작업이며 content/courses/README.md에 후속 과제로 남아 있다.
"""
import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

# revision identifiers, used by Alembic.
revision = '6f55307ed5e8'
down_revision = '580cc4a7ebab'
branch_labels = None
depends_on = None

learning_paths_t = sa.table(
    "learning_paths", sa.column("id", PG_UUID), sa.column("title", sa.String), sa.column("description", sa.Text),
    sa.column("target_experience_level", sa.String), sa.column("order_index", sa.Integer), sa.column("status", sa.String),
    sa.column("created_at", sa.DateTime(timezone=True)),
)
courses_t = sa.table(
    "courses", sa.column("id", PG_UUID), sa.column("learning_path_id", PG_UUID), sa.column("title", sa.String),
    sa.column("description", sa.Text), sa.column("order_index", sa.Integer), sa.column("status", sa.String),
    sa.column("created_at", sa.DateTime(timezone=True)),
)
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

LESSONS = [
    {
        "title": "투자는 무엇인가",
        "objective": "투자와 저축의 차이를 설명하고, 투자의 기본 목적을 이해한다.",
        "body": "투자는 미래에 더 큰 가치를 얻기 위해 현재의 자원(돈, 시간)을 특정 자산에 투입하는 행위입니다. "
                "저축은 원금 손실 위험이 거의 없이 돈을 보관하는 것에 가깝지만, 투자는 원금 손실 가능성을 "
                "감수하는 대신 더 높은 기대수익을 추구합니다.",
        "example": "예: 100만원을 예금하면 이자는 적지만 원금은 거의 보장됩니다. 같은 100만원을 주식에 투자하면 "
                   "가격이 오르내리며 원금 손실 위험이 있지만, 장기적으로 더 높은 수익을 기대할 수 있습니다.",
        "summary": "투자는 원금 손실 위험을 감수하고 더 높은 기대수익을 추구하는 행위이며, 목적과 기간에 맞는 "
                   "수단을 선택하는 것이 중요합니다.",
        "questions": [
            {
                "prompt": "저축과 투자의 가장 큰 차이는 무엇인가요?",
                "explanation": "투자는 원금 손실 위험을 감수하는 대신 더 높은 기대수익을 추구한다는 점이 핵심입니다.",
                "choices": [
                    ("투자는 원금 손실 위험을 감수하고 더 높은 기대수익을 추구한다", True),
                    ("투자와 저축은 위험 수준이 동일하다", False),
                    ("저축은 항상 투자보다 수익률이 높다", False),
                    ("투자는 무조건 단기간에 끝난다", False),
                ],
            },
            {
                "prompt": "다음 중 투자에 대한 설명으로 옳은 것은?",
                "explanation": "투자는 미래의 더 큰 가치를 위해 현재 자원을 특정 자산에 투입하는 행위입니다.",
                "choices": [
                    ("미래의 더 큰 가치를 위해 현재 자원을 특정 자산에 투입하는 행위이다", True),
                    ("은행에 돈을 맡기고 이자를 받는 행위만을 의미한다", False),
                    ("원금 손실이 전혀 발생하지 않는 안전한 활동이다", False),
                    ("정해진 기간 없이 아무 때나 원금이 100% 보장된다", False),
                ],
            },
        ],
    },
    {
        "title": "수익과 위험의 관계",
        "objective": "기대수익과 위험이 비례하는 이유를 이해하고, 고수익=고위험 원칙을 설명한다.",
        "body": "일반적으로 기대수익이 높은 자산일수록 가격 변동성(위험)도 큽니다. 이는 투자자가 더 큰 불확실성을 "
                "감수하는 대가로 더 높은 보상을 요구하기 때문입니다. 반대로 위험이 낮은 자산(예금, 국채)은 "
                "기대수익도 낮습니다.",
        "example": "예: 국채는 안정적이지만 연 3~4% 수준의 수익을 기대하는 반면, 개별 주식은 연간 수익률이 크게 "
                   "출렁일 수 있지만 장기 평균 기대수익은 더 높을 수 있습니다.",
        "summary": "위험 없는 고수익은 존재하지 않습니다. 자신의 위험 감내 수준에 맞는 자산 배분이 중요합니다.",
        "questions": [
            {
                "prompt": "일반적으로 기대수익이 높은 자산의 특징은?",
                "explanation": "기대수익이 높을수록 가격 변동성(위험)도 함께 커지는 경향이 있습니다.",
                "choices": [
                    ("가격 변동성(위험)도 함께 높은 경향이 있다", True),
                    ("가격이 절대 하락하지 않는다", False),
                    ("원금이 100% 보장된다", False),
                    ("위험과는 아무 관련이 없다", False),
                ],
            },
            {
                "prompt": "다음 중 옳은 설명은?",
                "explanation": "위험을 전혀 감수하지 않으면서 꾸준히 고수익을 보장하는 투자는 존재하지 않습니다.",
                "choices": [
                    ("위험 없이 고수익을 꾸준히 보장하는 투자는 존재하지 않는다", True),
                    ("국채는 개별 주식보다 항상 기대수익이 높다", False),
                    ("위험이 낮을수록 기대수익도 항상 높아진다", False),
                    ("투자 위험은 수익과 전혀 상관관계가 없다", False),
                ],
            },
        ],
    },
    {
        "title": "주식과 주주의 권리",
        "objective": "주식이 무엇을 의미하는지, 주주가 가지는 기본 권리를 이해한다.",
        "body": "주식은 기업의 소유권을 나타내는 증서입니다. 주식을 보유한 사람(주주)은 보유 비율만큼 회사의 "
                "이익과 의사결정에 참여할 권리를 가집니다. 대표적인 권리로는 배당을 받을 권리(이익배당청구권), "
                "주주총회에서 의결권을 행사할 권리, 신주를 우선 배정받을 권리 등이 있습니다.",
        "example": "예: A기업 주식을 1% 보유하고 있다면, 이론적으로 그 회사 이익의 1%에 대한 배당 청구권과 "
                   "주주총회 의결권 1%를 가집니다.",
        "summary": "주식 보유는 단순한 가격 베팅이 아니라 기업의 부분 소유권을 갖는 것이며, 배당·의결권 등 "
                   "주주로서의 권리가 함께 따라옵니다.",
        "questions": [
            {
                "prompt": "주식을 보유한다는 것은 무엇을 의미하나요?",
                "explanation": "주식 보유는 해당 기업의 소유권 일부를 갖는 것을 의미합니다.",
                "choices": [
                    ("해당 기업의 소유권 일부를 갖는 것이다", True),
                    ("그 기업에 돈을 빌려주는 것이다", False),
                    ("그 기업의 직원이 되는 것이다", False),
                    ("아무런 권리도 없이 가격 변동만 따라가는 것이다", False),
                ],
            },
            {
                "prompt": "다음 중 대표적인 주주의 권리에 대한 설명으로 옳지 않은 것은?",
                "explanation": "주주는 회사가 파산할 경우 채권자보다 후순위로 잔여재산을 분배받습니다 — "
                               "채권자보다 먼저 상환받을 권리는 없습니다.",
                "choices": [
                    ("배당을 받을 권리(이익배당청구권)", False),
                    ("주주총회에서 의결권을 행사할 권리", False),
                    ("신주를 우선 배정받을 권리", False),
                    ("회사가 파산해도 채권자보다 먼저 자산을 돌려받을 권리", True),
                ],
            },
        ],
    },
    {
        "title": "ETF의 구조",
        "objective": "ETF가 무엇이며 개별 주식과 어떻게 다른지 이해한다.",
        "body": "ETF(상장지수펀드)는 여러 종목을 묶어 하나의 상품처럼 거래소에서 사고팔 수 있게 만든 펀드입니다. "
                "특정 지수(예: 코스피200, S&P500)를 추종하도록 설계되는 경우가 많아, 한 번의 매수로 여러 종목에 "
                "분산투자하는 효과를 얻을 수 있습니다.",
        "example": "예: 코스피200 ETF 1주를 사면, 코스피200에 포함된 200개 종목에 비중대로 분산투자한 것과 "
                   "비슷한 효과를 얻습니다.",
        "summary": "ETF는 개별 종목 선택의 부담 없이 분산투자 효과를 손쉽게 얻을 수 있는 수단입니다.",
        "questions": [
            {
                "prompt": "ETF의 가장 큰 특징은 무엇인가요?",
                "explanation": "ETF는 여러 종목을 묶어 거래소에서 하나의 상품처럼 매매할 수 있는 상품입니다.",
                "choices": [
                    ("여러 종목을 묶어 거래소에서 하나의 상품처럼 매매할 수 있다", True),
                    ("반드시 한 종목에만 투자한다", False),
                    ("원금 손실이 절대 발생하지 않는다", False),
                    ("거래소에서 매매할 수 없고 은행에서만 가입 가능하다", False),
                ],
            },
            {
                "prompt": "코스피200 ETF를 매수하면 얻는 효과로 가장 적절한 것은?",
                "explanation": "지수를 추종하는 ETF를 매수하면 해당 지수 구성 종목에 비중대로 분산투자하는 효과를 얻습니다.",
                "choices": [
                    ("코스피200에 포함된 여러 종목에 비중대로 분산투자하는 효과", True),
                    ("코스피200 지수와 무관한 무작위 종목에 투자하는 효과", False),
                    ("반드시 원금이 2배로 보장되는 효과", False),
                    ("해당 기업 하나의 경영권을 인수하는 효과", False),
                ],
            },
        ],
    },
    {
        "title": "채권과 금리",
        "objective": "채권의 기본 구조와 금리와의 관계를 이해한다.",
        "body": "채권은 정부나 기업이 투자자에게 돈을 빌리면서 발행하는 증서입니다. 채권을 산다는 것은 발행자에게 "
                "돈을 빌려주고, 정해진 기간 동안 이자를 받은 뒤 만기에 원금을 돌려받기로 약속받는 것입니다. "
                "시중 금리가 오르면 기존에 발행된 채권의 가격은 대체로 하락하고, 금리가 내리면 채권 가격은 "
                "대체로 상승합니다.",
        "example": "예: 연 3% 이자를 주는 채권을 보유하고 있는데 시중 금리가 5%로 오르면, 새로 발행되는 채권이 "
                   "더 매력적이므로 기존 채권의 가격은 하락하는 경향이 있습니다.",
        "summary": "채권은 '빌려주고 이자를 받는' 구조이며, 채권 가격은 시중 금리와 반대 방향으로 움직이는 "
                   "경향이 있습니다.",
        "questions": [
            {
                "prompt": "채권을 산다는 것은 기본적으로 무엇을 의미하나요?",
                "explanation": "채권 매수는 발행자에게 돈을 빌려주고 이자와 원금을 받기로 약속받는 것입니다.",
                "choices": [
                    ("발행자에게 돈을 빌려주고 이자와 원금을 받기로 약속받는 것", True),
                    ("그 기업의 소유권 일부를 갖는 것", False),
                    ("아무 조건 없이 기부하는 것", False),
                    ("발행자의 경영에 참여할 의결권을 갖는 것", False),
                ],
            },
            {
                "prompt": "시중 금리가 오르면 기존 채권 가격은 일반적으로 어떻게 되나요?",
                "explanation": "금리가 오르면 새로 발행되는 채권의 매력이 커져 기존 채권 가격은 대체로 하락합니다.",
                "choices": [
                    ("대체로 하락하는 경향이 있다", True),
                    ("대체로 상승하는 경향이 있다", False),
                    ("금리와 전혀 무관하게 움직인다", False),
                    ("항상 액면가에 고정된다", False),
                ],
            },
        ],
    },
]


def upgrade() -> None:
    now = datetime.now(timezone.utc)

    path_id = uuid.uuid4()
    op.execute(
        learning_paths_t.insert().values(
            id=path_id, title="투자 기초 입문", description="완전 초보자를 위한 첫 학습 경로",
            target_experience_level="BEGINNER", order_index=0, status="PUBLISHED", created_at=now,
        )
    )

    course_id = uuid.uuid4()
    op.execute(
        courses_t.insert().values(
            id=course_id, learning_path_id=path_id, title="투자 시작하기",
            description="투자의 기본 개념부터 채권까지", order_index=0, status="PUBLISHED", created_at=now,
        )
    )

    module_id = uuid.uuid4()
    op.execute(
        modules_t.insert().values(
            id=module_id, course_id=course_id, title="1부. 투자의 기본 개념", order_index=0,
            status="PUBLISHED", created_at=now,
        )
    )

    for lesson_index, lesson in enumerate(LESSONS):
        lesson_id = uuid.uuid4()
        op.execute(
            lessons_t.insert().values(
                id=lesson_id, module_id=module_id, title=lesson["title"],
                learning_objective=lesson["objective"], estimated_minutes=5, order_index=lesson_index,
                status="PUBLISHED", source="docs/product-spec.md 부록 B", reviewed_by=None, reviewed_at=None,
                created_at=now,
            )
        )

        blocks = [
            ("OBJECTIVE", lesson["objective"]),
            ("BODY", lesson["body"]),
            ("EXAMPLE", lesson["example"]),
            ("SUMMARY", lesson["summary"]),
        ]
        for block_index, (block_type, content) in enumerate(blocks):
            op.execute(
                content_blocks_t.insert().values(
                    id=uuid.uuid4(), lesson_id=lesson_id, block_type=block_type, content=content,
                    order_index=block_index,
                )
            )

        quiz_id = uuid.uuid4()
        op.execute(
            quizzes_t.insert().values(id=quiz_id, lesson_id=lesson_id, title=f"{lesson['title']} 이해 확인", pass_score_pct=70)
        )

        for q_index, question in enumerate(lesson["questions"]):
            question_id = uuid.uuid4()
            op.execute(
                questions_t.insert().values(
                    id=question_id, quiz_id=quiz_id, prompt=question["prompt"], question_type="SINGLE_CHOICE",
                    explanation=question["explanation"], order_index=q_index,
                )
            )
            for c_index, (label, is_correct) in enumerate(question["choices"]):
                op.execute(
                    choices_t.insert().values(
                        id=uuid.uuid4(), question_id=question_id, label=label, is_correct=is_correct,
                        order_index=c_index,
                    )
                )


def downgrade() -> None:
    op.execute(
        "DELETE FROM choices WHERE question_id IN (SELECT id FROM questions WHERE quiz_id IN "
        "(SELECT id FROM quizzes WHERE lesson_id IN (SELECT id FROM lessons WHERE module_id IN "
        "(SELECT id FROM modules WHERE course_id IN (SELECT id FROM courses WHERE title = '투자 시작하기')))))"
    )
    op.execute(
        "DELETE FROM questions WHERE quiz_id IN (SELECT id FROM quizzes WHERE lesson_id IN "
        "(SELECT id FROM lessons WHERE module_id IN (SELECT id FROM modules WHERE course_id IN "
        "(SELECT id FROM courses WHERE title = '투자 시작하기'))))"
    )
    op.execute(
        "DELETE FROM quizzes WHERE lesson_id IN (SELECT id FROM lessons WHERE module_id IN "
        "(SELECT id FROM modules WHERE course_id IN (SELECT id FROM courses WHERE title = '투자 시작하기')))"
    )
    op.execute(
        "DELETE FROM content_blocks WHERE lesson_id IN (SELECT id FROM lessons WHERE module_id IN "
        "(SELECT id FROM modules WHERE course_id IN (SELECT id FROM courses WHERE title = '투자 시작하기')))"
    )
    op.execute(
        "DELETE FROM lessons WHERE module_id IN (SELECT id FROM modules WHERE course_id IN "
        "(SELECT id FROM courses WHERE title = '투자 시작하기'))"
    )
    op.execute("DELETE FROM modules WHERE course_id IN (SELECT id FROM courses WHERE title = '투자 시작하기')")
    op.execute("DELETE FROM courses WHERE title = '투자 시작하기'")
    op.execute("DELETE FROM learning_paths WHERE title = '투자 기초 입문'")
