from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """앱 전역 설정. 값은 환경변수 또는 .env에서 로드한다."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "investment-learning-app-api"
    api_v1_prefix: str = "/v1"
    environment: str = "development"

    database_url: str = "postgresql+psycopg://app:app@localhost:5432/investment_learning"
    redis_url: str = "redis://localhost:6379/0"

    jwt_secret: str = "change-me-in-env"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 30

    # 모의투자 기본값 (ADR 0001에서 사용자 확인 후 확정 예정)
    default_virtual_cash_krw: int = 10_000_000
    default_base_currency: str = "KRW"

    # 시장 데이터 최신성 기준 (초). 이 시간을 넘으면 주문을 거부하거나 지연 모드로 처리한다.
    market_data_staleness_threshold_seconds: int = 900

    # 주문 후 단일 종목 비중이 이 값(%)을 초과하면 집중도 경고를 반환한다 (차단하지 않음).
    concentration_warning_threshold_pct: int = 30

    # AI 코치 (7.5-7.7). 키가 없으면 규칙 기반 graceful degradation 경로로 동작한다 (7.7).
    anthropic_api_key: str | None = None
    ai_coach_simple_model: str = "claude-haiku-4-5"
    ai_coach_complex_model: str = "claude-sonnet-5"
    ai_coach_prompt_version: str = "v1"


@lru_cache
def get_settings() -> Settings:
    return Settings()
