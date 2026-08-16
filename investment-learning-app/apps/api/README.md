# API (FastAPI)

모듈형 모놀리스로 시작하는 백엔드. 시장 데이터 수집과 모의 체결은
`services/market-data-worker`, `services/simulation-worker`로 분리한다.

## 로컬 실행

```bash
cp .env.example .env
docker compose -f ../../infra/docker/docker-compose.yml up -d
pip install -r requirements.txt
uvicorn app.main:app --reload
```

`GET /healthz` 로 기동 확인, `GET /docs` 에서 OpenAPI 문서를 확인할 수 있다.

## 구조

```text
app/
├─ main.py           # FastAPI app factory
├─ core/config.py     # 환경설정 (pydantic-settings)
├─ api/v1/            # 버전별 라우터 (auth, learning, instruments, portfolios, journals, ai)
├─ domain/            # 도메인 모델·서비스 (SQLAlchemy 모델은 여기에 추가 예정)
└─ workers/           # 비동기 작업 (체결 큐 소비 등)
```

현재 `api/v1/*` 라우터는 명세서(`docs/product-spec.md`) 9.2 엔드포인트 목록에 맞춘
스텁으로, Phase별로 실제 로직을 채워 나간다. 각 파일 상단 docstring에 해당 Phase와
명세서 절 번호를 표시했다.
