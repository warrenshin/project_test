"""학습 엔진. 명세서 6.2, 6.3, 9.2 참고.

콘텐츠는 status=PUBLISHED인 것만 노출한다. XP는 서버가 계산하며(6.3), 완료
이벤트마다 한 번만 지급된다(재시도해도 중복 지급되지 않음).
"""

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session as DbSession

from app.api.v1.learning_schemas import (
    ChoiceFeedback,
    ContentBlockResponse,
    CourseSummary,
    LearningPathResponse,
    LearningSummaryResponse,
    LessonDetailResponse,
    LessonProgressResponse,
    LessonProgressUpdateRequest,
    LessonProgressUpdateResponse,
    LessonSummary,
    ModuleSummary,
    QuestionResult,
    QuizAttemptRequest,
    QuizAttemptResponse,
    QuizChoiceResponse,
    QuizDetailResponse,
    QuizQuestionResponse,
    QuizSummary,
)
from app.core.db import get_db
from app.core.deps import get_current_user
from app.domain.learning import (
    CONTENT_PUBLISHED,
    Choice,
    ContentBlock,
    Course,
    LearningPath,
    Lesson,
    LessonProgress,
    Module,
    Question,
    Quiz,
    QuizAttempt,
    XpLedger,
)
from app.domain.services import gamification
from app.domain.user import User

router = APIRouter()


@router.get("/learning/paths", response_model=list[LearningPathResponse])
def list_learning_paths(db: DbSession = Depends(get_db)):
    paths = (
        db.query(LearningPath)
        .filter(LearningPath.status == CONTENT_PUBLISHED)
        .order_by(LearningPath.order_index)
        .all()
    )

    response = []
    for path in paths:
        courses = (
            db.query(Course)
            .filter(Course.learning_path_id == path.id, Course.status == CONTENT_PUBLISHED)
            .order_by(Course.order_index)
            .all()
        )
        course_summaries = []
        for course in courses:
            modules = (
                db.query(Module)
                .filter(Module.course_id == course.id, Module.status == CONTENT_PUBLISHED)
                .order_by(Module.order_index)
                .all()
            )
            module_summaries = []
            for module in modules:
                lessons = (
                    db.query(Lesson)
                    .filter(Lesson.module_id == module.id, Lesson.status == CONTENT_PUBLISHED)
                    .order_by(Lesson.order_index)
                    .all()
                )
                module_summaries.append(
                    ModuleSummary(
                        id=module.id,
                        title=module.title,
                        order_index=module.order_index,
                        lessons=[
                            LessonSummary(
                                id=lesson.id,
                                code=lesson.code,
                                title=lesson.title,
                                estimated_minutes=lesson.estimated_minutes,
                                order_index=lesson.order_index,
                            )
                            for lesson in lessons
                        ],
                    )
                )
            course_summaries.append(
                CourseSummary(
                    id=course.id,
                    title=course.title,
                    description=course.description,
                    order_index=course.order_index,
                    modules=module_summaries,
                )
            )
        response.append(
            LearningPathResponse(
                id=path.id,
                title=path.title,
                description=path.description,
                target_experience_level=path.target_experience_level,
                courses=course_summaries,
            )
        )
    return response


@router.get("/lessons/{lesson_id}", response_model=LessonDetailResponse)
def get_lesson(
    lesson_id: UUID, db: DbSession = Depends(get_db), current_user: User = Depends(get_current_user)
):
    lesson = db.query(Lesson).filter(Lesson.id == lesson_id, Lesson.status == CONTENT_PUBLISHED).first()
    if lesson is None:
        raise HTTPException(status_code=404, detail="강의를 찾을 수 없습니다.")

    blocks = (
        db.query(ContentBlock).filter(ContentBlock.lesson_id == lesson.id).order_by(ContentBlock.order_index).all()
    )
    quiz = db.query(Quiz).filter(Quiz.lesson_id == lesson.id).first()
    quiz_summary = None
    if quiz is not None:
        question_count = db.query(Question).filter(Question.quiz_id == quiz.id).count()
        quiz_summary = QuizSummary(
            id=quiz.id, title=quiz.title, question_count=question_count, pass_score_pct=quiz.pass_score_pct,
            content_version=quiz.content_version,
        )

    progress_row = (
        db.query(LessonProgress)
        .filter(LessonProgress.user_id == current_user.id, LessonProgress.lesson_id == lesson.id)
        .first()
    )
    progress = (
        LessonProgressResponse(status=progress_row.status, completed_at=progress_row.completed_at)
        if progress_row is not None
        else None
    )

    return LessonDetailResponse(
        id=lesson.id,
        code=lesson.code,
        title=lesson.title,
        learning_objective=lesson.learning_objective,
        estimated_minutes=lesson.estimated_minutes,
        source=lesson.source,
        reviewed_by=lesson.reviewed_by,
        reviewed_at=lesson.reviewed_at,
        source_url=lesson.source_url,
        source_confirmed_at=lesson.source_confirmed_at,
        content_version=lesson.content_version,
        market_scope=lesson.market_scope,
        review_status=lesson.review_status,
        content_blocks=[ContentBlockResponse.model_validate(b, from_attributes=True) for b in blocks],
        quiz=quiz_summary,
        progress=progress,
    )


@router.post("/lessons/{lesson_id}/progress", response_model=LessonProgressUpdateResponse)
def update_lesson_progress(
    lesson_id: UUID,
    payload: LessonProgressUpdateRequest,
    db: DbSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    lesson = db.query(Lesson).filter(Lesson.id == lesson_id, Lesson.status == CONTENT_PUBLISHED).first()
    if lesson is None:
        raise HTTPException(status_code=404, detail="강의를 찾을 수 없습니다.")

    now = datetime.now(timezone.utc)
    progress = (
        db.query(LessonProgress)
        .filter(LessonProgress.user_id == current_user.id, LessonProgress.lesson_id == lesson.id)
        .first()
    )
    if progress is None:
        progress = LessonProgress(user_id=current_user.id, lesson_id=lesson.id, status=payload.status, updated_at=now)
        db.add(progress)
    else:
        progress.status = payload.status
        progress.updated_at = now
    if payload.last_content_block_id is not None:
        progress.last_content_block_id = payload.last_content_block_id

    xp_awarded = 0
    if payload.status == "COMPLETED":
        if progress.completed_at is None:
            progress.completed_at = now
        xp_awarded = gamification.award_xp(
            db, current_user.id, gamification.XP_LESSON_COMPLETED, "LESSON_COMPLETED", lesson.id
        )

    db.commit()
    return LessonProgressUpdateResponse(status=progress.status, completed_at=progress.completed_at, xp_awarded=xp_awarded)


@router.get("/quizzes/{quiz_id}", response_model=QuizDetailResponse)
def get_quiz(quiz_id: UUID, db: DbSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    """퀴즈 문항 조회. 명세서 9.2에 명시적 엔드포인트는 없지만, 클라이언트가 채점 전 문항을
    렌더링하려면 필요하다. 정답 여부(Choice.is_correct)는 응답에 포함하지 않는다."""
    quiz = db.query(Quiz).filter(Quiz.id == quiz_id).first()
    if quiz is None:
        raise HTTPException(status_code=404, detail="퀴즈를 찾을 수 없습니다.")

    questions = db.query(Question).filter(Question.quiz_id == quiz.id).order_by(Question.order_index).all()
    question_responses = []
    for question in questions:
        choices = (
            db.query(Choice).filter(Choice.question_id == question.id).order_by(Choice.order_index).all()
        )
        question_responses.append(
            QuizQuestionResponse(
                id=question.id,
                prompt=question.prompt,
                question_type=question.question_type,
                choices=[QuizChoiceResponse(id=c.id, label=c.label) for c in choices],
            )
        )

    return QuizDetailResponse(
        id=quiz.id, title=quiz.title, pass_score_pct=quiz.pass_score_pct, questions=question_responses,
    )


@router.post("/quizzes/{quiz_id}/attempts", response_model=QuizAttemptResponse)
def submit_quiz_attempt(
    quiz_id: UUID,
    payload: QuizAttemptRequest,
    db: DbSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    quiz = db.query(Quiz).filter(Quiz.id == quiz_id).first()
    if quiz is None:
        raise HTTPException(status_code=404, detail="퀴즈를 찾을 수 없습니다.")

    questions = db.query(Question).filter(Question.quiz_id == quiz.id).order_by(Question.order_index).all()
    if not questions:
        raise HTTPException(status_code=422, detail="문항이 없는 퀴즈입니다.")

    results: list[QuestionResult] = []
    correct_count = 0
    for question in questions:
        choices = db.query(Choice).filter(Choice.question_id == question.id).order_by(Choice.order_index).all()
        correct_choice_ids = {c.id for c in choices if c.is_correct}
        submitted = set(payload.answers.get(question.id, []))
        is_correct = submitted == correct_choice_ids
        if is_correct:
            correct_count += 1
        results.append(
            QuestionResult(
                question_id=question.id, correct=is_correct, explanation=question.explanation,
                # 채점이 끝난 뒤에만 오답별 설명·정답 여부를 함께 보여준다(사전 조회
                # 시점인 QuizDetailResponse에는 절대 포함하지 않는다).
                choice_feedback=[
                    ChoiceFeedback(choice_id=c.id, label=c.label, is_correct=c.is_correct, explanation=c.explanation)
                    for c in choices
                ],
            )
        )

    score_pct = (correct_count / len(questions)) * 100
    passed = score_pct >= float(quiz.pass_score_pct)

    now = datetime.now(timezone.utc)
    db.add(
        QuizAttempt(
            user_id=current_user.id,
            quiz_id=quiz.id,
            answers={str(k): [str(c) for c in v] for k, v in payload.answers.items()},
            score_pct=score_pct,
            passed=passed,
            attempted_at=now,
        )
    )

    xp_awarded = 0
    if passed:
        xp_awarded = gamification.award_xp(db, current_user.id, gamification.XP_QUIZ_PASSED, "QUIZ_PASSED", quiz.id)

    db.commit()
    return QuizAttemptResponse(score_pct=score_pct, passed=passed, xp_awarded=xp_awarded, results=results)


@router.get("/me/learning-summary", response_model=LearningSummaryResponse)
def get_learning_summary(db: DbSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    total_xp = sum(
        row.amount for row in db.query(XpLedger).filter(XpLedger.user_id == current_user.id).all()
    )
    lessons_completed = (
        db.query(LessonProgress)
        .filter(LessonProgress.user_id == current_user.id, LessonProgress.status == "COMPLETED")
        .count()
    )
    quizzes_passed = (
        db.query(QuizAttempt.quiz_id)
        .filter(QuizAttempt.user_id == current_user.id, QuizAttempt.passed.is_(True))
        .distinct()
        .count()
    )

    return LearningSummaryResponse(
        total_xp=total_xp,
        lessons_completed=lessons_completed,
        quizzes_passed=quizzes_passed,
        current_streak_days=gamification.current_streak_days(db, current_user.id),
        todays_xp=gamification.today_xp_total(db, current_user.id),
        daily_xp_cap=gamification.XP_DAILY_CAP,
    )
