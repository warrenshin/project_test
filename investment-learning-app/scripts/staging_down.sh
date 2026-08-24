#!/bin/bash
# 로컬 스테이징을 중지한다. 컨테이너/네트워크만 제거하고 볼륨(DB 데이터)은
# 보존한다 — 데이터를 지우려면 이 스크립트가 아니라
# scripts/staging_reset_data.sh를 별도로, 명시적으로 실행해야 한다.
#
# 아래는 요구된 "한 줄 명령"과 동일한 동작을 하는 편의 래퍼다:
#
#   docker compose \
#     --project-name investment-learning-staging \
#     --env-file .env.staging \
#     -f docker-compose.yml \
#     -f docker-compose.staging.yml \
#     down

set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
source scripts/_staging_lib.sh

echo "[staging_down] investment-learning-staging 스택을 중지합니다(볼륨은 보존)..."
staging_compose down
echo "[staging_down] 완료. 데이터(볼륨)는 그대로 남아 있습니다."
