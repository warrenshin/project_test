"""인앱 알림(스텁) 테스트. 실제 푸시 발송이 없다는 전제 아래, 서버가 계산해
돌려주는 "지금 보여줄 알림" 목록만 검증한다 — 매수 유도·조급함을 자극하는
문구가 아니라 담담한 안내 문구인지도 함께 확인한다."""

import uuid
from datetime import datetime, timezone

from app.domain.journal import JournalEntry
from tests.conftest import client, seed_instrument_with_bar, signup_user


def _get_challenge_id() -> str:
    return client.get("/v1/challenges").json()[0]["id"]


def test_notifications_require_auth():
    res = client.get("/v1/me/notifications")
    assert res.status_code == 401


def test_fresh_user_without_challenge_has_no_notifications():
    cookies, _ = signup_user("notif-fresh")
    res = client.get("/v1/me/notifications", cookies=cookies)
    assert res.status_code == 200
    assert res.json() == []


def test_lesson_due_notification_appears_after_starting_challenge():
    cookies, _ = signup_user("notif-lesson")
    challenge_id = _get_challenge_id()
    res = client.post(f"/v1/challenges/{challenge_id}/start", json={}, cookies=cookies)
    assert res.status_code == 201, res.text

    notes = client.get("/v1/me/notifications", cookies=cookies).json()
    lesson_notes = [n for n in notes if n["type"] == "LESSON_DUE"]
    assert len(lesson_notes) == 1
    # 조급함을 자극하거나 매수를 종용하는 문구가 없어야 한다.
    for n in notes:
        for forbidden in ["지금 매수", "매수하세요", "기회를 놓", "손실을 만회"]:
            assert forbidden not in n["title"] and forbidden not in n["body"]


def test_badge_earned_notification_appears_after_earning_badge(db):
    from app.domain.learning import Choice, Lesson, Question, Quiz

    cookies, _ = signup_user("notif-badge")
    challenge_id = _get_challenge_id()
    uc = client.post(f"/v1/challenges/{challenge_id}/start", json={}, cookies=cookies).json()

    lesson = db.query(Lesson).filter(Lesson.title == "투자는 무엇인가").first()
    quiz = db.query(Quiz).filter(Quiz.lesson_id == lesson.id).first()
    questions = db.query(Question).filter(Question.quiz_id == quiz.id).all()
    answers = {}
    for q in questions:
        correct = db.query(Choice).filter(Choice.question_id == q.id, Choice.is_correct.is_(True)).first()
        answers[str(q.id)] = [str(correct.id)]
    assert client.post(f"/v1/lessons/{lesson.id}/progress", json={"status": "COMPLETED"}, cookies=cookies).status_code == 200
    assert client.post(f"/v1/quizzes/{quiz.id}/attempts", json={"answers": answers}, cookies=cookies).status_code == 200

    detail = client.get(f"/v1/challenges/{challenge_id}").json()
    mission = next(m for m in detail["days"][0]["missions"] if m["code"] == "day1_lesson")
    verify_res = client.post(
        f"/v1/me/challenges/{uc['id']}/missions/{mission['id']}/verify", json={}, cookies=cookies
    )
    assert verify_res.json()["mission_completed"] is True
    assert any(b["code"] == "first_step" for b in verify_res.json()["newly_awarded_badges"])

    notes = client.get("/v1/me/notifications", cookies=cookies).json()
    badge_notes = [n for n in notes if n["type"] == "BADGE_EARNED"]
    assert len(badge_notes) == 1
    assert badge_notes[0]["href"] == "/badges"


def test_reviewable_trade_notification_appears_for_unreviewed_order(db):
    cookies, portfolio_id = signup_user("notif-review")
    instrument = seed_instrument_with_bar(db, "NOTIFREV1", "NASDAQ", "USD", close=100)
    journal_res = client.post(
        "/v1/journals/pre-trade",
        json={
            "portfolio_id": portfolio_id, "instrument_id": str(instrument.id), "thesis": "판단 근거",
            "counter_evidence": ["반대 근거"], "stop_loss_condition": "손절 조건",
        },
        cookies=cookies,
    )
    journal_id = journal_res.json()["id"]

    # 실제 체결 플로우 없이, "주문이 걸린 뒤 아직 복기하지 않은 일지" 상태만
    # 재현한다(order_id에는 FK 제약이 없다 — journal_entries.order_id는 참조
    # 무결성 없는 nullable UUID 컬럼).
    db.query(JournalEntry).filter(JournalEntry.id == journal_id).update(
        {"order_id": uuid.uuid4(), "actual_entry_at": datetime.now(timezone.utc)}
    )
    db.commit()

    notes = client.get("/v1/me/notifications", cookies=cookies).json()
    review_notes = [n for n in notes if n["type"] == "TRADE_REVIEW_DUE"]
    assert len(review_notes) == 1
    assert review_notes[0]["href"] == f"/journal/{journal_id}"


def test_notifications_are_isolated_per_user():
    cookies_a, _ = signup_user("notif-iso-a")
    cookies_b, _ = signup_user("notif-iso-b")
    challenge_id = _get_challenge_id()
    client.post(f"/v1/challenges/{challenge_id}/start", json={}, cookies=cookies_a)

    notes_a = client.get("/v1/me/notifications", cookies=cookies_a).json()
    notes_b = client.get("/v1/me/notifications", cookies=cookies_b).json()
    assert any(n["type"] == "LESSON_DUE" for n in notes_a)
    assert notes_b == []
