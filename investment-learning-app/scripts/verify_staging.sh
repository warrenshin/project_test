#!/bin/bash
# 로컬 스테이징 스택이 기동된 뒤, 요구된 항목들을 자동으로 확인한다.
# scripts/staging_up.sh로 스택을 먼저 띄운 뒤 실행해야 한다.
#
# 확인 항목(요구사항 8번):
#  1. dev Compose와 project name/volume이 다름
#  2. web/API 헬스 200
#  3. API readiness 200
#  4. DB migration이 head와 일치
#  5. 데모 종목 존재
#  6. lesson-01~05 공개(PUBLISHED) 상태
#  7. lesson-06~15는 READY_FOR_REVIEW/REVIEW_REQUIRED(게시 전) 상태
#  8. lesson-06~15가 일반 사용자 API로 노출되지 않음
#  9. 헬스 응답/로그에 비밀정보 노출 없음
# 10. 스테이징 재시작 후에도 데이터 유지
# 11. backup + 임시 DB로의 restore 성공

set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
source scripts/_staging_lib.sh
set -e

API_BASE="http://127.0.0.1:${STAGING_API_PORT:-8001}"
WEB_BASE="http://127.0.0.1:${STAGING_WEB_PORT:-3001}"

FAILURES=0
pass() { echo "  [PASS] $1"; }
fail() { echo "  [FAIL] $1"; FAILURES=$((FAILURES + 1)); }

run_sql() {
    staging_compose exec -T postgres \
        psql -U "${POSTGRES_USER_VALUE}" -d "${POSTGRES_DB_VALUE}" -tAc "$1"
}

POSTGRES_USER_VALUE="$(grep -E '^POSTGRES_USER=' "$STAGING_ENV_FILE" | tail -n1 | cut -d= -f2-)"
POSTGRES_DB_VALUE="$(grep -E '^POSTGRES_DB=' "$STAGING_ENV_FILE" | tail -n1 | cut -d= -f2-)"
POSTGRES_USER_VALUE="${POSTGRES_USER_VALUE:-staging_app}"
POSTGRES_DB_VALUE="${POSTGRES_DB_VALUE:-investment_learning_staging}"

echo "=== 1. dev Compose와 project name/volume 분리 확인 ==="
if docker volume ls --format '{{.Name}}' | grep -qx "investment-learning-staging_postgres_data"; then
    pass "staging 전용 볼륨(investment-learning-staging_postgres_data) 존재"
else
    fail "staging 전용 볼륨을 찾을 수 없음"
fi
if docker volume ls --format '{{.Name}}' | grep -qx "postgres_data"; then
    echo "  [정보] dev 볼륨(postgres_data)도 함께 존재 — 정상(서로 다른 이름이므로 충돌 없음)"
fi
if [ "$(staging_compose ps --format '{{.Name}}' 2>/dev/null | grep -c "^investment-learning-staging-")" -ge 1 ] \
    || staging_compose ps --format '{{.Name}}' 2>/dev/null | grep -q "investment-learning-staging"; then
    pass "staging project name으로 컨테이너가 기동됨"
else
    fail "staging project name 컨테이너를 확인할 수 없음"
fi

echo "=== 2. web/API 헬스 200 ==="
API_LIVE_CODE="$(curl -s -o /tmp/staging_health_live.json -w '%{http_code}' "$API_BASE/health/live" || echo "000")"
[ "$API_LIVE_CODE" = "200" ] && pass "API /health/live -> 200" || fail "API /health/live -> $API_LIVE_CODE"

WEB_CODE="$(curl -s -o /dev/null -w '%{http_code}' "$WEB_BASE/" || echo "000")"
[ "$WEB_CODE" = "200" ] && pass "web / -> 200" || fail "web / -> $WEB_CODE"

echo "=== 3. API readiness 200 ==="
READY_CODE="$(curl -s -o /tmp/staging_health_ready.json -w '%{http_code}' "$API_BASE/health/ready" || echo "000")"
[ "$READY_CODE" = "200" ] && pass "API /health/ready -> 200" || fail "API /health/ready -> $READY_CODE"

echo "=== 4. DB migration이 head와 일치 ==="
DB_REV="$(run_sql 'SELECT version_num FROM alembic_version;' | tr -d '[:space:]')"
HEAD_REV="$(staging_compose exec -T api alembic heads 2>/dev/null | awk '{print $1}' | tr -d '[:space:]')"
if [ -n "$DB_REV" ] && [ -n "$HEAD_REV" ] && [ "$DB_REV" = "$HEAD_REV" ]; then
    pass "DB revision($DB_REV) == alembic head($HEAD_REV)"
else
    fail "DB revision($DB_REV) != alembic head($HEAD_REV)"
fi

echo "=== 5. 데모 종목 존재 ==="
INSTRUMENT_COUNT="$(run_sql 'SELECT count(*) FROM instruments;' | tr -d '[:space:]')"
[ "${INSTRUMENT_COUNT:-0}" -gt 0 ] 2>/dev/null && pass "instruments 존재 (count=$INSTRUMENT_COUNT)" || fail "instruments가 비어 있음"

echo "=== 6. lesson-01~05(code가 없는 초기 강의)는 PUBLISHED로 공개 ==="
LEGACY_PUBLISHED_COUNT="$(run_sql "SELECT count(*) FROM lessons WHERE code IS NULL AND status = 'PUBLISHED';" | tr -d '[:space:]')"
[ "${LEGACY_PUBLISHED_COUNT:-0}" -ge 5 ] 2>/dev/null \
    && pass "code 없는(1~5강 등) PUBLISHED 강의 $LEGACY_PUBLISHED_COUNT건" \
    || fail "code 없는 PUBLISHED 강의가 5건 미만(count=$LEGACY_PUBLISHED_COUNT)"

echo "=== 7. lesson-06~15는 게시 전 상태(READY_FOR_REVIEW/REVIEW_REQUIRED) ==="
PRE_PUBLISH_COUNT="$(run_sql "SELECT count(*) FROM lessons WHERE code ~ '^lesson-(0[6-9]|1[0-5])\$' AND status = 'READY_FOR_REVIEW' AND review_status = 'REVIEW_REQUIRED';" | tr -d '[:space:]')"
[ "${PRE_PUBLISH_COUNT:-0}" -eq 10 ] 2>/dev/null \
    && pass "lesson-06~15 전부(10건) 게시 전 상태" \
    || fail "lesson-06~15 게시 전 상태 건수가 10이 아님(count=$PRE_PUBLISH_COUNT) — 이미 게시가 진행됐을 수 있음"

echo "=== 8. lesson-06~15가 일반 사용자 API로 노출되지 않음 ==="
PATHS_BODY="$(curl -s "$API_BASE/v1/learning/paths" || true)"
if echo "$PATHS_BODY" | grep -Eq 'lesson-(0[6-9]|1[0-5])'; then
    fail "일반 사용자 API 응답에 lesson-06~15 코드가 노출됨"
else
    pass "일반 사용자 API 응답에 lesson-06~15 코드 없음"
fi

echo "=== 9. 헬스 응답/로그에 비밀정보 노출 없음 ==="
SECRET_PATTERNS=("JWT_SECRET" "POSTGRES_PASSWORD" "staging_app_local_only" "ANTHROPIC_API_KEY")
LEAK_FOUND=0
for f in /tmp/staging_health_live.json /tmp/staging_health_ready.json; do
    for pat in "${SECRET_PATTERNS[@]}"; do
        if grep -qi "$pat" "$f" 2>/dev/null; then
            LEAK_FOUND=1
        fi
    done
done
if [ "$LEAK_FOUND" -eq 0 ]; then
    pass "헬스 응답 본문에 알려진 비밀 패턴 없음"
else
    fail "헬스 응답 본문에 비밀로 의심되는 패턴이 발견됨(내용은 로그에 출력하지 않음)"
fi
LOG_SNAPSHOT="$(staging_compose logs --no-color api 2>/dev/null | tail -n 500 || true)"
LOG_LEAK=0
for pat in "${SECRET_PATTERNS[@]}"; do
    if echo "$LOG_SNAPSHOT" | grep -qi "$pat"; then
        LOG_LEAK=1
    fi
done
if [ "$LOG_LEAK" -eq 0 ]; then
    pass "api 컨테이너 로그(최근 500줄)에 알려진 비밀 패턴 없음"
else
    fail "api 컨테이너 로그에 비밀로 의심되는 패턴이 발견됨(내용은 로그에 출력하지 않음)"
fi

echo "=== 10. 스테이징 재시작 후 데이터 유지 ==="
BEFORE_COUNT="$(run_sql 'SELECT count(*) FROM instruments;' | tr -d '[:space:]')"
staging_compose restart postgres api >/dev/null
for _ in $(seq 1 60); do
    RC="$(curl -s -o /dev/null -w '%{http_code}' "$API_BASE/health/ready" || echo "000")"
    [ "$RC" = "200" ] && break
    sleep 2
done
AFTER_COUNT="$(run_sql 'SELECT count(*) FROM instruments;' | tr -d '[:space:]')"
if [ "$BEFORE_COUNT" = "$AFTER_COUNT" ] && [ "${AFTER_COUNT:-0}" -gt 0 ] 2>/dev/null; then
    pass "재시작 전후 instruments count 동일 유지($BEFORE_COUNT)"
else
    fail "재시작 전후 데이터 불일치(before=$BEFORE_COUNT, after=$AFTER_COUNT)"
fi

echo "=== 11. backup + 임시 DB로의 restore 성공 ==="
if scripts/staging_backup.sh; then
    LATEST_BACKUP="$(ls -1t backups/staging_*.dump 2>/dev/null | head -n1 || true)"
    if [ -n "$LATEST_BACKUP" ] && scripts/staging_restore_test.sh "$LATEST_BACKUP"; then
        pass "backup + restore-to-temp-DB 성공 ($LATEST_BACKUP)"
    else
        fail "restore-to-temp-DB 실패"
    fi
else
    fail "backup 실패"
fi

echo ""
echo "=== 요약 ==="
if [ "$FAILURES" -eq 0 ]; then
    echo "모든 검증 통과."
    exit 0
else
    echo "$FAILURES 건 실패."
    exit 1
fi
