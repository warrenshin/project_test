#!/usr/bin/env bash
# CI 전용 헬퍼: 지정한 URL이 timeout 안에 정상 응답(HTTP 2xx)할 때까지 재시도한다.
# 무한 대기하지 않는다 — timeout을 넘기면 명확한 오류로 실패한다.
#
#   wait_for_http.sh <url> <표시용 이름> [max_seconds=180]
set -euo pipefail

url="$1"
name="$2"
max_seconds="${3:-180}"
waited=0

until curl -fsS "$url" >/dev/null 2>&1; do
  if [ "$waited" -ge "$max_seconds" ]; then
    echo "::error::${name} did not become ready within ${max_seconds}s (${url})"
    exit 1
  fi
  sleep 3
  waited=$((waited + 3))
done

echo "${name} ready after ${waited}s"
