from tests.conftest import client, signup_user


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_learning_paths_include_seeded_lessons():
    res = client.get("/v1/learning/paths")
    assert res.status_code == 200
    paths = res.json()
    assert len(paths) >= 1

    lesson_titles = []
    for path in paths:
        for course in path["courses"]:
            for module in course["modules"]:
                for lesson in module["lessons"]:
                    lesson_titles.append(lesson["title"])
    assert "투자는 무엇인가" in lesson_titles


def _find_first_lesson_id() -> str:
    paths = client.get("/v1/learning/paths").json()
    return paths[0]["courses"][0]["modules"][0]["lessons"][0]["id"]


def test_lesson_detail_requires_auth():
    lesson_id = _find_first_lesson_id()
    res = client.get(f"/v1/lessons/{lesson_id}")
    assert res.status_code == 401


def test_complete_lesson_awards_xp_once():
    token, _ = signup_user("learner")
    lesson_id = _find_first_lesson_id()

    detail = client.get(f"/v1/lessons/{lesson_id}", headers=_auth(token))
    assert detail.status_code == 200
    body = detail.json()
    assert len(body["content_blocks"]) == 4
    assert body["quiz"]["question_count"] == 2
    assert body["progress"] is None

    first = client.post(
        f"/v1/lessons/{lesson_id}/progress", json={"status": "COMPLETED"}, headers=_auth(token)
    )
    assert first.status_code == 200
    assert first.json()["xp_awarded"] == 10

    # 이미 완료 처리된 강의를 다시 완료 처리해도 XP가 중복 지급되지 않는다
    second = client.post(
        f"/v1/lessons/{lesson_id}/progress", json={"status": "COMPLETED"}, headers=_auth(token)
    )
    assert second.status_code == 200
    assert second.json()["xp_awarded"] == 0

    summary = client.get("/v1/me/learning-summary", headers=_auth(token)).json()
    assert summary["total_xp"] == 10
    assert summary["lessons_completed"] == 1
    assert summary["current_streak_days"] == 1


def test_quiz_with_empty_answers_fails_without_xp():
    token, _ = signup_user("quiztaker")
    lesson_id = _find_first_lesson_id()
    detail = client.get(f"/v1/lessons/{lesson_id}", headers=_auth(token)).json()
    quiz_id = detail["quiz"]["id"]

    res = client.post(f"/v1/quizzes/{quiz_id}/attempts", json={"answers": {}}, headers=_auth(token))
    assert res.status_code == 200
    body = res.json()
    assert body["passed"] is False
    assert float(body["score_pct"]) == 0
    assert body["xp_awarded"] == 0
    assert len(body["results"]) == 2
    assert all(r["correct"] is False for r in body["results"])
    assert all(r["explanation"] for r in body["results"])


def test_quiz_pass_flow(db):
    from app.domain.learning import Choice, Question, Quiz

    token, _ = signup_user("passer")
    lesson_id = _find_first_lesson_id()
    detail = client.get(f"/v1/lessons/{lesson_id}", headers=_auth(token)).json()
    quiz_id = detail["quiz"]["id"]

    questions = db.query(Question).filter(Question.quiz_id == quiz_id).all()
    answers = {}
    for question in questions:
        correct_choice = db.query(Choice).filter(Choice.question_id == question.id, Choice.is_correct.is_(True)).first()
        answers[str(question.id)] = [str(correct_choice.id)]

    res = client.post(f"/v1/quizzes/{quiz_id}/attempts", json={"answers": answers}, headers=_auth(token))
    assert res.status_code == 200
    body = res.json()
    assert body["passed"] is True
    assert float(body["score_pct"]) == 100
    assert body["xp_awarded"] == 15

    # 재응시해서 다시 합격해도 XP는 다시 지급되지 않는다
    res2 = client.post(f"/v1/quizzes/{quiz_id}/attempts", json={"answers": answers}, headers=_auth(token))
    assert res2.json()["xp_awarded"] == 0

    summary = client.get("/v1/me/learning-summary", headers=_auth(token)).json()
    assert summary["quizzes_passed"] == 1
    assert summary["total_xp"] == 15


def test_get_quiz_returns_questions_without_correct_answer():
    token, _ = signup_user("quizreader")
    lesson_id = _find_first_lesson_id()
    detail = client.get(f"/v1/lessons/{lesson_id}", headers=_auth(token)).json()
    quiz_id = detail["quiz"]["id"]

    res = client.get(f"/v1/quizzes/{quiz_id}", headers=_auth(token))
    assert res.status_code == 200
    body = res.json()
    assert body["id"] == quiz_id
    assert len(body["questions"]) == 2
    for question in body["questions"]:
        assert question["choices"]
        for choice in question["choices"]:
            assert "is_correct" not in choice


def test_daily_xp_cap_enforced(db):
    from app.domain.services import gamification
    import uuid as uuid_module

    token, _ = signup_user("capped")

    # 남은 한도를 초과하는 큰 금액을 직접 지급 시도해 상한이 지켜지는지 검증한다.
    from app.domain.user import User

    user = db.query(User).filter(User.email.like("capped-%")).order_by(User.created_at.desc()).first()
    awarded = gamification.award_xp(db, user.id, 1000, "TEST_BULK", uuid_module.uuid4())
    db.commit()
    assert awarded == gamification.XP_DAILY_CAP  # 1000을 요청해도 일일 상한(100)까지만 지급된다

    summary = client.get("/v1/me/learning-summary", headers=_auth(token)).json()
    assert summary["todays_xp"] == gamification.XP_DAILY_CAP
