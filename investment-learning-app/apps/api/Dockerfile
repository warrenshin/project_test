# --- deps: 의존성만 별도 스테이지에서 설치해 캐시 재사용을 극대화한다 ---
FROM python:3.12-slim AS deps
WORKDIR /app
COPY requirements.txt .
# requirements.txt는 모든 패키지가 ==으로 고정된 lockfile 역할을 겸한다.
RUN pip install --no-cache-dir --user -r requirements.txt

# --- runtime: 실행에 필요한 것만 담은 최종 이미지 ---
FROM python:3.12-slim AS runtime
WORKDIR /app

# non-root 사용자로 실행한다 — 컨테이너가 뚫려도 root 권한을 주지 않기 위함.
RUN addgroup --system app && adduser --system --ingroup app --home /home/app --no-create-home app \
    && mkdir -p /home/app/.local && chown -R app:app /home/app

COPY --from=deps /root/.local /home/app/.local
COPY --chown=app:app . .
RUN chmod +x scripts/docker_entrypoint.sh

ENV PATH=/home/app/.local/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

USER app

EXPOSE 8000

# 외부 LLM/시장 데이터 공급자가 아니라 이 프로세스 자신의 /health/live만 본다 —
# 외부 서비스 일시 장애로 컨테이너가 불필요하게 재시작되지 않게 하기 위함.
HEALTHCHECK --interval=10s --timeout=5s --start-period=30s --retries=5 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health/live', timeout=3).status == 200 else 1)"

ENTRYPOINT ["./scripts/docker_entrypoint.sh"]
