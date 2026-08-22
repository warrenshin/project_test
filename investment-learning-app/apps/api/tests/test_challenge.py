"""7일 학습 챌린지: 시작, 잠금, 소유권, XP 중복·상한, 배지, timezone 경계.

수익률·거래횟수는 어디에서도 보상 기준으로 쓰이지 않는다는 전제를 감사하듯
확인한다 — 모든 미션은 학습완료/퀴즈통과/일지완성도/코칭확인처럼 "과정"만
본다.
"""

import uuid
from datetime import date, datetime, timedelta, timezone

import pytest

from app.core.db import SessionLocal
from app.domain.challenge import (
    Challenge,
    ChallengeDay,
    ChallengeMission,
    UserBadge,
    UserChallenge,
    UserChallengeDay,
    UserMissionProgress,
)
from app.domain.learning import Lesson, Quiz
from app.domain.portfolio import Portfolio
from app.domain.services import challenge as challenge_service
from app.domain.user import Profile
from tests.conftest import client, signup_user

CHALLENGE_CODE = "seven-day-challenge"


def _idem() -> dict:
    return {"Idempotency-Key": str(uuid.uuid4())}


def _get_challenge_id() -> str:
    return client.get("/v1/challenges").json()[0]["id"]


def _get_detail(challenge_id: str) -> dict:
    return client.get(f"/v1/challenges/{challenge_id}").json()


def _start(cookies) -> dict:
    res = client.post(f"/v1/challenges/{_get_challenge_id()}/start", json={}, cookies=cookies)
    assert res.status_code == 201, res.text
    return res.json()


def _mission(detail: dict, day_index: int, code: str) -> dict:
    return next(m for m in detail["days"][day_index]["missions"] if m["code"] == code)


def _verify(cookies, uc_id: str, mission_id: str, payload: dict | None = None) -> dict:
    res = client.post(
        f"/v1/me/challenges/{uc_id}/missions/{mission_id}/verify", json=payload or {}, cookies=cookies
    )
    return res


def _complete_lesson_and_quiz(cookies, lesson_title: str, db) -> None:
    from app.domain.learning import Choice, Question

    lesson = db.query(Lesson).filter(Lesson.title == lesson_title).first()
    quiz = db.query(Quiz).filter(Quiz.lesson_id == lesson.id).first()
    questions = db.query(Question).filter(Question.quiz_id == quiz.id).all()
    answers = {}
    for q in questions:
        correct = db.query(Choice).filter(Choice.question_id == q.id, Choice.is_correct.is_(True)).first()
        answers[str(q.id)] = [str(correct.id)]
    res = client.post(f"/v1/lessons/{lesson.id}/progress", json={"status": "COMPLETED"}, cookies=cookies)
    assert res.status_code == 200, res.text
    res = client.post(f"/v1/quizzes/{quiz.id}/attempts", json={"answers": answers}, cookies=cookies)
    assert res.status_code == 200 and res.json()["passed"], res.text


# --- 시작 ---


def test_start_challenge_succeeds():
    cookies, _ = signup_user("challenge-start")
    uc = _start(cookies)
    assert uc["status"] == "ACTIVE"
    assert uc["current_day"] == 1
    assert uc["timezone"] == "Asia/Seoul"
    assert len(uc["days"]) == 7


def test_duplicate_start_is_rejected():
    cookies, _ = signup_user("challenge-dup")
    _start(cookies)
    res = client.post(f"/v1/challenges/{_get_challenge_id()}/start", json={}, cookies=cookies)
    assert res.status_code == 409, res.text


def test_start_uses_profile_timezone_by_default(db):
    cookies, portfolio_id = signup_user("challenge-tz")
    user_id = db.query(Portfolio).filter(Portfolio.id == portfolio_id).first().user_id
    db.query(Profile).filter(Profile.user_id == user_id).update({"timezone": "America/New_York"})
    db.commit()

    uc = _start(cookies)
    assert uc["timezone"] == "America/New_York"


# --- 접근 통제(IDOR) ---


def test_other_user_cannot_access_my_challenge():
    cookies_a, _ = signup_user("challenge-owner")
    uc_a = _start(cookies_a)

    cookies_b, _ = signup_user("challenge-intruder")
    res = client.get(f"/v1/me/challenges/{uc_a['id']}", cookies=cookies_b)
    assert res.status_code == 404


def test_other_user_cannot_verify_my_mission():
    cookies_a, _ = signup_user("challenge-owner2")
    detail = _get_detail(_get_challenge_id())
    uc_a = _start(cookies_a)
    mission = _mission(detail, 0, "day1_goal")

    cookies_b, _ = signup_user("challenge-intruder2")
    res = _verify(cookies_b, uc_a["id"], mission["id"], {"note": "몰래 완료 시도"})
    assert res.status_code == 404

    # 실제로 완료되지 않았어야 한다.
    state = client.get(f"/v1/me/challenges/{uc_a['id']}", cookies=cookies_a).json()
    assert state["days"][0]["missions"][2]["completed"] is False


# --- Day 잠금 ---


def test_future_day_mission_is_locked():
    cookies, _ = signup_user("challenge-locked")
    detail = _get_detail(_get_challenge_id())
    uc = _start(cookies)
    day2_mission = _mission(detail, 1, "day2_quiz")

    res = _verify(cookies, uc["id"], day2_mission["id"])
    assert res.status_code == 423


def test_missed_day_can_still_be_completed_later(db):
    """하루를 놓쳐도(현재 Day가 더 진행돼도) 이전 Day는 계속 완료할 수 있다 —
    즉시 실패시키지 않고 다음 접속 시 이어서 진행 가능해야 한다."""
    cookies, _ = signup_user("challenge-catchup")
    detail = _get_detail(_get_challenge_id())
    uc = _start(cookies)

    user_challenge = db.query(UserChallenge).filter(UserChallenge.id == uc["id"]).first()
    user_challenge.started_at = user_challenge.started_at - timedelta(days=3)
    user_challenge.started_date_local = user_challenge.started_date_local - timedelta(days=3)
    db.commit()

    state = client.get(f"/v1/me/challenges/{uc['id']}", cookies=cookies).json()
    assert state["current_day"] == 4

    goal_mission = _mission(detail, 0, "day1_goal")
    res = _verify(cookies, uc["id"], goal_mission["id"], {"note": "그래도 Day1은 할 수 있다"})
    assert res.status_code == 200
    assert res.json()["mission_completed"] is True


# --- timezone 경계·DST (순수 계산 함수 단위 테스트 — DB 불필요) ---


def _fake_user_challenge(tz: str, started_date_local: date) -> UserChallenge:
    uc = UserChallenge()
    uc.timezone = tz
    uc.started_date_local = started_date_local
    uc.status = "ACTIVE"
    uc.completed_at = None
    return uc


def test_current_day_number_just_before_midnight_local():
    uc = _fake_user_challenge("Asia/Seoul", date(2026, 3, 1))
    # 2026-03-01 23:59 KST = 2026-03-01 14:59 UTC -> 여전히 Day 1이어야 한다.
    now = datetime(2026, 3, 1, 14, 59, tzinfo=timezone.utc)
    assert challenge_service.current_day_number(uc, now) == 1


def test_current_day_number_just_after_midnight_local():
    uc = _fake_user_challenge("Asia/Seoul", date(2026, 3, 1))
    # 2026-03-02 00:01 KST = 2026-03-01 15:01 UTC -> Day 2로 넘어가야 한다.
    now = datetime(2026, 3, 1, 15, 1, tzinfo=timezone.utc)
    assert challenge_service.current_day_number(uc, now) == 2


def test_current_day_number_handles_dst_spring_forward():
    """America/New_York은 2026-03-08 02:00에 DST가 시작된다(시계가 1시간
    앞으로 간다). 그 경계를 넘나들어도 날짜 차이 계산이 흔들리면 안 된다."""
    uc = _fake_user_challenge("America/New_York", date(2026, 3, 7))
    before = datetime(2026, 3, 8, 4, 30, tzinfo=timezone.utc)  # 2026-03-07 23:30 EST
    after = datetime(2026, 3, 8, 5, 30, tzinfo=timezone.utc)  # 2026-03-08 01:30 EDT(DST 이후 오프셋)
    assert challenge_service.current_day_number(uc, before) == 1
    assert challenge_service.current_day_number(uc, after) == 2


def test_invalid_timezone_is_rejected():
    with pytest.raises(challenge_service.InvalidTimezoneError):
        challenge_service.validate_timezone("Not/ARealZone")


# --- mission.config 노출 안전성(내부 조건식 비노출) ---


def test_scenario_choice_public_config_never_exposes_correct_answer():
    """SCENARIO_CHOICE의 config에는 채점용 정답 키(correct_choice)가 들어있다.
    클라이언트에 내려주는 public_config에는 선택지(options)만 있어야 하고,
    correct_choice·explanation 같은 내부 채점 정보는 절대 섞여 나가면 안 된다."""
    detail = _get_detail(_get_challenge_id())
    mission = _mission(detail, 3, "day4_scenario")
    assert "options" in mission["public_config"]
    assert "correct_choice" not in mission["public_config"]
    assert "explanation" not in mission["public_config"]
    assert set(mission["public_config"]["options"].keys()) == {"A", "B"}


def test_lesson_and_quiz_public_config_expose_only_navigation_ids():
    detail = _get_detail(_get_challenge_id())
    lesson_mission = _mission(detail, 0, "day1_lesson")
    quiz_mission = _mission(detail, 0, "day1_quiz")
    assert set(lesson_mission["public_config"].keys()) == {"lesson_id"}
    assert set(quiz_mission["public_config"].keys()) == {"quiz_id", "lesson_id"}
    # 퀴즈 미션도 강의 상세 화면으로 바로 이동할 수 있어야 하므로 lesson_id를 함께 받는다.
    assert quiz_mission["public_config"]["lesson_id"] == lesson_mission["public_config"]["lesson_id"]


# --- evidence 소유권 ---


def test_journal_mission_rejects_other_users_journal(db):
    cookies_a, portfolio_id_a = signup_user("challenge-journal-a")
    cookies_b, portfolio_id_b = signup_user("challenge-journal-b")
    detail = _get_detail(_get_challenge_id())
    uc_a = _start(cookies_a)
    mission = _mission(detail, 2, "day3_journal")

    from tests.conftest import seed_instrument_with_bar

    instrument = seed_instrument_with_bar(db, "CHALJ1", "NASDAQ", "USD", close=100)
    journal_res = client.post(
        "/v1/journals/pre-trade",
        json={
            "portfolio_id": portfolio_id_b, "instrument_id": str(instrument.id), "thesis": "성장성이 좋다고 판단",
            "counter_evidence": ["경쟁 심화 우려"], "stop_loss_condition": "매입가 대비 -10%",
        },
        cookies=cookies_b,
    )
    assert journal_res.status_code == 201, journal_res.text
    journal_id_b = journal_res.json()["id"]

    # Day3 미션이므로 우선 Day3가 잠기지 않도록 챌린지 시작일을 앞당긴다(소유권
    # 검증 자체를 테스트하려는 것이지 Day 잠금을 테스트하려는 게 아니다).
    user_challenge = db.query(UserChallenge).filter(UserChallenge.id == uc_a["id"]).first()
    user_challenge.started_at -= timedelta(days=2)
    user_challenge.started_date_local -= timedelta(days=2)
    db.commit()

    res = _verify(cookies_a, uc_a["id"], mission["id"], {"journal_id": journal_id_b})
    assert res.status_code == 200
    assert res.json()["mission_completed"] is False
    assert "찾을 수 없습니다" in res.json()["reason"]


def test_journal_mission_rejects_journal_created_before_challenge_start(db):
    cookies, portfolio_id = signup_user("challenge-journal-old")
    from tests.conftest import seed_instrument_with_bar

    instrument = seed_instrument_with_bar(db, "CHALJ2", "NASDAQ", "USD", close=100)
    journal_res = client.post(
        "/v1/journals/pre-trade",
        json={
            "portfolio_id": portfolio_id, "instrument_id": str(instrument.id), "thesis": "판단 근거",
            "counter_evidence": ["반대 근거"], "stop_loss_condition": "손절 조건",
        },
        cookies=cookies,
    )
    journal_id = journal_res.json()["id"]

    detail = _get_detail(_get_challenge_id())
    uc = _start(cookies)
    # 챌린지 시작(started_at)을 일지 작성 이후 시각으로 옮겨 "챌린지 시작 전
    # 일지"인 것처럼 만든다. started_date_local은 별도로 2일 전으로 당겨
    # Day3 잠금은 풀되(day 판단 기준), started_at 자체는 일지 생성 시각보다
    # 뒤로 두어(소유권 판단 기준) 두 조건을 동시에 만족시킨다.
    user_challenge = db.query(UserChallenge).filter(UserChallenge.id == uc["id"]).first()
    user_challenge.started_at = datetime.now(timezone.utc) + timedelta(minutes=5)
    user_challenge.started_date_local = user_challenge.started_date_local - timedelta(days=2)
    db.commit()

    mission = _mission(detail, 2, "day3_journal")
    res = _verify(cookies, uc["id"], mission["id"], {"journal_id": journal_id})
    assert res.json()["mission_completed"] is False
    assert "챌린지 시작 이후" in res.json()["reason"]


def test_order_preview_mission_rejects_other_users_portfolio():
    cookies_a, portfolio_id_a = signup_user("challenge-order-a")
    cookies_b, portfolio_id_b = signup_user("challenge-order-b")
    detail = _get_detail(_get_challenge_id())
    uc_a = _start(cookies_a)
    mission = _mission(detail, 1, "day2_preview")

    from tests.conftest import seed_instrument_with_bar

    db = SessionLocal()
    instrument = seed_instrument_with_bar(db, "CHALORD1", "NASDAQ", "USD", close=100)
    instrument_id = str(instrument.id)
    # Day2 미션이므로 잠기지 않도록 챌린지 시작일을 하루 앞당긴다.
    user_challenge = db.query(UserChallenge).filter(UserChallenge.id == uc_a["id"]).first()
    user_challenge.started_at -= timedelta(days=1)
    user_challenge.started_date_local -= timedelta(days=1)
    db.commit()
    db.close()

    res = _verify(
        cookies_a, uc_a["id"], mission["id"],
        {"portfolio_id": portfolio_id_b, "instrument_id": instrument_id, "side": "BUY", "order_type": "MARKET", "quantity": "1"},
    )
    assert res.json()["mission_completed"] is False


def test_coaching_mission_requires_own_ai_message():
    cookies, _ = signup_user("challenge-coach")
    detail = _get_detail(_get_challenge_id())
    uc = _start(cookies)
    mission = _mission(detail, 5, "day6_coaching")

    # Day6 미션이므로 잠기지 않도록 챌린지 시작일을 5일 앞당긴다.
    db = SessionLocal()
    user_challenge = db.query(UserChallenge).filter(UserChallenge.id == uc["id"]).first()
    user_challenge.started_at -= timedelta(days=5)
    user_challenge.started_date_local -= timedelta(days=5)
    db.commit()
    db.close()

    res = _verify(cookies, uc["id"], mission["id"])
    assert res.json()["mission_completed"] is False

    conv = client.post("/v1/ai/conversations", json={}, cookies=cookies)
    assert conv.status_code == 201, conv.text
    msg = client.post(
        f"/v1/ai/conversations/{conv.json()['id']}/messages", json={"content": "이 일지 어때?"}, cookies=cookies
    )
    assert msg.status_code == 201, msg.text

    res = _verify(cookies, uc["id"], mission["id"])
    assert res.json()["mission_completed"] is True


# --- 중복·동시성 ---


def test_duplicate_mission_verification_is_idempotent_and_awards_xp_once():
    cookies, _ = signup_user("challenge-idem")
    detail = _get_detail(_get_challenge_id())
    uc = _start(cookies)
    mission = _mission(detail, 0, "day1_goal")

    first = _verify(cookies, uc["id"], mission["id"], {"note": "이번주 목표1"})
    assert first.json()["xp_awarded"] == 10
    second = _verify(cookies, uc["id"], mission["id"], {"note": "다른 텍스트로 재요청"})
    assert second.json()["already_completed"] is True
    assert second.json()["xp_awarded"] == 0


def test_concurrent_verification_does_not_double_award_xp(db):
    """두 요청이 동시에 같은 미션을 완료하려는 상황을 재현한다 — unique
    제약(SAVEPOINT)이 실제로 경합을 막는지 확인한다."""
    cookies, portfolio_id = signup_user("challenge-race")
    user_id = db.query(Portfolio).filter(Portfolio.id == portfolio_id).first().user_id
    challenge = db.query(Challenge).filter(Challenge.code == CHALLENGE_CODE).first()
    user_challenge = challenge_service.start_challenge(db, user_id, challenge.id, "Asia/Seoul")
    db.commit()

    day1 = db.query(ChallengeDay).filter(ChallengeDay.challenge_id == challenge.id, ChallengeDay.day_number == 1).first()
    mission = db.query(ChallengeMission).filter(ChallengeMission.challenge_day_id == day1.id, ChallengeMission.code == "day1_goal").first()

    session_b = SessionLocal()
    try:
        uc_b = session_b.query(UserChallenge).filter(UserChallenge.id == user_challenge.id).first()
        day1_b = session_b.query(ChallengeDay).filter(ChallengeDay.id == day1.id).first()
        mission_b = session_b.query(ChallengeMission).filter(ChallengeMission.id == mission.id).first()
        outcome_b = challenge_service.verify_mission(session_b, user_id, uc_b, mission_b, day1_b, {"note": "세션 B가 먼저"})
        session_b.commit()
        assert outcome_b.result.ok is True
        assert outcome_b.xp_awarded == 10

        # session(=db, "세션 A")은 세션 B의 커밋을 모르는 채로 같은 미션을 검증하려 한다.
        outcome_a = challenge_service.verify_mission(db, user_id, user_challenge, mission, day1, {"note": "세션 A가 뒤늦게"})
        db.commit()
        assert outcome_a.already_completed is True
        assert outcome_a.xp_awarded == 0

        count = (
            db.query(UserMissionProgress)
            .filter(UserMissionProgress.user_challenge_id == user_challenge.id, UserMissionProgress.challenge_mission_id == mission.id)
            .count()
        )
        assert count == 1
    finally:
        session_b.close()


def test_daily_xp_cap_limits_total_but_missions_still_complete(db):
    """하루 안에 여러 Day의 미션을 몰아서 완료하면 일일 XP 상한(100)을 넘는
    지급은 잘려야 한다 — 하지만 미션 완료 자체는 막히지 않는다."""
    cookies, portfolio_id = signup_user("challenge-cap")
    detail = _get_detail(_get_challenge_id())
    uc = _start(cookies)
    user_challenge = db.query(UserChallenge).filter(UserChallenge.id == uc["id"]).first()

    # Day 4까지 한꺼번에 열어(catch-up 정책 재사용) 여러 Day의 미션을 오늘 안에
    # 다 완료해 상한을 넘겨본다.
    user_challenge.started_at = user_challenge.started_at - timedelta(days=3)
    user_challenge.started_date_local = user_challenge.started_date_local - timedelta(days=3)
    db.commit()
    db.close()

    _complete_lesson_and_quiz(cookies, "투자는 무엇인가", SessionLocal())

    total_awarded = 0
    for day_index, code, payload in [
        (0, "day1_lesson", {}), (0, "day1_quiz", {}), (0, "day1_goal", {"note": "이번주 학습목표"}),
        (3, "day4_concentration", {}),
        (3, "day4_scenario", {"choice": "A"}),
    ]:
        mission = _mission(detail, day_index, code)
        res = _verify(cookies, uc["id"], mission["id"], payload)
        total_awarded += res.json()["xp_awarded"]

    summary = client.get("/v1/me/learning-summary", cookies=cookies).json()
    assert summary["todays_xp"] <= summary["daily_xp_cap"]
    assert total_awarded <= 100  # 챌린지 미션 XP만으로도 상한을 넘지 않게 잘렸어야 한다


# --- 배지 ---


def test_first_step_badge_awarded_once(db):
    cookies, _ = signup_user("challenge-badge1")
    detail = _get_detail(_get_challenge_id())
    uc = _start(cookies)
    _complete_lesson_and_quiz(cookies, "투자는 무엇인가", db)

    mission = _mission(detail, 0, "day1_lesson")
    res = _verify(cookies, uc["id"], mission["id"])
    assert any(b["code"] == "first_step" for b in res.json()["newly_awarded_badges"])

    badges = client.get("/v1/me/badges", cookies=cookies).json()
    assert sum(1 for b in badges if b["code"] == "first_step") == 1

    # 다시 평가해도 중복 지급되지 않는다.
    challenge_service.evaluate_and_award_badges(db, db.query(Portfolio).filter(Portfolio.id == client.get("/v1/me/portfolio", cookies=cookies).json()["id"]).first().user_id)
    db.commit()
    badges_again = client.get("/v1/me/badges", cookies=cookies).json()
    assert sum(1 for b in badges_again if b["code"] == "first_step") == 1


def test_badge_evidence_is_preserved(db):
    cookies, portfolio_id = signup_user("challenge-badge-evidence")
    user_id = db.query(Portfolio).filter(Portfolio.id == portfolio_id).first().user_id
    detail = _get_detail(_get_challenge_id())
    uc = _start(cookies)
    _complete_lesson_and_quiz(cookies, "투자는 무엇인가", db)
    mission = _mission(detail, 0, "day1_lesson")
    _verify(cookies, uc["id"], mission["id"])

    badge = db.query(UserBadge).filter(UserBadge.user_id == user_id).first()
    assert badge is not None
    assert badge.evidence_type == "LessonProgress"
    assert badge.evidence_id is not None


# --- 완주 ---


def test_seven_day_completion_awards_bonus_and_badge(db):
    cookies, portfolio_id = signup_user("challenge-finisher")
    user_id = db.query(Portfolio).filter(Portfolio.id == portfolio_id).first().user_id
    challenge = db.query(Challenge).filter(Challenge.code == CHALLENGE_CODE).first()
    user_challenge = challenge_service.start_challenge(db, user_id, challenge.id, "Asia/Seoul")
    db.commit()
    # 7일 전부 지금 당장 열어놓고 순서대로 완료한다(정책상 이전 Day 완료는 언제나 허용).
    user_challenge.started_at -= timedelta(days=10)
    user_challenge.started_date_local -= timedelta(days=10)
    db.commit()

    days = db.query(ChallengeDay).filter(ChallengeDay.challenge_id == challenge.id).order_by(ChallengeDay.day_number).all()

    def complete(day, code, payload=None):
        mission = db.query(ChallengeMission).filter(ChallengeMission.challenge_day_id == day.id, ChallengeMission.code == code).first()
        outcome = challenge_service.verify_mission(db, user_id, user_challenge, mission, day, payload or {})
        db.commit()
        return outcome

    _complete_lesson_and_quiz(cookies, "투자는 무엇인가", db)
    complete(days[0], "day1_lesson"); complete(days[0], "day1_quiz"); complete(days[0], "day1_goal", {"note": "이번주 학습목표"})

    from tests.conftest import seed_instrument_with_bar
    order_lesson = db.query(Lesson).filter(Lesson.title == "주문 방식: 시장가와 지정가").first()
    quiz2 = db.query(Quiz).filter(Quiz.lesson_id == order_lesson.id).first()
    _complete_lesson_and_quiz(cookies, "주문 방식: 시장가와 지정가", db)
    instrument = seed_instrument_with_bar(db, "CHALFIN1", "NASDAQ", "USD", close=100)
    complete(days[1], "day2_lesson"); complete(days[1], "day2_quiz")
    complete(days[1], "day2_preview", {
        "portfolio_id": portfolio_id, "instrument_id": str(instrument.id), "side": "BUY", "order_type": "MARKET", "quantity": "1",
    })

    journal_res = client.post(
        "/v1/journals/pre-trade",
        json={
            "portfolio_id": portfolio_id, "instrument_id": str(instrument.id), "thesis": "판단 근거",
            "counter_evidence": ["반대 근거"], "stop_loss_condition": "손절 조건",
        },
        cookies=cookies,
    )
    journal_id = journal_res.json()["id"]
    complete(days[2], "day3_journal", {"journal_id": journal_id})

    diversification_lesson = db.query(Lesson).filter(Lesson.title == "분산과 집중위험").first()
    _complete_lesson_and_quiz(cookies, "분산과 집중위험", db)
    complete(days[3], "day4_lesson"); complete(days[3], "day4_quiz")
    complete(days[3], "day4_concentration")
    complete(days[3], "day4_scenario", {"choice": "A"})

    complete(days[4], "day5_order_preview", {"journal_id": journal_id})
    complete(days[4], "day5_disclosure", {"acknowledged": True})

    _complete_lesson_and_quiz(cookies, "행동편향 살펴보기", db)
    complete(days[5], "day6_lesson"); complete(days[5], "day6_quiz")
    complete(days[5], "day6_bias")
    conv = client.post("/v1/ai/conversations", json={"journal_id": journal_id}, cookies=cookies).json()
    client.post(f"/v1/ai/conversations/{conv['id']}/messages", json={"content": "코칭 요청"}, cookies=cookies)
    complete(days[5], "day6_coaching")

    # Day1~6 미션만으로 이미 일일 XP 상한(100)에 근접·초과했을 것이다 — 이
    # 테스트는 "7일 완주 시 보너스 XP·배지가 지급되는지"를 보려는 것이지
    # 일일 상한 자체를 다시 검증하려는 게 아니므로(그건 별도 테스트가 담당),
    # 지금까지 쌓인 XP 기록을 "어제"로 옮겨 오늘의 상한을 새로 확보한다.
    db.query(challenge_service.gamification.XpLedger).filter(
        challenge_service.gamification.XpLedger.user_id == user_id
    ).update({"awarded_at": datetime.now(timezone.utc) - timedelta(days=1)})
    db.commit()

    client.post(
        f"/v1/journals/{journal_id}/post-trade",
        json={"followed_plan": True, "expectation_gap": "예상과 비슷했다", "behavior_to_repeat": "계획대로 손절"},
        cookies=cookies,
    )
    complete(days[6], "day7_review", {"journal_id": journal_id})
    complete(days[6], "day7_score", {"journal_id": journal_id})
    outcome = complete(days[6], "day7_next_action", {"note": "다음엔 더 분산하기"})

    assert outcome.challenge_completed is True
    db.refresh(user_challenge)
    assert user_challenge.completed_at is not None

    badges = {b for b, in db.query(challenge_service.BadgeDefinition.code).join(
        UserBadge, UserBadge.badge_definition_id == challenge_service.BadgeDefinition.id
    ).filter(UserBadge.user_id == user_id).all()}
    assert "seven_day_finisher" in badges

    total_xp_reason = sum(
        row.amount for row in db.query(challenge_service.gamification.XpLedger).filter(
            challenge_service.gamification.XpLedger.user_id == user_id,
            challenge_service.gamification.XpLedger.reason == challenge_service.XP_REASON_COMPLETE,
        )
    )
    assert total_xp_reason == challenge_service.CHALLENGE_COMPLETE_BONUS_XP
