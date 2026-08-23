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
Docker로 전체 앱(Postgres+API+웹)을 한 번에 띄우는 방법은 루트 `README.md`의
"빠른 시작 (Docker Compose, 한 번의 명령)"과 아래 "Docker / 배포 준비" 절을
참고한다.

## 구조

```text
app/
├─ main.py            # FastAPI app factory
├─ core/
│  ├─ config.py        # 환경설정 (pydantic-settings)
│  ├─ db.py             # SQLAlchemy 세션/엔진
│  ├─ deps.py            # get_current_user (HttpOnly access 쿠키 검증)
│  ├─ cookies.py         # 인증 쿠키 설정/삭제 (Set-Cookie 속성 일원화)
│  ├─ csrf.py            # OriginCheckMiddleware (상태변경 요청 Origin 검증)
│  └─ security.py       # Argon2id 해싱, JWT 발급·검증
├─ api/v1/             # 버전별 라우터 (auth, learning, instruments, portfolios, journals, ai)
├─ domain/
│  ├─ *.py              # SQLAlchemy 도메인 모델 (user, market, portfolio, journal, policy, learning, ai)
│  └─ services/
│     ├─ execution.py     # 모의 체결 엔진 (6.7) — build_quote, execute_order
│     ├─ market_data.py   # 시장 데이터 provider 추상화·검증·upsert (6.4)
│     ├─ market_data_service.py # 시세 신선도 판단 (FRESH/STALE/UNAVAILABLE, Phase A)
│     ├─ gamification.py  # XP 산정 규칙 (6.3) — 일일 상한, 이벤트당 1회 지급
│     ├─ coaching.py      # 과정 점수(7.3)·행동편향 탐지(7.4)
│     └─ ai_coach.py      # AI 코치 파이프라인 (7.5-7.7) — Claude API + 규칙기반 폴백
├─ scripts/
│  ├─ ingest_market_data.py       # 수동 시세 수집 CLI (라이브 미검증, README 참고)
│  ├─ refresh_demo_market_data.py # 데모 종목 최신 시세 as_of 새로고침
│  ├─ wait_for_db.py              # DB 연결 대기 (컨테이너 시작 순서 방어)
│  ├─ docker_entrypoint.sh        # 컨테이너 시작 시퀀스 (DB 대기→migration→시세 새로고침→서버)
│  └─ smoke_test.py               # 배포 후 핵심 흐름 확인용 smoke test
└─ workers/            # (미사용) 비동기 작업 placeholder — 실제 체결은 아직 API 요청 안에서 동기 실행
alembic/                # DB 마이그레이션 (학습 콘텐츠·데모 종목 시드 포함)
```

## Docker / 배포 준비

`Dockerfile`은 2-스테이지 빌드다: `deps` 스테이지에서 `requirements.txt`(모든
패키지가 `==`로 고정된 lockfile 역할)로 의존성을 설치하고, `runtime`
스테이지는 그 결과물과 애플리케이션 코드만 담아 non-root 사용자(`app`)로
실행한다. `.dockerignore`로 `tests/`, `.venv/`, `.git/` 등 런타임에 불필요한
파일은 이미지에 들어가지 않는다. 이미지 자체에는 `.env` 등 비밀정보가 담긴
파일을 `COPY`하지 않으며, 빌드 인자로도 비밀값을 받지 않는다 — 모든 비밀은
컨테이너 실행 시점에 `env_file`/`environment`로만 주입한다.

컨테이너 시작 시퀀스(`scripts/docker_entrypoint.sh`, `ENTRYPOINT`로 등록):

1. `scripts/wait_for_db.py` — DB에 연결될 때까지 최대 60초 재시도. docker-compose의
   `depends_on: condition: service_healthy`가 대부분의 순서 문제를 막아주지만,
   이 스크립트만으로 컨테이너를 단독 실행하는 경우를 대비한 방어적 장치다.
2. `alembic upgrade head` — 스키마 마이그레이션과 시드 데이터(학습 콘텐츠,
   데모 종목, 수수료 정책)를 함께 반영한다. 이미 최신이면 아무 것도 하지
   않는다(멱등) — 재실행해도 콘텐츠·종목이 중복되지 않고 기존 사용자 데이터도
   보존된다.
3. `scripts/refresh_demo_market_data.py` — 데모 종목 최신 bar의 `as_of`를
   현재 시각으로 새로고침한다(가격은 바꾸지 않는다). 이것도 멱등하다.
4. `uvicorn app.main:app` 시작.

**이 중 어느 단계든 실패하면 스크립트가 `set -e`로 즉시 종료되어 컨테이너가
"실패"로 표시된다 — migration이나 seed 실패를 조용히 넘기고 애플리케이션이
잘못된 스키마 위에서 뜨는 일은 없다.**

`HEALTHCHECK`는 이 프로세스 자신의 `/health/live`만 확인한다(DB나 외부
서비스에 의존하지 않음 — 외부 LLM/시장 데이터 공급자 장애로 컨테이너가
불필요하게 재시작되면 안 되기 때문이다). docker-compose에서는 다른 서비스가
"API가 실제로 요청을 처리할 준비가 됐는지" 알아야 하므로 compose 레벨
healthcheck를 `/health/ready`로 재정의해 사용한다(`../../docker-compose.yml`).

### Health / Readiness 엔드포인트 (`app/api/health.py`)

- `GET /health/live` — 프로세스 liveness만 확인. 어떤 의존성도 확인하지 않는다.
- `GET /health/ready` — DB 연결 + Alembic 마이그레이션이 최신(head)인지
  확인한다. **판단 기준은 이 두 가지뿐이다.** 실패하면 503과 함께 짧은
  `reason` 코드(`database_unavailable` 또는 `migration_pending`)만 반환한다
  — DB URL, 예외 메시지, 스택트레이스 등은 응답에 절대 포함하지 않는다.

### Smoke test (`scripts/smoke_test.py`)

```bash
python -m scripts.smoke_test --base-url http://localhost:8000 --origin http://localhost:3000
```

liveness/readiness → 회원가입 → 로그아웃/로그인(쿠키에 `HttpOnly` 있는지
확인) → `/v1/auth/me` → 1강 조회 → 퀴즈 제출 → SK하이닉스 검색 → 포트폴리오
조회 → 거래 전 일지 생성 → 가상 매수 주문 → 포트폴리오 반영 확인 → 로그아웃
→ 로그아웃 후 보호 API 401 확인, 순서로 검증한다. 매 실행마다 무작위 이메일로
새로 가입하므로(`smoke-<임의 12자리>@example.com`) 몇 번을 반복 실행해도
기존 데이터를 훼손하지 않는다. 상태변경 요청에는 `Origin` 헤더가 실려야
하므로(`--origin`, CSRF 방어) 기본값은 `CORS_ALLOWED_ORIGINS_RAW`의 개발
기본값과 맞춰 두었다 — 다른 CORS 설정을 쓰면 이 값도 함께 바꿔야 한다.

## 시장 데이터 공급자 추상화 (Phase A)

한국·미국 시장에 서로 다른 공급자를 붙일 수 있고, 개발용과 운영용 공급자를
분리할 수 있도록 `app/domain/services/market_data.py`에 `MarketDataProvider`
추상화를 두었다(구현 전 결정사항 1). 현재는 두 구현체뿐이다:

- **`DemoMarketDataProvider`**(기본값) — 외부 네트워크를 전혀 쓰지 않는다.
  티커별로 결정론적인 합성 일봉을 생성해(같은 티커는 항상 같은 데이터)
  수집→검증→upsert 파이프라인을 재현·테스트할 수 있게 한다.
- **`StooqMarketDataProvider`** — 무료 stooq.com CSV 어댑터. **개발·기술검증
  용으로만 유지하며 상용 운영의 기본 공급자로 쓰지 않는다** — 상업적 표시·
  재배포 권한을 공식 문서에서 확인하지 못했기 때문이다(시장 데이터 공급자
  조사 보고서 참고). `MARKET_DATA_PROVIDER=stooq`로 `ENVIRONMENT=production`을
  같이 쓰면 `app/core/config.py`의 검증기가 앱 기동을 거부한다 — 실패해도
  데모 가격으로 조용히 대체하지 않는다는 원칙을 기동 단계에서부터 강제한다.

`app/domain/services/market_data_service.py`의 `get_price_point()`가 시세
신선도를 판단한다 — `execution.build_quote`(주문 경로)와 포트폴리오 조회
경로가 각자 다른 기준으로 "오래됨"을 판단하지 않도록, 판단 로직
(`market_data.classify_price_freshness`)을 한 곳에 모았다.

| 상태 | 의미 | 주문 | 포트폴리오 조회 |
|---|---|---|---|
| `FRESH` | 임계값(`MARKET_DATA_STALENESS_THRESHOLD_SECONDS`, 기본 900초) 이내 | 정상 체결 | 그대로 표시 |
| `STALE` | bar는 있지만 임계값을 넘김 | 409로 거부(기존 동작 유지) | 참고값으로 표시 + 경고 배지 + 기준시각 |
| `UNAVAILABLE` | bar 자체가 없거나 환율이 없어 포트폴리오 통화로 환산 불가 | 422로 거부(기존 동작 유지) | 0원·손실로 계산하지 않고 "시세 확인 불가"로 표시, 합계에서만 제외 |

`GET /v1/portfolios/{id}/positions`의 각 포지션에 `price_status`·`price_as_of`가,
`GET /v1/portfolios/{id}`와 `/performance`에 포트폴리오 전체 수준의
`market_data_status`(`FRESH`/`STALE`/`UNAVAILABLE`/보유종목 없으면 `EMPTY`)·
`market_data_as_of`·`has_unavailable_positions`가 추가됐다. `market_data_status`는
가장 나쁜 상태를 우선한다(하나라도 UNAVAILABLE이면 전체가 UNAVAILABLE) — 경고를
놓치지 않기 위해서다.

새 DB migration은 없다 — 상태는 기존 `bars`/`fx_rates`로부터 요청 시점에
계산되며, 저장이 필요한 새 영속 상태가 없기 때문이다.

`apps/api/scripts/ingest_market_data.py`는 `--provider demo|stooq`로 공급자를
고를 수 있다(기본값은 `MARKET_DATA_PROVIDER` 설정).

## 구현 상태

- **auth** (`/v1/auth/*`) — 구현 완료: 회원가입(약관 동의 검증, 만 14세 미만 가입 제한,
  포트폴리오 자동 생성 및 초기 가상현금 지급), 로그인, `GET /v1/auth/me`(로그인 상태
  확인), `POST /v1/auth/logout`, refresh-token 회전(재사용 탐지 시 사용자 전체 세션
  폐기). **2026-08부터 access/refresh 토큰을 응답 본문(JSON)으로 내려주지 않고
  HttpOnly Secure 쿠키로만 전달한다** — 아래 "인증 쿠키 정책" 절 참고.

### 인증 쿠키 정책 (HttpOnly Secure 쿠키)

이전에는 로그인/refresh 응답 JSON에 access/refresh 토큰을 담아 프런트엔드가
`localStorage`에 저장하고 `Authorization: Bearer` 헤더로 보냈다. 이 방식은 XSS 한
번으로 저장된 토큰을 그대로 탈취당할 수 있다는 위험이 있어, 서버가 관리하는
HttpOnly 쿠키 기반 인증으로 전환했다.

- 로그인/회원가입/refresh 성공 시 서버가 `Set-Cookie`로 access·refresh 쿠키를
  내려준다. 두 쿠키 모두 `HttpOnly=true`(JavaScript로 값을 읽을 수 없음)이며,
  응답 JSON 본문에는 토큰 문자열이 전혀 포함되지 않는다.
- `Authorization: Bearer` 헤더는 더 이상 인증에 쓰이지 않는다(완전히 제거했다 —
  토큰이 응답 본문으로 내려가지 않으므로 클라이언트가 헤더에 채워 넣을 값 자체가
  없다). `app/core/deps.py`의 `get_current_user`는 access 쿠키만 읽는다.
- refresh-token 회전과 재사용 탐지(이전 세대 refresh token 재사용 시 해당 사용자의
  모든 세션 폐기)는 쿠키 전환 후에도 동일하게 동작한다 — 저장 방식만 바뀌었을 뿐
  회전·탐지 로직(`app/domain/user.py`의 `UserSession`, `app/api/v1/auth.py`)은
  그대로다. DB에는 여전히 refresh token의 해시만 저장한다(평문 저장 아님).
- `POST /v1/auth/logout`은 refresh 쿠키가 가리키는 세션을 서버에서 즉시 폐기하고,
  요청에 실린 쿠키 유무와 무관하게 항상 access/refresh 쿠키 삭제 응답을 내려준다
  (멱등). **알려진 한계**: access token은 상태 비저장(stateless) JWT라 만료 전에는
  서버 측에서 개별 무효화할 수 없다 — 로그아웃 시 즉시 폐기되는 것은 refresh
  세션이며, 탈취된 access token은 만료 시각(`ACCESS_TOKEN_EXPIRE_MINUTES`, 기본
  30분)까지는 이론상 유효하다. 이는 stateless JWT의 업계 표준 트레이드오프이며,
  이를 없애려면 access token마다 서버 측 상태를 두는(사실상 세션 방식) 구조가
  필요해 이번 범위에서는 채택하지 않았다.

쿠키 이름·속성은 모두 `app/core/config.py`의 `Settings`(환경변수/`.env`로 설정)로
관리한다 — 하드코딩된 값이 없다.

| 설정 | 환경변수 | 개발 기본값 | production 필수값 |
|---|---|---|---|
| access 쿠키 이름 | `ACCESS_COOKIE_NAME` | `ilapp_access_token` | 임의 (동일 유지 권장) |
| refresh 쿠키 이름 | `REFRESH_COOKIE_NAME` | `ilapp_refresh_token` | 임의 (동일 유지 권장) |
| `HttpOnly` | (항상 true, 설정 불가) | `true` | `true` |
| `Secure` | `COOKIE_SECURE` | `false` (HTTP localhost 개발용) | **`true` 필수** |
| `SameSite` | `COOKIE_SAMESITE` | `lax` | `lax`(권장) — `none`은 `Secure=true`와 함께만 허용 |
| `Domain` | `COOKIE_DOMAIN` | 미설정(host-only) | 하위 도메인 공유가 실제로 필요할 때만 명시적으로 설정 |
| access 쿠키 `Path` | `ACCESS_COOKIE_PATH` | `/` | `/` |
| refresh 쿠키 `Path` | `REFRESH_COOKIE_PATH` | `/v1/auth` | `/v1/auth` (필요한 엔드포인트에만 실리도록 좁게 제한) |
| access 쿠키 수명 | `ACCESS_TOKEN_EXPIRE_MINUTES` | 30분 | 배포 정책에 맞게 조정 |
| refresh 쿠키 수명 | `REFRESH_TOKEN_EXPIRE_DAYS` | 30일 | 배포 정책에 맞게 조정 |

`ENVIRONMENT=production`일 때 `app/core/config.py`의 `Settings` 검증기가 안전하지
않은 조합이면 **앱 기동 자체를 실패시킨다**(조용히 경고만 하고 넘어가지 않는다):
`COOKIE_SECURE=false`인 경우, `COOKIE_SAMESITE=none`인데 `COOKIE_SECURE=true`가
아닌 경우, `JWT_SECRET`이 기본값(`change-me-in-env`)인 경우.

로그아웃과 refresh 실패 시 쿠키 삭제는 **쿠키를 설정할 때와 정확히 동일한
속성**(`Path`, `Domain`, `SameSite`, `Secure`)으로 `Set-Cookie`를 보내
`app/core/cookies.py`의 `clear_auth_cookies`에서 처리한다 — 속성이 하나라도
다르면 브라우저가 다른 쿠키로 취급해 삭제되지 않기 때문이다.

### CSRF 방어

쿠키 기반 인증은 브라우저가 요청마다 쿠키를 자동으로 실어 보내므로, 공격자
사이트가 사용자 브라우저를 통해 의도치 않은 상태 변경 요청(CSRF)을 보낼 수 있다는
위험이 새로 생긴다. 이 프로젝트는 아래 조합으로 방어한다:

1. **`SameSite=Lax` 쿠키** — 다른 사이트에서 발생한 대부분의 자동 요청(예: 이미지
   태그, 폼 자동 제출을 통한 GET)에는 쿠키가 실리지 않는다.
2. **Origin 검증 미들웨어**(`app/core/csrf.py`의 `OriginCheckMiddleware`) — 상태를
   변경하는 메서드(POST/PUT/PATCH/DELETE)는 `Origin` 헤더가
   `CORS_ALLOWED_ORIGINS_RAW`에 등록된 허용 origin과 정확히 일치해야 통과한다.
   `Origin` 헤더가 없거나 허용 목록에 없으면 403으로 차단한다. GET/HEAD/OPTIONS는
   상태를 변경하지 않으므로 이 검사에서 제외한다(안전한 메서드는 원래 상태를
   바꾸면 안 된다는 HTTP 시맨틱스를 그대로 따른다).

별도의 이중 제출(double-submit) CSRF 토큰은 **의도적으로 추가하지 않았다**: 이
프로젝트는 프런트엔드 origin이 하나(`apps/web`)뿐인 단순한 구조이고, `SameSite=Lax`
+ Origin 검증 조합이 OWASP가 권장하는 최소 방어선을 이미 충족한다. 개발 환경에서
`localhost:3000`(프런트)과 `localhost:8000`(백엔드)은 포트가 달라도 스킴+호스트가
같아 "same-site"로 취급되므로 `SameSite=Lax` 쿠키가 정상적으로 오간다. CORS의
`allow_origins`는 항상 명시적 목록이며(`app/main.py`), `allow_credentials=true`와
와일드카드 origin(`*`)을 함께 쓰지 않는다 — 이는 브라우저 사양상 애초에 허용되지
않기도 하고, 이 조합이 CSRF·자격증명 탈취 위험을 크게 키우기 때문이다.
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
  1~15강이 시드되어 있다(6~15강 중 8개 PUBLISHED·2개는 검수 대기 중 DRAFT —
  `docs/features/investment-lessons-06-15.md` 참고).
  **아직 없는 것**: 콘텐츠 게시 승인 워크플로(초안→검수→승인, 11.1)는 status 필드
  수준만 있고, 7일/28일 챌린지·배지·스트릭 보상 UI는 구현하지 않았다(스트릭 일수
  자체는 `/me/learning-summary`에서 XP 지급일 기준으로 계산해 제공).
- **journals** (`/v1/journals/*`, `/v1/me/journals`, `/v1/me/bias-report`) — 구현
  완료: 거래 전/후 일지, 목록·단건 조회(`GET /v1/me/journals`, `GET
  /v1/journals/{id}` — 명세서 9.2에 명시적 엔드포인트는 없지만 프런트엔드가 필요로
  해 추가), 수정 시 원문을 `journal_versions`로 보존, 규칙 기반 과정 점수(7.3, 6개
  항목 가중합), 행동편향 탐지 7종 전부(확증편향·처분효과·집중위험·추격매수·
  손실회피·물타기 집착·과잉매매, 7.4 — 항상 "관찰된 거래 패턴"으로 표현하고
  진단으로 표현하지 않음). `POST /v1/portfolios/{id}/orders`가
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

로컬 개발 주소는 백엔드 `http://localhost:8000`(Playwright E2E는 `:8100`), 프런트
`http://localhost:3000`(Playwright E2E는 `:3100`)이다.

인증이 쿠키 기반으로 바뀌면서 프런트엔드는 모든 API 요청에 `credentials:
"include"`를 반드시 실어야 브라우저가 쿠키를 함께 보낸다(`apps/web/src/lib/api.ts`
참고). **production 배포는 반드시 HTTPS여야 한다** — `COOKIE_SECURE=true`인
쿠키는 HTTPS 연결에서만 브라우저가 전송하므로, HTTP로 배포하면 인증 자체가
동작하지 않는다(의도된 fail-safe 동작이다).

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

`tests/test_auth.py`에 HttpOnly 쿠키 인증 보안 테스트가 포함되어 있다: 로그인
응답의 `Set-Cookie` HttpOnly 속성 확인, production 쿠키 정책(`Secure` 강제) 검증,
응답 JSON에 토큰이 없는지 확인, 쿠키 없이 보호 API 호출 시 401, 다른 사용자 데이터
접근 차단, refresh 회전·재사용 차단, 로그아웃 후 세션 무효화, 만료된 access
token의 refresh 성공, 잘못된/누락된 Origin의 상태변경 요청 차단, 허용된 Origin의
상태변경 요청 성공, Bearer 헤더로는 더 이상 인증되지 않음 등.

CI(`.github/workflows/investment-learning-api-ci.yml`)는 Postgres 서비스 컨테이너를
띄우고 `alembic upgrade head` 후 테스트를 실행한다.

마이그레이션 원복성은 아래로 검증한다(다운그레이드는 seed 데이터를 포함해 로컬
DB를 초기화하므로 개발용 DB에서만 실행한다):

```bash
alembic downgrade base && alembic upgrade head
```

프런트엔드 E2E 테스트(Playwright)는 `apps/web/README.md`의 "E2E 테스트" 절 참고.
