#!/usr/bin/env bash
# CI 전용 임시 .env를 현재 디렉터리에 생성한다. 실제 운영 비밀값은 전혀
# 쓰지 않는다 — JWT_SECRET은 이 실행에서만 쓰는 무작위 값이고, 나머지는
# 로컬/CI 전용으로 안전한 예시값(apps/api/.env.example, 루트 .env.example과
# 동일한 개발 기본값)이다. GitHub repository secret이 하나도 없어도 동작한다.
#
# JWT_SECRET과 POSTGRES_PASSWORD는 GitHub Actions 로그 마스킹(::add-mask::)에
# 등록한다 — 이후 `docker compose config` 등에서 값이 노출되더라도 로그에는
# ***로 대체된다. 이 .env 파일은 job이 끝나면 runner와 함께 사라지며,
# 어떤 워크플로 단계에서도 artifact로 업로드하지 않는다.
set -euo pipefail

JWT_SECRET_VALUE="$(openssl rand -hex 32)"
POSTGRES_PASSWORD_VALUE="ci-$(openssl rand -hex 8)"

echo "::add-mask::${JWT_SECRET_VALUE}"
echo "::add-mask::${POSTGRES_PASSWORD_VALUE}"

cat >.env <<EOF
ENVIRONMENT=development

POSTGRES_USER=app
POSTGRES_PASSWORD=${POSTGRES_PASSWORD_VALUE}
POSTGRES_DB=investment_learning
POSTGRES_PORT=5432

DATABASE_URL=postgresql+psycopg://app:${POSTGRES_PASSWORD_VALUE}@postgres:5432/investment_learning
REDIS_URL=redis://redis:6379/0
API_PORT=8000

JWT_SECRET=${JWT_SECRET_VALUE}
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=30

ACCESS_COOKIE_NAME=ilapp_access_token
REFRESH_COOKIE_NAME=ilapp_refresh_token
# CI 러너는 HTTP(localhost)로만 접근하므로 false — production 기본값이 아니다.
COOKIE_SECURE=false
COOKIE_SAMESITE=lax
ACCESS_COOKIE_PATH=/
REFRESH_COOKIE_PATH=/v1/auth

# CI에서 실제로 쓰는 localhost origin만 명시 — 와일드카드 없음.
CORS_ALLOWED_ORIGINS_RAW=http://localhost:3000,http://127.0.0.1:3000

DEFAULT_VIRTUAL_CASH_KRW=10000000
DEFAULT_BASE_CURRENCY=KRW
MARKET_DATA_STALENESS_THRESHOLD_SECONDS=900
CONCENTRATION_WARNING_THRESHOLD_PCT=30

# 비워둠 — 규칙 기반 AI 코칭 폴백 경로로 동작한다. 실제 LLM 연동은 이번
# 검증 범위 밖이다.
ANTHROPIC_API_KEY=
AI_COACH_SIMPLE_MODEL=claude-haiku-4-5
AI_COACH_COMPLEX_MODEL=claude-sonnet-5
AI_COACH_PROMPT_VERSION=v1

WEB_PORT=3000
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
EOF

echo "CI 전용 .env 생성 완료 (값은 로그에 출력하지 않음)"
