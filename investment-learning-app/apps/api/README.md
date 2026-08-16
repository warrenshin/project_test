# API (FastAPI)

모듈형 모놀리스로 시작하는 백엔드. 시장 데이터 수집과 모의 체결은
`services/market-data-worker`, `services/simulation-worker`로 분리한다.

## 로컬 실행

```bash
cp .env.example .env
docker compose -f ../../infra/docker/docker-compose.yml up -d
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload
```

`GET /healthz` 로 기동 확인, `GET /docs` 에서 OpenAPI 문서를 확인할 수 있다.

## 구조

```text
app/
├─ main.py            # FastAPI app factory
├─ core/
│  ├─ config.py        # 환경설정 (pydantic-settings)
│  ├─ db.py             # SQLAlchemy 세션/엔진
│  └─ security.py       # Argon2id 해싱, JWT 발급·검증
├─ api/v1/             # 버전별 라우터 (auth, learning, instruments, portfolios, journals, ai)
├─ domain/             # SQLAlchemy 도메인 모델
└─ workers/            # 비동기 작업 (체결 큐 소비 등)
alembic/                # DB 마이그레이션
```

## 구현 상태

- **auth** (`/v1/auth/*`) — 구현 완료: 회원가입(약관 동의 검증, 만 14세 미만 가입 제한),
  로그인, refresh-token 회전(재사용 탐지 시 사용자 전체 세션 폐기). 세션은 DB에
  기록되어 있어 추후 원격 로그아웃(다른 기기 세션 조회·폐기) 엔드포인트를 얹을 수 있다.
- 나머지 `api/v1/*` 라우터는 명세서(`docs/product-spec.md`) 9.2 엔드포인트 목록에 맞춘
  스텁이다. 각 파일 상단 docstring에 해당 Phase와 명세서 절 번호를 표시했다.

## 테스트

```bash
DATABASE_URL=postgresql+psycopg://app:app@localhost:5432/investment_learning pytest -q
```

CI(`.github/workflows/investment-learning-api-ci.yml`)는 Postgres 서비스 컨테이너를
띄우고 `alembic upgrade head` 후 테스트를 실행한다.
