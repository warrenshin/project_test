#!/bin/bash
# 이미 떠 있는 로컬 스테이징(scripts/staging_up.sh로 기동한 스택)을 대상으로
# apps/web/e2e-staging/의 스테이징 전용 Playwright E2E를 실행하는 래퍼.
#
# 이 스크립트가 하는 일:
#  1) staging 컨테이너 4개가 모두 healthy인지 확인한다(재시작/재빌드하지 않음 —
#     healthy가 아니면 사람이 먼저 scripts/staging_up.sh를 실행하도록 안내하고 중단).
#  2) lesson-06~15의 status/review_status와 lesson_review_audits(06~15) 건수를
#     Playwright 실행 "직전"에 스냅샷한다(읽기 전용 SELECT만 사용 — INSERT/UPDATE/
#     DELETE 없음).
#  3) apps/web에서 스테이징 전용 설정(playwright.staging.config.ts)으로 Playwright를
#     실행한다. 기존 playwright.config.ts(개발 DB + 자체 webServer)는 전혀 건드리지
#     않는다 — 이 스크립트는 항상 -c playwright.staging.config.ts만 사용한다.
#  4) 실행 "직후" 같은 값을 다시 조회해 1)과 완전히 동일한지 대조한다. 하나라도
#     다르면(즉 E2E가 게시 상태나 감사기록을 건드렸다면) 실패로 처리한다 — Playwright
#     자체가 성공해도 이 대조에서 실패하면 스크립트는 0이 아닌 코드로 종료한다.
#
# 이 스크립트는 절대로 하지 않는 것: 컨테이너 재빌드/재시작, 개발 DB(5432) 기동,
# staging_reset_data.sh/docker compose down -v 호출, DB에 대한 쓰기 쿼리.

set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
source scripts/_staging_lib.sh

require_staging_env_file

POSTGRES_USER_VALUE="$(grep -E '^POSTGRES_USER=' "$STAGING_ENV_FILE" | tail -n1 | cut -d= -f2-)"
POSTGRES_DB_VALUE="$(grep -E '^POSTGRES_DB=' "$STAGING_ENV_FILE" | tail -n1 | cut -d= -f2-)"
POSTGRES_USER_VALUE="${POSTGRES_USER_VALUE:-staging_app}"
POSTGRES_DB_VALUE="${POSTGRES_DB_VALUE:-investment_learning_staging}"

run_sql() {
    staging_compose exec -T postgres psql -U "$POSTGRES_USER_VALUE" -d "$POSTGRES_DB_VALUE" -tAc "$1"
}

echo "[staging_e2e_run] staging 컨테이너 4개가 모두 healthy인지 확인 중(재시작하지 않음)..."
for svc in postgres redis api web; do
    STATUS="$(staging_compose ps --format '{{.Health}}' "$svc" 2>/dev/null || true)"
    if [ "$STATUS" != "healthy" ]; then
        echo "[오류] $svc 컨테이너가 healthy 상태가 아닙니다(status='${STATUS}')." >&2
        echo "       먼저 scripts/staging_up.sh로 로컬 스테이징을 기동하세요." >&2
        exit 1
    fi
done
echo "[staging_e2e_run] 컨테이너 상태 확인됨: postgres/redis/api/web 전부 healthy"

echo "[staging_e2e_run] 게시 상태/감사기록 사전 스냅샷 조회 중(읽기 전용)..."
BEFORE_LESSON_STATE="$(run_sql "SELECT code, status, review_status FROM lessons WHERE code ~ '^lesson-(0[6-9]|1[0-5])\$' ORDER BY code;")"
BEFORE_AUDIT_COUNT="$(run_sql "SELECT count(*) FROM lesson_review_audits WHERE lesson_code ~ '^lesson-(0[6-9]|1[0-5])\$';")"

echo "[staging_e2e_run] apps/web에서 스테이징 전용 Playwright 실행 중..."
export STAGING_WEB_BASE_URL="${STAGING_WEB_BASE_URL:-http://localhost:${STAGING_WEB_PORT:-3001}}"
export STAGING_API_BASE_URL="${STAGING_API_BASE_URL:-http://localhost:${STAGING_API_PORT:-8001}}"

set +e
(cd apps/web && npx playwright test -c playwright.staging.config.ts "$@")
TEST_EXIT=$?
set -e

echo "[staging_e2e_run] 게시 상태/감사기록 사후 스냅샷 조회 중(읽기 전용)..."
AFTER_LESSON_STATE="$(run_sql "SELECT code, status, review_status FROM lessons WHERE code ~ '^lesson-(0[6-9]|1[0-5])\$' ORDER BY code;")"
AFTER_AUDIT_COUNT="$(run_sql "SELECT count(*) FROM lesson_review_audits WHERE lesson_code ~ '^lesson-(0[6-9]|1[0-5])\$';")"

INTEGRITY_OK=1
if [ "$BEFORE_LESSON_STATE" != "$AFTER_LESSON_STATE" ]; then
    echo "[오류] E2E 실행 전후 lesson-06~15의 status/review_status가 달라졌습니다." >&2
    INTEGRITY_OK=0
fi
if [ "$BEFORE_AUDIT_COUNT" != "$AFTER_AUDIT_COUNT" ]; then
    echo "[오류] E2E 실행 전후 lesson_review_audits(06~15) 건수가 달라졌습니다(before=${BEFORE_AUDIT_COUNT}, after=${AFTER_AUDIT_COUNT})." >&2
    INTEGRITY_OK=0
fi

if [ "$INTEGRITY_OK" -eq 1 ]; then
    echo "[staging_e2e_run] 게시 상태/감사기록 무결성 확인됨 — E2E 실행 전후 완전히 동일합니다(audits=${AFTER_AUDIT_COUNT}건)."
else
    echo "[staging_e2e_run] 게시 상태 무결성 위반 — 아래에서 실패로 처리합니다." >&2
fi

if [ "$TEST_EXIT" -ne 0 ]; then
    echo "[staging_e2e_run] Playwright 실행이 실패했습니다(exit=${TEST_EXIT})." >&2
fi

if [ "$TEST_EXIT" -ne 0 ] || [ "$INTEGRITY_OK" -ne 1 ]; then
    exit 1
fi

echo "[staging_e2e_run] 완료: Playwright 통과 + 게시 상태/감사기록 불변 확인됨."
