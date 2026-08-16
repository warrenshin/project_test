"""학습 엔진. 명세서 6.2, 9.2 참고.

Phase 2에서 구현 예정: LearningPath > Course > Module > Lesson 계층,
진도·퀴즈 시도, 콘텐츠 버전 관리.
"""

from fastapi import APIRouter, HTTPException

router = APIRouter()

_NOT_IMPLEMENTED = "Phase 2에서 구현 예정 (docs/product-spec.md 6.2, 9.2)"


@router.get("/learning/paths")
def list_learning_paths():
    raise HTTPException(status_code=501, detail=_NOT_IMPLEMENTED)


@router.get("/lessons/{lesson_id}")
def get_lesson(lesson_id: str):
    raise HTTPException(status_code=501, detail=_NOT_IMPLEMENTED)


@router.post("/lessons/{lesson_id}/progress")
def update_lesson_progress(lesson_id: str):
    raise HTTPException(status_code=501, detail=_NOT_IMPLEMENTED)


@router.post("/quizzes/{quiz_id}/attempts")
def submit_quiz_attempt(quiz_id: str):
    raise HTTPException(status_code=501, detail=_NOT_IMPLEMENTED)
