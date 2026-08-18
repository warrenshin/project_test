#!/bin/sh
# API 컨테이너 시작 시퀀스: DB 대기 -> migration -> 데모 시세 새로고침 -> 서버 실행.
#
# `set -e`로 어느 단계든 실패하면 즉시 스크립트가 0이 아닌 코드로 종료되어
# 컨테이너가 "실패"로 표시된다 — migration이나 seed가 실패했는데 조용히
# 서버가 뜨는 일은 없다.
set -e

echo "[entrypoint] 데이터베이스 연결을 기다린다..."
python -m scripts.wait_for_db

echo "[entrypoint] alembic upgrade head (마이그레이션 + 시드 데이터)..."
alembic upgrade head

echo "[entrypoint] 데모 종목 최신 시세 as_of를 새로고침한다..."
python -m scripts.refresh_demo_market_data

echo "[entrypoint] API 서버를 시작한다..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
