#!/usr/bin/env bash
# CI 전용 헬퍼: docker-compose 서비스의 컨테이너 HEALTHCHECK가 "healthy"가
# 될 때까지 timeout 안에서 재시도한다. 무한 대기하지 않는다 — timeout을
# 넘기면 컨테이너 상태와 최근 로그를 출력하고 명확한 오류로 실패한다.
#
#   wait_for_container_healthy.sh <compose 서비스명> [max_seconds=180]
#
# docker-compose.yml이 있는 디렉터리에서 실행해야 한다(docker compose ps로
# 컨테이너를 찾는다).
set -euo pipefail

service="$1"
max_seconds="${2:-180}"
waited=0

while true; do
  cid="$(docker compose ps -q "$service" 2>/dev/null || true)"
  if [ -z "$cid" ]; then
    status="not_created"
  else
    status="$(docker inspect -f '{{.State.Health.Status}}' "$cid" 2>/dev/null || echo "unknown")"
  fi

  if [ "$status" = "healthy" ]; then
    echo "${service} healthy after ${waited}s"
    exit 0
  fi

  if [ "$waited" -ge "$max_seconds" ]; then
    echo "::error::${service} did not become healthy within ${max_seconds}s (last status: ${status})"
    docker compose ps
    docker compose logs --tail=100 "$service" || true
    exit 1
  fi

  sleep 3
  waited=$((waited + 3))
done
