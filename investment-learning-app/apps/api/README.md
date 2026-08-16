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
│  ├─ deps.py            # get_current_user (Bearer access token 검증)
│  └─ security.py       # Argon2id 해싱, JWT 발급·검증
├─ api/v1/             # 버전별 라우터 (auth, learning, instruments, portfolios, journals, ai)
├─ domain/
│  ├─ *.py              # SQLAlchemy 도메인 모델 (user, market, portfolio, journal, policy)
│  └─ services/
│     └─ execution.py    # 모의 체결 엔진 (6.7) — build_quote, execute_order
└─ workers/            # (미사용) 비동기 작업 placeholder — 실제 체결은 아직 API 요청 안에서 동기 실행
alembic/                # DB 마이그레이션
```

## 구현 상태

- **auth** (`/v1/auth/*`) — 구현 완료: 회원가입(약관 동의 검증, 만 14세 미만 가입 제한,
  포트폴리오 자동 생성 및 초기 가상현금 지급), 로그인, refresh-token 회전(재사용 탐지 시
  사용자 전체 세션 폐기).
- **portfolios/orders** (`/v1/me/portfolio`, `/v1/portfolios/*`, `/v1/orders/*`) — 구현
  완료: 원장(ledger_entries) 기반 현금 계산, 시장가·지정가 모의 체결(6.7 근사 규칙),
  수수료·세금·환전 스프레드 정책 적용(KR/US, `fee_policies`/`fx_rates`), 8단계 주문
  검증(9.3), Idempotency-Key 기반 중복 주문 방지, 주문 후 집중도 경고, 포지션 평단가·
  평가손익, 기본 성과 지표(`/performance`). **알려진 한계**: 체결은 API 요청 안에서
  동기 실행되므로, LIMIT 주문이 최초 요청 시점에 체결되지 못하면 이후 새 시세가 들어와도
  재평가되지 않고 ACCEPTED로 남는다 — 비동기 재평가 워커는 `services/simulation-worker`
  참고. 장 운영시간(거래소 캘린더) 검증과 기업행사(액면분할·배당 등) 반영도 아직 없다.
  FX 환율은 `market-data-worker`가 없어 seed 플레이스홀더 값(USD/KRW)을 사용한다.
- 나머지 `api/v1/*` 라우터(학습, 종목검색, 일지, AI)는 명세서(`docs/product-spec.md`)
  9.2 엔드포인트 목록에 맞춘 스텁이다. 각 파일 상단 docstring에 해당 Phase와 명세서
  절 번호를 표시했다.

## 테스트

```bash
DATABASE_URL=postgresql+psycopg://app:app@localhost:5432/investment_learning pytest -q
```

CI(`.github/workflows/investment-learning-api-ci.yml`)는 Postgres 서비스 컨테이너를
띄우고 `alembic upgrade head` 후 테스트를 실행한다.
