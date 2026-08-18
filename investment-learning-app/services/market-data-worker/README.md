# market-data-worker

시장 데이터 수집·정규화 (6.4). OHLCV, 호가/체결 근사, 거래소 영업일·세션, 환율,
기업행사, 기본 재무·밸류에이션 지표를 수집하고 결측·이상치·중복을 검증한다.

## 현재 상태

Provider 추상화·검증·upsert 로직은 `apps/api/app/domain/services/market_data.py`에
구현되어 있고(별도 프로세스로 분리되지 않은 상태, `simulation-worker`와 동일한
임시 구조), `apps/api/scripts/ingest_market_data.py`로 수동 실행할 수 있다.

**중요: 라이브 연동은 이 개발 세션에서 검증하지 못했다.** 구현해 둔
`StooqProvider`(stooq.com 무료 CSV)는 이 세션의 샌드박스 아웃바운드 정책이
금융 데이터 호스트에 대한 egress를 차단하고 있어(`curl`로 확인, 403 policy
denial) 실제로 데이터를 받아오는지 테스트하지 못했다. egress가 허용된 환경에서
반드시 먼저 소규모로 재검증한 뒤 사용해야 한다. ADR 0001의 "무료 API로 시작"
결정은 이 provider를 후보로 남겨두되, 운영 투입 전 데이터 정확성·재배포 라이선스
조건을 재확인해야 한다 (6.4 규칙, 19장 법률 체크리스트).

지금 API가 서빙하는 종목/시세 데이터는 라이브 수집이 아니라 데모용 시드
마이그레이션(`alembic/versions/..._seed_sample_instruments_and_bars...py`)의
정적 샘플 4종목(삼성전자, SK하이닉스, AAPL, MSFT)이다. 이 데이터의
`source`는 `"seed-sample"`로 표시되며 실거래 판단 근거가 될 수 없다.

## 아직 없는 것

- 거래소 영업일·세션(market_sessions), 환율 실시간 파이프라인(현재 `fx_rates`는
  seed 플레이스홀더), 기업행사(corporate_actions), 재무지표(fundamentals)
- 이 로직을 실제 별도 프로세스/스케줄러로 분리하는 작업 (현재는 apps/api 안의
  모듈 + 수동 CLI 스크립트)
- 데이터 공급자와의 재배포 라이선스 계약 (19장 법률 체크리스트 필수 항목)
