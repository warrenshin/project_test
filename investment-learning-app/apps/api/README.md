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
│  ├─ *.py              # SQLAlchemy 도메인 모델 (user, market, portfolio, journal, policy, learning, ai)
│  └─ services/
│     ├─ execution.py     # 모의 체결 엔진 (6.7) — build_quote, execute_order
│     ├─ market_data.py   # 시장 데이터 provider 추상화·검증·upsert (6.4)
│     ├─ gamification.py  # XP 산정 규칙 (6.3) — 일일 상한, 이벤트당 1회 지급
│     ├─ coaching.py      # 과정 점수(7.3)·행동편향 탐지(7.4)
│     └─ ai_coach.py      # AI 코치 파이프라인 (7.5-7.7) — Claude API + 규칙기반 폴백
├─ scripts/
│  └─ ingest_market_data.py  # 수동 시세 수집 CLI (라이브 미검증, README 참고)
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
- **instruments** (`/v1/instruments/*`) — 구현 완료: 종목 검색(티커·이름·거래소 필터),
  상세(최근가·기준시각·출처·지연초), bars 조회(시간순). 실제 시세 데이터는
  `services/market-data-worker/README.md` 참고 — 이 세션에서는 라이브 수집을
  검증하지 못해 정적 샘플 4종목(seed-sample)만 조회 가능하다. fundamentals는 아직
  501 스텁이다.
- **learning** (`/v1/learning/paths`, `/v1/lessons/*`, `/v1/quizzes/{id}` [GET/POST],
  `/v1/me/learning-summary`) — 구현 완료: LearningPath>Course>Module>Lesson 계층,
  콘텐츠 블록(학습목표·본문·예시·핵심요약), 퀴즈 문항 조회(`GET /v1/quizzes/{id}` —
  정답 여부는 응답에 포함하지 않는다), 채점(정답 선택지 집합 비교, 오답 해설 포함),
  진도 기록, 서버 계산 XP(6.3 — 완료 이벤트당 1회만 지급, 일일 상한 적용). 콘텐츠는
  1~5강만 시드되어 있다 (`content/courses/README.md` 참고).
  **아직 없는 것**: 콘텐츠 게시 승인 워크플로(초안→검수→승인, 11.1)는 status 필드
  수준만 있고, 7일/28일 챌린지·배지·스트릭 보상 UI는 구현하지 않았다(스트릭 일수
  자체는 `/me/learning-summary`에서 XP 지급일 기준으로 계산해 제공).
- **journals** (`/v1/journals/*`, `/v1/me/journals`, `/v1/me/bias-report`) — 구현
  완료: 거래 전/후 일지, 목록·단건 조회(`GET /v1/me/journals`, `GET
  /v1/journals/{id}` — 명세서 9.2에 명시적 엔드포인트는 없지만 프런트엔드가 필요로
  해 추가), 수정 시 원문을 `journal_versions`로 보존, 규칙 기반 과정 점수(7.3, 6개
  항목 가중합), 행동편향 탐지 3종(확증편향·처분효과·집중위험, 7.4 — 항상 "관찰된
  거래 패턴"으로 표현하고 진단으로 표현하지 않음). 나머지 4개 편향 유형(추격매수·
  손실회피·물타기 집착·과잉매매)은 미구현. `POST /v1/portfolios/{id}/orders`가
  `pre_trade_journal_id`를 받으면 체결 성공 시 해당 일지의 `order_id`를 자동으로
  채운다 — 처분효과 탐지가 일지↔주문을 연결해 조회하는 데 필요하다.
- **ai** (`/v1/ai/*`, `/v1/journals/{id}/coaching`) — 구현 완료: 의도분류(정책
  필터)→검색(강의 콘텐츠 키워드 매칭)→정량 규칙 엔진(과정 점수·시세·현금잔고를
  결정론적으로 계산해 LLM에 문맥으로 전달)→LLM 설명→출력 정책 검사(직접 매매지시·
  수익보장 패턴 차단)→출처·기준시각 표시 파이프라인. **중요**: 이 개발 세션에는
  `ANTHROPIC_API_KEY`가 설정되어 있지 않아 실제 LLM 호출 경로를 라이브로 검증하지
  못했다 — `ANTHROPIC_API_KEY`가 없거나 API 호출이 실패하면 규칙 기반 폴백으로
  graceful degradation하며(7.7 요구사항), 이 폴백 경로는 테스트로 검증했다. 응답에
  `degraded: true`가 표시되면 폴백 경로다. 시스템 프롬프트는
  `content/prompts/v1-investment-coach.md`에 버전 관리한다(7.7).

## 웹 프런트엔드(apps/web) 연동

`apps/web`(Next.js) 로컬 개발 서버에서 이 API를 호출하려면 CORS 허용 origin이
맞아야 한다. 기본값은 `http://localhost:3000`, `http://127.0.0.1:3000`이며
`CORS_ALLOWED_ORIGINS_RAW` 환경변수(쉼표 구분)로 바꿀 수 있다
(`app/core/config.py`). 자세한 프런트엔드 실행 방법은 `apps/web/README.md` 참고.

데모 종목 시드 시세는 `market_data_staleness_threshold_seconds`(기본 900초)를
넘기면 주문이 거부된다. 라이브 시세 공급자가 없는 이 환경에서는 시드 데이터가
한 번 오래되면 데모 자체가 막히므로, 로컬에서 오래 개발하거나 데모하기 전에
아래 스크립트로 최신 bar의 as_of만 새로고침한다(가격은 바꾸지 않는다):

```bash
python -m scripts.refresh_demo_market_data
```

## 테스트

```bash
DATABASE_URL=postgresql+psycopg://app:app@localhost:5432/investment_learning pytest -q
```

CI(`.github/workflows/investment-learning-api-ci.yml`)는 Postgres 서비스 컨테이너를
띄우고 `alembic upgrade head` 후 테스트를 실행한다.

마이그레이션 원복성은 아래로 검증한다(다운그레이드는 seed 데이터를 포함해 로컬
DB를 초기화하므로 개발용 DB에서만 실행한다):

```bash
alembic downgrade base && alembic upgrade head
```

프런트엔드 E2E 테스트(Playwright)는 `apps/web/README.md`의 "E2E 테스트" 절 참고.
