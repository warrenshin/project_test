"""app/core/config.py의 DATABASE_URL 드라이버 정규화 검증기를 확인한다.

Render/Heroku류 호스팅 제공자는 DATABASE_URL을 `postgres://` 또는
`postgresql://` 스킴으로 준다. 이 프로젝트는 psycopg2가 아니라 psycopg(3)만
설치돼 있으므로(requirements.txt) 드라이버를 명시하지 않은 URL은 `+psycopg`로
정규화돼야 한다 — 그렇지 않으면 SQLAlchemy가 기본값인 psycopg2를 찾다가
ModuleNotFoundError로 기동에 실패한다.
"""

from app.core.config import Settings


def test_bare_postgres_scheme_is_normalized_to_psycopg():
    settings = Settings(database_url="postgres://user:pw@example-host:5432/db")
    assert settings.database_url == "postgresql+psycopg://user:pw@example-host:5432/db"


def test_bare_postgresql_scheme_is_normalized_to_psycopg():
    settings = Settings(database_url="postgresql://user:pw@example-host:5432/db")
    assert settings.database_url == "postgresql+psycopg://user:pw@example-host:5432/db"


def test_explicit_psycopg_scheme_is_left_unchanged():
    settings = Settings(database_url="postgresql+psycopg://user:pw@example-host:5432/db")
    assert settings.database_url == "postgresql+psycopg://user:pw@example-host:5432/db"
