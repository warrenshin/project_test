#!/bin/bash
# 로컬 스테이징 데이터(named volume)까지 완전히 삭제한다.
# staging_down.sh(볼륨 보존)와 반드시 분리된, 별도의 명시적 명령이다 —
# 실수로 데이터를 지우는 것을 막기 위해 기본 down 명령에는 -v를 절대
# 포함하지 않는다(요구사항).
#
# 실제로 지우는 것: docker-compose.staging.yml에 정의된
# investment-learning-staging_postgres_data 볼륨뿐이다. dev의 postgres_data
# 볼륨이나 운영 DB는 이 스크립트가 알지도, 건드리지도 못한다(별도 프로젝트).

set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
source scripts/_staging_lib.sh

if [ "${1:-}" != "--yes-delete-staging-data" ]; then
    echo "[staging_reset_data] 이 명령은 로컬 스테이징 DB 데이터를 영구 삭제합니다." >&2
    echo "                     확인했다면 다음과 같이 다시 실행하세요:" >&2
    echo "                     scripts/staging_reset_data.sh --yes-delete-staging-data" >&2
    exit 1
fi

echo "[staging_reset_data] investment-learning-staging 스택과 볼륨을 함께 삭제합니다..."
staging_compose down -v
echo "[staging_reset_data] 완료. investment-learning-staging_postgres_data 볼륨이 삭제됐습니다."
