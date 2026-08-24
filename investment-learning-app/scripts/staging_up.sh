#!/bin/bash
# 로컬 스테이징을 기동한다. 아래는 요구된 "한 줄 명령"과 완전히 동일한 동작을
# 하는 편의 래퍼일 뿐이다 — 직접 아래 명령을 그대로 실행해도 동일하다:
#
#   docker compose \
#     --project-name investment-learning-staging \
#     --env-file .env.staging \
#     -f docker-compose.yml \
#     -f docker-compose.staging.yml \
#     up --build -d
#
# 이 래퍼가 추가로 하는 일: .env.staging이 없거나 예시 플레이스홀더를 그대로
# 쓰고 있으면 컨테이너가 크래시루프하기 전에 미리 사람이 읽을 수 있는 오류로
# 중단한다.

set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
source scripts/_staging_lib.sh

require_staging_env_file
assert_staging_database_url_is_safe

echo "[staging_up] investment-learning-staging 스택을 기동합니다..."
staging_compose up --build -d

echo "[staging_up] 기동 명령을 실행했습니다. 상태 확인:"
staging_compose ps
echo "[staging_up] 준비 상태 확인은 scripts/verify_staging.sh 를 실행하세요."
