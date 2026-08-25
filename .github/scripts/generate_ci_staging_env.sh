#!/usr/bin/env bash
# CI 전용 임시 .env.staging을 현재 디렉터리(investment-learning-app/)에
# 생성한다. generate_ci_env.sh(dev CI용)와 동일한 원칙 — 실제 비밀값은 전혀
# 쓰지 않고, JWT_SECRET·POSTGRES_PASSWORD는 이 실행에서만 쓰는 무작위 값이며
# GitHub Actions 로그 마스킹(::add-mask::)에 등록한다. 이 파일은 job이
# 끝나면 러너와 함께 사라지고, artifact로 업로드하지 않는다.
#
# dev CI용 .env와의 차이: ENVIRONMENT=staging이고 DATABASE_URL 호스트가
# staging-postgres다(docker-compose.staging.yml의 네트워크 별칭). 이 CI
# 인스턴스는 실제 클라우드 스테이징처럼 COOKIE_SECURE=true로 검증한다
# (로컬 개발자용 .env.staging.example의 COOKIE_SECURE=false 예외는 순수
# 로컬 HTTP 전용이라 여기서는 켜지 않는다 — README의 구분 참고).
set -euo pipefail

JWT_SECRET_VALUE="$(openssl rand -hex 32)"
POSTGRES_PASSWORD_VALUE="ci-staging-$(openssl rand -hex 8)"

echo "::add-mask::${JWT_SECRET_VALUE}"
echo "::add-mask::${POSTGRES_PASSWORD_VALUE}"

cat >.env.staging <<EOF
ENVIRONMENT=staging

POSTGRES_USER=staging_app
POSTGRES_PASSWORD=${POSTGRES_PASSWORD_VALUE}
POSTGRES_DB=investment_learning_staging

DATABASE_URL=postgresql+psycopg://staging_app:${POSTGRES_PASSWORD_VALUE}@staging-postgres:5432/investment_learning_staging
REDIS_URL=redis://staging-redis:6379/0

STAGING_API_PORT=8001
STAGING_WEB_PORT=3001

JWT_SECRET=${JWT_SECRET_VALUE}
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=14
ACCESS_COOKIE_NAME=access_token
REFRESH_COOKIE_NAME=refresh_token

# CI에서는 실제 클라우드 스테이징과 같은 경로(Secure=true)를 검증한다.
COOKIE_SECURE=true
STAGING_ALLOW_INSECURE_COOKIE=false
COOKIE_SAMESITE=lax

CORS_ALLOWED_ORIGINS_RAW=http://localhost:3001,http://127.0.0.1:3001

NEXT_PUBLIC_API_BASE_URL=http://localhost:8001

DEFAULT_VIRTUAL_CASH_KRW=10000000
DEFAULT_BASE_CURRENCY=KRW
MARKET_DATA_STALENESS_THRESHOLD_SECONDS=86400
MARKET_DATA_PROVIDER=demo
CONCENTRATION_WARNING_THRESHOLD_PCT=30

ANTHROPIC_API_KEY=
AI_COACH_SIMPLE_MODEL=claude-haiku-4-5
AI_COACH_COMPLEX_MODEL=claude-sonnet-5
AI_COACH_PROMPT_VERSION=v1
EOF

echo "CI 전용 .env.staging 생성 완료 (값은 로그에 출력하지 않음)"
