"""시드 데이터 행 수를 code별로 나눠 JSON으로 출력한다.

migration/seed를 재실행해도 중복이 생기지 않는지(멱등성) CI에서 재실행 전/후
숫자를 비교하기 위한 용도다. 값을 바꾸지 않고 읽기만 한다.

lessons_total은 전체 강의 수가 몇 강까지 늘어나도 자동으로 커지므로 정보
로그로만 쓴다 — pass/fail 판단에 쓰지 않는다(고정값 비교는
verify_lesson_content_integrity.py가 code 집합 단위로 한다). code가 없는
레거시 행(현재는 없지만 향후를 대비)은 lessons_without_code로 별도 집계해
code별 딕셔너리에 숨겨진 채로 누락되지 않게 한다.

    python -m scripts.count_seed_rows
"""

import json

from app.core.db import SessionLocal
from app.domain.learning import Lesson
from app.domain.market import Instrument


def main() -> None:
    db = SessionLocal()
    try:
        lessons = db.query(Lesson.code).all()
        lessons_by_code: dict[str, int] = {}
        lessons_without_code = 0
        for (code,) in lessons:
            if code is None:
                lessons_without_code += 1
            else:
                lessons_by_code[code] = lessons_by_code.get(code, 0) + 1
        instrument_count = db.query(Instrument).filter(Instrument.valid_to.is_(None)).count()
        print(
            json.dumps(
                {
                    "lessons_total": len(lessons),
                    "lessons_without_code": lessons_without_code,
                    "lessons_by_code": lessons_by_code,
                    "instruments": instrument_count,
                },
                sort_keys=True,
            )
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()
