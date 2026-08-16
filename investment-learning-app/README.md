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
│  ├─ mobile/            # Flutter 앱
│  ├─ admin-web/         # Next.js 관리자 웹
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

## 로컬 개발 시작

```bash
cd apps/api
cp .env.example .env
docker compose -f ../../infra/docker/docker-compose.yml up -d   # Postgres, Redis
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload
```

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
- [ ] 학습 엔진 MVP (Phase 2)
- [ ] 투자일지·AI 코칭 MVP (Phase 4)
