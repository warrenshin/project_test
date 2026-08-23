"""사람이 작성한 검수 문서(docs/content-review 첨부 감사 결과)가 지적한 6~15강
콘텐츠 오류가 실제로 고쳐졌고, 이후 되돌아가지 않는지 확인하는 회귀 테스트다.

이 파일은 alembic/versions/a9c8d7e6f5b4_correct_lessons_06_15_content_per_external_review.py
가 적용하는 수정이 실제 DB에 반영됐는지만 확인한다 — 수정 자체의 근거(공식
출처 원문 대조)는 여전히 사람이 직접 확인해야 하며, 이 테스트는 그것을
대신하지 않는다. 아울러 이 migration이 상태 필드(status/review_status/
reviewed_by/reviewed_at/source_confirmed_at)를 전혀 건드리지 않았는지도
확인한다 — 콘텐츠를 고쳤다고 해서 검수·게시 상태가 앞당겨지면 안 된다.
"""

from app.domain.learning import CONTENT_READY_FOR_REVIEW, Choice, ContentBlock, Lesson, Question, Quiz, REVIEW_REQUIRED

NEW_LESSON_CODES = [f"lesson-{n:02d}" for n in range(6, 16)]


def _lesson_by_code(db, code: str) -> Lesson:
    lesson = db.query(Lesson).filter(Lesson.code == code).first()
    assert lesson is not None, f"{code}를 찾을 수 없습니다."
    return lesson


def _block(db, lesson: Lesson, block_type: str) -> ContentBlock:
    block = db.query(ContentBlock).filter(ContentBlock.lesson_id == lesson.id, ContentBlock.block_type == block_type).first()
    assert block is not None, f"{lesson.code}의 {block_type} 블록을 찾을 수 없습니다."
    return block


def _question(db, lesson: Lesson, order_index: int) -> Question:
    quiz = db.query(Quiz).filter(Quiz.lesson_id == lesson.id).first()
    assert quiz is not None
    question = db.query(Question).filter(Question.quiz_id == quiz.id, Question.order_index == order_index).first()
    assert question is not None
    return question


def test_corrections_do_not_change_authoring_or_review_state(db):
    """콘텐츠 오타·표현 수정이 검수·게시 상태를 앞당기지 않았는지 확인한다 —
    이 회귀 테스트가 가장 중요하게 지키는 불변조건이다."""
    for code in NEW_LESSON_CODES:
        lesson = _lesson_by_code(db, code)
        assert lesson.status == CONTENT_READY_FOR_REVIEW, f"{code}의 status가 바뀜 — 콘텐츠 수정이 게시를 유발하면 안 됩니다."
        assert lesson.review_status == REVIEW_REQUIRED
        assert lesson.reviewed_by is None
        assert lesson.reviewed_at is None
        assert lesson.source_confirmed_at is None, f"{code}: source_url을 채웠다고 source_confirmed_at까지 채우면 안 됩니다."


def test_lesson06_no_longer_overgeneralizes_dst_and_after_hours_orders(db):
    lesson = _lesson_by_code(db, "lesson-06")
    body = _block(db, lesson, "BODY").content
    assert "미국 정규장 자체는 동부시간(ET) 기준 09:30~16:00으로 고정 운영되지만" in body
    assert "장 마감 후 주문의 접수·취소·시간외 체결·다음 세션 이월 여부는 주문 유형, 유효기간, 거래소 및 증권사 정책에 따라 다릅니다" in body
    # 예전처럼 "다음 정규장이 열리는 시점에 실제로 체결을 시도합니다"라고 단정하지 않는다.
    assert "많은 거래 플랫폼은 장이 닫혀 있어도" not in body

    q3 = _question(db, lesson, 2)
    assert "증권사" in q3.explanation and "정책" in q3.explanation
    correct = db.query(Choice).filter(Choice.question_id == q3.id, Choice.is_correct.is_(True)).first()
    assert "증권사" in correct.label and "정책" in correct.label

    assert lesson.source_url == "https://global.krx.co.kr/contents/GLB/06/0602/0602010201/GLB0602010201T1.jsp"


def test_lesson07_reflects_partial_fill_and_order_ttl(db):
    lesson = _lesson_by_code(db, "lesson-07")
    body = _block(db, lesson, "BODY").content
    assert "부분체결" in body
    assert "주문 유효기간" in body
    assert "가격의 상한을 지정" in body and "가격의 하한을 지정" in body

    q2 = _question(db, lesson, 1)
    assert "매도호가" in q2.prompt  # "9,700원까지만 내려왔다"는 모호한 조건이 아니라 매도호가 기준으로 명확화됨
    assert lesson.source_url is not None and "investor.gov" in lesson.source_url


def test_lesson08_practice_no_longer_asserts_app_pricing_basis(db):
    lesson = _lesson_by_code(db, "lesson-08")
    practice = _block(db, lesson, "PRACTICE").content
    assert "포트폴리오 화면에서 방금 매수한 종목의 평가손익을 확인해보세요" not in practice
    assert "서비스마다 다를 수 있으므로" in practice


def test_lesson09_fee_example_has_explicit_computed_breakdown(db):
    lesson = _lesson_by_code(db, "lesson-09")
    example = _block(db, lesson, "EXAMPLE").content
    for expected in ("150원", "165원", "1,980원", "2,295원", "97,705원", "9.77%"):
        assert expected in example, f"lesson-09 EXAMPLE에 {expected}가 없습니다: {example}"
    body = _block(db, lesson, "BODY").content
    assert "왕복" in body and "편도" in body


def test_lesson10_uses_net_return_wording_not_confusing_실질수익률(db):
    lesson = _lesson_by_code(db, "lesson-10")
    body = _block(db, lesson, "BODY").content
    assert "비용 차감 후 순수익률" in body
    assert "비용 반영 후(실질) 수익률" not in body
    assert "시간가중수익률" in body or "금액가중수익률" in body


def test_lesson11_compounding_states_assumptions_and_qualifies_q3(db):
    lesson = _lesson_by_code(db, "lesson-11")
    body = _block(db, lesson, "BODY").content
    assert "연 1회 복리로 계산" in body

    q3 = _question(db, lesson, 2)
    assert "일정한 양수" in q3.explanation


def test_lesson12_mdd_defined_via_running_peak(db):
    lesson = _lesson_by_code(db, "lesson-12")
    body = _block(db, lesson, "BODY").content
    assert "각 시점까지의 누적 최고 가치(고점)" in body
    assert "최종 누적수익률" in _block(db, lesson, "EXAMPLE").content


def test_lesson13_correlation_explanation_does_not_imply_opposite_movement(db):
    lesson = _lesson_by_code(db, "lesson-13")
    q4 = _question(db, lesson, 3)
    assert "같은 방향·같은 폭으로 함께 움직이지 않을 가능성" in q4.explanation
    assert "한쪽이 하락할 때 다른 쪽이 덜 하락하거나 상승할 가능성" not in q4.explanation


def test_lesson14_bonds_and_cash_are_not_presented_as_risk_free(db):
    lesson = _lesson_by_code(db, "lesson-14")
    body = _block(db, lesson, "BODY").content
    assert "채권도 금리 상승" in body
    assert "현금도 물가상승" in body
    assert "새로 납입하는 자금을 비중이 부족한 자산군에 배분" in body


def test_lesson15_market_cap_defined_as_common_equity_not_whole_company(db):
    lesson = _lesson_by_code(db, "lesson-15")
    body = _block(db, lesson, "BODY").content
    assert "보통주 지분 전체의 시장가치" in body
    assert "이자부부채" in body
    assert "우선주" in body

    terms = _block(db, lesson, "TERMS").content
    assert "보통주 지분" in terms

    q3 = _question(db, lesson, 2)
    correct = db.query(Choice).filter(Choice.question_id == q3.id, Choice.is_correct.is_(True)).first()
    assert "이자부부채" in correct.label
