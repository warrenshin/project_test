"""assign stable codes to existing lessons 1-5 and seven-day-challenge cards

Revision ID: e75a015c620b
Revises: c1a2b3d4e5f6
Create Date: 2026-08-23T08:00:00.000000

CI가 "필수 seed lesson code 집합이 각각 정확히 1개씩 존재하는지"를 검증하려면
기존 1~5강·7일 챌린지 카드 강의도 안정적인 code가 있어야 한다. 이 migration은
title로 기존 행을 찾아 code만 채우는 순수 UPDATE다 — id·content·status·
review_status·진도(lesson_progress)·XP 무엇도 건드리지 않는다.

멱등: lesson-01의 code가 이미 채워져 있으면 아무것도 하지 않는다.
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'e75a015c620b'
down_revision = 'c1a2b3d4e5f6'
branch_labels = None
depends_on = None

# title -> code. 1~5강은 부록 B 순서, 챌린지 카드는 7일 챌린지에서 실제 쓰이는
# Day 번호를 코드에 반영해 둔다(challenge_missions.config는 lesson_id(UUID)를
# 참조하므로 이 code 부여 자체는 챌린지 미션 연결에 영향을 주지 않는다).
TITLE_TO_CODE = {
    "투자는 무엇인가": "lesson-01",
    "수익과 위험의 관계": "lesson-02",
    "주식과 주주의 권리": "lesson-03",
    "ETF의 구조": "lesson-04",
    "채권과 금리": "lesson-05",
    "주문 방식: 시장가와 지정가": "challenge-day2-order-types",
    "분산과 집중위험": "challenge-day4-diversification",
    "행동편향 살펴보기": "challenge-day6-bias",
}


def upgrade() -> None:
    conn = op.get_bind()
    already_done = conn.execute(
        sa.text("SELECT 1 FROM lessons WHERE title = '투자는 무엇인가' AND code IS NOT NULL")
    ).first()
    if already_done is not None:
        return  # 멱등: 이미 채워져 있으면 아무것도 하지 않는다.

    for title, code in TITLE_TO_CODE.items():
        result = conn.execute(
            sa.text("UPDATE lessons SET code = :code WHERE title = :title AND code IS NULL"),
            {"code": code, "title": title},
        )
        if result.rowcount == 0:
            # 대상 강의가 아예 없으면(예: 테스트 DB에서 이전 migration을 건너뛴
            # 경우) 조용히 넘어간다 — 이 migration은 "있으면 채운다"이지 새로
            # 만들지 않는다.
            continue


def downgrade() -> None:
    codes = tuple(TITLE_TO_CODE.values())
    conn = op.get_bind()
    conn.execute(
        sa.text("UPDATE lessons SET code = NULL WHERE code IN :codes").bindparams(
            sa.bindparam("codes", expanding=True)
        ),
        {"codes": list(codes)},
    )
