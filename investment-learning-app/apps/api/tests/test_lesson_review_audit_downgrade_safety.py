"""c1a2b3d4e5f6(6~15강 시드) downgrade가 lesson_review_audits 존재 시 안전하게
중단되는지 검증한다 — 일반 API 테스트가 아니라 migration 자체를 실제
Postgres에 대해 downgrade/upgrade하며 확인하는 전용 테스트다
(test_lessons_06_15_migration.py, test_migration_duplicate_instrument_merge.py와
동일한 패턴).

격리 원칙: 이 저장소의 테스트 DB는 파일 간 공유되고 트랜잭션으로 롤백되지
않는다. 이 파일은 lesson-06~15에 실제로 감사기록을 만들거나 지우는 시나리오를
다루므로, 매 테스트가 시작 전 상태를 정확히 스냅샷하고 끝나기 전에 반드시
그대로 복원한다 — 그래야 다른 테스트 파일들이 전제하는 "6~15강은
READY_FOR_REVIEW다"라는 상태가 이 파일 실행 이후에도 깨지지 않는다. 이 복원은
순전히 테스트 격리 목적이며, migration 자체가 감사기록을 자동 삭제하지 않는다는
프로덕션 안전 정책과는 무관하다.
"""
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text

from app.domain.learning import (
    CONTENT_PUBLISHED,
    CONTENT_READY_FOR_REVIEW,
    REVIEW_REQUIRED,
    REVIEW_REVIEWED,
    Choice,
    ContentBlock,
    Lesson,
    LessonReviewAudit,
    Question,
    Quiz,
)
from scripts.publish_lesson import publish_lesson
from datetime import datetime, timezone

DOWN_REVISION = "8255aa2780e6"  # 이 migration 바로 이전
TARGET_REVISION = "c1a2b3d4e5f6"  # 이 migration 자체
NEW_LESSON_CODES = [f"lesson-{n:02d}" for n in range(6, 16)]


def _alembic_config() -> Config:
    api_root = Path(__file__).resolve().parents[1]
    return Config(str(api_root / "alembic.ini"))


def _current_head(cfg: Config) -> str:
    heads = ScriptDirectory.from_config(cfg).get_heads()
    assert len(heads) == 1, f"head가 여러 개입니다: {heads}"
    return heads[0]


def _current_db_revision(conn) -> str:
    row = conn.execute(text("SELECT version_num FROM alembic_version")).first()
    return row[0] if row else None


def _snapshot_audits(db) -> list[dict]:
    rows = db.query(LessonReviewAudit).filter(LessonReviewAudit.lesson_code.in_(NEW_LESSON_CODES)).all()
    return [
        {
            "id": r.id, "lesson_id": r.lesson_id, "lesson_code": r.lesson_code,
            "content_version": r.content_version, "action": r.action, "reviewer": r.reviewer,
            "reviewed_at": r.reviewed_at, "source_verified": r.source_verified, "note": r.note,
            "performed_at": r.performed_at,
        }
        for r in rows
    ]


def _delete_all_audits(db) -> None:
    db.query(LessonReviewAudit).filter(LessonReviewAudit.lesson_code.in_(NEW_LESSON_CODES)).delete(
        synchronize_session=False
    )
    db.commit()


def _restore_audits(db, snapshot: list[dict]) -> None:
    _delete_all_audits(db)
    for row in snapshot:
        db.add(LessonReviewAudit(**row))
    db.commit()


def _snapshot_lessons(db, codes: list[str]) -> dict[str, dict]:
    out = {}
    for code in codes:
        l = db.query(Lesson).filter(Lesson.code == code).first()
        out[code] = {
            "status": l.status, "review_status": l.review_status, "reviewed_by": l.reviewed_by,
            "reviewed_at": l.reviewed_at, "source_confirmed_at": l.source_confirmed_at,
        }
    return out


def _restore_lessons(db, snapshot: dict[str, dict]) -> None:
    for code, fields in snapshot.items():
        l = db.query(Lesson).filter(Lesson.code == code).first()
        for k, v in fields.items():
            setattr(l, k, v)
    db.commit()


def _table_counts(db) -> dict[str, int]:
    return {
        "lessons_06_15": db.query(Lesson).filter(Lesson.code.in_(NEW_LESSON_CODES)).count(),
        "content_blocks": db.query(ContentBlock)
        .join(Lesson, ContentBlock.lesson_id == Lesson.id)
        .filter(Lesson.code.in_(NEW_LESSON_CODES))
        .count(),
        "quizzes": db.query(Quiz).join(Lesson, Quiz.lesson_id == Lesson.id).filter(Lesson.code.in_(NEW_LESSON_CODES)).count(),
        "questions": db.query(Question)
        .join(Quiz, Question.quiz_id == Quiz.id)
        .join(Lesson, Quiz.lesson_id == Lesson.id)
        .filter(Lesson.code.in_(NEW_LESSON_CODES))
        .count(),
        "choices": db.query(Choice)
        .join(Question, Choice.question_id == Question.id)
        .join(Quiz, Question.quiz_id == Quiz.id)
        .join(Lesson, Quiz.lesson_id == Lesson.id)
        .filter(Lesson.code.in_(NEW_LESSON_CODES))
        .count(),
        "audits": db.query(LessonReviewAudit).filter(LessonReviewAudit.lesson_code.in_(NEW_LESSON_CODES)).count(),
    }


@pytest.fixture
def clean_audit_slate(db):
    """이 테스트 파일이 실행되는 동안 lesson-06~15의 lesson_review_audits를
    비운 상태에서 시작하도록 보장하고, 끝나면 원래 있던 행을 정확히(같은
    id·모든 컬럼값) 복원한다. 다른 프로세스가 이미 만들어 둔 감사기록이
    있어도(예: 운영자가 실제로 강의를 승인해 둔 상태) 이 테스트 실행 동안만
    안전하게 비웠다가 그대로 되돌리므로 데이터가 유실되지 않는다."""
    session = db
    original = _snapshot_audits(session)
    _delete_all_audits(session)
    try:
        yield session
    finally:
        _restore_audits(session, original)


def test_downgrade_succeeds_when_no_audit_records_exist(clean_audit_slate):
    """감사기록이 전혀 없으면 기존과 동일하게 downgrade/upgrade가 정상 동작한다."""
    db = clean_audit_slate
    cfg = _alembic_config()
    head = _current_head(cfg)

    command.downgrade(cfg, DOWN_REVISION)
    db.expire_all()
    assert db.query(Lesson).filter(Lesson.code.in_(NEW_LESSON_CODES)).count() == 0

    command.upgrade(cfg, head)
    db.expire_all()
    assert db.query(Lesson).filter(Lesson.code.in_(NEW_LESSON_CODES)).count() == 10
    for l in db.query(Lesson).filter(Lesson.code.in_(NEW_LESSON_CODES)).all():
        assert l.status == CONTENT_READY_FOR_REVIEW
        assert l.review_status == REVIEW_REQUIRED


def _publish_throwaway(db, code: str) -> None:
    lesson = db.query(Lesson).filter(Lesson.code == code).first()
    publish_lesson(
        db, code=code, expected_content_version=lesson.content_version, reviewer="downgrade-safety-test",
        reviewed_at=datetime.now(timezone.utc), source_verified=bool(lesson.source_url), note="downgrade 안전성 테스트용 임시 승인",
    )


def test_downgrade_blocked_when_one_lesson_has_audit_record(clean_audit_slate):
    """lesson-06 하나만 승인(감사기록 존재)돼 있어도 downgrade는 명확한 오류로
    즉시 중단되고, DB 상태는 시도 전과 완전히 동일하게 유지돼야 한다."""
    db = clean_audit_slate
    cfg = _alembic_config()

    lesson_snapshot = _snapshot_lessons(db, NEW_LESSON_CODES)
    _publish_throwaway(db, "lesson-06")

    before_counts = _table_counts(db)
    conn = db.connection()
    before_revision = _current_db_revision(conn)

    with pytest.raises(RuntimeError, match="승인\\(게시\\) 감사기록이"):
        command.downgrade(cfg, DOWN_REVISION)

    db.expire_all()
    after_counts = _table_counts(db)
    assert after_counts == before_counts, "downgrade 실패 후 행 개수가 달라짐 — 부분 적용 의심"

    conn = db.connection()
    after_revision = _current_db_revision(conn)
    assert after_revision == before_revision, "downgrade 실패 후에도 alembic_version이 바뀜"

    audits = db.query(LessonReviewAudit).filter(LessonReviewAudit.lesson_code == "lesson-06").all()
    assert len(audits) == 1, "감사기록이 자동으로 삭제되면 안 된다"

    lesson06 = db.query(Lesson).filter(Lesson.code == "lesson-06").first()
    assert lesson06.status == CONTENT_PUBLISHED
    assert lesson06.review_status == REVIEW_REVIEWED

    _restore_lessons(db, lesson_snapshot)


def test_downgrade_blocked_when_multiple_lessons_have_audit_records(clean_audit_slate):
    """여러 강의(lesson-07, lesson-12 — 하나는 source_url 있음, 하나는 없음)에
    감사기록이 있어도 동일하게 중단되고, 오류 메시지에 두 코드가 모두
    언급돼야 한다."""
    db = clean_audit_slate
    cfg = _alembic_config()

    lesson_snapshot = _snapshot_lessons(db, NEW_LESSON_CODES)
    _publish_throwaway(db, "lesson-07")
    _publish_throwaway(db, "lesson-12")

    before_counts = _table_counts(db)

    with pytest.raises(RuntimeError) as exc_info:
        command.downgrade(cfg, DOWN_REVISION)
    message = str(exc_info.value)
    assert "lesson-07" in message
    assert "lesson-12" in message
    assert "자동으로 삭제" in message or "자동 삭제" in message

    db.expire_all()
    assert _table_counts(db) == before_counts

    audits = db.query(LessonReviewAudit).filter(LessonReviewAudit.lesson_code.in_(["lesson-07", "lesson-12"])).all()
    assert len(audits) == 2

    _restore_lessons(db, lesson_snapshot)


def test_downgrade_error_message_explains_no_auto_delete_and_ops_responsibility(clean_audit_slate):
    """오류 메시지가 요구된 세 가지 내용을 전부 담고 있는지 문구 자체를 확인한다:
    (1) 승인된 감사기록 때문에 안전한 downgrade 불가 (2) 감사기록 자동 삭제 안 함
    (3) 운영자가 데이터 보존/롤백 계획을 수립해야 함."""
    db = clean_audit_slate
    cfg = _alembic_config()
    lesson_snapshot = _snapshot_lessons(db, NEW_LESSON_CODES)
    _publish_throwaway(db, "lesson-15")

    with pytest.raises(RuntimeError) as exc_info:
        command.downgrade(cfg, DOWN_REVISION)
    message = str(exc_info.value)
    assert "안전" in message and "downgrade" in message.lower() or "안전" in message
    assert "감사기록" in message
    assert "자동" in message and "삭제" in message
    assert "운영자" in message

    _restore_lessons(db, lesson_snapshot)


def test_full_downgrade_base_to_head_still_passes_on_clean_slate(clean_audit_slate):
    """감사기록이 없는 상태에서는 base부터 head까지 전체 downgrade/upgrade
    왕복도 여전히 성공해야 한다(이번 수정이 다른 migration에 영향을 주지
    않는지 확인)."""
    db = clean_audit_slate
    cfg = _alembic_config()
    head = _current_head(cfg)

    command.downgrade(cfg, "base")
    db.expire_all()
    command.upgrade(cfg, head)
    db.expire_all()

    lessons = db.query(Lesson).filter(Lesson.code.in_(NEW_LESSON_CODES)).all()
    assert len(lessons) == 10
    for l in lessons:
        assert l.status == CONTENT_READY_FOR_REVIEW
        assert l.review_status == REVIEW_REQUIRED
        assert l.reviewed_by is None
