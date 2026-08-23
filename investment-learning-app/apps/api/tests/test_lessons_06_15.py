"""6~15강 투자교육 콘텐츠: 작성/검수 상태 분리, 미승인 콘텐츠 비노출, 콘텐츠
무결성, 기존 데이터 보존.

이 파일은 "코드가 있으니 안전하다"는 주장이 아니라, 실제 HTTP 흐름과 DB 상태로
다음을 확인한다:
1. 10개 강의 전부 status=READY_FOR_REVIEW, review_status=REVIEW_REQUIRED로
   시드되어 있다 — 하나도 PUBLISHED/REVIEWED가 아니다(에이전트 자기 승인 없음).
   reviewed_by/reviewed_at/source_confirmed_at도 전부 NULL이다.
2. 10개 전부 목록(GET /v1/learning/paths)·단건 조회(GET /v1/lessons/{id})·
   퀴즈 조회/응시(GET /v1/quizzes/{id}, POST .../attempts) 어디에도 노출되지
   않는다 — quiz_id를 알아도 마찬가지다(IDOR 방지).
3. 문항 구조(4문항×4선택지×정답1개×오답별 설명)는 DB 레벨에서 무결하다.
4. 퀴즈 채점 메커니즘(정답 비노출, 채점 후 choice_feedback) 자체는 여전히
   정상 동작한다 — 이미 게시된 기존 콘텐츠(1강)와, 이 테스트 전용으로 만든
   가짜 게시 강의(실제 6~15강이 아님)로 검증한다.
5. 기존 1~5강 데이터(진도 포함)와 7일 챌린지 카드 강의는 이번 추가로 전혀
   영향받지 않는다.
"""

import uuid

from app.domain.learning import (
    CONTENT_PUBLISHED,
    CONTENT_READY_FOR_REVIEW,
    REVIEW_REQUIRED,
    Choice,
    ContentBlock,
    Lesson,
    LessonProgress,
    Module,
    Question,
    Quiz,
)
from tests.conftest import client, signup_user

NEW_LESSON_CODES = [f"lesson-{n:02d}" for n in range(6, 16)]


def _lesson_by_code(db, code: str) -> Lesson:
    lesson = db.query(Lesson).filter(Lesson.code == code).first()
    assert lesson is not None, f"{code}가 시드되지 않았습니다"
    return lesson


def _make_published_test_lesson(db) -> tuple[Lesson, Quiz, list[Question]]:
    """실제 6~15강이 아닌, 이 테스트 파일 전용의 가짜 게시 강의를 만든다 —
    채점 메커니즘 자체(정답 비노출, choice_feedback)를 검증하기 위함이다.
    이걸로 실제 강의를 승인한 것처럼 오인되지 않도록 code에 test- 접두어를
    쓰고, title에도 명시한다."""
    # 기존 어떤 모듈에도 끼워 넣지 않고 이 테스트 전용 모듈을 새로 만든다 —
    # "1부"·"2부" 모듈의 강의 수를 세는 다른 테스트들을 오염시키지 않기 위함.
    course = db.query(Module).first().course_id
    test_module = Module(course_id=course, title=f"[테스트 전용] {uuid.uuid4().hex[:8]}", order_index=999)
    db.add(test_module)
    db.flush()
    lesson = Lesson(
        module_id=test_module.id, code=f"test-quiz-mechanics-{uuid.uuid4().hex[:8]}",
        title="[테스트 전용] 퀴즈 채점 메커니즘 검증용 가짜 강의", status=CONTENT_PUBLISHED,
        content_version="v1",
    )
    db.add(lesson)
    db.flush()
    quiz = Quiz(lesson_id=lesson.id, title="테스트 퀴즈", pass_score_pct=70, content_version="v1")
    db.add(quiz)
    db.flush()
    question = Question(quiz_id=quiz.id, prompt="2+2는?", question_type="SINGLE_CHOICE", explanation="기본 산수입니다.")
    db.add(question)
    db.flush()
    choices = [
        Choice(question_id=question.id, label="3", is_correct=False, order_index=0, explanation="3은 오답입니다."),
        Choice(question_id=question.id, label="4", is_correct=True, order_index=1, explanation="4가 정답입니다."),
        Choice(question_id=question.id, label="5", is_correct=False, order_index=2, explanation="5는 오답입니다."),
        Choice(question_id=question.id, label="6", is_correct=False, order_index=3, explanation="6은 오답입니다."),
    ]
    db.add_all(choices)
    db.commit()
    return lesson, quiz, [question]


# --- 작성/검수 상태(자기 승인 방지) ---


def test_all_ten_new_lessons_are_ready_for_review_not_self_approved(db):
    lessons = db.query(Lesson).filter(Lesson.code.in_(NEW_LESSON_CODES)).all()
    assert len(lessons) == 10
    for lesson in lessons:
        assert lesson.status == CONTENT_READY_FOR_REVIEW, f"{lesson.code}: status={lesson.status}"
        assert lesson.review_status == REVIEW_REQUIRED, f"{lesson.code}: review_status={lesson.review_status}"
        assert lesson.reviewed_by is None, f"{lesson.code}: reviewed_by가 채워져 있음(자기 승인 의심)"
        assert lesson.reviewed_at is None, f"{lesson.code}: reviewed_at이 채워져 있음(자기 승인 의심)"
        assert lesson.source_confirmed_at is None, f"{lesson.code}: source_confirmed_at이 채워져 있음(미확인 출처를 확인된 것처럼 표시)"


def test_lesson_module_order_places_new_module_after_existing_ones(db):
    new_module = db.query(Module).filter(Module.title == "2부. 실전 투자와 리스크 관리").first()
    old_module = db.query(Module).filter(Module.title == "1부. 투자의 기본 개념").first()
    card_module = db.query(Module).filter(Module.title == "보충: 7일 챌린지 카드").first()
    assert new_module is not None and old_module is not None and card_module is not None
    assert old_module.order_index < card_module.order_index < new_module.order_index


def test_lessons_within_new_module_are_ordered_06_through_15(db):
    module = db.query(Module).filter(Module.title == "2부. 실전 투자와 리스크 관리").first()
    lessons = db.query(Lesson).filter(Lesson.module_id == module.id).order_by(Lesson.order_index).all()
    assert [l.code for l in lessons] == NEW_LESSON_CODES


def test_each_new_lesson_has_four_questions_with_exactly_one_correct_choice(db):
    for code in NEW_LESSON_CODES:
        lesson = _lesson_by_code(db, code)
        quiz = db.query(Quiz).filter(Quiz.lesson_id == lesson.id).first()
        questions = db.query(Question).filter(Question.quiz_id == quiz.id).all()
        assert len(questions) == 4, code
        for q in questions:
            choices = db.query(Choice).filter(Choice.question_id == q.id).all()
            assert len(choices) == 4, (code, q.prompt)
            assert sum(1 for c in choices if c.is_correct) == 1, (code, q.prompt)
            assert all(c.explanation for c in choices), (code, q.prompt, "오답별 설명 누락")


def test_each_new_lesson_has_all_nine_content_block_types(db):
    expected_types = {"OBJECTIVE", "BODY", "EXAMPLE", "MISCONCEPTION", "SUMMARY", "SELF_CHECK", "TERMS", "PRACTICE", "SOURCE"}
    for code in NEW_LESSON_CODES:
        lesson = _lesson_by_code(db, code)
        blocks = db.query(ContentBlock).filter(ContentBlock.lesson_id == lesson.id).all()
        block_types = {b.block_type for b in blocks}
        assert expected_types <= block_types, (code, block_types)


# --- 미승인 강의 비노출(전부 READY_FOR_REVIEW이므로 10개 전부 대상) ---


def test_none_of_the_ten_new_lessons_appear_in_learning_paths_listing():
    res = client.get("/v1/learning/paths")
    assert res.status_code == 200
    titles = {
        lesson["title"]
        for path in res.json()
        for course in path["courses"]
        for module in course["modules"]
        for lesson in module["lessons"]
    }
    new_titles = {"거래소와 장 운영시간", "시장가와 지정가", "호가·스프레드·유동성", "수수료·세금·환율",
                  "투자수익률 계산", "복리의 효과와 한계", "변동성과 최대낙폭", "분산투자의 원리",
                  "자산배분 기초", "시가총액과 기업가치"}
    assert not (titles & new_titles), titles & new_titles


def test_all_ten_new_lessons_return_404_on_direct_detail_fetch_even_authenticated(db):
    cookies, _ = signup_user("lesson-ready-block")
    for code in NEW_LESSON_CODES:
        lesson = _lesson_by_code(db, code)
        res = client.get(f"/v1/lessons/{lesson.id}", cookies=cookies)
        assert res.status_code == 404, code


def test_all_ten_new_lesson_quizzes_return_404_via_quiz_id_even_if_guessed(db):
    """IDOR 방지: quiz_id를 안다고 해도(예: 다른 사용자가 흘렸거나 추측한 경우)
    미승인 강의의 문항·선택지를 볼 수 없어야 한다."""
    cookies, _ = signup_user("lesson-quiz-idor-block")
    for code in NEW_LESSON_CODES:
        lesson = _lesson_by_code(db, code)
        quiz = db.query(Quiz).filter(Quiz.lesson_id == lesson.id).first()
        res = client.get(f"/v1/quizzes/{quiz.id}", cookies=cookies)
        assert res.status_code == 404, code


def test_all_ten_new_lesson_quiz_attempts_return_404_even_with_correct_answers(db):
    cookies, _ = signup_user("lesson-quiz-attempt-idor-block")
    for code in NEW_LESSON_CODES:
        lesson = _lesson_by_code(db, code)
        quiz = db.query(Quiz).filter(Quiz.lesson_id == lesson.id).first()
        question = db.query(Question).filter(Question.quiz_id == quiz.id).first()
        correct = db.query(Choice).filter(Choice.question_id == question.id, Choice.is_correct.is_(True)).first()
        res = client.post(
            f"/v1/quizzes/{quiz.id}/attempts", json={"answers": {str(question.id): [str(correct.id)]}},
            cookies=cookies,
        )
        assert res.status_code == 404, code


# --- 퀴즈 채점 메커니즘 자체는 정상 동작(기존 게시 콘텐츠 + 테스트 전용 가짜 강의로 검증) ---


def test_quiz_pre_answer_never_exposes_correct_choice_or_explanation_on_published_lesson(db):
    """이미 게시된 기존 콘텐츠(1강)로 확인한다 — 6~15강은 게시돼 있지 않으므로
    이 경로로는 검증할 수 없다."""
    cookies, _ = signup_user("lesson-quiz-noleak")
    paths = client.get("/v1/learning/paths").json()
    first_lesson_id = paths[0]["courses"][0]["modules"][0]["lessons"][0]["id"]
    res = client.get(f"/v1/lessons/{first_lesson_id}", cookies=cookies)
    quiz_id = res.json()["quiz"]["id"]

    quiz_res = client.get(f"/v1/quizzes/{quiz_id}", cookies=cookies)
    assert quiz_res.status_code == 200
    for question in quiz_res.json()["questions"]:
        for choice in question["choices"]:
            assert "is_correct" not in choice
            assert "explanation" not in choice


def test_quiz_grading_reveals_choice_feedback_only_after_submission(db):
    cookies, _ = signup_user("lesson-quiz-feedback")
    lesson, quiz, questions = _make_published_test_lesson(db)
    question = questions[0]
    correct = db.query(Choice).filter(Choice.question_id == question.id, Choice.is_correct.is_(True)).first()

    res = client.post(
        f"/v1/quizzes/{quiz.id}/attempts", json={"answers": {str(question.id): [str(correct.id)]}}, cookies=cookies,
    )
    assert res.status_code == 200
    body = res.json()
    assert body["passed"] is True
    assert float(body["score_pct"]) == 100
    result = body["results"][0]
    assert result["correct"] is True
    assert len(result["choice_feedback"]) == 4
    assert sum(1 for c in result["choice_feedback"] if c["is_correct"]) == 1
    assert all(c["explanation"] for c in result["choice_feedback"])


def test_quiz_grading_correctly_marks_wrong_answer(db):
    cookies, _ = signup_user("lesson-quiz-wrong")
    lesson, quiz, questions = _make_published_test_lesson(db)
    question = questions[0]
    wrong = db.query(Choice).filter(Choice.question_id == question.id, Choice.is_correct.is_(False)).first()

    res = client.post(
        f"/v1/quizzes/{quiz.id}/attempts", json={"answers": {str(question.id): [str(wrong.id)]}}, cookies=cookies,
    )
    body = res.json()
    assert body["results"][0]["correct"] is False


# --- 기존 데이터 보존 ---


def test_existing_lesson_1_to_5_untouched_and_now_have_stable_codes(db):
    old_module = db.query(Module).filter(Module.title == "1부. 투자의 기본 개념").first()
    lessons = db.query(Lesson).filter(Lesson.module_id == old_module.id).order_by(Lesson.order_index).all()
    assert len(lessons) == 5
    assert lessons[0].title == "투자는 무엇인가"
    # 이번 감사에서 code만 추가로 채웠다(별도 migration, UPDATE-only) — 다른
    # 필드는 전혀 바뀌지 않았다.
    assert [l.code for l in lessons] == [f"lesson-{n:02d}" for n in range(1, 6)]
    assert all(l.status == CONTENT_PUBLISHED for l in lessons)  # 기존 상태 그대로


def test_existing_challenge_card_lessons_untouched(db):
    card_module = db.query(Module).filter(Module.title == "보충: 7일 챌린지 카드").first()
    lessons = db.query(Lesson).filter(Lesson.module_id == card_module.id).all()
    titles = {l.title for l in lessons}
    assert {"주문 방식: 시장가와 지정가", "분산과 집중위험", "행동편향 살펴보기"} <= titles
    assert all(l.status == CONTENT_PUBLISHED for l in lessons)


def test_existing_lesson_progress_preserved_across_new_seed(db):
    cookies, _ = signup_user("lesson-old-progress")
    old_module = db.query(Module).filter(Module.title == "1부. 투자의 기본 개념").first()
    first_lesson = (
        db.query(Lesson).filter(Lesson.module_id == old_module.id).order_by(Lesson.order_index).first()
    )
    res = client.post(f"/v1/lessons/{first_lesson.id}/progress", json={"status": "COMPLETED"}, cookies=cookies)
    assert res.status_code == 200

    progress = (
        db.query(LessonProgress)
        .filter(LessonProgress.lesson_id == first_lesson.id)
        .order_by(LessonProgress.updated_at.desc())
        .first()
    )
    assert progress is not None and progress.status == "COMPLETED"
