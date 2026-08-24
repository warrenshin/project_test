#!/bin/bash
# 로컬 스테이징 Postgres를 pg_dump(custom format)로 백업한다.
#
# 요구사항 준수:
# - 백업 파일은 저장소 밖(기본값)이거나, 저장소 안이면 .gitignore된 backups/에
#   저장한다(둘 다 이 저장소는 후자로 처리 — .gitignore에 /backups/ 등록됨).
# - 파일명에 UTC 타임스탬프를 포함한다.
# - 0바이트 백업은 거부(삭제 후 비정상 종료)한다.
# - 백업 파일 내용이나 DB 비밀번호를 로그에 남기지 않는다(파일명·크기만 출력).

set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
source scripts/_staging_lib.sh

require_staging_env_file
assert_staging_database_url_is_safe

BACKUP_DIR="${STAGING_BACKUP_DIR:-backups}"
mkdir -p "$BACKUP_DIR"

TIMESTAMP="$(utc_timestamp)"
OUT_FILE="$BACKUP_DIR/staging_${TIMESTAMP}.dump"

POSTGRES_USER_VALUE="$(grep -E '^POSTGRES_USER=' "$STAGING_ENV_FILE" | tail -n1 | cut -d= -f2-)"
POSTGRES_DB_VALUE="$(grep -E '^POSTGRES_DB=' "$STAGING_ENV_FILE" | tail -n1 | cut -d= -f2-)"
POSTGRES_USER_VALUE="${POSTGRES_USER_VALUE:-staging_app}"
POSTGRES_DB_VALUE="${POSTGRES_DB_VALUE:-investment_learning_staging}"

echo "[staging_backup] postgres 컨테이너 상태 확인 중..."
if ! staging_compose ps postgres --status running >/dev/null 2>&1; then
    echo "[오류] staging postgres 컨테이너가 실행 중이 아닙니다. 먼저 scripts/staging_up.sh를 실행하세요." >&2
    exit 1
fi

echo "[staging_backup] pg_dump 실행 중 (파일명만 출력하며, DB 비밀번호나 덤프 내용은 로그에 남기지 않습니다)..."
# 비밀번호는 컨테이너 안의 POSTGRES_PASSWORD 환경변수로 이미 설정돼 있으므로
# pg_dump가 로컬(같은 컨테이너 내부) 신뢰 연결로 접근한다 — 커맨드라인 인자로
# 비밀번호를 넘기지 않는다(프로세스 목록에 노출되는 것을 막기 위함).
staging_compose exec -T postgres \
    pg_dump --format=custom --no-owner --no-privileges \
    -U "$POSTGRES_USER_VALUE" -d "$POSTGRES_DB_VALUE" \
    > "$OUT_FILE"

SIZE_BYTES=$(wc -c < "$OUT_FILE" | tr -d ' ')
if [ "$SIZE_BYTES" -eq 0 ]; then
    rm -f "$OUT_FILE"
    echo "[오류] 백업 파일 크기가 0바이트입니다 — 삭제하고 실패로 처리합니다." >&2
    exit 1
fi

echo "[staging_backup] 완료: $OUT_FILE (${SIZE_BYTES} bytes)"
