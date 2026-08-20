"""시드 데이터 행 수를 JSON으로 출력한다.

migration/seed를 재실행해도 중복이 생기지 않는지(멱등성) CI에서 재실행 전/후
숫자를 비교하기 위한 용도다. 값을 바꾸지 않고 읽기만 한다.

    python -m scripts.count_seed_rows
"""

import json

from app.core.db import SessionLocal
from app.domain.learning import Lesson
from app.domain.market import Instrument


def main() -> None:
    db = SessionLocal()
    try:
        lesson_count = db.query(Lesson).count()
        instrument_count = db.query(Instrument).filter(Instrument.valid_to.is_(None)).count()
        print(json.dumps({"lessons": lesson_count, "instruments": instrument_count}))
    finally:
        db.close()


if __name__ == "__main__":
    main()
