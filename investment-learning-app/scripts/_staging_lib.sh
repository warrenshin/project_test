#!/bin/bash
# 스테이징 스크립트 공통 헬퍼. 다른 scripts/staging_*.sh가 source해서 쓴다.
# 단독 실행 대상이 아니다.

set -euo pipefail

STAGING_PROJECT_NAME="investment-learning-staging"
STAGING_ENV_FILE=".env.staging"
STAGING_COMPOSE_ARGS=(--project-name "$STAGING_PROJECT_NAME" --env-file "$STAGING_ENV_FILE" -f docker-compose.yml -f docker-compose.staging.yml)

# 이 함수들은 반드시 investment-learning-app/ 디렉터리(docker-compose.yml이
# 있는 위치)에서 실행돼야 한다 — 모든 staging_*.sh는 스크립트 자신의 위치를
# 기준으로 cd한 뒤 여기 함수들을 부른다.

staging_compose() {
    docker compose "${STAGING_COMPOSE_ARGS[@]}" "$@"
}

# .env.staging이 없거나, 예시 플레이스홀더를 그대로 쓰고 있으면 조기에
# 사람이 읽을 수 있는 오류로 중단한다(컨테이너가 크래시루프하기 전에 미리
# 잡아준다 — app/core/config.py의 검증기가 최종 방어선이고 이건 그 앞단의
# 사용성 개선용 사전 점검이다).
require_staging_env_file() {
    if [ ! -f "$STAGING_ENV_FILE" ]; then
        echo "[오류] $STAGING_ENV_FILE 이 없습니다. 먼저 실행하세요:" >&2
        echo "  cp .env.staging.example .env.staging" >&2
        echo "  그리고 JWT_SECRET을 무작위 값으로 교체하세요 (예: openssl rand -hex 32)" >&2
        exit 1
    fi
    if grep -v '^\s*#' "$STAGING_ENV_FILE" | grep -q "change-me"; then
        echo "[오류] $STAGING_ENV_FILE 에 예시 플레이스홀더(\"change-me\" 포함 값)가 남아있습니다." >&2
        echo "       JWT_SECRET 등 SECRET 표시된 값을 실제 무작위 값으로 교체한 뒤 다시 실행하세요." >&2
        exit 1
    fi
    if grep -qi "^ENVIRONMENT=" "$STAGING_ENV_FILE" && ! grep -qi "^ENVIRONMENT=staging" "$STAGING_ENV_FILE"; then
        echo "[오류] $STAGING_ENV_FILE 의 ENVIRONMENT가 staging이 아닙니다 — 잘못된 env 파일일 수 있습니다." >&2
        exit 1
    fi
}

# database_url 값에서 호스트가 정말 staging-postgres인지, 'prod'로 보이는
# 문자열이 없는지 이 스크립트 레벨에서도 다시 확인한다(운영 안전장치는
# app/core/config.py가 최종 강제하지만, 게시/백업처럼 파괴적일 수 있는
# 스크립트는 여기서도 한 번 더 확인해 조기에 중단한다).
assert_staging_database_url_is_safe() {
    local url
    url=$(grep -E "^DATABASE_URL=" "$STAGING_ENV_FILE" | tail -n1 | cut -d= -f2-)
    if [ -z "$url" ]; then
        echo "[오류] $STAGING_ENV_FILE 에 DATABASE_URL이 없습니다." >&2
        exit 1
    fi
    case "$url" in
        *@staging-postgres:*) ;;
        *)
            echo "[오류] DATABASE_URL 호스트가 staging-postgres가 아닙니다 — dev/운영 DB로 잘못" >&2
            echo "       연결하는 것을 막기 위해 중단합니다: $url" >&2
            exit 1
            ;;
    esac
    if echo "$url" | grep -qi "prod"; then
        echo "[오류] DATABASE_URL에 'prod'로 보이는 문자열이 포함돼 있습니다 — 운영 DB로 오인해" >&2
        echo "       중단합니다." >&2
        exit 1
    fi
}

utc_timestamp() {
    date -u +"%Y%m%dT%H%M%SZ"
}
