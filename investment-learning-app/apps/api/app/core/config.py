import logging
import sys
from functools import lru_cache
from typing import Literal
from urllib.parse import urlsplit

from pydantic import model_validator
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

    # 시장 데이터 공급자 선택 (Phase A: apps/api/scripts/ingest_market_data.py가
    # 어떤 MarketDataProvider를 쓸지 결정). "stooq"는 개발·기술검증용으로만
    # 쓴다 — 상업적 표시·재배포 권한이 확인되지 않았기 때문에 아래 검증기가
    # production에서 이 값을 막는다. 선정된 상용 공급자가 생기기 전까지는
    # production에서 "demo"만 허용된다.
    market_data_provider: Literal["demo", "stooq"] = "demo"

    # 주문 후 단일 종목 비중이 이 값(%)을 초과하면 집중도 경고를 반환한다 (차단하지 않음).
    concentration_warning_threshold_pct: int = 30

    # 행동편향 탐지(7.4) 임계치. 추격매수: 매수 시점 기준 최근 며칠간 이 이상
    # 급등했는데 진입 조건 없이 매수하면 후보로 본다. 과잉매매: 이 시간(시간)
    # 이내에 이 건수 이상 주문하면 후보로 본다. 전부 "진단"이 아니라 코칭 방향을
    # 잡기 위한 관찰 임계치이며, 운영 설정으로 조정 가능하다.
    chasing_rally_lookback_days: int = 5
    chasing_rally_gain_threshold_pct: int = 8
    overtrading_window_hours: int = 24
    overtrading_order_threshold: int = 5

    # --- 6~15강 교육 콘텐츠용 "예시" 참고 수치 (실제 수수료·세율·시장운영시간이
    # 아니다) ---
    # 수수료·세금·환율(9강), 장 운영시간(6강)처럼 실제로는 증권사·상품·시점마다
    # 다르고 자주 바뀌는 값을, 강의 본문 텍스트에 하드코딩하지 않고 여기 설정으로
    # 분리해 둔다 — 값이 바뀌면 콘텐츠를 다시 쓰지 않고 이 설정만 갱신하면 된다.
    # 강의 시드 마이그레이션이 이 값을 읽어 "예시 계산" 문단에 반영한다.
    # 실제 수수료·세율이 아니라 계산 연습용 가정치라는 점을 각 강의 본문에도
    # 명시한다.
    education_example_fee_rate_pct: str = "0.015"
    education_example_domestic_tax_rate_pct: str = "0.18"
    education_example_fx_spread_pct: str = "1.0"
    # 정규장 시간(09:00~15:30 KST, 09:30~16:00 ET)은 여러 공개 자료에서 일관되게
    # 확인되는 안정적인 값이라 여기 반영한다. 다만 프리마켓·애프터마켓 등 확장
    #거래시간의 정확한 시각은 2026년 기준 제도 개편이 진행 중이라(자료마다 세부
    # 시각이 엇갈림) 여기 설정에 넣지 않고, 강의 본문에서 "공식 공지 확인 필요"로만
    # 안내한다 — 이 강의가 DRAFT/REVIEW_REQUIRED로 남아있는 이유이기도 하다.
    kr_market_regular_session: str = "09:00~15:30 (KST)"
    us_market_regular_session: str = "09:30~16:00 (ET)"

    # AI 코치 (7.5-7.7). 키가 없으면 규칙 기반 graceful degradation 경로로 동작한다 (7.7).
    anthropic_api_key: str | None = None
    ai_coach_simple_model: str = "claude-haiku-4-5"
    ai_coach_complex_model: str = "claude-sonnet-5"
    ai_coach_prompt_version: str = "v1"

    # apps/web(Next.js) 로컬 개발 서버 CORS 허용 origin (쉼표로 구분)
    cors_allowed_origins_raw: str = "http://localhost:3000,http://127.0.0.1:3000"

    # --- 인증 쿠키 정책 (HttpOnly Secure 쿠키 기반 인증, 2026-08 마이그레이션) ---
    # 쿠키 이름
    access_cookie_name: str = "ilapp_access_token"
    refresh_cookie_name: str = "ilapp_refresh_token"
    # 개발 기본값은 HTTP localhost에서 동작해야 하므로 Secure=false.
    # production에서는 반드시 true로 재정의해야 하며, 아래 검증기가 이를 강제한다.
    cookie_secure: bool = False
    cookie_samesite: Literal["lax", "strict", "none"] = "lax"
    # 하위 도메인 간 공유가 실제로 필요하지 않은 한 Domain 속성은 비워 둔다
    # (host-only 쿠키가 더 안전하고 좁은 기본값이다).
    cookie_domain: str | None = None
    # refresh 쿠키는 refresh/logout 엔드포인트에만 필요하므로 Path를 좁게 제한해
    # 다른 API 요청에는 아예 실리지 않게 한다. access 쿠키는 모든 API 호출에 필요하다.
    access_cookie_path: str = "/"
    refresh_cookie_path: str = "/v1/auth"

    # --- 로컬 스테이징 전용 예외 스위치 ---
    # environment=staging이고 이 값이 false(기본)면 COOKIE_SECURE=false를 거부한다.
    # true로 켜는 것은 "로컬 Docker Compose에서 순수 HTTP로만 테스트한다"는 의미이며,
    # 절대로 인터넷에 노출해서는 안 된다(never expose to the internet). 실제 클라우드
    # 스테이징(HTTPS로 서빙)에서는 이 값을 켜지 않고 COOKIE_SECURE=true를 써야 한다.
    staging_allow_insecure_cookie: bool = False

    @property
    def cors_allowed_origins(self) -> list[str]:
        return [o.strip() for o in self.cors_allowed_origins_raw.split(",") if o.strip()]

    @model_validator(mode="after")
    def _validate_production_security_policy(self) -> "Settings":
        """production 환경에서 안전하지 않은 기본값으로 기동되는 것을 막는다.

        HttpOnly 쿠키 인증에서 Secure 플래그 누락은 토큰이 평문 HTTP로 노출될 수
        있다는 뜻이므로, 이 조합은 조용히 경고하는 대신 앱 기동 자체를 실패시킨다.
        """
        if self.environment == "production":
            if not self.cookie_secure:
                raise ValueError(
                    "production 환경에서는 COOKIE_SECURE=true가 필수입니다 "
                    "(HttpOnly Secure 쿠키 정책 — 평문 HTTP로 인증 쿠키가 노출되는 것을 막는다)."
                )
            if self.cookie_samesite == "none" and not self.cookie_secure:
                raise ValueError("SameSite=None 쿠키는 Secure=true와 함께만 사용할 수 있습니다.")
            if self.jwt_secret == "change-me-in-env":
                raise ValueError("production 환경에서는 JWT_SECRET을 반드시 변경해야 합니다.")
            if self.market_data_provider == "stooq":
                raise ValueError(
                    "production 환경에서는 MARKET_DATA_PROVIDER=stooq를 쓸 수 없습니다 — "
                    "Stooq는 개발·기술검증용이며 상업적 표시·재배포 권한이 확인되지 않았습니다. "
                    "선정된 상용 공급자가 아직 없으므로 지금은 'demo'만 허용됩니다."
                )

        if self.environment == "staging":
            self._validate_staging_safety_policy()
        return self

    def _validate_staging_safety_policy(self) -> None:
        """로컬 스테이징이 실수로 dev DB·운영 DB에 연결되거나, 예시 비밀값을
        그대로 쓴 채 기동되는 것을 막는다. 여기서 raise하면 앱이 기동되기
        전에(Settings() 생성 시점) 즉시 실패한다 — docker_entrypoint.sh가
        uvicorn을 exec하기 전 단계이므로, 헬스체크가 절대 healthy가 되지 않는다.
        """
        host = urlsplit(self.database_url).hostname or ""

        if host != "staging-postgres":
            raise ValueError(
                "staging 환경에서는 DATABASE_URL의 호스트가 반드시 'staging-postgres'여야 "
                f"합니다(현재: {host!r}). dev DB('postgres')나 운영 DB를 그대로 재사용하는 것을 "
                "막기 위한 안전장치입니다 — docker-compose.staging.yml의 네트워크 별칭을 "
                "확인하세요."
            )

        lowered_db_url = self.database_url.lower()
        if "prod" in lowered_db_url:
            raise ValueError(
                "staging 환경의 DATABASE_URL에 'prod'로 보이는 문자열이 포함되어 있습니다 — "
                "운영 DB에 잘못 연결하는 것을 막기 위해 기동을 거부합니다."
            )

        placeholder_secrets = ("change-me-in-env",)
        if self.jwt_secret in placeholder_secrets or "change-me" in self.jwt_secret.lower():
            raise ValueError(
                "staging 환경에서도 JWT_SECRET에 예시 기본값을 그대로 쓸 수 없습니다 — "
                ".env.staging에서 무작위 값으로 교체하세요(예: openssl rand -hex 32)."
            )
        if len(self.jwt_secret) < 16:
            raise ValueError("staging 환경의 JWT_SECRET이 너무 짧습니다(16자 이상 필요).")

        if not self.cookie_secure and not self.staging_allow_insecure_cookie:
            raise ValueError(
                "staging 환경에서 COOKIE_SECURE=false를 쓰려면 STAGING_ALLOW_INSECURE_COOKIE=true를 "
                "함께 설정해야 합니다. 이는 '로컬 Docker Compose에서 순수 HTTP로만 테스트한다'는 "
                "의도적 예외이며 절대 인터넷에 노출하면 안 됩니다 — 실제 HTTPS로 서빙되는 클라우드 "
                "스테이징에서는 COOKIE_SECURE=true를 쓰세요."
            )
        if not self.cookie_secure and self.staging_allow_insecure_cookie:
            logging.getLogger(__name__).warning(
                "[staging] COOKIE_SECURE=false로 기동합니다 — 이는 로컬 전용 예외입니다. "
                "이 인스턴스를 절대 인터넷에 노출하지 마세요(never expose to the internet)."
            )
            print(
                "[staging] 경고: COOKIE_SECURE=false(로컬 전용) — 절대 인터넷에 노출하지 마세요.",
                file=sys.stderr,
            )

        if not self.cors_allowed_origins:
            raise ValueError("staging 환경에서는 CORS_ALLOWED_ORIGINS_RAW가 비어 있을 수 없습니다.")
        for origin in self.cors_allowed_origins:
            origin_host = urlsplit(origin).hostname or ""
            if origin_host not in ("localhost", "127.0.0.1"):
                raise ValueError(
                    f"staging(로컬) 환경의 CORS_ALLOWED_ORIGINS_RAW에 loopback이 아닌 origin이 "
                    f"있습니다: {origin!r} — 로컬 스테이징은 localhost/127.0.0.1에서만 접근 가능해야 "
                    "합니다(외부 노출 금지)."
                )


@lru_cache
def get_settings() -> Settings:
    return Settings()
