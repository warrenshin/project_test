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


@lru_cache
def get_settings() -> Settings:
    return Settings()
