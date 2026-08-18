# Web (Next.js)

`apps/api`(FastAPI)와 통신하는 사용자용 프런트엔드. React 19 + Next.js 16 App Router +
TypeScript, 별도 CSS 프레임워크 없이 `src/app/globals.css`의 디자인 토큰만 사용한다.

**인증(2026-08부터)**: 서버가 관리하는 HttpOnly Secure 쿠키 기반 인증을 쓴다.
access/refresh 토큰은 JavaScript가 절대 읽거나 저장하지 않는다 — `localStorage`에
아무 것도 남기지 않으며, `Authorization` 헤더도 만들지 않는다. `src/lib/api.ts`의
모든 요청은 `credentials: "include"`로 쿠키를 함께 보내고, 로그인 상태는
`GET /v1/auth/me`로 서버에 물어 확인한다(`src/lib/auth-context.tsx`). 자세한 정책은
`apps/api/README.md`의 "인증 쿠키 정책"/"CSRF 방어" 절 참고.

이전 버전 사용자가 남긴 `localStorage`의 예전 토큰은 앱 시작 시 값을 읽거나
서버로 보내지 않고 즉시 삭제한다(`src/lib/api.ts`의
`purgeLegacyLocalStorageTokens`) — 삭제된 예전 세션의 사용자는 다시 로그인해야
한다. 이 마이그레이션 코드는 예전 세션이 모두 자연 만료(refresh 최대 수명, 기본
30일)된 뒤에는 안전하게 제거할 수 있도록 별도 함수로 분리해 두었다.

## 핵심 사용자 흐름

회원가입 → 학습(강의·퀴즈·XP) → 종목 검색·상세 → 거래 전 투자일지 → 가상 시장가
주문 → 포트폴리오 반영 → 거래 후 복기 → 규칙 기반 AI 코칭 확인

모든 화면은 로딩·빈 상태·API 오류(`ErrorBlock`+재시도)·시세 지연 상태를 표시하며,
주문 관련 화면은 항상 `VirtualFundsBanner`로 가상자금·모의투자임을 명시한다
(`src/components/States.tsx`, `src/components/VirtualFundsBanner.tsx`,
`src/components/MarketDataBadge.tsx`).

## 로컬 실행

백엔드(`apps/api`)가 먼저 떠 있어야 한다. `apps/api/README.md`를 따라
Postgres 기동·마이그레이션·`uvicorn`까지 실행한 뒤:

```bash
cd apps/web
npm install
npm run dev            # http://localhost:3000
```

기본적으로 `http://localhost:8000`의 API를 호출한다. 다른 포트/호스트를 쓰려면
`NEXT_PUBLIC_API_BASE_URL` 환경변수를 설정한다(예: `.env.local`).

백엔드는 기본적으로 `http://localhost:3000`, `http://127.0.0.1:3000` origin만
CORS를 허용한다(`apps/api/app/core/config.py`의 `cors_allowed_origins_raw`). 다른
포트에서 프런트엔드를 띄우면 백엔드 쪽 `CORS_ALLOWED_ORIGINS_RAW` 환경변수도 함께
맞춰야 한다.

### 데모 시세가 "오래되었다"고 주문이 거부될 때

이 프로젝트는 라이브 시세 공급자 없이 데모 종목 4개(삼성전자/SK하이닉스/AAPL/MSFT)의
시드 데이터만 사용한다(아래 "알려진 제한" 참고). 서버는 시세 기준시각이
`market_data_staleness_threshold_seconds`(기본 900초)보다 오래되면 주문을 거부한다.
DB를 오래 띄워두고 개발하다 보면 시드 시세가 이 기준을 넘겨 매수/매도가 막힐 수 있다.
이때는 `apps/api`에서 아래 스크립트로 데모 종목 최신 bar의 as_of만 현재 시각으로
새로고침한다(가격 자체는 바꾸지 않는다):

```bash
cd apps/api
python -m scripts.refresh_demo_market_data
```

## E2E 테스트 (Playwright)

`e2e/full-flow.spec.ts`는 위 핵심 흐름 전체를 브라우저로 실제 클릭해가며 검증하고,
새로고침·재로그인 후에도 데이터(포트폴리오 보유 종목, 일지 복기 결과)가 유지되는지도
함께 확인한다. 이어서 로그아웃 후 보호 화면 접근이 막히는지(뒤로가기로 이전 화면이
bfcache에서 되살아나도 보호 데이터가 노출되지 않는지)와, access token 만료 시
refresh가 요청당 최대 1회만 재시도되는지(동시에 여러 요청이 401을 받아도 refresh
호출은 한 번만 나가는 single-flight 동작, refresh까지 실패하면 로그인 화면으로
이동하고 무한 재시도하지 않는 것)를 별도 `describe` 블록으로 검증한다.

```bash
cd apps/web
npm install
npx playwright test
```

`playwright.config.ts`가 API(`:8100`)와 웹(`:3100`) 개발 서버를 테스트 실행 시
자동으로 띄우고 종료한다(수동으로 서버를 미리 켜둘 필요 없음). API 서버를 띄우기
직전에 `scripts.refresh_demo_market_data`를 자동으로 실행해 위의 "시세가 오래됨"
문제를 피한다. 로컬 Postgres(`investment_learning` DB, 계정 `app`/`app`)가 떠 있고
`alembic upgrade head`까지 적용되어 있어야 한다.

Chromium은 샌드박스에 사전 설치되어 있어(`/opt/pw-browsers/chromium`) `playwright
install`을 실행할 필요가 없다(`playwright.config.ts`의 `launchOptions.executablePath`
참고).

퀴즈 정답 선택은 시드 마이그레이션(`6f55307ed5e8_seed_first_5_lessons_with_quizzes`)에서
각 문항의 첫 번째 선택지가 정답으로 고정되어 있다는 점에 의존한다 — 시드 데이터를
바꾸면 이 테스트도 함께 갱신해야 한다.

## 알려진 제한 (이번 범위에서 의도적으로 다루지 않음)

- 데모 종목 4개(삼성전자/SK하이닉스/AAPL/MSFT)만 조회·거래 가능. 실시간 시세 공급자
  연동은 이번 범위 밖이다(`apps/api/README.md`의 market-data-worker 항목 참고).
- AI 코칭은 이 환경에 `ANTHROPIC_API_KEY`가 없어 규칙 기반 폴백 경로만 실제로
  검증했다. 코칭 결과의 `degraded: true`가 폴백 경로임을 나타낸다.
- 주문은 시장가만 화면에서 지원한다(API 자체는 지정가도 지원하지만 주문 화면에는
  노출하지 않았다).
- 학습 콘텐츠는 1~5강만 있다. 6강 이후는 `/learn` 목록에 나타나지 않는다.
- 디자인은 기존 최소 디자인 시스템(`globals.css`)을 그대로 사용했고 전면 개편은
  하지 않았다.
