"""운영자 전용 승인 CLI(scripts/publish_lesson.py)의 동작을 검증한다.

중요: 이 테스트는 실제 lesson-06~15 콘텐츠를 승인하지 않는다 — 성공 경로는
이 테스트 파일이 직접 만든 "가짜" 강의(throwaway lesson)에 대해서만
검증한다. 에이전트가 실제 콘텐츠를 스스로 승인하는 일이 테스트 과정에서마저
벌어지지 않도록 하기 위함이다. 실제 lesson-06~15가 여전히
READY_FOR_REVIEW/REVIEW_REQUIRED 상태로 남아 있는지는 별도로 확인한다.
"""

import uuid
from datetime import datetime, timezone

import pytest

from app.domain.learning import (
    CONTENT_PUBLISHED,
    CONTENT_READY_FOR_REVIEW,
    REVIEW_REQUIRED,
    REVIEW_REVIEWED,
    Lesson,
    LessonReviewAudit,
    Module,
)
from scripts.publish_lesson import PublishRejected, publish_lesson


def _throwaway_module_id(db):
    """실제 "1부"·"2부" 모듈에 가짜 강의를 끼워 넣으면 그 모듈의 강의 수를
    세는 다른 테스트 파일이 깨진다(이 저장소는 테스트 간 DB를 롤백하지 않고
    공유한다) — 항상 새 모듈을 만들어 완전히 격리한다."""
    course_id = db.query(Module).first().course_id
    module = Module(course_id=course_id, title=f"[테스트 전용] {uuid.uuid4().hex[:8]}", order_index=999)
    db.add(module)
    db.flush()
    return module.id


def _make_ready_for_review_lesson(db, *, code: str, content_version="v1", source_url=None) -> Lesson:
    lesson = Lesson(
        module_id=_throwaway_module_id(db), code=code, title=f"테스트 강의 {code}", status=CONTENT_READY_FOR_REVIEW,
        review_status=REVIEW_REQUIRED, content_version=content_version, source_url=source_url,
    )
    db.add(lesson)
    db.commit()
    db.refresh(lesson)
    return lesson


def test_publish_rejects_unknown_code(db):
    with pytest.raises(PublishRejected, match="존재하지 않습니다"):
        publish_lesson(
            db, code="lesson-does-not-exist-xyz", expected_content_version="v1", reviewer="tester",
            reviewed_at=datetime.now(timezone.utc), source_verified=False, note="test",
        )


def test_publish_rejects_content_version_mismatch(db):
    lesson = _make_ready_for_review_lesson(db, code=f"test-{uuid.uuid4().hex[:8]}")
    with pytest.raises(PublishRejected, match="content_version 불일치"):
        publish_lesson(
            db, code=lesson.code, expected_content_version="v999", reviewer="tester",
            reviewed_at=datetime.now(timezone.utc), source_verified=False, note="test",
        )
    db.refresh(lesson)
    assert lesson.status == CONTENT_READY_FOR_REVIEW  # 바뀌지 않았다


def test_publish_rejects_when_source_url_present_but_not_verified(db):
    lesson = _make_ready_for_review_lesson(
        db, code=f"test-{uuid.uuid4().hex[:8]}", source_url="https://example.com/official-source"
    )
    with pytest.raises(PublishRejected, match="출처 URL"):
        publish_lesson(
            db, code=lesson.code, expected_content_version="v1", reviewer="tester",
            reviewed_at=datetime.now(timezone.utc), source_verified=False, note="test",
        )
    db.refresh(lesson)
    assert lesson.status == CONTENT_READY_FOR_REVIEW
    assert lesson.source_confirmed_at is None


def test_publish_rejects_source_verified_true_when_no_source_url_exists(db):
    """출처 URL이 아예 없는 강의(예: lesson-12처럼 후보 출처 자체가 없는 경우)에
    --source-verified true를 지정하면 거절해야 한다 — 확인할 대상이 없는데
    "확인했다"는 감사기록을 남기는 것은 의미상 모순이다."""
    lesson = _make_ready_for_review_lesson(db, code=f"test-{uuid.uuid4().hex[:8]}", source_url=None)
    with pytest.raises(PublishRejected, match="출처 URL이 없습니다"):
        publish_lesson(
            db, code=lesson.code, expected_content_version="v1", reviewer="tester",
            reviewed_at=datetime.now(timezone.utc), source_verified=True, note="test",
        )
    db.refresh(lesson)
    assert lesson.status == CONTENT_READY_FOR_REVIEW  # 바뀌지 않았다
    assert lesson.reviewed_by is None


def test_publish_rejects_wrong_status(db):
    lesson = Lesson(
        module_id=_throwaway_module_id(db), code=f"test-{uuid.uuid4().hex[:8]}", title="이미 DRAFT",
        status="DRAFT", review_status=REVIEW_REQUIRED, content_version="v1",
    )
    db.add(lesson)
    db.commit()
    with pytest.raises(PublishRejected, match="READY_FOR_REVIEW"):
        publish_lesson(
            db, code=lesson.code, expected_content_version="v1", reviewer="tester",
            reviewed_at=datetime.now(timezone.utc), source_verified=False, note="test",
        )


def test_publish_rejects_empty_reviewer_or_note(db):
    lesson = _make_ready_for_review_lesson(db, code=f"test-{uuid.uuid4().hex[:8]}")
    with pytest.raises(PublishRejected, match="reviewer"):
        publish_lesson(
            db, code=lesson.code, expected_content_version="v1", reviewer="   ",
            reviewed_at=datetime.now(timezone.utc), source_verified=False, note="ok",
        )
    with pytest.raises(PublishRejected, match="승인 사유"):
        publish_lesson(
            db, code=lesson.code, expected_content_version="v1", reviewer="tester",
            reviewed_at=datetime.now(timezone.utc), source_verified=False, note="  ",
        )


def test_publish_success_on_throwaway_lesson_without_source(db):
    """가짜 강의(실제 콘텐츠 아님)에 대해서만 성공 경로를 검증한다."""
    lesson = _make_ready_for_review_lesson(db, code=f"test-{uuid.uuid4().hex[:8]}")
    reviewed_at = datetime.now(timezone.utc)

    result = publish_lesson(
        db, code=lesson.code, expected_content_version="v1", reviewer="qa-tester",
        reviewed_at=reviewed_at, source_verified=False, note="테스트용 가짜 강의 승인",
    )
    assert result.already_done is False

    db.refresh(lesson)
    assert lesson.status == CONTENT_PUBLISHED
    assert lesson.review_status == REVIEW_REVIEWED
    assert lesson.reviewed_by == "qa-tester"
    assert lesson.reviewed_at == reviewed_at.date()
    assert lesson.source_confirmed_at is None  # 출처 URL이 없었으므로

    audit = db.query(LessonReviewAudit).filter(LessonReviewAudit.lesson_id == lesson.id).first()
    assert audit is not None
    assert audit.reviewer == "qa-tester"
    assert audit.action == "PUBLISHED"
    assert audit.note == "테스트용 가짜 강의 승인"


def test_publish_success_with_verified_source_sets_confirmed_at(db):
    lesson = _make_ready_for_review_lesson(
        db, code=f"test-{uuid.uuid4().hex[:8]}", source_url="https://example.com/official"
    )
    reviewed_at = datetime.now(timezone.utc)

    publish_lesson(
        db, code=lesson.code, expected_content_version="v1", reviewer="qa-tester",
        reviewed_at=reviewed_at, source_verified=True, note="원문 직접 확인함",
    )
    db.refresh(lesson)
    assert lesson.source_confirmed_at == reviewed_at.date()


def test_publish_rerun_is_idempotent_no_duplicate_audit(db):
    lesson = _make_ready_for_review_lesson(db, code=f"test-{uuid.uuid4().hex[:8]}")
    reviewed_at = datetime.now(timezone.utc)
    kwargs = dict(
        code=lesson.code, expected_content_version="v1", reviewer="qa-tester", reviewed_at=reviewed_at,
        source_verified=False, note="첫 승인",
    )

    first = publish_lesson(db, **kwargs)
    assert first.already_done is False
    second = publish_lesson(db, **kwargs)
    assert second.already_done is True

    audits = db.query(LessonReviewAudit).filter(LessonReviewAudit.lesson_id == lesson.id).all()
    assert len(audits) == 1  # 두 번 호출했어도 감사기록은 한 건뿐


def test_publish_does_not_accept_multiple_codes_in_one_call():
    """publish_lesson()의 시그니처 자체가 code 하나만 받는다(리스트·와일드카드 없음) —
    함수 시그니처 검사로 "일괄 게시 불가" 설계를 확인한다."""
    import inspect

    sig = inspect.signature(publish_lesson)
    assert sig.parameters["code"].annotation is str


# --- 실제 lesson-06~15가 여전히 미승인 상태인지(에이전트가 스스로 승인하지 않았는지) ---


def test_real_lessons_06_15_remain_ready_for_review_untouched(db):
    codes = [f"lesson-{n:02d}" for n in range(6, 16)]
    lessons = db.query(Lesson).filter(Lesson.code.in_(codes)).all()
    assert len(lessons) == 10
    for lesson in lessons:
        assert lesson.status == CONTENT_READY_FOR_REVIEW, f"{lesson.code}가 이미 게시됨 — 자기 승인 의심"
        assert lesson.review_status == REVIEW_REQUIRED
        assert lesson.reviewed_by is None
        assert lesson.reviewed_at is None
        assert lesson.source_confirmed_at is None

    audits = db.query(LessonReviewAudit).filter(LessonReviewAudit.lesson_code.in_(codes)).all()
    assert len(audits) == 0, "실제 lesson-06~15에 대한 승인 감사기록이 존재함 — 자기 승인 의심"
