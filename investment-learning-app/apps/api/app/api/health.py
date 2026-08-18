"""Liveness/readiness 엔드포인트.

/health/live: 프로세스가 요청을 처리할 수 있는 상태로 살아 있는지만 확인한다.
             DB나 외부 서비스에 의존하지 않는다 — orchestrator가 이 값을 보고
             컨테이너를 재시작할지 판단하므로, DB가 잠깐 느려졌다고 멀쩡한
             프로세스를 죽이면 안 된다.
/health/ready: 실제 요청을 처리할 준비가 됐는지 확인한다 — DB 연결과 Alembic
              마이그레이션이 최신(head)인지를 본다. 둘 중 하나라도 실패하면
              503을 반환해 로드밸런서/오케스트레이터가 이 인스턴스로 트래픽을
              보내지 않게 한다.

두 엔드포인트 모두 내부 오류 메시지, DB URL, 스택트레이스 등 민감한 정보를
응답에 절대 포함하지 않는다 — 사유는 정해진 짧은 코드(reason)로만 알린다.
"""

import pathlib

from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.core.db import engine

router = APIRouter(tags=["ops"])

_ALEMBIC_INI = pathlib.Path(__file__).resolve().parents[2] / "alembic.ini"


def _expected_head_revision() -> str | None:
    try:
        config = Config(str(_ALEMBIC_INI))
        script = ScriptDirectory.from_config(config)
        return script.get_current_head()
    except Exception:
        return None


@router.get("/health/live")
def health_live():
    return {"status": "ok"}


@router.get("/health/ready")
def health_ready():
    try:
        with engine.connect() as conn:
            current_revision = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
    except Exception:
        return JSONResponse(status_code=503, content={"status": "not_ready", "reason": "database_unavailable"})

    expected_revision = _expected_head_revision()
    if expected_revision is not None and current_revision != expected_revision:
        return JSONResponse(status_code=503, content={"status": "not_ready", "reason": "migration_pending"})

    return {"status": "ready"}
