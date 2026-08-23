"""학습 콘텐츠 무결성을 "전체 강의 수" 같은 깨지기 쉬운 고정값이 아니라,
필수 code 집합의 존재·중복 여부와 승인 상태로 검증한다.

향후 lesson-16이 추가돼도 이 스크립트나 CI 워크플로를 고칠 필요가 없다 —
EXPECTED_CODES에 새 code만 추가하면 된다(그마저도 "이 강의가 반드시
있어야 한다"를 강제하고 싶을 때만 필요하고, 강제하고 싶지 않다면 아예
건드리지 않아도 된다: 이 스크립트는 EXPECTED_CODES에 없는 code가 추가로
있어도 실패시키지 않는다 — 존재해야 하는 것만 확인하지, 그 이상 있으면
안 된다고 막지 않는다).

검증 항목:
1. EXPECTED_CODES의 각 code가 정확히 1개씩 존재한다.
2. code 중복이 전혀 없다(unique 인덱스가 있지만 애플리케이션 레벨에서도
   재확인 — 인덱스가 실수로 빠진 채 배포되는 경우를 대비).
3. lesson-06~15는 전부 status=READY_FOR_REVIEW다(에이전트가 자기 승인해
   PUBLISHED로 만들지 않았는지 CI에서도 매번 확인).
4. lesson-06~15는 실행 중인 API의 `GET /v1/learning/paths` 응답 어디에도
   나타나지 않는다(선택적 — API_BASE_URL이 주어졌을 때만 수행).

전체 강의 수는 정보 로그로만 출력한다.

    python -m scripts.verify_lesson_content_integrity [--api-base-url http://localhost:8000]
"""

import argparse
import sys
import urllib.request
import json as json_module

from app.core.db import SessionLocal
from app.domain.learning import CONTENT_READY_FOR_REVIEW, Lesson

EXPECTED_CODES = {
    "lesson-01", "lesson-02", "lesson-03", "lesson-04", "lesson-05",
    "challenge-day2-order-types", "challenge-day4-diversification", "challenge-day6-bias",
    "lesson-06", "lesson-07", "lesson-08", "lesson-09", "lesson-10",
    "lesson-11", "lesson-12", "lesson-13", "lesson-14", "lesson-15",
}

NEW_LESSON_CODES = {f"lesson-{n:02d}" for n in range(6, 16)}


def _fail(errors: list[str]) -> None:
    for e in errors:
        print(f"::error::{e}", file=sys.stderr)
    sys.exit(1)


def verify_db(db) -> list[str]:
    errors: list[str] = []

    all_codes = [row[0] for row in db.query(Lesson.code).filter(Lesson.code.isnot(None)).all()]
    print(f"정보: 전체 강의(code 보유) 수 = {len(all_codes)} (pass/fail 기준 아님, 정보용)")

    code_counts: dict[str, int] = {}
    for code in all_codes:
        code_counts[code] = code_counts.get(code, 0) + 1

    duplicates = {c: n for c, n in code_counts.items() if n > 1}
    if duplicates:
        errors.append(f"code 중복 발견: {duplicates}")

    for expected in sorted(EXPECTED_CODES):
        count = code_counts.get(expected, 0)
        if count != 1:
            errors.append(f"필수 lesson code {expected!r}가 정확히 1개여야 하는데 {count}개입니다.")

    new_lessons = db.query(Lesson).filter(Lesson.code.in_(NEW_LESSON_CODES)).all()
    if len(new_lessons) != len(NEW_LESSON_CODES):
        errors.append(f"신규 강의(lesson-06~15) {len(NEW_LESSON_CODES)}개 중 {len(new_lessons)}개만 발견됨.")
    for lesson in new_lessons:
        if lesson.status != CONTENT_READY_FOR_REVIEW:
            errors.append(
                f"{lesson.code}의 status가 {lesson.status!r}입니다 — READY_FOR_REVIEW여야 합니다"
                "(에이전트가 스스로 승인했을 가능성 — 반드시 확인 필요)."
            )

    return errors


def verify_api_hides_unpublished(api_base_url: str) -> list[str]:
    errors: list[str] = []
    try:
        with urllib.request.urlopen(f"{api_base_url}/v1/learning/paths", timeout=10) as resp:
            paths = json_module.loads(resp.read())
    except Exception as exc:  # noqa: BLE001 — CI 진단용으로 원인을 그대로 보여준다
        errors.append(f"GET /v1/learning/paths 호출 실패: {exc}")
        return errors

    titles = {
        lesson["title"]
        for path in paths
        for course in path.get("courses", [])
        for module in course.get("modules", [])
        for lesson in module.get("lessons", [])
    }
    # 신규 강의 제목 중 하나라도 공개 API 응답에 보이면 실패 — 정확한 제목 목록은
    # DB에서 직접 가져와 이 스크립트가 콘텐츠를 다시 베껴 쓰지 않게 한다.
    db = SessionLocal()
    try:
        new_titles = {
            row[0]
            for row in db.query(Lesson.title).filter(Lesson.code.in_(NEW_LESSON_CODES)).all()
        }
    finally:
        db.close()

    leaked = titles & new_titles
    if leaked:
        errors.append(f"미승인 신규 강의가 공개 API에 노출됨: {leaked}")
    return errors


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-base-url", default=None, help="주어지면 실행 중인 API에 대해 공개 노출 여부도 확인한다.")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        errors = verify_db(db)
    finally:
        db.close()

    if args.api_base_url:
        errors += verify_api_hides_unpublished(args.api_base_url)

    if errors:
        _fail(errors)

    print("강의 콘텐츠 무결성 확인 OK: 필수 code 전부 존재, 중복 없음, 신규 강의는 전부 READY_FOR_REVIEW.")


if __name__ == "__main__":
    main()
