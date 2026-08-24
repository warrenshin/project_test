"""로컬 스테이징 안전 검증기(app/core/config.py의 environment=='staging' 분기)를
검증한다. test_auth.py::test_production_cookie_policy_requires_secure_and_valid_secret
와 동일한 패턴(Settings()를 직접 생성해 ValidationError를 확인) — 이 테스트는
실제 스테이징 DB/컨테이너를 띄우지 않고 순수하게 pydantic 검증 로직만 확인한다.
"""

import pytest
from pydantic import ValidationError

from app.core.config import Settings

_VALID_STAGING_KWARGS = dict(
    environment="staging",
    database_url="postgresql+psycopg://staging_app:x@staging-postgres:5432/investment_learning_staging",
    jwt_secret="a-sufficiently-long-random-staging-secret",
    cookie_secure=True,
    cors_allowed_origins_raw="http://localhost:3001",
)


def test_staging_settings_valid_configuration_boots():
    settings = Settings(**_VALID_STAGING_KWARGS)
    assert settings.environment == "staging"


def test_staging_rejects_non_staging_postgres_host():
    bad = dict(_VALID_STAGING_KWARGS, database_url="postgresql+psycopg://app:app@postgres:5432/investment_learning")
    with pytest.raises(ValidationError, match="staging-postgres"):
        Settings(**bad)


def test_staging_rejects_localhost_host_too():
    """dev DB를 로컬 포트포워딩(localhost:5432)으로 잘못 가리키는 경우도 막는다."""
    bad = dict(_VALID_STAGING_KWARGS, database_url="postgresql+psycopg://app:app@localhost:5432/investment_learning")
    with pytest.raises(ValidationError, match="staging-postgres"):
        Settings(**bad)


def test_staging_rejects_prod_looking_database_url():
    bad = dict(
        _VALID_STAGING_KWARGS,
        database_url="postgresql+psycopg://app:app@staging-postgres:5432/investment_learning_prod",
    )
    with pytest.raises(ValidationError, match="prod"):
        Settings(**bad)


def test_staging_rejects_default_jwt_secret():
    bad = dict(_VALID_STAGING_KWARGS, jwt_secret="change-me-in-env")
    with pytest.raises(ValidationError, match="JWT_SECRET"):
        Settings(**bad)


def test_staging_rejects_unedited_example_placeholder_secret():
    """.env.staging.example의 기본값을 그대로 쓰는 경우("change-me" 패턴 포함)도 막는다."""
    bad = dict(_VALID_STAGING_KWARGS, jwt_secret="staging-local-placeholder-change-me-32chars-min")
    with pytest.raises(ValidationError, match="change-me|JWT_SECRET"):
        Settings(**bad)


def test_staging_rejects_too_short_jwt_secret():
    bad = dict(_VALID_STAGING_KWARGS, jwt_secret="short")
    with pytest.raises(ValidationError, match="JWT_SECRET"):
        Settings(**bad)


def test_staging_rejects_insecure_cookie_without_explicit_opt_in():
    bad = dict(_VALID_STAGING_KWARGS, cookie_secure=False, staging_allow_insecure_cookie=False)
    with pytest.raises(ValidationError, match="STAGING_ALLOW_INSECURE_COOKIE"):
        Settings(**bad)


def test_staging_allows_insecure_cookie_with_explicit_local_opt_in():
    ok = dict(_VALID_STAGING_KWARGS, cookie_secure=False, staging_allow_insecure_cookie=True)
    settings = Settings(**ok)
    assert settings.cookie_secure is False
    assert settings.staging_allow_insecure_cookie is True


def test_staging_rejects_empty_cors_origins():
    bad = dict(_VALID_STAGING_KWARGS, cors_allowed_origins_raw="")
    with pytest.raises(ValidationError, match="CORS"):
        Settings(**bad)


def test_staging_rejects_non_loopback_cors_origin():
    bad = dict(_VALID_STAGING_KWARGS, cors_allowed_origins_raw="https://staging.example.com")
    with pytest.raises(ValidationError, match="localhost/127.0.0.1"):
        Settings(**bad)


def test_staging_allows_127_0_0_1_cors_origin():
    ok = dict(_VALID_STAGING_KWARGS, cors_allowed_origins_raw="http://127.0.0.1:3001")
    settings = Settings(**ok)
    assert settings.cors_allowed_origins == ["http://127.0.0.1:3001"]
