"""DB가 준비될 때까지 짧은 간격으로 재시도한다.

docker-compose의 `depends_on: condition: service_healthy`가 대부분의 시작 순서
문제를 막아주지만, 이 스크립트만으로 컨테이너를 단독 실행하거나 오케스트레이터가
시작 순서를 보장하지 않는 환경에서도 migration이 조용히 실패하지 않도록 하는
방어적 장치다. 정해진 시간 안에 연결되지 않으면 0이 아닌 코드로 종료해 컨테이너가
"실패"로 표시되게 한다 — 절대 조용히 넘어가지 않는다.

    python -m scripts.wait_for_db
"""

import sys
import time

from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError

from app.core.config import get_settings

MAX_WAIT_SECONDS = 60
RETRY_INTERVAL_SECONDS = 2


def main() -> None:
    settings = get_settings()
    engine = create_engine(settings.database_url)
    deadline = time.monotonic() + MAX_WAIT_SECONDS
    last_error: Exception | None = None

    while time.monotonic() < deadline:
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            print("[wait_for_db] 데이터베이스에 연결됐다.")
            return
        except OperationalError as exc:
            last_error = exc
            time.sleep(RETRY_INTERVAL_SECONDS)

    print(
        f"[wait_for_db] {MAX_WAIT_SECONDS}초 동안 데이터베이스에 연결하지 못해 포기한다: {last_error}",
        file=sys.stderr,
    )
    sys.exit(1)


if __name__ == "__main__":
    main()
