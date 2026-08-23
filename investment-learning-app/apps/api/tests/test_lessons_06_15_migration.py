"""alembic/versions/c1a2b3d4e5f6(6~15강 시드)을 실제로 downgrade/upgrade하며
검증한다 — 일반 API 테스트가 아니라 migration 자체의 재현성·데이터 보존을
확인하는 전용 테스트다(tests/test_migration_duplicate_instrument_merge.py와
동일한 패턴).

시나리오:
1. downgrade -> upgrade 후에도 10개 강의가 정확히 복원된다(멱등적 재생성).
2. 이 migration의 downgrade는 6~15강만 지우고, 기존 1~5강·챌린지 카드
   강의·진도(lesson_progress)는 전혀 건드리지 않는다.
"""

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

from app.domain.learning import Lesson, LessonProgress, Module
from tests.conftest import signup_user, client

DOWN_REVISION = "8255aa2780e6"  # 이 migration 바로 이전
TARGET_REVISION = "c1a2b3d4e5f6"  # 이 migration 자체


def _alembic_config() -> Config:
    api_root = Path(__file__).resolve().parents[1]
    return Config(str(api_root / "alembic.ini"))


def _current_head(cfg: Config) -> str:
    heads = ScriptDirectory.from_config(cfg).get_heads()
    assert len(heads) == 1, f"head가 여러 개입니다: {heads}"
    return heads[0]


@pytest.fixture
def migration_cycle():
    cfg = _alembic_config()
    head_revision = _current_head(cfg)
    command.downgrade(cfg, DOWN_REVISION)
    yield cfg
    command.upgrade(cfg, head_revision)


NEW_LESSON_CODES = [f"lesson-{n:02d}" for n in range(6, 16)]


def test_downgrade_then_upgrade_restores_all_ten_lessons(migration_cycle, db):
    """이 migration이 관리하는 code 집합(lesson-06~15)만 확인한다 — 이 저장소의
    테스트는 파일 간 DB를 롤백하지 않고 공유하므로, 다른 테스트 파일이 만든
    무관한 code(예: 승인 CLI 테스트용 가짜 강의)가 같은 DB에 남아 있을 수
    있다는 전제 위에서, "전체 DB에 code가 하나도 없다"처럼 과도하게 넓은
    불변조건은 검사하지 않는다."""
    cfg = migration_cycle
    assert db.query(Lesson).filter(Lesson.code.in_(NEW_LESSON_CODES)).count() == 0  # downgrade 직후

    command.upgrade(cfg, TARGET_REVISION)
    db.expire_all()

    codes = sorted(
        l.code for l in db.query(Lesson).filter(Lesson.code.in_(NEW_LESSON_CODES)).all()
    )
    assert codes == NEW_LESSON_CODES


def test_downgrade_preserves_existing_lessons_and_progress(migration_cycle, db):
    """6~15강 migration을 내렸다 올려도, 이전부터 있던 1~5강·진도는 그대로여야
    한다 — 이번 migration의 downgrade가 code IN (...) 조건으로만 지우기 때문에
    다른 강의를 건드리지 않는다는 것을 실제로 확인한다."""
    cfg = migration_cycle

    old_module = db.query(Module).filter(Module.title == "1부. 투자의 기본 개념").first()
    assert old_module is not None
    old_lessons = db.query(Lesson).filter(Lesson.module_id == old_module.id).all()
    assert len(old_lessons) == 5  # downgrade 후에도 그대로

    cookies, _ = signup_user("lesson-migration-progress")
    first_lesson = old_lessons[0]
    res = client.post(f"/v1/lessons/{first_lesson.id}/progress", json={"status": "COMPLETED"}, cookies=cookies)
    assert res.status_code == 200

    command.upgrade(cfg, TARGET_REVISION)
    db.expire_all()

    progress = db.query(LessonProgress).filter(LessonProgress.lesson_id == first_lesson.id).first()
    assert progress is not None and progress.status == "COMPLETED"
