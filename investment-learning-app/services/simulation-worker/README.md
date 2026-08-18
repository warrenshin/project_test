# simulation-worker

모의 체결 엔진 (6.6-6.7). 시장가·지정가 체결 근사, 비용(수수료·세금·환전 스프레드)
계산, 기업행사 반영을 담당한다. at-least-once 실행을 전제로 idempotent하게 설계한다.

## 현재 상태

체결 로직 자체는 `apps/api/app/domain/services/execution.py`에 동기 방식으로
구현되어 있고, `POST /v1/portfolios/{portfolio_id}/orders` 요청 안에서 즉시
호출된다 (MARKET은 즉시 체결, LIMIT은 최신 bar 기준으로 체결 가능하면 체결,
아니면 ACCEPTED로 대기).

**아직 없는 것**: 이 별도 worker 프로세스 자체. 지금은 LIMIT 주문이 최초 요청
시점에 체결되지 못하면 새 시세가 들어와도 재평가되지 않고 ACCEPTED 상태로
남는다. 이 worker가 생기면:

- Redis/Celery 큐에서 미체결 주문을 소비해 새 bar 도착마다 재평가
- 기업행사(액면분할·배당 등) 반영
- `execution.py`의 `build_quote`/`execute_order`를 그대로 재사용 가능하도록 설계됨
  (DB 세션과 도메인 모델에만 의존, API 레이어와 분리되어 있음)
