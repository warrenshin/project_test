# 투자교육 콘텐츠 6~15강

기존 학습 엔진(`LearningPath > Course > Module > Lesson > ContentBlock`,
`Quiz > Question > Choice`, `LessonProgress`, `XpLedger`)을 그대로 재사용해
부록 B 목차의 6~15강을 추가한 콘텐츠 확장이다. 새 도메인 모델이나 CMS를
새로 만들지 않았다 — `Lesson`/`Choice`/`Quiz`에 몇 개 컬럼만 additive로
추가했다.

## 1. 강의 목록과 상태

"투자 시작하기" 코스 아래 새 모듈 **"2부. 실전 투자와 리스크 관리"**(기존
"1부. 투자의 기본 개념", "보충: 7일 챌린지 카드" 다음 순서)에 10개 강의가
있다.

| code | 제목 | 상태 | 검수상태 | 시장 범위 |
|---|---|---|---|---|
| lesson-06 | 거래소와 장 운영시간 | **DRAFT** | REVIEW_REQUIRED | KR_US |
| lesson-07 | 시장가와 지정가 | PUBLISHED | REVIEWED | GLOBAL |
| lesson-08 | 호가·스프레드·유동성 | PUBLISHED | REVIEWED | GLOBAL |
| lesson-09 | 수수료·세금·환율 | **DRAFT** | REVIEW_REQUIRED | KR_US |
| lesson-10 | 투자수익률 계산 | PUBLISHED | REVIEWED | GLOBAL |
| lesson-11 | 복리의 효과와 한계 | PUBLISHED | REVIEWED | GLOBAL |
| lesson-12 | 변동성과 최대낙폭 | PUBLISHED | REVIEWED | GLOBAL |
| lesson-13 | 분산투자의 원리 | PUBLISHED | REVIEWED | GLOBAL |
| lesson-14 | 자산배분 기초 | PUBLISHED | REVIEWED | GLOBAL |
| lesson-15 | 시가총액과 기업가치 | PUBLISHED | REVIEWED | GLOBAL |

6강(장 운영시간)·9강(수수료·세금·환율)은 **의도적으로 DRAFT로 남겨뒀다** —
`Lesson.status`가 DRAFT면 `GET /v1/learning/paths`·`GET /v1/lessons/{id}`
어디에도 노출되지 않는다(기존 "PUBLISHED만 노출" 정책을 그대로 따름).
이 두 강의는 시장운영시간·수수료·세율처럼 시점에 따라 바뀌고 이 개발
환경(샌드박스)에서 한국거래소·SEC 등 1차 출처 사이트에 직접 접속해 최종
확인하지 못했다는 한계가 있어, 검수 없이 공개하지 않는다.

## 2. 강의 코드(`Lesson.code`)

6강부터는 UUID와 별개로 안정적인 문자열 코드(`lesson-06` ~ `lesson-15`)를
갖는다. 기존 1~5강·7일 챌린지 카드 강의는 `code`가 `NULL`이다(소급 채움
없음). 부분 unique 인덱스(`code IS NOT NULL`)라 기존 행에 영향이 없다.

## 3. 강의 하나의 콘텐츠 구조

`content_blocks.block_type`을 다음 9종으로 확장했다(기존 1~5강은
OBJECTIVE/BODY/EXAMPLE/SUMMARY 4종만 사용, 6~15강은 9종 모두 사용):

| block_type | 의미 |
|---|---|
| OBJECTIVE | 학습목표(3개 이하) |
| BODY | 본문(짧은 문단 여러 개 — 모바일 카드 단위로 표시) |
| EXAMPLE | 쉬운 숫자 예제 |
| MISCONCEPTION | 흔한 오해 |
| SUMMARY | 핵심 요약(3~5개) |
| SELF_CHECK | 스스로 확인할 질문 |
| TERMS | 관련 용어 |
| PRACTICE | 관련 실습(가능하면 실제 앱 기능과 연결, 거래 강제 없음) |
| SOURCE | 출처(자료명·URL·확인일·적용 시장·변경 가능성) |

`Lesson` 컬럼에도 구조화된 메타데이터가 있다: `source`(자료명),
`source_url`, `source_confirmed_at`(확인일), `content_version`,
`market_scope`, `review_status`. `GET /v1/lessons/{id}` 응답에 전부
포함되며, 모든 응답에는 "교육용 콘텐츠이며 특정 종목 매수·매도를 권유하거나
수익을 보장하지 않습니다" 고지(`disclosure` 필드)가 항상 붙는다.

## 4. 변동 가능한 금융정보 관리(설정·콘텐츠 분리)

수수료율·세율·환전스프레드·거래소 정규장 시간처럼 시점에 따라 달라지는
숫자는 강의 본문에 직접 쓰지 않고 `app.core.config.Settings`에 교육용
"예시" 상수로 뒀다:

- `education_example_fee_rate_pct`, `education_example_domestic_tax_rate_pct`,
  `education_example_fx_spread_pct` (9강 계산 예시용 — **실제 수수료·세율
  아님**, 계산 연습을 위한 가정치)
- `kr_market_regular_session`, `us_market_regular_session` (6강 — 여러
  출처에서 일관되게 확인되는 정규장 시간만 반영. 프리마켓·애프터마켓 같은
  확장거래시간은 2026년 기준 제도 개편이 진행 중이라 설정값으로 못박지
  않고 본문에서 "공식 공지 확인 필요"로만 안내한다)

값이 바뀌면 이 설정만 갱신하고 시드 migration(`c1a2b3d4e5f6`)을 다시
실행하면 된다(멱등이라 재실행 자체는 안전하지만, 값 변경을 반영하려면
`lessons.code`로 기존 행을 지우고 다시 시드하거나 별도 UPDATE
migration을 추가해야 한다 — 현재는 최초 1회 시드만 지원한다).

## 5. 퀴즈 작성 원칙

- 강의당 정확히 4문항: 개념 확인 / 숫자 계산 / 흔한 오해 / 실제 상황 판단.
- 문항당 선택지 4개, 정답은 항상 정확히 1개(복수정답·애매한 정답 없음 —
  `tests/test_lessons_06_15.py::test_each_lesson_has_four_questions_with_exactly_one_correct_choice`로
  전수 검증).
- `Choice.explanation`(오답별 설명)을 모든 선택지에 채운다. 정답 공개 전
  (`GET /v1/quizzes/{id}`)에는 `is_correct`/`explanation`을 절대 노출하지
  않고, 채점 후(`POST /v1/quizzes/{id}/attempts`)에만 `choice_feedback`로
  선택지별 정답 여부·설명을 함께 준다.
- 계산 문항은 정수/소수 계산이며 서버가 그대로 채점한다(부동소수점 반올림
  오차가 답을 가르는 경계는 만들지 않았다).
- 선택지 표시 순서 랜덤화는 프런트엔드에서 지원한다(`apps/web`의
  `shuffled()` — 정답 데이터 자체는 서버가 관리하므로 표시 순서만 섞는다).
- `Quiz.content_version`으로 문항 버전을 표시한다. 이후 문항을 고쳐도
  과거 `QuizAttempt`는 제출 시점의 `score_pct`/`passed`를 그대로 저장하고
  있어(다시 채점하지 않음) 무효화되지 않는다.

## 6. 게시 승인 절차(DRAFT → PUBLISHED)

이 저장소에는 아직 별도 관리자 웹/CMS가 없다(범위 밖). 6강·9강처럼
DRAFT로 남은 강의를 검수 후 공개하려면:

1. 한국거래소·미국 거래소(NYSE/Nasdaq)·금융감독원 등 1차 공식 출처에서
   최신 수치를 직접 확인한다.
2. 필요하면 `app/core/config.py`의 교육용 예시 상수(`kr_market_regular_session`
   등)를 갱신한다.
3. 본문이 최신 사실과 맞는지 확인한 뒥, `lessons` 테이블에서 해당
   `code`의 `status`를 `PUBLISHED`, `review_status`를 `REVIEWED`로,
   `reviewed_by`/`reviewed_at`을 채우는 additive migration을 추가한다
   (기존 `936d...`류 seed migration과 같은 패턴 — DELETE 없이 UPDATE만).
4. 전체 테스트·Playwright를 재실행해 회귀가 없는지 확인한다.

## 7. Seed 방법

```bash
cd apps/api
alembic upgrade head
```

`c1a2b3d4e5f6` migration은 `lessons.code = 'lesson-06'` 존재 여부로
멱등성을 보장한다(이미 시드돼 있으면 아무것도 하지 않는다). 되돌리려면:

```bash
alembic downgrade 8255aa2780e6  # 6~15강만 제거, 1~5강·챌린지 카드는 보존
```

## 8. 테스트

- `apps/api/tests/test_lessons_06_15.py` — seed 상태, PUBLISHED 노출/DRAFT
  비노출, 퀴즈 채점·정답 비노출·오답별 설명, XP 중복 방지, 기존 1~5강·
  챌린지 카드·진도 보존.
- `apps/api/tests/test_lessons_06_15_migration.py` — 이 migration 자체의
  downgrade/upgrade 재현성과 기존 데이터 보존(`test_migration_duplicate_instrument_merge.py`와
  동일한 패턴).
- `apps/web/e2e/lessons-06-15.spec.ts` — 7강 진입부터 완료·퀴즈·XP·새로고침
  유지까지 실제 화면 흐름, DRAFT 강의 비노출(화면+API), 390px 모바일.

## 9. 교육용 정보 고지

이 강의들은 교육용 콘텐츠이며 투자 추천이나 수익 보장이 아니다. 특정
종목의 매수·매도를 지시하지 않는다. 9강은 법률·세무 자문이 아니라는
점을 본문에 명시한다. 실제 투자 결정 전에는 각 거래소·감독기관의 최신
공식 자료를 직접 확인해야 한다 — 모든 강의 상세 API 응답(`disclosure`
필드)과 화면에 이 고지가 항상 함께 표시된다.
