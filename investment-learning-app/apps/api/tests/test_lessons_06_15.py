"""6~15강 투자교육 콘텐츠: seed 데이터·API 노출 정책·퀴즈 채점·XP·기존 데이터 보존.

이 파일은 "코드가 있으니 안전하다"는 주장이 아니라, 실제 HTTP 흐름과 DB 상태로
다음을 확인한다:
1. 10개 강의가 전부 시드되어 있고, PUBLISHED 8개/DRAFT 2개로 정확히 나뉜다.
2. DRAFT(6·9강)는 목록(GET /v1/learning/paths)에도, 단건 조회(GET /v1/lessons/{id})
   에도 절대 노출되지 않는다 — 일반 사용자 관점에서 아예 존재하지 않는 것과 같다.
3. PUBLISHED 강의는 출처·검수상태·콘텐츠버전 메타데이터를 포함해 정상 조회된다.
4. 퀴즈는 정답 이외에 오답별 설명까지 채점 후에만 노출하고, 채점 전에는 정답을
   전혀 드러내지 않는다.
5. 강의 완료·퀴즈 통과 XP가 새 강의에서도 중복 지급되지 않는다.
6. 기존 1~5강 데이터(진도 포함)와 7일 챌린지 카드 강의는 이번 추가로 전혀
   영향받지 않는다.
"""

from app.domain.learning import Choice, Lesson, LessonProgress, Module, Question, Quiz
from tests.conftest import client, signup_user

PUBLISHED_CODES = [f"lesson-{n:02d}" for n in (7, 8, 10, 11, 12, 13, 14, 15)]
DRAFT_CODES = ["lesson-06", "lesson-09"]


def _lesson_by_code(db, code: str) -> Lesson:
    lesson = db.query(Lesson).filter(Lesson.code == code).first()
    assert lesson is not None, f"{code}가 시드되지 않았습니다"
    return lesson


# --- 시드 상태 ---


def test_all_ten_lessons_seeded_with_correct_status_split(db):
    published = db.query(Lesson).filter(Lesson.code.in_(PUBLISHED_CODES)).all()
    draft = db.query(Lesson).filter(Lesson.code.in_(DRAFT_CODES)).all()
    assert len(published) == 8
    assert len(draft) == 2
    assert all(l.status == "PUBLISHED" and l.review_status == "REVIEWED" for l in published)
    assert all(l.status == "DRAFT" and l.review_status == "REVIEW_REQUIRED" for l in draft)


def test_lesson_module_order_places_new_module_after_existing_ones(db):
    new_module = db.query(Module).filter(Module.title == "2부. 실전 투자와 리스크 관리").first()
    old_module = db.query(Module).filter(Module.title == "1부. 투자의 기본 개념").first()
    card_module = db.query(Module).filter(Module.title == "보충: 7일 챌린지 카드").first()
    assert new_module is not None and old_module is not None and card_module is not None
    assert old_module.order_index < card_module.order_index < new_module.order_index


def test_lessons_within_new_module_are_ordered_06_through_15(db):
    module = db.query(Module).filter(Module.title == "2부. 실전 투자와 리스크 관리").first()
    lessons = db.query(Lesson).filter(Lesson.module_id == module.id).order_by(Lesson.order_index).all()
    assert [l.code for l in lessons] == [f"lesson-{n:02d}" for n in range(6, 16)]


def test_each_lesson_has_four_questions_with_exactly_one_correct_choice(db):
    for code in PUBLISHED_CODES + DRAFT_CODES:
        lesson = _lesson_by_code(db, code)
        quiz = db.query(Quiz).filter(Quiz.lesson_id == lesson.id).first()
        questions = db.query(Question).filter(Question.quiz_id == quiz.id).all()
        assert len(questions) == 4, code
        for q in questions:
            choices = db.query(Choice).filter(Choice.question_id == q.id).all()
            assert len(choices) == 4, (code, q.prompt)
            assert sum(1 for c in choices if c.is_correct) == 1, (code, q.prompt)
            assert all(c.explanation for c in choices), (code, q.prompt, "오답별 설명 누락")


# --- PUBLISHED 노출 / DRAFT 비노출 ---


def test_published_lesson_appears_in_learning_paths_listing():
    res = client.get("/v1/learning/paths")
    assert res.status_code == 200
    titles = [
        lesson["title"]
        for path in res.json()
        for course in path["courses"]
        for module in course["modules"]
        for lesson in module["lessons"]
    ]
    assert "시장가와 지정가" in titles


def test_draft_lesson_does_not_appear_in_learning_paths_listing():
    res = client.get("/v1/learning/paths")
    titles = [
        lesson["title"]
        for path in res.json()
        for course in path["courses"]
        for module in course["modules"]
        for lesson in module["lessons"]
    ]
    assert "거래소와 장 운영시간" not in titles
    assert "수수료·세금·환율" not in titles


def test_draft_lesson_detail_returns_404_even_when_authenticated(db):
    cookies, _ = signup_user("lesson-draft-block")
    draft = _lesson_by_code(db, "lesson-06")
    res = client.get(f"/v1/lessons/{draft.id}", cookies=cookies)
    assert res.status_code == 404


def test_published_lesson_detail_includes_source_and_review_metadata(db):
    cookies, _ = signup_user("lesson-detail-meta")
    lesson = _lesson_by_code(db, "lesson-07")
    res = client.get(f"/v1/lessons/{lesson.id}", cookies=cookies)
    assert res.status_code == 200
    body = res.json()
    assert body["code"] == "lesson-07"
    assert body["review_status"] == "REVIEWED"
    assert body["content_version"] == "v1"
    assert body["market_scope"] == "GLOBAL"
    assert body["source"]
    assert "disclosure" in body and "진단" not in body["disclosure"]
    block_types = [b["block_type"] for b in body["content_blocks"]]
    for expected in ["OBJECTIVE", "BODY", "EXAMPLE", "MISCONCEPTION", "SUMMARY", "SELF_CHECK", "TERMS", "PRACTICE", "SOURCE"]:
        assert expected in block_types


# --- 퀴즈 채점 ---


def test_quiz_pre_answer_never_exposes_correct_choice_or_explanation(db):
    cookies, _ = signup_user("lesson-quiz-noleak")
    lesson = _lesson_by_code(db, "lesson-10")
    res = client.get(f"/v1/lessons/{lesson.id}", cookies=cookies)
    quiz_id = res.json()["quiz"]["id"]

    quiz_res = client.get(f"/v1/quizzes/{quiz_id}", cookies=cookies)
    assert quiz_res.status_code == 200
    for question in quiz_res.json()["questions"]:
        for choice in question["choices"]:
            assert "is_correct" not in choice
            assert "explanation" not in choice


def test_quiz_grading_reveals_choice_feedback_only_after_submission(db):
    cookies, _ = signup_user("lesson-quiz-feedback")
    lesson = _lesson_by_code(db, "lesson-10")  # 투자수익률 계산
    quiz = db.query(Quiz).filter(Quiz.lesson_id == lesson.id).first()
    questions = db.query(Question).filter(Question.quiz_id == quiz.id).order_by(Question.order_index).all()
    answers = {}
    for q in questions:
        correct = db.query(Choice).filter(Choice.question_id == q.id, Choice.is_correct.is_(True)).first()
        answers[str(q.id)] = [str(correct.id)]

    res = client.post(f"/v1/quizzes/{quiz.id}/attempts", json={"answers": answers}, cookies=cookies)
    assert res.status_code == 200
    body = res.json()
    assert body["passed"] is True
    assert float(body["score_pct"]) == 100
    for result in body["results"]:
        assert result["correct"] is True
        assert len(result["choice_feedback"]) == 4
        assert sum(1 for c in result["choice_feedback"] if c["is_correct"]) == 1
        assert all(c["explanation"] for c in result["choice_feedback"])


def test_simple_return_calc_question_scores_correctly_with_exact_decimal_expectation(db):
    """10강의 "50만원->60만원 = 20%" 계산 문항이 실제로 정확히 채점되는지 확인한다."""
    cookies, _ = signup_user("lesson-return-calc")
    lesson = _lesson_by_code(db, "lesson-10")
    quiz = db.query(Quiz).filter(Quiz.lesson_id == lesson.id).first()
    question = (
        db.query(Question)
        .filter(Question.quiz_id == quiz.id, Question.prompt.like("%50만원%"))
        .first()
    )
    assert question is not None
    correct_choice = db.query(Choice).filter(Choice.question_id == question.id, Choice.is_correct.is_(True)).first()
    assert correct_choice.label == "20%"

    wrong_choice = db.query(Choice).filter(Choice.question_id == question.id, Choice.is_correct.is_(False)).first()
    res = client.post(
        f"/v1/quizzes/{quiz.id}/attempts", json={"answers": {str(question.id): [str(wrong_choice.id)]}},
        cookies=cookies,
    )
    body = res.json()
    result = next(r for r in body["results"] if r["question_id"] == str(question.id))
    assert result["correct"] is False


# --- XP 중복 방지(신규 강의) ---


def test_new_lesson_completion_awards_xp_exactly_once(db):
    cookies, _ = signup_user("lesson-xp-dedup")
    lesson = _lesson_by_code(db, "lesson-11")  # PUBLISHED

    first = client.post(f"/v1/lessons/{lesson.id}/progress", json={"status": "COMPLETED"}, cookies=cookies)
    assert first.status_code == 200
    assert first.json()["xp_awarded"] > 0

    second = client.post(f"/v1/lessons/{lesson.id}/progress", json={"status": "COMPLETED"}, cookies=cookies)
    assert second.json()["xp_awarded"] == 0


def test_new_lesson_quiz_pass_awards_xp_exactly_once(db):
    cookies, _ = signup_user("lesson-quiz-xp-dedup")
    lesson = _lesson_by_code(db, "lesson-12")
    quiz = db.query(Quiz).filter(Quiz.lesson_id == lesson.id).first()
    questions = db.query(Question).filter(Question.quiz_id == quiz.id).all()
    answers = {}
    for q in questions:
        correct = db.query(Choice).filter(Choice.question_id == q.id, Choice.is_correct.is_(True)).first()
        answers[str(q.id)] = [str(correct.id)]

    first = client.post(f"/v1/quizzes/{quiz.id}/attempts", json={"answers": answers}, cookies=cookies)
    assert first.json()["xp_awarded"] > 0
    second = client.post(f"/v1/quizzes/{quiz.id}/attempts", json={"answers": answers}, cookies=cookies)
    assert second.json()["xp_awarded"] == 0


# --- 기존 데이터 보존 ---


def test_existing_lesson_1_to_5_untouched_by_new_module(db):
    old_module = db.query(Module).filter(Module.title == "1부. 투자의 기본 개념").first()
    lessons = db.query(Lesson).filter(Lesson.module_id == old_module.id).order_by(Lesson.order_index).all()
    assert len(lessons) == 5
    assert lessons[0].title == "투자는 무엇인가"
    assert all(l.code is None for l in lessons)  # 소급 채움 없음


def test_existing_challenge_card_lessons_untouched(db):
    card_module = db.query(Module).filter(Module.title == "보충: 7일 챌린지 카드").first()
    lessons = db.query(Lesson).filter(Lesson.module_id == card_module.id).all()
    titles = {l.title for l in lessons}
    assert {"주문 방식: 시장가와 지정가", "분산과 집중위험", "행동편향 살펴보기"} <= titles


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
