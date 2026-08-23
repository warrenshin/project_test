"""add lesson content metadata columns (code, source, review, version) + review audit table

Revision ID: 8255aa2780e6
Revises: b5ae854dc4ef
Create Date: 2026-08-23T00:00:00.000000

6~15강 콘텐츠를 위한 순수 additive 스키마 변경이다 — 기존 테이블 구조·데이터는
전혀 건드리지 않는다:

- lessons: code(안정적 식별자, 부분 unique — NULL 허용), source_url,
  source_confirmed_at, content_version, market_scope, review_status
- choices: explanation(오답별 설명, 채점 후 응답에만 노출)
- quizzes: content_version
- lesson_review_audits: 운영자 승인(publish_lesson.py) 감사기록. (lesson_id,
  content_version, action) unique 제약으로 같은 콘텐츠 버전에 대한 동일 승인
  액션 재실행이 멱등하다.

전부 additive이고 review_audits 테이블도 새 테이블이라 기존 행은 채울 필요가
없다. downgrade는 컬럼/테이블만 제거하고 다른 데이터는 건드리지 않는다.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '8255aa2780e6'
down_revision = 'b5ae854dc4ef'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('lessons', sa.Column('code', sa.String(length=64), nullable=True))
    op.add_column('lessons', sa.Column('source_url', sa.String(length=512), nullable=True))
    op.add_column('lessons', sa.Column('source_confirmed_at', sa.Date(), nullable=True))
    op.add_column('lessons', sa.Column('content_version', sa.String(length=16), nullable=True))
    op.add_column('lessons', sa.Column('market_scope', sa.String(length=32), nullable=True))
    op.add_column('lessons', sa.Column('review_status', sa.String(length=16), nullable=True))
    op.create_index(
        'uq_lessons_code', 'lessons', ['code'], unique=True, postgresql_where=sa.text('code IS NOT NULL')
    )

    op.add_column('choices', sa.Column('explanation', sa.Text(), nullable=True))

    op.add_column('quizzes', sa.Column('content_version', sa.String(length=16), nullable=True))

    op.create_table(
        'lesson_review_audits',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('lesson_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('lesson_code', sa.String(length=64), nullable=False),
        sa.Column('content_version', sa.String(length=16), nullable=False),
        sa.Column('action', sa.String(length=16), nullable=False),
        sa.Column('reviewer', sa.String(length=128), nullable=False),
        sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('source_verified', sa.Boolean(), nullable=False),
        sa.Column('note', sa.Text(), nullable=False),
        sa.Column('performed_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['lesson_id'], ['lessons.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'lesson_id', 'content_version', 'action', name='uq_lesson_review_audits_lesson_version_action'
        ),
    )


def downgrade() -> None:
    op.drop_table('lesson_review_audits')

    op.drop_column('quizzes', 'content_version')
    op.drop_column('choices', 'explanation')

    op.drop_index('uq_lessons_code', table_name='lessons')
    op.drop_column('lessons', 'review_status')
    op.drop_column('lessons', 'market_scope')
    op.drop_column('lessons', 'content_version')
    op.drop_column('lessons', 'source_confirmed_at')
    op.drop_column('lessons', 'source_url')
    op.drop_column('lessons', 'code')
