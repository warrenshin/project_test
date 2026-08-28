# AI 투자교육·모의투자·투자일지 코칭 앱

초보 투자자가 실제 자금을 위험에 노출하지 않고 투자 원리와 의사결정 과정을 익히는 앱.
전체 제품·기술 명세는 [`docs/product-spec.md`](./docs/product-spec.md)를 기준으로 한다.

## 제품의 세 축

1. **AI 투자교육** — 짧은 학습, 퀴즈, 사례와 AI 질의응답
2. **정교한 모의투자** — 실제 시장의 가격·비용·체결 제약을 최대한 현실적으로 재현
3. **투자일지 코칭** — 거래 전 판단과 거래 후 결과를 비교해 행동편향과 원칙 준수도를 코칭

## 법적·운영상 경계 (반드시 준수)

- 실제 자금을 입금·보관·운용하지 않는다.
- 실제 증권 주문을 접수·중개하지 않으며 증권계좌에 연결하지 않는다.
- 개인별 종목 매수·매도 지시나 수익 보장을 제공하지 않는다.
- 모든 포트폴리오·손익은 가상자금임을 항상 명확히 표시한다.
- AI 결과는 교육용 설명이며 출처와 기준시각을 함께 제공한다.

## 저장소 구조

```text
investment-learning-app/
├─ apps/
│  ├─ mobile/            # Flutter 앱 (계획, 미구현)
│  ├─ admin-web/         # Next.js 관리자 웹 (계획, 미구현)
│  ├─ web/                # Next.js 사용자용 웹 (실제 구현됨 — mobile 대신 웹으로 MVP 진행)
│  └─ api/                # FastAPI 백엔드 (모듈형 모놀리스)
├─ services/
│  ├─ market-data-worker/ # 시장 데이터 수집
│  ├─ simulation-worker/  # 모의 체결 엔진
│  └─ ai-orchestrator/    # AI 코치 파이프라인 (RAG + 정책 필터)
├─ packages/
│  ├─ domain-models/      # 공유 도메인 모델·타입
│  ├─ api-contracts/      # API 스키마 계약
│  ├─ design-system/      # 공유 UI 컴포넌트
│  └─ observability/      # 로깅·트레이싱 공통 유틸
├─ content/
│  ├─ courses/            # 강의 콘텐츠
│  ├─ quizzes/            # 퀴즈 문항
│  └─ prompts/            # AI 시스템 프롬프트 버전 관리
├─ infra/
│  ├─ terraform/
│  └─ docker/
├─ tests/
│  ├─ contract/
│  ├─ e2e/
│  ├─ simulation/          # 원장·체결 불변조건 테스트
│  └─ ai-evals/            # AI 골든셋 회귀평가
└─ docs/
   ├─ adr/                 # 아키텍처 결정 기록
   ├─ api/
   ├─ compliance/
   └─ product-spec.md       # 제품·기술 명세 원본
```

## 개발 원칙

1. 수익보다 과정 — 좋은 결과가 아니라 좋은 판단 습관을 보상한다.
2. 가상과 실제를 어떤 화면에서도 혼동하지 않게 명확히 분리한다.
3. 원장(ledger)이 진실의 원천이며 모든 잔고는 이벤트에서 재현 가능해야 한다.
4. LLM은 설명자일 뿐, 가격·지표·체결은 결정론적 엔진이 계산한다.
5. 금융 정보에는 항상 출처와 기준시각을 표시한다.
6. 모의체결은 유리한 가정보다 보수적이고 설명 가능한 가정을 사용한다.
7. 구독 결제와 해지는 학습만큼 이해하기 쉬워야 한다.
8. 실제 투자·자문·자동매매는 MVP 범위 밖이며 별도 인허가 프로젝트로 다룬다.

## 로드맵 (개요)

| Phase | 내용 | 기간 |
|---|---|---|
| 0 | 발견·설계 (리서치, 프로토타입, ADR) | 2~3주 |
| 1 | 기반 (저장소, CI/CD, 인증, DB) | 2주 |
| 2 | 학습 MVP | 3주 |
| 3 | 모의투자 MVP | 4주 |
| 4 | 일지·AI 코칭 | 3주 |
| 5 | 결제·품질·베타 | 2~3주 |

세부 내용은 `docs/product-spec.md`의 16장을 참고한다.

## 빠른 시작 (Docker Compose, 한 번의 명령)

가장 빠르게 전체 앱(Postgres + API + 웹)을 띄우는 방법이다. Docker와 Docker
Compose만 있으면 된다.

1. 저장소를 clone한다.
2. `investment-learning-app` 디렉터리로 이동한다.
   ```bash
   cd investment-learning-app
   ```
3. `.env.example`을 참고해 로컬 `.env`를 준비한다 (`.env`는 git에 커밋하지
   않는다).
   ```bash
   cp .env.example .env
   ```
4. 전체 앱을 빌드하고 실행한다.
   ```bash
   docker compose up --build
   ```
5. 브라우저에서 접속한다.
   - 프런트엔드: http://localhost:3000
   - 백엔드 API: http://localhost:8000 (예: http://localhost:8000/health/live)
6. 종료하려면 터미널에서 `Ctrl+C`를 누르거나, 별도 터미널에서
   `docker compose down`을 실행한다.
7. `docker compose down`은 컨테이너만 제거하고 데이터는 남는다 — PostgreSQL
   데이터는 named volume(`postgres_data`)에 저장되므로 재실행(`docker compose
   up`)해도 회원가입한 계정·일지·포트폴리오가 유지된다. 데이터까지 완전히
   지우려면 `docker compose down -v`를 명시적으로 실행해야 한다(자동으로
   지워지지 않는다).

시작 순서는 `postgres`(healthy) → `api`(마이그레이션+시드 적용 후
`/health/ready`가 healthy가 될 때까지 대기) → `web` 순이다. 이 순서와 각
컨테이너 구성의 자세한 내용은 `apps/api/README.md`의 "Docker / 배포 준비"
절을 참고한다.

### 개발모드 실행 (Docker 없이)

Docker 없이 각 서버를 직접(hot-reload와 함께) 띄우고 싶을 때 쓴다.

백엔드:

```bash
cd apps/api
cp .env.example .env
docker compose -f ../../infra/docker/docker-compose.yml up -d   # Postgres, Redis (앱 컨테이너는 아님)
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload
```

프런트엔드(별도 터미널, 백엔드가 떠 있어야 함):

```bash
cd apps/web
npm install
npm run dev   # http://localhost:3000
```

두 서버를 함께 실행하는 방법, 데모 시세 새로고침(오래된 시세로 주문이 막힐 때),
Playwright E2E 테스트 실행 방법은 `apps/web/README.md`를 참고한다.

### Production-like 실행 (Docker 없이)

배포와 동일한 production 빌드 방식을 Docker 없이 직접 확인하고 싶을 때 쓴다
(`next dev`/`uvicorn --reload`가 아니라 실제 production 서버 프로세스로 뜬다).

```bash
# 백엔드
cd apps/api
ENVIRONMENT=development alembic upgrade head
ENVIRONMENT=development uvicorn app.main:app --host 0.0.0.0 --port 8000   # --reload 없음

# 프런트엔드 (별도 터미널)
cd apps/web
npm run build   # next build — production 빌드
npm run start   # next start — production 서버
```

### Health / Readiness

- `GET /health/live` — 프로세스가 살아 있는지만 확인한다. DB나 외부 서비스에
  의존하지 않는다 — 외부 LLM(Claude API)이나 시장 데이터 공급자가 일시적으로
  응답하지 않아도 이 값은 계속 200을 반환해야 한다(그런 이유로 컨테이너가
  재시작되면 안 되므로).
- `GET /health/ready` — 실제 요청을 처리할 준비가 됐는지 확인한다: DB에
  연결할 수 있는지, Alembic 마이그레이션이 최신(head)까지 적용됐는지를 본다.
  **readiness 판단 기준은 정확히 이 두 가지뿐이다.** 둘 중 하나라도 아니면
  503을 반환한다. 응답에는 DB URL·내부 오류 메시지·스택트레이스 등 민감한
  정보를 절대 포함하지 않는다.
- 프런트엔드는 `GET /api/health`(Next.js 자체 라우트)로 서버 프로세스
  liveness만 확인한다.

### Migration과 seed

- Alembic 마이그레이션(`apps/api/alembic/versions/`)에 학습 콘텐츠(1~5강 +
  6~15강 — 6~15강 10개는 시드 시점에 전부 `READY_FOR_REVIEW`(게시 전, 공개
  API 미노출)이며 사람 검수자가 `scripts/publish_lesson.py`로 개별 승인해야
  공개된다. `docs/features/investment-lessons-06-15.md` 참고), 퀴즈, 데모
  종목 4개(삼성전자/SK하이닉스/AAPL/MSFT), 수수료 정책
  시드가 함께 들어 있다 — 별도 seed 스크립트가 아니라 `alembic upgrade head`
  한 번으로 스키마와 초기 데이터가 함께 반영된다.
- 이미 최신 상태인 DB에 다시 `alembic upgrade head`를 실행해도 안전하다 —
  Alembic이 DB에 저장된 현재 리비전을 보고 이미 적용된 마이그레이션은
  건너뛰므로, 콘텐츠나 종목이 중복 생성되지 않는다. 기존 사용자·일지·
  포트폴리오 데이터도 그대로 유지된다.
- Docker 컨테이너는 시작할 때마다 데모 종목의 최신 시세 `as_of`를 현재
  시각으로 새로고침한다(`scripts/refresh_demo_market_data.py`) — 가격 자체나
  종목 수를 바꾸지 않고 타임스탬프만 갱신하므로 몇 번을 재실행해도 안전하다.
- migration이나 seed가 실패하면 컨테이너 자체가 실패로 종료된다(`apps/api/
  scripts/docker_entrypoint.sh`가 `set -e`로 동작) — 조용히 넘어가 애플리케이션이
  잘못된 스키마로 뜨는 일은 없다.
- production 환경에서 이 과정이 임의의 테스트 사용자 계정을 만들지는 않는다
  — 시드되는 것은 학습 콘텐츠·종목·수수료 정책뿐이다.

### Smoke test

배포된 인스턴스(로컬이든 docker-compose든)에 대해 핵심 흐름이 실제로
동작하는지 빠르게 확인한다.

```bash
cd apps/api
python -m scripts.smoke_test --base-url http://localhost:8000 --origin http://localhost:3000
```

liveness/readiness, 회원가입, 로그인(쿠키 설정 확인), `/v1/auth/me`, 1강 조회,
퀴즈 제출, SK하이닉스 검색, 거래 전 일지 생성, 가상 매수 주문, 포트폴리오
반영, 로그아웃, 로그아웃 후 보호 API 401을 순서대로 확인한다. 매 실행마다
무작위 이메일로 새로 가입하므로 몇 번을 실행해도 기존 데이터를 훼손하지
않는다.

### 전체 테스트

```bash
# 백엔드
cd apps/api && pytest -q

# 프런트엔드
cd apps/web
npx tsc --noEmit
npx eslint .
npm run build
npx playwright test
npm audit
```

### 로그 확인

```bash
docker compose logs -f            # 전체
docker compose logs -f api        # 백엔드만
docker compose logs -f web        # 프런트엔드만
docker compose logs -f postgres   # DB만
```

### CI에서의 Docker Compose 통합 검증

이 저장소를 개발한 샌드박스는 Docker 데몬을 구동할 수 없는 제한된 환경이라
(아래 "알려진 제한사항" 참고), 실제 Docker 실행 검증은 GitHub Actions의
Ubuntu runner에서 수행한다(`.github/workflows/investment-learning-docker-build-ci.yml`).
이 워크플로는 `investment-learning-app/apps/api/**`, `apps/web/**`,
`docker-compose.yml`이 바뀐 PR/`main` push에서 실행되며 다음을 실제로
확인한다:

- API/Web production 이미지 빌드, non-root 사용자, 올바른 HEALTHCHECK,
  이미지에 `.env`/`.git`/테스트/Python 캐시가 없는지(`build-*-image` job).
- 빈 volume에서 `docker compose build --no-cache` → `docker compose up -d`로
  최초 실행, `/health/live`·`/health/ready`·Web `/api/health` 확인, 1~5강·
  데모 종목 시드 확인, smoke test(`compose-integration` job).
- migration/seed를 컨테이너가 뜬 상태에서 다시 실행해도 행 수가 늘지 않는지
  (멱등성 검증).
- web → api → postgres 순서로 각각 재시작한 뒤 health가 다시 정상화되는지,
  재시작 전 만든 테스트 사용자·투자일지가 재시작 후에도 그대로 남아 있는지
  (`scripts/restart_persistence_test.py`로 검증 — 운영 데이터를 지우는 기능은
  없다).
- 잘못된 production 쿠키 설정, DB가 늦게 뜨는 상황, migration이 적용되지
  않은 DB에서 각각 안전하게 반응하는지(`failure-scenarios` job, 격리된
  임시 컨테이너만 사용 — 위 통합 테스트 스택은 건드리지 않는다).

CI는 GitHub repository secret 없이도 동작한다 — `JWT_SECRET` 등은 매 실행마다
무작위로 새로 생성해 로그에 마스킹 처리한다(`.github/scripts/generate_ci_env.sh`).
어떤 job도 컨테이너 레지스트리에 이미지를 push하거나 외부 환경에 배포하지
않는다. 실행 결과는 저장소의 Actions 탭에서 이 워크플로 이름으로 확인할 수
있다.

### 로컬 Docker Desktop / WSL2에서 실행하기

위 "빠른 시작"과 동일한 명령이지만, 최초 실행은 base 이미지 다운로드와
`npm ci`/`pip install`을 새로 하기 때문에 몇 분 정도 걸릴 수 있다(이후
재실행은 Docker 레이어 캐시 덕분에 훨씬 빠르다):

```bash
cd investment-learning-app
cp .env.example .env
docker compose up --build
```

- **health 확인**: `curl http://localhost:8000/health/live`,
  `curl http://localhost:8000/health/ready`, `curl http://localhost:3000/api/health`.
  또는 `docker compose ps`로 각 컨테이너의 `STATUS` 열에 `(healthy)`가
  붙는지 확인한다.
- **로그 확인**: 위 "로그 확인" 절의 `docker compose logs -f [서비스명]`.
- **데이터 유지 확인**: 회원가입 후 `docker compose restart api` (또는
  `web`/`postgres`)를 실행하고, health가 다시 정상화된 뒤 같은 계정으로
  다시 로그인해 데이터가 남아 있는지 확인한다. 자동화된 버전은
  `apps/api/scripts/restart_persistence_test.py` 참고(운영 데이터를 지우는
  기능은 없다 — 새 테스트 계정을 만들고 조회만 한다).

#### ⚠️ 로컬 데이터 volume 완전 삭제 (주의 — 되돌릴 수 없음)

`docker compose down`은 컨테이너만 정리하고 PostgreSQL 데이터는 named
volume(`postgres_data`)에 그대로 남는다. **아래 명령은 그 volume까지
영구적으로 삭제한다 — 회원가입한 모든 계정, 투자일지, 포트폴리오 데이터가
전부 사라지며 되돌릴 수 없다.** 로컬에서 완전히 새로 시작하고 싶을 때만,
정말로 필요한 경우에만 실행한다:

```bash
docker compose down -v
```

CI 워크플로도 매 실행 끝에 이 명령을 쓰지만, 그건 CI 러너 안에서만 존재하는
격리된 볼륨이라 안전하다 — **로컬 개발 환경이나 운영 환경에서는 이 명령이
실제 데이터를 지운다는 점을 항상 염두에 둘 것.**

### 알려진 제한사항 (이번 staging 준비 범위)

- 이 저장소를 개발한 샌드박스는 Docker 데몬을 실제로 구동할 수 없는 제한된
  컨테이너 환경이라(중첩 컨테이너 미지원), `docker compose up --build`를 이
  환경(개발 세션의 샌드박스)에서 직접 실행해 검증하지는 못했다. 대신 위
  "CI에서의 Docker Compose 통합 검증" 절에서 설명한 GitHub Actions 워크플로가
  실제 Docker 데몬이 있는 Ubuntu runner에서 최초 실행·health·멱등성·재시작 후
  데이터 유지·장애 시나리오까지 실제로 검증한다 — 그 실행 결과는 PR의 Checks
  탭에서 확인할 수 있다. 이 세션에서는 Dockerfile·docker-compose.yml·
  헬스체크·entrypoint 스크립트를 코드 검토와 (가능한 범위의) 개별 요소
  검증(예: `docker compose config`로 구성 유효성 확인, Next.js standalone
  서버를 Docker 밖에서 직접 실행해 정상 동작 확인)으로 보강했다 — CI 실행
  결과가 이 항목의 실질적인 검증 결과다.
- 라이브 시장 데이터 공급자 연동과 실제 Anthropic API 연결은 이번 범위에서도
  다루지 않는다 — `ANTHROPIC_API_KEY`를 비워두면 규칙 기반 AI 코칭 폴백
  경로로 동작한다.
- 이 앱은 **실제 자금을 입금·보관·운용하지 않고 실제 증권 주문을 접수·
  중개하지 않는 모의투자(가상자금) 학습 앱**이다 — 모든 화면의 금액과 손익은
  가상자금 기준이다.

## 로컬 스테이징 환경 (Local Staging)

`chore/local-staging-environment`에서 추가됨. **개발(dev) / 로컬 스테이징 /
클라우드 스테이징 / 운영(production)은 서로 다른 네 가지 개념이다** — 이
문서에서 "스테이징"이라고 하면 기본적으로 아래 표의 "로컬 스테이징"을
가리킨다(아직 클라우드 스테이징은 이 저장소에 없다).

| | dev(개발) | **로컬 스테이징** | 클라우드 스테이징(아직 없음) | production(아직 없음) |
|---|---|---|---|---|
| 실행 위치 | 개발자 로컬 Docker | 개발자 로컬 Docker | 클라우드(예정) | 클라우드 |
| DB | `postgres_data` 볼륨 | `investment-learning-staging_postgres_data` 볼륨(완전 분리) | 별도 클라우드 DB | 별도 클라우드 DB |
| Compose 파일 | `docker-compose.yml` | `docker-compose.yml` + `docker-compose.staging.yml` | (미정) | (미정) |
| `ENVIRONMENT` | `development` | `staging` | `staging` | `production` |
| 접근 범위 | `localhost`만 | **`localhost`/`127.0.0.1`만 — 인터넷 노출 금지** | 팀 내부(HTTPS) | 실제 사용자(HTTPS) |
| `COOKIE_SECURE` | `false` | `false`(로컬 HTTP 전용 예외, 아래 참고) | `true`(필수) | `true`(필수) |
| 목적 | 일상 개발 | PR 병합 전 "깨끗한 volume에서 처음부터" 배포 절차 리허설, 강의 게시 절차 리허설 | 실제 배포 전 마지막 확인 | 실서비스 |

**로컬 스테이징은 클라우드 스테이징을 대체하지 않는다.** 운영 배포 전에는
여전히 실제 클라우드 스테이징 환경(HTTPS, 팀이 접근 가능한 URL, 실제
비밀관리 서비스 연동)이 별도로 필요하다 — 이 브랜치는 그 클라우드 인프라를
만들지 않았다(범위 밖, 아래 "알려진 제한사항" 참고). 로컬 스테이징의
목적은 좁다: dev 환경/데이터와 완전히 분리된 상태에서 "빈 DB에서부터 migration
→ 시드 → 강의 게시" 전체 절차를 실수 없이 반복 연습하고 자동 검증하는 것이다.

### 왜 스테이징 DB와 운영 DB를 절대 공유하면 안 되는가

스테이징은 배포 절차·마이그레이션·백업/복원 절차를 "실패해도 안전하게"
반복 연습하는 곳이다. 운영 DB와 연결을 공유하면 스테이징에서의 실수(잘못된
마이그레이션 되돌리기, 테스트 데이터 삽입, 강의 게시 스크립트 오작동)가
그대로 실제 사용자 데이터를 훼손한다. 그래서 이 저장소는 여러 겹의
안전장치를 둔다: ① `docker-compose.staging.yml`이 `staging-postgres`라는
전용 네트워크 별칭의 완전히 분리된 named volume만 쓰고, ② `.env.staging`의
`DATABASE_URL` 호스트가 반드시 `staging-postgres`여야 하며, ③
`app/core/config.py`의 `Settings` 검증기가 `ENVIRONMENT=staging`일 때 그
호스트가 아니면(또는 URL에 `prod`로 보이는 문자열이 있으면) **앱 기동
자체를 거부**한다(`apps/api/tests/test_staging_settings.py`로 검증).

### 로컬 스테이징 기동

```bash
cd investment-learning-app
cp .env.staging.example .env.staging
# .env.staging을 열어 JWT_SECRET을 무작위 값으로 교체한다 (예: openssl rand -hex 32)
# — 예시 플레이스홀더를 그대로 두면 위 안전장치가 기동을 거부한다.

docker compose \
  --project-name investment-learning-staging \
  --env-file .env.staging \
  -f docker-compose.yml \
  -f docker-compose.staging.yml \
  up --build -d
```

편의 스크립트(`scripts/staging_up.sh`)는 위와 완전히 동일한 동작을 하며,
`.env.staging`이 없거나 예시 플레이스홀더가 남아있으면 컨테이너가
크래시루프하기 전에 미리 사람이 읽을 수 있는 오류로 중단한다.

- 접속 주소: 웹 http://localhost:3001 , API http://localhost:8001
  (dev의 3000/8000과 충돌하지 않는다 — dev를 동시에 띄워둬도 무방하다)
- Postgres는 기본적으로 호스트 포트를 열지 않는다(외부 노출 최소화).
  로컬 디버깅용으로 열어야 하면 `docker-compose.staging.yml`의 주석 처리된
  `127.0.0.1:5433:5432` 항목을 참고한다(항상 localhost 전용으로만 연다).
- 검증: `bash scripts/verify_staging.sh` — dev와 project name/volume이
  분리돼 있는지, web/API 헬스·readiness가 200인지, DB migration이 head와
  일치하는지, 데모 종목이 있는지, 1~5강은 공개(PUBLISHED)이고 6~15강은
  아직 게시 전(READY_FOR_REVIEW/REVIEW_REQUIRED)이며 일반 사용자 API로
  노출되지 않는지, 헬스 응답/로그에 비밀정보가 없는지, 재시작 후에도 데이터가
  유지되는지, backup/restore가 실제로 성공하는지까지 자동으로 확인한다.

### 중지·데이터 삭제

```bash
# 중지만 — 볼륨(DB 데이터)은 보존된다
docker compose \
  --project-name investment-learning-staging \
  --env-file .env.staging \
  -f docker-compose.yml \
  -f docker-compose.staging.yml \
  down
```

**데이터(volume)까지 완전히 삭제하는 명령은 별도다** — 기본 `down` 명령에는
`-v`를 절대 포함하지 않는다:

```bash
bash scripts/staging_reset_data.sh --yes-delete-staging-data
```

### 백업·복원 절차

```bash
bash scripts/staging_backup.sh          # backups/staging_<UTC타임스탬프>.dump 생성 (0바이트면 실패 처리)
bash scripts/staging_restore_test.sh    # 가장 최근 백업을 "임시 검증용" Postgres 컨테이너에만 복원해 확인
                                          # (원본 staging-postgres는 절대 건드리지 않는다)
```

`backups/`는 `.gitignore`에 등록돼 있다 — 백업 파일은 저장소에 커밋되지
않는다. 두 스크립트 모두 DB 비밀번호나 덤프 내용을 로그에 출력하지 않는다
(파일명·크기·행 수 같은 메타데이터만 출력).

### 강의(lesson-06~15) 게시 절차 (로컬 스테이징)

`scripts/publish_reviewed_lessons_staging.sh`는 `apps/api/scripts/publish_lesson.py`
(운영자 전용 CLI, `apps/api/README.md`·`docs/features/investment-lessons-06-15.md`
참고)를 로컬 스테이징 컨테이너 안에서 강의별로 하나씩 호출하는 래퍼다.
**사람 운영자가 실제 검수를 마친 뒤 직접 실행해야 하며, 에이전트가 스스로
`--execute`로 실행해서는 안 된다** — `publish_lesson.py` 자체의 설계 원칙과
동일하다.

```bash
# 1) 사전 점검만(기본값) — ENVIRONMENT/DB 호스트/최근 백업 존재/현재 lesson
#    상태를 확인만 하고 아무것도 바꾸지 않는다.
bash scripts/publish_reviewed_lessons_staging.sh

# 2) 실제 게시 — 사람 운영자가 검수 후에만 실행한다.
bash scripts/publish_reviewed_lessons_staging.sh --execute --reviewer="검수자 이름"
```

안전장치: `ENVIRONMENT=staging` 확인, `DATABASE_URL` 호스트가
`staging-postgres`인지 확인(운영으로 의심되면 즉시 중단), 24시간 이내 백업이
있는지 확인, 강의별 `content_version`/`source_url` 유무를 조회해
`--source-verified` 값과 모순되면(예: 출처 URL이 있는데 false로 지정하려는
경우) 그 즉시 전체 시퀀스를 중단, 한 강의라도 실패하면 이후 강의는 처리하지
않고 중단, 실행 후 상태·감사기록(`lesson_review_audits`) 재조회, 동일 명령
재실행 시 이미 승인된 강의는 `publish_lesson.py` 자체의 멱등성 덕분에 건너뛴다.

### 게시된 강의(lesson-06~15) 스테이징 E2E (Playwright)

`apps/web/e2e-staging/`는 **이미 게시가 끝난 로컬 스테이징**을 대상으로 하는
전용 Playwright 스펙이다. `apps/web/e2e/`(기존 개발용 E2E)와는 설정·테스트
디렉터리·실행 명령이 전부 분리돼 있고 서로 절대 공유하지 않는다.

| | 기존 개발 E2E (`apps/web/e2e/`) | 스테이징 E2E (`apps/web/e2e-staging/`) |
|---|---|---|
| 설정 파일 | `playwright.config.ts` | `playwright.staging.config.ts` |
| 대상 | 자체 기동한 `next dev` + 자체 마이그레이션한 **개발 DB**(포트 3100/8100, `postgresql://app:app@localhost:5432/...`) | **이미 떠 있는 로컬 스테이징**(포트 3001/8001) — webServer를 전혀 기동하지 않는다 |
| 전제 조건 | 매 실행 fresh DB(빈 상태에서 migrate) | 스테이징 DB가 **lesson-06~15 게시(PUBLISHED/REVIEWED) 완료** 상태여야 함 — 게시 전이면 목록·제목 검증이 실패한다 |
| 실행 명령 | `npm run test:e2e` | `npm run test:e2e:staging` 또는 `scripts/staging_e2e_run.sh` |
| 개발 포트(3000/8000/5432) 접근 | 함(그 자체가 대상) | 하지 않음 — 설정 로드 시점에 강제 차단 |
| production/클라우드 접근 | 하지 않음 | 하지 않음 — `STAGING_E2E_ALLOW_REMOTE=true`를 명시하지 않는 한 localhost 외 URL은 즉시 거부 |

**이미 실행 중인 로컬 스테이징을 대상으로 실행하는 명령** (스택을 재빌드·재시작하지
않는다 — `scripts/staging_up.sh`로 이미 떠 있어야 한다):

```bash
# 권장: 게시 상태/감사기록이 실행 전후 동일한지까지 자동으로 대조하는 래퍼
cd investment-learning-app
bash scripts/staging_e2e_run.sh

# 또는 Playwright만 직접 실행(웹앱 디렉터리 안에서)
cd investment-learning-app/apps/web
npm ci                         # 최초 1회
npx playwright install --with-deps chromium   # 최초 1회
npm run test:e2e:staging
```

기본 대상은 `http://localhost:3001`(web) / `http://localhost:8001`(API)이다.
`STAGING_WEB_BASE_URL` / `STAGING_API_BASE_URL` 환경변수로 덮어쓸 수 있지만,
localhost/127.0.0.1이 아닌 값이나 개발 포트(3000/8000/5432)를 주면 설정 로드
시점에 즉시 에러로 중단된다(운영/클라우드 오접속 방지).

**테스트 계정 데이터**: 매 실행 UUID 기반의 새 이메일(`staging-e2e-<태그>-<uuid>@example.com`)로만
회원가입한다 — 기존 사용자나 기존 진도 데이터를 절대 재사용하지 않는다. 생성된
테스트 계정과 그 진도·퀴즈 응시 기록은 **정리되지 않고 그대로 남는다** — 로컬
스테이징은 필요하면 언제든 `scripts/staging_reset_data.sh --yes-delete-staging-data`로
전체 초기화 가능한 일회성 데이터이므로 허용했다. UUID 기반 고유 이메일이라 기존
데이터와 충돌하지 않는다. 이 스펙은 실제 투자 주문을 생성하지 않고,
`lesson_review_audits`나 강의 게시 상태(`status`/`review_status`)를 직접 바꾸는
API도 호출하지 않는다 — `scripts/staging_e2e_run.sh`가 실행 전후 두 값을
읽기 전용 SELECT로 대조해 이를 보증한다.

**CI fixture 게시 vs 실제 게시 승인**: `.github/workflows/investment-learning-staging-published-lessons-e2e.yml`은
매 실행마다 완전히 새로운 일회용 스테이징을 기동해 `--reviewer="ci-human-review-fixture"`로
강의를 게시한 뒤 이 E2E를 실행한다. **이 CI가 초록불이라는 것은 "게시 파이프라인이
기술적으로 동작한다"는 뜻일 뿐, 실제 콘텐츠에 대한 사람의 검수·승인을 의미하지
않는다.** 실제(로컬이든 향후 클라우드든) 게시는 반드시 사람 검수자가 본문·퀴즈를
직접 읽고 `--reviewer="<실명>"`으로 스스로 실행해야 한다 — 위
["강의(lesson-06~15) 게시 절차"](#강의lesson-06~15-게시-절차-로컬-스테이징) 참고.

### `COOKIE_SECURE=false` 예외 — 반드시 읽을 것

`.env.staging.example`의 기본값은 `COOKIE_SECURE=false` +
`STAGING_ALLOW_INSECURE_COOKIE=true`다. **이것은 "로컬 Docker Compose에서
순수 HTTP(`http://localhost`)로만 테스트한다"는 의도적인 예외이며, 이
조합으로 띄운 인스턴스를 절대 인터넷에 노출해서는 안 된다.** 클라우드에
어떤 형태로든 배포하는 순간(포트포워딩·터널링·리버스프록시 포함) 이
조합은 인증 쿠키가 평문으로 오갈 수 있다는 뜻이 된다. 실제 HTTPS로 서빙되는
클라우드 스테이징/운영에서는 `COOKIE_SECURE=true`가 필수이며(위 표),
`app/core/config.py`의 검증기가 `STAGING_ALLOW_INSECURE_COOKIE=true` 없이
`COOKIE_SECURE=false`를 쓰면 기동 자체를 거부한다 — 즉 이 예외는 명시적으로
켜야만 동작하고, 켜면 컨테이너 시작 로그에 경고가 남는다.

### CI에서의 로컬 스테이징 검증

`.github/workflows/investment-learning-staging-ci.yml`이 매 PR·main 푸시마다
빈 volume에서부터 스테이징 스택 전체를 새로 기동해
`scripts/verify_staging.sh`(backup/restore-to-temp-DB, 재시작 후 데이터 유지
포함)를 실행하고 항상 `-v`로 정리한다. **이 워크플로가 띄우는 인스턴스는
그 실행 안에서만 존재하는 일회용(ephemeral) 검증 환경이다** — 상시
운영되는 서버가 아니며, 실제 클라우드 스테이징을 대체하지 않는다. Repository
secret은 쓰지 않는다 — `JWT_SECRET` 등은 매 실행마다 무작위로 새로 생성해
로그에 마스킹 처리한다(`.github/scripts/generate_ci_staging_env.sh`).

`.github/workflows/investment-learning-staging-published-lessons-e2e.yml`은 이
워크플로의 **명확한 후속 단계**(별도 파일, main에서의 성공 이후 `workflow_run`으로
연결됨)로, 매번 새로 기동한 일회용 스택에서 `--reviewer="ci-human-review-fixture"`로
강의를 게시한 뒤 위 "게시된 강의 스테이징 E2E" 절의 Playwright 스펙을 실행하고
항상 정리한다. 이 워크플로가 성공해도 실제 콘텐츠 게시 승인을 의미하지 않는다 —
바로 위 "CI fixture 게시 vs 실제 게시 승인" 절 참고.

### 알려진 제한사항 (로컬 스테이징 범위)

- 이 저장소를 개발한 샌드박스는 Docker 데몬을 구동할 수 없어(중첩 컨테이너
  미지원), `docker compose ... up --build`로 스테이징 스택을 이 세션에서
  직접 기동해 검증하지는 못했다. `docker compose config`로 두 compose
  파일(`docker-compose.yml` + `docker-compose.staging.yml`) 병합 결과가
  올바른지(포트·볼륨·env_file이 dev와 완전히 분리되는지)는 직접 확인했고,
  `app/core/config.py`의 staging 안전 검증기는 pytest로 실제 실행해
  확인했다(`apps/api/tests/test_staging_settings.py`). 실제 기동·health·
  migration/seed·backup/restore·재시작 유지 검증은 위 GitHub Actions
  워크플로가 실제 Docker 데몬이 있는 Ubuntu runner에서 수행한다 — 실행
  결과는 PR의 Checks 탭에서 확인할 수 있다.
- 실제 클라우드 스테이징 환경(HTTPS, 별도 클라우드 DB, 비밀관리 서비스
  연동)은 이 브랜치에도 아직 없다 — 운영 배포 전에는 별도로 구성해야 한다.
- `scripts/publish_reviewed_lessons_staging.sh`는 이번 작업에서 만들고
  사전 점검(`--execute` 없이 실행)까지만 확인했다 — 실제 게시(`--execute`)는
  사람 운영자가 검수를 마친 뒤 별도로 실행해야 한다.

## 현재 진행 상태

- [x] 저장소 골격 구성
- [x] 제품 명세 문서화
- [x] 초기 아키텍처 결정 확정 (`docs/adr/0001-initial-decisions.md`: 한국+미국 동시 지원,
      무료 시세 API로 시작, AI 코치는 Anthropic Claude API. 무료/유료 경계 등 일부는 대기)
- [x] Phase 1: 인증(회원가입·로그인·refresh 회전)·DB 마이그레이션·CI
- [x] Phase 3 핵심: 모의투자 원장·주문·체결 (한국·미국 이중 시장, KR/US 수수료·세금
      정책, 8단계 주문 검증, idempotency, 포지션·성과 조회) — 장 운영시간 검증, 기업행사,
      비동기 재평가 워커는 후속 작업으로 남음 (`apps/api/README.md` 참고)
- [x] 시장 데이터: 종목 검색·상세·bars API 구현. **단, 라이브 수집은 이 개발 세션의
      샌드박스 egress 정책상 검증하지 못함** — 지금은 데모용 정적 샘플 4종목만 조회
      가능 (`services/market-data-worker/README.md` 참고, 운영 투입 전 재검증 필요)
- [x] Phase 2 핵심: 학습 엔진 (콘텐츠 계층, 진도, 퀴즈 채점, 서버 계산 XP·연속학습일).
      1~15강 시드 완료(6~15강 10개는 시드 시점에 전부 READY_FOR_REVIEW —
      사람 검수자가 `scripts/publish_lesson.py`로 개별 승인해야 공개된다.
      `docs/features/investment-lessons-06-15.md` 참고), 16~30강
      콘텐츠 작성은 후속 작업으로 남음. 7일 챌린지·과정 중심 배지는 구현 완료
      (`docs/features/seven-day-challenge.md` 참고)
- [x] Phase 4 핵심: 투자일지(거래 전/후, 버전 보존)·과정 점수(7.3)·행동편향 탐지 3종
      (확증편향·처분효과·집중위험)·AI 코치 파이프라인(검색→정량엔진→LLM→정책필터→출처
      표시). **단, `ANTHROPIC_API_KEY`가 이 개발 세션에 설정되어 있지 않아 실제 LLM
      호출은 검증하지 못함** — 지금은 규칙 기반 graceful degradation 경로만 실제로
      동작을 확인했다 (`apps/api/README.md` 참고, 운영 투입 전 실제 키로 재검증 필요)
- [x] 핵심 End-to-End 사용자 흐름: `apps/web`(Next.js) 프런트엔드로 회원가입→1강
      학습→퀴즈 제출/XP→종목 검색→거래 전 일지→가상 시장가 매수→포트폴리오 반영→
      거래 후 복기→규칙 기반 AI 코칭까지 실제 API에 연결. 새로고침·재로그인 후 데이터
      유지, 로딩·빈 상태·오류·시세 지연 표시, 모든 주문 화면의 가상자금 명시를
      Playwright E2E 테스트(`apps/web/e2e/full-flow.spec.ts`)로 검증했다. 이 흐름을
      완성하며 백엔드에 읽기 전용 보완 엔드포인트 3개(`GET /v1/quizzes/{id}`,
      `GET /v1/journals/{id}`, `GET /v1/me/journals`)와 CORS 설정, 주문↔일지
      `order_id` 자동 연결(처분효과 탐지에 필요)을 추가했다(`apps/api/README.md`
      참고). 범위 밖: 실제 투자·증권계좌 연결, 6~30강, 나머지 4개 행동편향 유형,
      실시간 시세 공급자 교체, 실제 Claude API 연결, 디자인 전면 개편.
- [x] 보안 강화: 인증 토큰을 프런트엔드 `localStorage`(JS로 읽을 수 있어 XSS에
      취약)에서 서버가 관리하는 **HttpOnly Secure 쿠키**로 전환했다. access/refresh
      토큰은 이제 API 응답 JSON에 전혀 포함되지 않으며, `Authorization: Bearer`
      헤더 방식은 완전히 제거했다. CSRF는 `SameSite=Lax` 쿠키 + 상태변경 요청
      Origin 검증 미들웨어 조합으로 방어한다. production 환경은 안전하지 않은 쿠키
      설정(`COOKIE_SECURE=false` 등)이면 앱 기동 자체가 실패하도록 막아뒀다.
      refresh-token 회전·재사용 탐지는 기존 로직을 그대로 유지했다. 자세한 쿠키
      정책·CSRF 근거는 `apps/api/README.md`, 프런트엔드 변경사항은
      `apps/web/README.md` 참고.
- [x] Staging release 준비: `docker compose up --build` 한 번으로 Postgres·API·
      웹을 함께 띄울 수 있게 했다 — API/Web production Dockerfile(multi-stage,
      non-root, healthcheck), migration+시드+데모 시세 새로고침을 순서대로
      실행하고 실패 시 조용히 넘어가지 않는 API entrypoint 스크립트,
      `/health/live`·`/health/ready` 엔드포인트, 반복 실행해도 안전한 smoke
      test 스크립트(`apps/api/scripts/smoke_test.py`), 프런트엔드 CI와 Docker
      이미지 빌드 CI를 새로 추가했다. **단, 이 개발 세션의 샌드박스가 Docker
      데몬을 실제로 구동할 수 없어(중첩 컨테이너 미지원) `docker compose up
      --build` 자체는 이 환경에서 실행해 검증하지 못했다** — 구성 유효성
      (`docker compose config`)과 Docker 밖에서의 개별 요소(Next.js standalone
      프로덕션 서버 등) 동작은 확인했다. 실제 Docker 환경에서 최초 실행 시
      한 번은 직접 확인을 권장한다(`apps/api/README.md`, `apps/web/README.md`
      참고). 범위 밖: 외부 클라우드 실배포, 라이브 시장 데이터·실제 LLM
      연동, 유료 리소스.
- [x] 시장 데이터 공급자 추상화 + stale valuation 안전성 (Phase A): 한국·미국에
      서로 다른 공급자를, 개발용과 운영용을 분리해 붙일 수 있도록
      `MarketDataProvider` 추상화를 도입했다(`DemoMarketDataProvider` — 외부
      네트워크 없이 결정론적 합성 데이터, `StooqMarketDataProvider` — 개발·
      기술검증 전용, production에서는 기동 자체가 거부됨). 주문 경로의 stale
      차단(900초 초과 시 409)은 그대로 유지하면서 판단 로직을 한 곳
      (`market_data_service.get_price_point`)으로 모았고, 포트폴리오 조회에
      FRESH/STALE/UNAVAILABLE 상태를 추가했다 — STALE은 참고값+경고+기준시각과
      함께 표시하고, UNAVAILABLE은 0원·손실로 계산하지 않으며 합계에서만
      제외한다(목록에서 사라지지 않는다). 새 DB migration은 없다(기존
      bars/fx_rates로부터 요청 시점에 계산). 시장 데이터 파서·검증·업서트
      단위테스트를 신규로 33종 추가했다(이전에는 0건이었다). 범위 밖: 실제
      상용 공급자 연동, WebSocket·실시간화, 기업행사 반영, PlayMCP 조사(사용자
      결정에 따라 이번 Phase에서 승인하지 않음), 유료 API 호출(예산 0원).
- [x] 7일 학습 챌린지 + 과정 중심 배지 시스템: 기존 학습·퀴즈·XP·투자일지·
      모의투자를 하나의 흐름으로 잇는 초보자용 7일 챌린지를 추가했다. 새
      테이블 8개(challenges/challenge_days/challenge_missions/
      user_challenges/user_challenge_days/user_mission_progress/
      badge_definitions/user_badges)만 추가했고 기존 테이블은 손대지
      않았다. 모든 미션 완료·Day 상태·챌린지 상태·XP·배지는 서버가
      계산하며(EXPIRED·Day 상태는 DB에 저장하지 않고 조회 시점에 계산),
      각 미션은 실제 근거(LessonProgress/QuizAttempt/JournalEntry/
      Portfolio/AiMessage)를 서버가 소유권까지 검증한 뒤에만 완료
      처리한다 — 수익률이나 거래 횟수는 그 어떤 미션·배지 조건에도 쓰지
      않았다. 시간대는 `zoneinfo`로 DST-safe하게 계산하고 챌린지 시작
      시점에 고정하며, 하루를 놓쳐도 즉시 실패시키지 않고 이전 Day를
      계속 완료할 수 있다. XP 중복 지급은 `UserMissionProgress`/
      `UserBadge`의 unique 제약 + SAVEPOINT 패턴으로 막고, 챌린지 완주
      보너스는 compare-and-swap으로 정확히 한 번만 지급한다. 프런트엔드에
      `/challenge`(소개→시작→7일 진행 지도→완주 축하), `/badges`, 홈 화면
      위젯(PnL은 표시하지 않음)을 추가했다. 실제 푸시 발송 없이 조회
      시점에 계산되는 인앱 알림 스텁(`GET /v1/me/notifications`)도
      추가했다 — 매수를 종용하거나 조급함을 자극하는 문구는 쓰지 않는다.
      백엔드 테스트 27종, Playwright E2E 3종을 새로 추가했고 기존 전체
      테스트·E2E는 회귀 없이 그대로 통과한다. 자세한 내용은
      `docs/features/seven-day-challenge.md` 참고. 범위 밖: 실제 푸시,
      리더보드·친구 경쟁, 현금·쿠폰 보상, 6~30강 본편, 관리자를 통한 수동
      배지 지급(이 저장소에 아직 관리자 권한 체계가 없음).
- [x] 행동편향 탐지 7종 완성 (7.4): 기존에 구현돼 있던 확증편향·처분효과·
      집중위험 3종에 이어 나머지 4종(추격매수·손실회피·물타기 집착·
      과잉매매)을 `services/coaching.py`에 규칙 기반으로 추가했다. 추격매수는
      최근 N거래일 급등 + 진입 조건 미기재를, 손실회피는 체결과 연결된
      일지에서 손절 조건이 반복 변경됐는지를(자유 텍스트라 "하향" 방향까지는
      파싱하지 않고 변경 횟수를 신호로 씀), 물타기 집착은 직전보다 낮은
      가격에 같은 종목을 추가매수하면서 그 사이 새 투자 논리를 기록하지
      않았는지를, 과잉매매는 설정 가능한 시간창(기본 24시간) 안의 주문
      건수 급증을 본다. 전부 기존 3종과 동일하게 "진단"이 아니라 "관찰된
      거래 패턴"으로만 표현하고, `/v1/me/bias-report`·AI 코칭 프롬프트·
      7일 챌린지 Day6 BIAS_REVIEW 미션에 코드 변경 없이 그대로 반영된다
      (기존 코드가 이미 편향 유형에 무관하게 일반화돼 있었다). 새 임계치는
      운영 설정으로 뺐다(`chasing_rally_*`, `overtrading_*`). 신규 백엔드
      테스트 9종 추가, 기존 전체 테스트는 회귀 없이 그대로 통과한다. 범위
      밖: 자유 텍스트 손절 조건의 방향(상향/하향) 자동 판별 — 정규식·NLP
      없이는 오탐 위험이 커서 "반복 변경 횟수"로만 관찰한다.
- [x] 로컬 스테이징 환경 (`chore/local-staging-environment`): 기존
      `docker-compose.yml`을 건드리지 않고 `docker-compose.staging.yml`
      오버라이드 + `.env.staging.example`로, dev와 project name·포트·named
      volume이 전부 분리된 로컬 전용 스테이징 스택을 추가했다. dev
      서비스까지 함께 뜨는 것을 막기 위해 새 서비스 키를 만들지 않고 기존
      키(postgres/api/web)를 오버라이드하면서 네트워크 별칭(`staging-postgres`
      등)으로 스테이징 전용 호스트명을 부여했다 — Compose가 `ports`/`env_file`
      리스트를 파일 간에 대체가 아니라 합산한다는 점을 실측으로 확인하고
      `!override` 병합 태그로 바로잡았다(자세한 내용은 compose 파일 주석
      참고). `app/core/config.py`에 `ENVIRONMENT=staging` 전용 안전 검증기를
      추가해 `DATABASE_URL` 호스트가 `staging-postgres`가 아니거나, 운영처럼
      보이는 문자열이 있거나, 예시 비밀값을 그대로 쓰거나, CORS origin이
      loopback이 아니면 앱 기동 자체를 거부한다(`COOKIE_SECURE=false`는
      `STAGING_ALLOW_INSECURE_COOKIE=true`를 명시해야만 하는 로컬 전용
      예외로 별도 처리, `apps/api/tests/test_staging_settings.py`).
      `scripts/staging_{up,down,reset_data,backup,restore_test}.sh`,
      `scripts/verify_staging.sh`(요구된 검증 항목 전부), 그리고 사람 운영자
      전용 `scripts/publish_reviewed_lessons_staging.sh`(사전 점검까지만 이번
      작업에서 실행, 실제 게시는 하지 않음)를 추가했다. GitHub Actions
      워크플로(`investment-learning-staging-ci.yml`)가 매 PR·main 푸시마다
      빈 volume에서부터 스테이징 스택을 새로 띄워 전체 검증(health/readiness/
      migration/seed/노출/비밀정보/재시작 유지/backup+restore)을 수행하고
      항상 정리한다. **이 개발 세션은 Docker 데몬을 구동할 수 없어(중첩
      컨테이너 미지원) 실제 기동은 검증하지 못했다** — `docker compose
      config`로 두 compose 파일 병합 결과(포트·볼륨·env_file 분리)를
      직접 확인했고, 새 pytest는 실제로 실행해 통과를 확인했으며, 실제
      기동·backup/restore·재시작 유지 검증은 위 CI 워크플로가 수행한다. 실제
      클라우드 스테이징 환경은 이 브랜치에도 없다 — 운영 배포 전 별도 구성이
      필요하다(README "로컬 스테이징 환경" 절 참고).
