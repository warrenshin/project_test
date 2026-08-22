# 7일 학습 챌린지 · 과정 중심 배지 시스템

기존 학습·퀴즈·XP·투자일지·모의투자 기능을 하나의 흐름으로 잇는 초보자용
7일 챌린지다. **평가 대상은 언제나 "과정"이지 "결과"가 아니다** — 이 문서
전체에서 반복해서 확인할 수 있듯, 어떤 미션·배지도 수익률이나 거래 횟수를
조건으로 삼지 않는다.

## 1. 제품 목적과 보상 원칙

초보 투자자가 실제 자금을 넣기 전에 반드시 거쳐야 할 습관 — 학습, 투자
논리 문서화, 반대 근거 검토, 손실 제한 조건 설정, 복기 — 을 7일 안에
체험하게 만드는 것이 목적이다.

**보상하는 것**: 강의 완료, 퀴즈 이해도(통과), 거래 전 일지 작성, 반대
근거 기록, 손실 제한 조건 작성, 거래 후 복기, 계획 준수 여부 기록, 꾸준한
학습(서로 다른 날짜에 걸친 학습).

**절대 보상하지 않는 것**: 높은 수익률, 많은 주문 횟수, 큰 투자 금액,
특정 종목 매수, 연속 손실 후 추가 매수. 이 목록에 해당하는 어떤 지표도
미션 완료 조건이나 배지 조건, XP 지급 조건으로 쓰이지 않는다 — 아래 미션
표와 배지 표를 봐도 "수익률"이나 "거래 횟수"라는 단어 자체가 등장하지
않는다.

이렇게 설계한 이유는 단순하다: 초보자에게 "잘하고 있다"는 신호를 결과(운이
크게 개입하는 단기 수익률)가 아니라 스스로 통제할 수 있는 행동(계획을
세우고, 반대 의견을 찾고, 손실 조건을 정하고, 복기하는 것)에서 받게
하기 위해서다. 결과 기반 보상은 손실 회피·확증편향·과최적화 같은 행동
편향을 오히려 강화할 위험이 있다.

## 2. Day별 미션 구성

콘텐츠는 최대한 기존 1~5강을 재사용한다. Day 2/4/6처럼 대응하는 기존
강의가 없는 경우, 길게 새로 만들지 않고 기존 `Lesson`/`Quiz` 모델을 그대로
쓰는 아주 짧은(문항 2개짜리 퀴즈) "챌린지 전용 교육카드"를 만들었다 —
`Lesson`에 이미 `source`/`reviewed_by`/`reviewed_at`/`status` 필드가 있어
출처·검수 상태를 그대로 관리할 수 있기 때문에 별도 모델을 만들지 않았다.
이 카드들은 "투자 시작하기" 코스 아래 "보충: 7일 챌린지 카드" 모듈에
속한다.

| Day | 주제 | 미션 | 유형 | XP | 콘텐츠 출처 |
|---|---|---|---|---|---|
| 1 | 투자와 위험 | 1강 학습 | LESSON_COMPLETE | 10 | 기존 1강 "투자는 무엇인가" |
| | | 1강 퀴즈 통과 | QUIZ_PASS | 15 | 기존 퀴즈 |
| | | 이번 주 학습목표 정하기 | GOAL_NOTE (5자↑) | 10 | 신규(텍스트 입력) |
| 2 | 주문 방식 이해 | 주문 방식 카드 학습 | LESSON_COMPLETE | 10 | 챌린지 카드 |
| | | 시장가·지정가 퀴즈 통과 | QUIZ_PASS | 15 | 챌린지 카드 |
| | | 가상 주문 미리보기 | ORDER_PREVIEW | 15 | 실제 체결 불필요, 예상 비용만 확인 |
| 3 | 투자 논리 작성 | 거래 전 일지 완성 | JOURNAL_PRE_TRADE | 25 | 기존 투자일지 기능 |
| 4 | 분산과 집중위험 | 분산과 집중위험 카드 학습 | LESSON_COMPLETE | 10 | 챌린지 카드 |
| | | 분산투자 퀴즈 통과 | QUIZ_PASS | 15 | 챌린지 카드 |
| | | 내 포트폴리오 집중도 확인 | PORTFOLIO_CONCENTRATION_REVIEW | 10 | 추가 주문 불필요, 조회만 |
| | | 분산투자 교육 시나리오 | SCENARIO_CHOICE | 10 | 신규(선택형) |
| 5 | 모의투자 실습 | 일지와 연결된 가상 주문 미리보기 | ORDER_PREVIEW_LINKED_JOURNAL | 25 | Day3 일지 + 기존 주문 미리보기 |
| | | 가상자금·모의투자 고지 확인 | DISCLOSURE_ACK | 5 | 신규(체크박스) |
| 6 | 행동편향 | 행동편향 카드 학습 | LESSON_COMPLETE | 10 | 챌린지 카드 |
| | | 행동편향 퀴즈 통과 | QUIZ_PASS | 15 | 챌린지 카드 |
| | | 내 거래 패턴 확인 | BIAS_REVIEW | 10 | 기존 행동편향 탐지(확증편향·처분효과) |
| | | AI 코칭 확인 | COACHING_CONFIRM | 15 | 기존 AI 코칭(규칙기반 폴백 포함) |
| 7 | 복기와 계획 | 거래 후 복기 작성 | POST_TRADE_REVIEW | 25 | 기존 투자일지 복기 기능 |
| | | 과정 점수 확인 | PROCESS_SCORE_CHECK | 10 | 기존 과정 점수(7.3) |
| | | 다음 주 개선행동 선택 | GOAL_NOTE (5자↑) | 10 | 신규(텍스트 입력) |

Day5의 주문 미리보기는 **실제 체결을 요구하지 않는다** — 예상 비용을
확인하는 과정 자체가 완료 조건이다. Day2/4의 미션도 마찬가지로 추가 주문을
요구하지 않는다.

## 3. 데이터 모델

새 테이블 8개(`app/domain/challenge.py`)로 구성했고, 기존 테이블은
전혀 수정하지 않았다(마이그레이션이 기존 사용자 데이터에 손대지 않는다).

- `Challenge` / `ChallengeDay` / `ChallengeMission`: 콘텐츠 정의(버전,
  게시 상태 포함). 관리자 CMS가 아직 없어 Alembic 시드로 채우지만, 이
  테이블 구조 자체는 향후 CMS가 그대로 쓸 수 있게 설계했다(코드/버전/게시
  상태 필드가 이미 있다).
- `UserChallenge`: 사용자가 챌린지를 시작한 기록. `timezone`을 시작
  시점에 고정하고, `status`는 ACTIVE/COMPLETED만 DB에 저장한다(EXPIRED는
  아래 4절 참고).
- `UserChallengeDay`: Day별 완료 시각만 저장한다. Day 상태
  (LOCKED/AVAILABLE/IN_PROGRESS/COMPLETED)는 저장하지 않고 조회 시점에
  서버가 계산한다 — 클라이언트가 상태를 직접 지시할 수 없게 만드는
  구조적 장치다.
- `UserMissionProgress`: 미션별 완료 시각, XP 지급량, 근거 유형·ID.
  `(user_challenge_id, challenge_mission_id)` unique 제약으로 중복 완료를
  DB 레벨에서 막는다.
- `BadgeDefinition` / `UserBadge`: 배지 정의와 사용자별 획득 기록.
  `(user_id, badge_definition_id)` unique 제약으로 중복 지급을 막는다.

## 4. 시간대·미완료일 정책

- 저장은 항상 UTC. 사용자의 기준 시간대는 `Profile.timezone`(기본
  `Asia/Seoul`, 기존 필드 재사용)에서 가져와 챌린지 **시작 시점에 고정**한다
  — 이후 프로필 시간대를 바꿔도 이미 시작한 챌린지에는 영향이 없다(정책
  적용 시점을 모호하게 만들지 않기 위한 선택).
- Day 경계는 사용자 기준 시간대의 자정이다. `zoneinfo.ZoneInfo`(표준
  라이브러리)로 계산해 DST 전환에도 안전하다 — pytz의 고정 오프셋 문제를
  피했다.
- 하루를 놓쳐도 챌린지가 즉시 실패 처리되지 않는다. "현재 Day"는 그냥 시작일
  기준 경과일로 계속 전진하고, **이전 Day의 미션은 언제든 완료할 수
  있다**(미래 Day만 잠긴다). 실제 완료 날짜와 진행 상황은
  `UserMissionProgress.completed_at`/`UserChallengeDay.completed_at`에
  그대로 남으므로, "얼마나 밀렸는지"는 나중에도 그 기록으로 재구성할 수
  있다.
- 미래 Day의 미션은 서버가 423 Locked로 거부한다(재검증도 마찬가지).
- 같은 미션을 반복 요청해도 중복 완료·중복 XP가 발생하지 않는다
  (`already_completed: true`로 idempotent하게 응답).

## 5. 미션 근거(evidence) 검증

모든 미션은 클라이언트가 "완료했다"고 주장하는 값이 아니라, 서버가 실제
데이터를 조회해 판정한다(`app/domain/services/challenge.py`의
`_MISSION_VERIFIERS` 디스패치 테이블).

| 미션 유형 | 근거 조회 대상 | 소유권 검증 |
|---|---|---|
| LESSON_COMPLETE | `LessonProgress` (status=COMPLETED) | user_id 일치 |
| QUIZ_PASS | `QuizAttempt` (passed=true) | user_id 일치 |
| JOURNAL_PRE_TRADE / POST_TRADE_REVIEW / PROCESS_SCORE_CHECK / ORDER_PREVIEW_LINKED_JOURNAL | `JournalEntry` | user_id 일치 + 챌린지 시작 이후 작성분만 인정 |
| ORDER_PREVIEW | 실시간 재계산(`execution.build_quote`) | 본인 소유 `Portfolio` 확인 |
| PORTFOLIO_CONCENTRATION_REVIEW | 본인 `Portfolio`/`Position` 실시간 집계 | user_id 일치 |
| COACHING_CONFIRM | `AiMessage`/`AiConversation` | user_id 일치 + 챌린지 시작 이후 |
| BIAS_REVIEW | 기존 행동편향 탐지 서비스 재실행 | user_id 일치 |
| GOAL_NOTE / SCENARIO_CHOICE / DISCLOSURE_ACK | 사용자 입력값 자체(서버가 조건 검사) | 해당 없음(제출값 검증) |

**LESSON_COMPLETE/QUIZ_PASS는 챌린지 시작 전 완료 기록도 인정한다** — 같은
이해를 다시 확인시키는 것은 불필요한 마찰이라고 판단했다. 반면 일지 작성,
주문 미리보기 연결, 복기, AI 코칭 확인처럼 "이번에 실제로 행동했는지"를
보는 미션은 챌린지 시작 시각 이후에 만들어진 근거만 인정한다 — 그렇지
않으면 오래된 일지 하나로 여러 Day를 한 번에 완료해버릴 수 있다.

다른 사용자의 일지 ID·포트폴리오 ID·대화 ID를 근거로 제출해도 소유권
검사에서 걸러진다(IDOR 방지, 아래 8절).

## 6. XP 정책

기존 XP 원장(`gamification.award_xp`, 일일 상한 100)을 그대로 재사용하고
수정하지 않았다. 대신 이 기능이 만드는 새 unique 제약
(`UserMissionProgress`, `UserBadge`)이 XP 지급 함수가 호출되기 **전에**
중복을 막아, 기존 XP 원장의(단순 체크 후 삽입 방식이라 이론상 경합
가능성이 있는) 약한 방어선에 의존하지 않게 만들었다.

- 미션 XP는 `ChallengeMission.xp_amount`로 서버가 고정한다(클라이언트가
  값을 보낼 수 없다).
- 같은 미션은 정확히 한 번만 XP를 받는다 — 재검증은 idempotent.
- 동시 요청 두 개가 같은 미션을 동시에 완료하려 해도(예: 두 탭)
  `db.begin_nested()` + unique 제약 위반 포착 패턴(SAVEPOINT)으로 한
  번만 성공한다.
- 하루 XP 상한을 넘기면 초과분은 잘리지만(0으로 지급될 수도 있음) 미션
  완료 자체는 막히지 않는다 — "오늘 상한을 넘겨서 완료가 안 됐다"는 혼란을
  주지 않기 위함이다.
- 7일 챌린지 완주 보너스(`CHALLENGE_COMPLETE_BONUS_XP = 50`,
  reason=`CHALLENGE_COMPLETE`)는 마지막 필수 미션이 완료되는 순간
  compare-and-swap(`UserChallenge.completed_at IS NULL` 조건부 UPDATE)으로
  정확히 한 번만 지급된다. 이 보너스도 같은 일일 상한을 공유한다(수익률과는
  무관하게, XP 지급 규칙만 일관되게 적용한 것).
- 관리자가 나중에 미션 XP 값이나 배지 조건을 바꿔도, 이미
  `UserMissionProgress`/`UserBadge`에 기록된 과거 지급량은 그대로
  보존된다 — 조회 시점에 재계산하지 않는다.

## 7. 배지 시스템

| 배지 코드 | 이름 | 조건 |
|---|---|---|
| first_step | 첫걸음 | 강의 1개 완료 |
| principled_investor | 원칙 있는 투자자 | 일지 `thesis` 작성 |
| other_side | 반대편의 시선 | 일지 `counter_evidence` 1개 이상 |
| risk_management_intro | 위험관리 입문 | 일지 `stop_loss_condition` 작성 |
| power_of_review | 복기의 힘 | 일지 `followed_plan` 기록(복기 완료) |
| steady_learner | 꾸준한 학습자 | 서로 다른 3일에 걸쳐 학습 완료 |
| seven_day_finisher | 7일 완주 | 7일 챌린지의 모든 Day 필수 미션 완료 |
| cost_check_habit (선택) | 비용 확인 습관 | 주문 미리보기에서 비용 확인 |
| plan_adherence (선택) | 계획 준수 | `followed_plan = true` 기록 |
| balanced_portfolio (선택) | 균형 잡힌 포트폴리오 | 분산투자 시나리오 미션 완료 |

의도적으로 **만들지 않은** 배지: 최고 수익률, 거래왕, 큰손, 연속 매수,
손실 만회 — 전부 결과·거래량 기반이라 이 시스템의 원칙에 어긋난다.
리더보드나 사용자 간 순위 비교 기능도 없다.

기술적으로는 `BadgeDefinition.condition_type` + `condition_config`을
`_BADGE_EVALUATORS` 디스패치 테이블로 연결한다 — 조건의 실제 판정 로직은
항상 서버 코드에 있고, `condition_config`은 판정에 필요한 부가 정보(예:
어떤 필드를 볼지)만 담는다. 배지는 (a) 미션을 성공적으로 검증할 때마다,
(b) `GET /v1/me/badges` 조회 시점마다 평가한다 — 챌린지 미션이 아니라
일반 학습 화면에서 조건을 채운 경우도 놓치지 않기 위해서다. 이미 받은
배지는 다시 평가하지 않아(조건이 나중에 바뀌어도) 과거 획득 기록에
영향이 없다. 관리자를 통한 수동 배지 지급은 **의도적으로 구현하지
않았다** — 이 코드베이스에는 아직 관리자 권한(RBAC) 체계 자체가 없어서,
임시방편으로 "관리자 확인"을 만드는 대신 정식 RBAC이 생긴 뒤 추가하는
쪽을 택했다(아래 11절 참고).

## 8. 보안

- 모든 사용자 데이터 엔드포인트는 인증(HttpOnly 쿠키 기반 `get_current_user`)이
  필요하다.
- 다른 사용자의 챌린지 진행 상황·미션은 조회도 검증도 불가능하다 —
  존재하지 않는 것과 소유자가 다른 것을 구분하지 않고 항상 404를 반환한다
  (IDOR 방지, 존재 여부 자체를 노출하지 않음).
- 미션 근거로 제출된 모든 객체 ID(journal_id, portfolio_id, instrument_id)는
  서버가 소유권을 재검증한다 — 다른 사용자의 ID를 제출해도 통과하지
  않는다.
- 미션 완료·XP·배지는 클라이언트가 직접 지정할 수 없다 — 요청 바디에는
  그런 필드 자체가 없고, 응답은 항상 서버 계산 결과다.
- 미션의 `config`(예: `SCENARIO_CHOICE`의 정답 키)는 API 응답에 그대로
  노출되지 않는다. `public_config`이라는 화이트리스트를 별도로 두어,
  화면에 실제로 필요한 값(예: 강의 ID, 선택지 목록)만 골라 내려주고
  정답 키(`correct_choice`) 같은 채점 정보는 절대 포함하지 않는다
  (`tests/test_challenge.py`의
  `test_scenario_choice_public_config_never_exposes_correct_answer`로
  회귀 방지).
- 일지 원문·인증 토큰·쿠키는 로그에 남기지 않는다(기존 로깅 정책을 그대로
  따른다).

## 9. API

| Method | Path | 설명 |
|---|---|---|
| GET | `/v1/challenges` | 게시된 챌린지 목록 |
| GET | `/v1/challenges/{id}` | 챌린지 상세(Day·미션 구조) |
| POST | `/v1/challenges/{id}/start` | 챌린지 시작(이미 시작했으면 409) |
| GET | `/v1/me/challenges/active` | 내 진행 중인 챌린지(없으면 404) |
| GET | `/v1/me/challenges/{id}` | 내 챌린지 상세 진행 상황 |
| POST | `/v1/me/challenges/{id}/missions/{mission_id}/verify` | 미션 완료 검증 |
| GET | `/v1/badges` | 게시된 배지 정의 목록 |
| GET | `/v1/me/badges` | 내가 획득한 배지 |
| GET | `/v1/me/notifications` | 인앱 알림(스텁, 10절 참고) |

응답 스키마는 `apps/api/app/api/v1/challenge_schemas.py`에 있고, OpenAPI
스펙(`/openapi.json`)과 `apps/web/src/lib/types.ts`의 TypeScript 타입을
수동으로 맞춰뒀다(공유 코드 생성기는 아직 없다).

## 10. 프런트엔드

- `/challenge`: 챌린지 소개(미시작 상태) → 시작 → 7일 진행 지도(오늘 Day가
  펼쳐진 상태로 시작, 다른 Day도 펼쳐 볼 수 있음) → 완주 축하 화면까지
  한 화면 흐름으로 처리한다. 각 Day는 LOCKED/AVAILABLE/IN_PROGRESS/COMPLETED
  상태를 아이콘(🔒▶️🟡✅) + 텍스트로 함께 표시한다(색상만으로 구분하지
  않음).
- `/badges`: 배지 목록(획득/미획득 구분) + 탭하면 상세 설명.
- 홈 화면(`/`): 현재 Day, 오늘 완료한 미션 수, 다음 할 일, "이어하기"
  버튼, 7일 완주까지의 진행률 막대를 보여준다. **손익(PnL)은 이 위젯
  어디에도 표시하지 않는다** — 챌린지 진행 상황과 투자 성과를 시각적으로
  분리했다.
- 미션 유형별 입력 폼(`MissionActionForm`)이 강의/퀴즈 딥링크, 목표
  텍스트 입력, 선택형 시나리오, 체크박스 고지, 종목 검색+수량 입력,
  일지 선택 등을 미션 유형에 맞춰 렌더링한다.
- `prefers-reduced-motion`을 존중한다(스켈레톤 애니메이션·진행률 바
  전환 모두 이 미디어 쿼리로 끈다).
- 모바일 390px 뷰포트에서 가로 스크롤 없이 렌더링됨을 E2E로 확인했다.

## 11. 알림(인앱 스텁)

**실제 푸시 발송(APNs/FCM 등)은 이번 범위에 포함하지 않는다.** 별도 발송
큐나 알림 테이블도 만들지 않았다 — 대신 `GET /v1/me/notifications`가
조회 시점에 "지금 보여줄 것"을 계산해서 돌려준다
(`app/domain/services/notifications.py`). 지원 종류: 오늘의 학습, 복기
대기 거래, 다음 챌린지 스텝, 배지 획득. 문구는 전부 담담한 안내
문구이고, "지금 매수하세요", "기회를 놓칩니다" 같은 조급함을 자극하거나
손실 포지션에 추가 행동을 유도하는 표현은 쓰지 않는다(회귀 테스트로
금지 문구 목록을 확인한다).

## 12. 관리자·시드

`alembic/versions/cb3cb7383a73_*.py`가 기본 챌린지·챌린지 카드·배지를
멱등하게 시드한다 — 이미 챌린지 코드가 존재하면 아무것도 하지 않고
건너뛴다. 재실행해도 행 수가 늘지 않는다(수동으로
`alembic stamp <이전 리비전> && alembic upgrade head`로 재실행을
검증했다). production에 테스트 사용자를 만들지 않는다. 정식 관리자
CMS는 아직 없지만, `Challenge`/`ChallengeDay`/`ChallengeMission`/
`BadgeDefinition`이 이미 버전(`version`)과 게시 상태(`status`) 필드를
갖고 있어 향후 CMS가 이 테이블을 그대로 쓸 수 있다.

## 13. 테스트

- `apps/api/tests/test_challenge.py` (21개): 시작/중복시작, IDOR(챌린지
  조회·미션 검증 모두), 미래 Day 잠금, 미완료일 이어하기, timezone 경계
  2종 + DST, 잘못된 timezone 거부, 근거 소유권(일지 2종, 주문/포트폴리오,
  AI 코칭), 중복 검증 idempotent, 동시 검증 시 XP 중복 지급 없음, 일일 XP
  상한, 배지 최초 1회 지급 + 근거 보존, `public_config` 노출 안전성 2종,
  전체 7일 완주(보너스 XP·배지까지).
- `apps/api/tests/test_notifications.py` (6개): 인증 필요, 챌린지 미시작
  시 빈 목록, 챌린지 시작 후 알림 등장, 배지 획득 알림, 미복기 거래 알림,
  사용자별 격리, 금지 문구 부재.
- `apps/web/e2e/challenge-flow.spec.ts` (3개): 시작→Day1 3개 미션 완료
  →XP·배지 반영→새로고침 후 유지→Day2 잠금 확인, 모바일 390px 렌더링,
  에러/재시도.
- 기존 `apps/web/e2e/full-flow.spec.ts`(학습·모의투자·일지·AI 코칭 전체
  흐름)는 이번 변경 이후에도 그대로 통과한다.
- 마이그레이션 업/다운그레이드는 `apps/api/tests/test_migration_duplicate_instrument_merge.py`가
  매 테스트마다 head까지 왕복하는 방식으로 간접 검증한다(이 파일이 새
  head를 동적으로 찾도록 이번에 고쳤다 — 아래 "알려진 이슈" 참고).

## 14. 마이그레이션과 롤백

- `937dbb491085`: 8개 신규 테이블 생성(challenges, challenge_days,
  challenge_missions, user_challenges, user_challenge_days,
  user_mission_progress, badge_definitions, user_badges). 기존 테이블은
  변경하지 않는다.
- `cb3cb7383a73`: 기본 챌린지·카드 콘텐츠·배지 시드(멱등).
- 롤백(`alembic downgrade`)은 이 기능이 만든 데이터만 역순으로 지운다
  (미션 진행 기록 → Day 기록 → 챌린지 → 배지 지급 기록 → 배지 정의 →
  미션 → Day → 챌린지 → 챌린지 카드 강의/퀴즈). 기존 사용자의 학습·
  포트폴리오·일지 데이터는 어떤 마이그레이션도 건드리지 않는다.

## 15. 알려진 제한사항·범위 제외

- 실제 푸시 알림, 리더보드, 친구 경쟁, 현금·쿠폰 보상, 실제 투자·결제·
  실시간 시세, 상용 시장 데이터 공급자, 실제 Claude API 연동은 범위
  밖이다(이 저장소 전체의 기존 원칙과 동일).
- 1~5강 이외의 강의(6~30강) 본편은 만들지 않았다 — Day2/4/6은 짧은
  챌린지 전용 카드로 대체했다.
- 확증편향·처분효과 2종 외의 나머지 행동편향 유형은 이번 범위에
  포함하지 않는다(기존 코드베이스의 범위를 그대로 따랐다).
- 관리자를 통한 수동 배지 지급 API는 만들지 않았다 — 이 저장소에
  아직 관리자 권한 체계가 없기 때문이다(7절 참고).
