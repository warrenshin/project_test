#!/bin/bash
# 스테이징 백업이 실제로 복원 가능한지 검증한다.
#
# 요구사항 준수:
# - 복원은 반드시 "임시 검증용 DB"에만 수행한다 — 원본 staging-postgres는
#   절대 건드리지 않는다(이 스크립트는 별도의 일회용 postgres 컨테이너를
#   docker run으로 새로 띄우고, 검증이 끝나면 성공/실패와 무관하게 항상
#   제거한다).
# - 복원 후 핵심 테이블 행 수와 alembic revision을 확인한다.
# - 백업 파일 내용이나 DB 비밀번호를 로그에 남기지 않는다.

set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
source scripts/_staging_lib.sh

BACKUP_DIR="${STAGING_BACKUP_DIR:-backups}"
BACKUP_FILE="${1:-}"

if [ -z "$BACKUP_FILE" ]; then
    BACKUP_FILE="$(ls -1t "$BACKUP_DIR"/staging_*.dump 2>/dev/null | head -n1 || true)"
fi
if [ -z "$BACKUP_FILE" ] || [ ! -f "$BACKUP_FILE" ]; then
    echo "[오류] 복원할 백업 파일을 찾을 수 없습니다. 먼저 scripts/staging_backup.sh를 실행하거나" >&2
    echo "       경로를 인자로 넘기세요: scripts/staging_restore_test.sh backups/staging_....dump" >&2
    exit 1
fi

VERIFY_CONTAINER="investment-learning-staging-restore-verify-$(utc_timestamp | tr -d 'TZ')"
VERIFY_DB="restore_verify"
VERIFY_USER="restore_verify"
VERIFY_PASSWORD="restore-verify-local-only-$$"

cleanup() {
    docker rm -f "$VERIFY_CONTAINER" >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "[staging_restore_test] 임시 검증용 Postgres 컨테이너를 띄웁니다 (원본 staging-postgres는 건드리지 않습니다)..."
docker run -d --rm --name "$VERIFY_CONTAINER" \
    -e POSTGRES_USER="$VERIFY_USER" \
    -e POSTGRES_PASSWORD="$VERIFY_PASSWORD" \
    -e POSTGRES_DB="$VERIFY_DB" \
    postgres:16-alpine >/dev/null

echo "[staging_restore_test] 컨테이너 준비를 기다립니다..."
for _ in $(seq 1 30); do
    if docker exec "$VERIFY_CONTAINER" pg_isready -U "$VERIFY_USER" -d "$VERIFY_DB" >/dev/null 2>&1; then
        break
    fi
    sleep 1
done
if ! docker exec "$VERIFY_CONTAINER" pg_isready -U "$VERIFY_USER" -d "$VERIFY_DB" >/dev/null 2>&1; then
    echo "[오류] 임시 검증용 Postgres가 준비되지 않았습니다." >&2
    exit 1
fi

echo "[staging_restore_test] 백업 파일을 컨테이너로 복사하고 pg_restore를 실행합니다 (내용은 출력하지 않습니다)..."
docker cp "$BACKUP_FILE" "$VERIFY_CONTAINER:/tmp/restore_target.dump"
docker exec "$VERIFY_CONTAINER" \
    pg_restore --no-owner --no-privileges -U "$VERIFY_USER" -d "$VERIFY_DB" /tmp/restore_target.dump

echo "[staging_restore_test] 핵심 테이블 행 수와 alembic revision을 확인합니다..."
run_sql() {
    docker exec -e PGPASSWORD="$VERIFY_PASSWORD" "$VERIFY_CONTAINER" \
        psql -U "$VERIFY_USER" -d "$VERIFY_DB" -tAc "$1"
}

ALEMBIC_REV="$(run_sql "SELECT version_num FROM alembic_version;" | tr -d '[:space:]')"
LESSON_COUNT="$(run_sql "SELECT count(*) FROM lessons;" | tr -d '[:space:]')"
INSTRUMENT_COUNT="$(run_sql "SELECT count(*) FROM instruments;" | tr -d '[:space:]')"

echo "[staging_restore_test] 결과: alembic_version=${ALEMBIC_REV}, lessons=${LESSON_COUNT}, instruments=${INSTRUMENT_COUNT}"

if [ -z "$ALEMBIC_REV" ]; then
    echo "[오류] 복원된 DB에 alembic_version이 없습니다 — 복원 실패로 간주합니다." >&2
    exit 1
fi
if [ "$LESSON_COUNT" -eq 0 ] || [ "$INSTRUMENT_COUNT" -eq 0 ]; then
    echo "[오류] 복원된 DB의 핵심 테이블이 비어 있습니다 — 복원 실패로 간주합니다." >&2
    exit 1
fi

echo "[staging_restore_test] 복원 검증 성공: $BACKUP_FILE"
