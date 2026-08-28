#!/bin/bash
# lesson-06~15를 로컬 스테이징에서 승인·게시하는 운영자 전용 래퍼.
#
# *** 이 스크립트는 사람 운영자가 실제 검수를 마친 뒤 터미널에서 직접
# 실행해야 한다 — apps/api/scripts/publish_lesson.py와 동일한 원칙(작성과
# 승인의 분리)이 이 래퍼에도 그대로 적용된다. 에이전트가 이 스크립트를
# 스스로 --execute로 실행해서는 안 된다. ***
#
# 이번 작업 지시( chore/local-staging-environment )에서는 이 스크립트를
# "만들기만" 하고 --execute로 실제 게시하지 않는다. --execute 없이 실행하면
# 사전 점검(아래 1~4단계)까지만 수행하고 아무것도 바꾸지 않은 채 종료한다
# (구조적 테스트 목적).
#
# 안전장치:
#  1) .env.staging의 ENVIRONMENT가 staging인지 확인
#  2) DATABASE_URL 호스트가 staging-postgres인지 확인, 운영처럼 보이면 중단
#  3) 실행 직전 백업이 존재하는지(기본: 24시간 이내) 확인
#  4) lesson-06~15의 현재 content_version/status를 조회해 출력
#  5) --execute가 있을 때만: 강의를 하나씩 승인 — lesson-12는 반드시
#     --source-verified false, 나머지는 --source-verified true로 호출한다.
#     단, 실제 lesson.source_url 유무와 이 값이 모순되면(publish_lesson.py
#     자체 규칙 위반) 그 즉시 전체 시퀀스를 중단한다 — 이후 강의는 전혀
#     건드리지 않는다.
#  6) 실행 후 상태·감사기록을 다시 조회해 출력
#  7) 동일 명령 재실행 시 멱등(이미 승인된 강의는 건너뜀 — publish_lesson.py
#     자체가 멱등하므로 그 결과를 그대로 보여준다)

set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
source scripts/_staging_lib.sh

CI_FIXTURE_REVIEWER="ci-human-review-fixture"
CI_FIXTURE_NOTE="CI 전용 fixture 게시 — 실제 사람 검수 아님 (.github/workflows/investment-learning-staging-published-lessons-e2e.yml)"

EXECUTE=0
REVIEWER=""
CI_FIXTURE=0
for arg in "$@"; do
    case "$arg" in
        --execute) EXECUTE=1 ;;
        --reviewer=*) REVIEWER="${arg#--reviewer=}" ;;
        --ci-fixture) CI_FIXTURE=1 ;;
        *)
            echo "[오류] 알 수 없는 인자: $arg" >&2
            exit 1
            ;;
    esac
done

# --ci-fixture는 GitHub Actions 워크플로 전용이다 — 사람 운영자가 로컬에서
# 실제 게시를 대신 승인하는 우회로가 되지 않도록 두 겹으로 막는다: (1) CI=true
# (GitHub Actions가 자동으로 설정) 환경이 아니면 아예 거부, (2) --ci-fixture
# 없이 --reviewer=ci-human-review-fixture를 직접 넘기는 것도 거부해, 이
# "fixture" reviewer 이름을 흉내 낸 값이 --ci-fixture 경로를 거치지 않고는
# 절대 감사기록에 남지 않게 한다.
if [ "$CI_FIXTURE" -eq 1 ]; then
    if [ -n "$REVIEWER" ]; then
        echo "[오류] --ci-fixture와 --reviewer=를 함께 지정할 수 없습니다 — --ci-fixture는" >&2
        echo "       reviewer/note 값을 스스로 고정합니다." >&2
        exit 1
    fi
    if [ "${CI:-}" != "true" ]; then
        echo "[오류] --ci-fixture는 CI 환경(CI=true)에서만 허용됩니다 — 로컬에서 실제 게시를" >&2
        echo "       대신하는 용도로 쓰면 안 됩니다. 사람 검수자는 --reviewer=\"<실명>\"을 쓰세요." >&2
        exit 1
    fi
    REVIEWER="$CI_FIXTURE_REVIEWER"
elif [ "$REVIEWER" = "$CI_FIXTURE_REVIEWER" ]; then
    echo "[오류] --reviewer=\"$CI_FIXTURE_REVIEWER\"는 예약된 CI 전용 fixture 이름입니다 —" >&2
    echo "       --ci-fixture 플래그(그리고 CI=true 환경)를 통해서만 쓸 수 있습니다." >&2
    exit 1
fi

require_staging_env_file
assert_staging_database_url_is_safe

# 1) ENVIRONMENT 확인 (require_staging_env_file이 이미 확인하지만, 게시처럼
#    되돌리기 어려운 작업이므로 한 번 더 명시적으로 확인한다)
if ! grep -qi "^ENVIRONMENT=staging" "$STAGING_ENV_FILE"; then
    echo "[오류] .env.staging의 ENVIRONMENT가 staging이 아닙니다 — 중단합니다." >&2
    exit 1
fi
echo "[1/7] ENVIRONMENT=staging 확인됨"

# 2) DB 호스트 확인은 assert_staging_database_url_is_safe에서 이미 수행됨
echo "[2/7] DATABASE_URL이 staging-postgres를 가리키는지 확인됨(운영 의심 문자열 없음)"

# 3) 최근 백업 존재 확인
BACKUP_DIR="${STAGING_BACKUP_DIR:-backups}"
MAX_BACKUP_AGE_SECONDS="${STAGING_PUBLISH_MAX_BACKUP_AGE_SECONDS:-86400}"
LATEST_BACKUP="$(ls -1t "$BACKUP_DIR"/staging_*.dump 2>/dev/null | head -n1 || true)"
if [ -z "$LATEST_BACKUP" ]; then
    echo "[오류] 게시 전 백업이 없습니다. 먼저 scripts/staging_backup.sh를 실행하세요." >&2
    exit 1
fi
BACKUP_MTIME="$(date -r "$LATEST_BACKUP" +%s 2>/dev/null || echo 0)"
NOW="$(date +%s)"
BACKUP_AGE=$((NOW - BACKUP_MTIME))
if [ "$BACKUP_AGE" -gt "$MAX_BACKUP_AGE_SECONDS" ]; then
    echo "[오류] 가장 최근 백업($LATEST_BACKUP)이 너무 오래됐습니다(${BACKUP_AGE}초 전). " >&2
    echo "       scripts/staging_backup.sh를 다시 실행한 뒤 진행하세요." >&2
    exit 1
fi
echo "[3/7] 최근 백업 확인됨: $LATEST_BACKUP (${BACKUP_AGE}초 전)"

# 4) 현재 상태 조회
POSTGRES_USER_VALUE="$(grep -E '^POSTGRES_USER=' "$STAGING_ENV_FILE" | tail -n1 | cut -d= -f2-)" || true
POSTGRES_DB_VALUE="$(grep -E '^POSTGRES_DB=' "$STAGING_ENV_FILE" | tail -n1 | cut -d= -f2-)" || true
POSTGRES_USER_VALUE="${POSTGRES_USER_VALUE:-staging_app}"
POSTGRES_DB_VALUE="${POSTGRES_DB_VALUE:-investment_learning_staging}"

run_sql() {
    staging_compose exec -T postgres \
        psql -U "$POSTGRES_USER_VALUE" -d "$POSTGRES_DB_VALUE" -tAc "$1"
}

echo "[4/7] lesson-06~15 현재 상태:"
run_sql "SELECT code, content_version, status, review_status, (source_url IS NOT NULL) AS has_source_url FROM lessons WHERE code ~ '^lesson-(0[6-9]|1[0-5])\$' ORDER BY code;"

LESSON_CODES=$(seq -w 6 15 | sed 's/^/lesson-/')

if [ "$EXECUTE" -ne 1 ]; then
    echo ""
    echo "[dry-run] --execute를 넘기지 않아 실제 게시는 수행하지 않았습니다."
    echo "[dry-run] 실제 실행하려면 사람 운영자가 검수를 마친 뒤 다음과 같이 실행하세요:"
    echo "  scripts/publish_reviewed_lessons_staging.sh --execute --reviewer=\"<이름>\""
    echo "[dry-run] (CI 전용 fixture 게시는 --execute --ci-fixture — CI=true 환경에서만 허용됨)"
    exit 0
fi

if [ "$CI_FIXTURE" -ne 1 ] && [ -z "$REVIEWER" ]; then
    echo "[오류] --execute와 함께 --reviewer=\"<이름>\"을 반드시 지정해야 합니다." >&2
    exit 1
fi

PUBLISH_NOTE="로컬 스테이징 게시 절차(scripts/publish_reviewed_lessons_staging.sh)를 통한 승인"
if [ "$CI_FIXTURE" -eq 1 ]; then
    PUBLISH_NOTE="$CI_FIXTURE_NOTE"
fi

echo "[5/7] 강의를 하나씩 승인합니다 (lesson-12만 source-verified=false)..."
for CODE in $LESSON_CODES; do
    ROW="$(run_sql "SELECT content_version, (source_url IS NOT NULL) FROM lessons WHERE code = '$CODE';")"
    CONTENT_VERSION="$(echo "$ROW" | cut -d'|' -f1)"
    HAS_SOURCE_URL="$(echo "$ROW" | cut -d'|' -f2)"

    if [ "$CODE" = "lesson-12" ]; then
        EXPECTED_VERIFIED="false"
    else
        EXPECTED_VERIFIED="true"
    fi

    # source_url 유무와 지정하려는 source-verified 값이 모순되면(즉
    # publish_lesson.py 자체의 안전장치를 어길 값이면) 아예 호출하지 않고
    # 전체 시퀀스를 즉시 중단한다.
    if [ "$HAS_SOURCE_URL" = "t" ] && [ "$EXPECTED_VERIFIED" = "false" ]; then
        echo "[오류] $CODE 는 source_url이 있는데 source-verified=false로 지정하려 했습니다 — 모순. 중단합니다." >&2
        exit 1
    fi
    if [ "$HAS_SOURCE_URL" = "f" ] && [ "$EXPECTED_VERIFIED" = "true" ]; then
        echo "[오류] $CODE 는 source_url이 없는데 source-verified=true로 지정하려 했습니다 — 모순. 중단합니다." >&2
        exit 1
    fi

    echo "  -> $CODE (content_version=$CONTENT_VERSION, source-verified=$EXPECTED_VERIFIED)"
    if ! staging_compose exec -T api python -m scripts.publish_lesson \
        --code "$CODE" \
        --content-version "$CONTENT_VERSION" \
        --reviewer "$REVIEWER" \
        --source-verified "$EXPECTED_VERIFIED" \
        --note "$PUBLISH_NOTE"; then
        echo "[오류] $CODE 승인 중 실패 — 이후 강의는 처리하지 않고 즉시 중단합니다." >&2
        exit 1
    fi
done

echo "[6/7] 게시 후 상태·감사기록 재확인:"
run_sql "SELECT code, status, review_status, reviewed_by FROM lessons WHERE code ~ '^lesson-(0[6-9]|1[0-5])\$' ORDER BY code;"
run_sql "SELECT lesson_code, action, source_verified FROM lesson_review_audits WHERE lesson_code ~ '^lesson-(0[6-9]|1[0-5])\$' ORDER BY lesson_code;"

echo "[7/7] 재실행 멱등성은 이 명령을 동일 인자로 다시 실행해 확인하세요 —"
echo "      publish_lesson.py가 이미 승인된 강의를 감사기록 기준으로 감지해 그대로 성공 처리합니다."
