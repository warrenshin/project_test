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

| code | 제목 | 상태(seed 시점) | 검수상태(seed 시점) | 시장 범위 |
|---|---|---|---|---|
| lesson-06 | 거래소와 장 운영시간 | READY_FOR_REVIEW | REVIEW_REQUIRED | KR_US |
| lesson-07 | 시장가와 지정가 | READY_FOR_REVIEW | REVIEW_REQUIRED | GLOBAL |
| lesson-08 | 호가·스프레드·유동성 | READY_FOR_REVIEW | REVIEW_REQUIRED | GLOBAL |
| lesson-09 | 수수료·세금·환율 | READY_FOR_REVIEW | REVIEW_REQUIRED | KR_US |
| lesson-10 | 투자수익률 계산 | READY_FOR_REVIEW | REVIEW_REQUIRED | GLOBAL |
| lesson-11 | 복리의 효과와 한계 | READY_FOR_REVIEW | REVIEW_REQUIRED | GLOBAL |
| lesson-12 | 변동성과 최대낙폭 | READY_FOR_REVIEW | REVIEW_REQUIRED | GLOBAL |
| lesson-13 | 분산투자의 원리 | READY_FOR_REVIEW | REVIEW_REQUIRED | GLOBAL |
| lesson-14 | 자산배분 기초 | READY_FOR_REVIEW | REVIEW_REQUIRED | GLOBAL |
| lesson-15 | 시가총액과 기업가치 | READY_FOR_REVIEW | REVIEW_REQUIRED | GLOBAL |

**10개 전부 시드 migration(`c1a2b3d4e5f6`)이 채우는 초기 배포 상태는
`status=READY_FOR_REVIEW`, `review_status=REVIEW_REQUIRED`다** — 예전에는
이 표가 "8개는 이미 PUBLISHED, 6강·9강 2개만 DRAFT로 보류"라고 적어 뒀지만,
이는 거버넌스 상태모델을 `DRAFT`/`PUBLISHED` 2단계에서
`READY_FOR_REVIEW`→(사람 검수)→`PUBLISHED` 흐름으로 바로잡은 수정(강의
콘텐츠를 작성한 에이전트가 스스로 승인할 수 없게 하기 위함) 이후 갱신되지
않은 오래된 서술이었다. `status`가 `PUBLISHED`가 아니면(즉 `READY_FOR_REVIEW`든
`DRAFT`든) `GET /v1/learning/paths`·`GET /v1/lessons/{id}` 어디에도 노출되지
않는다(기존 "PUBLISHED만 노출" 정책 그대로).

10개 전부 사람 검수·승인(`scripts/publish_lesson.py`, 아래 6절)이 있어야만
공개된다 — 그 전까지는 하나도 노출되지 않는다. 6강(장 운영시간)·9강(수수료·
세금·환율)은 시장운영시간·수수료·세율처럼 시점에 따라 바뀌는 값을 다루고
이 개발 환경(샌드박스)에서 한국거래소·SEC 등 1차 출처 사이트에 직접 접속해
최종 확인하지 못했다는 한계가 있어, 다른 8개보다 더 신중한 검수(공식
출처 재확인)가 필요하다는 점만 다르다 — `status`/`review_status` 자체는
나머지 8개와 동일하게 시작한다.

**주의 — 이 표는 저장소의 seed 시점 상태이지, 실제 배포된 환경의 현재
상태가 아니다.** 예를 들어 dev/스테이징/운영 DB에서 운영자가
`scripts/publish_lesson.py`로 일부 강의를 이미 승인·게시했다면, 그
환경에서는 해당 강의의 `status`가 `PUBLISHED`로 바뀌어 있다. 특정
환경에서 실제로 무엇이 게시돼 있는지 확인하려면 이 문서가 아니라 그
환경의 DB(`lessons` 테이블)나 `GET /v1/learning/paths` 응답을 직접 조회해야
한다 — Git 저장소의 문서는 운영 게시 상태를 대신하지 않는다.

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

## 6. 게시 승인 절차(READY_FOR_REVIEW → PUBLISHED)

이 저장소에는 아직 별도 관리자 웹/CMS가 없다(범위 밖). **강의 상태를 직접
UPDATE하는 migration이나 수동 SQL로 게시해서는 안 된다** — 이 10개 강의는
에이전트(AI)가 작성했고, 작성과 승인을 분리해 에이전트가 자기 콘텐츠를
스스로 승인하지 못하게 하는 것이 이 절차 전체의 목적이다(아래
`scripts/publish_lesson.py`의 존재 이유). 사람 검수자가 강의를 검수 후
공개하려면:

1. `docs/content-review/lessons-06-15-review.md`의 강의별 체크리스트를
   확인한다. 6강(장 운영시간)·9강(수수료·세금·환율)은 한국거래소·미국
   거래소(NYSE/Nasdaq)·금융감독원 등 1차 공식 출처에서 최신 수치를 직접
   대조해야 한다.
2. 필요하면 `app/core/config.py`의 교육용 예시 상수(`kr_market_regular_session`
   등)를 갱신한다.
3. 본문이 최신 사실과 맞는지 확인한 뒤, 운영자 전용 CLI로 강의 하나씩
   승인한다(일괄 승인 기능은 의도적으로 없다):
   ```bash
   cd apps/api
   python -m scripts.publish_lesson \
       --code lesson-07 --content-version v1 --reviewer "hong.gildong" \
       --source-verified true --note "..."
   ```
   승인마다 `lesson_review_audits`에 누가·언제·어떤 근거로 승인했는지
   감사기록이 남는다(자세한 안전장치는 `apps/api/scripts/publish_lesson.py`
   docstring, 롤백 시 이 감사기록이 어떻게 작동하는지는
   `apps/api/README.md`의 "게시된 콘텐츠 migration 롤백 주의사항" 참고).
4. 전체 테스트·Playwright를 재실행해 회귀가 없는지 확인한다.

로컬 스테이징 환경에서는 이 절차를 사람이 직접 실행하기 전
`scripts/publish_reviewed_lessons_staging.sh`(저장소 루트,
`README.md`의 "로컬 스테이징 환경" 절 참고)로 사전 점검(환경·DB 호스트·
백업 존재 확인)까지만 자동화해 두었다 — 실제 승인 실행은 여전히 사람
운영자의 몫이다.

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

**주의 — 강의가 하나라도 승인(게시)된 뒤에는 이 downgrade가 자동으로 막힌다.**
`scripts/publish_lesson.py`로 강의를 승인할 때마다 `lesson_review_audits`에
감사기록이 남는데, 이 감사기록이 하나라도 존재하는 상태에서 위 downgrade를
실행하면 `c1a2b3d4e5f6.downgrade()`가 **아무 것도 지우지 않고** 먼저 확인부터 해
`RuntimeError`로 즉시 중단한다(외래키 위반으로 도중에 실패하는 것을 막기 위한
사전 검사). 감사기록을 자동으로 삭제하지 않는 것은 의도된 동작이다 — 승인
이력은 "누가·언제·무엇을 근거로 게시했는지"를 남기는 감사 자료이므로, 콘텐츠
migration이 조용히 지워서는 안 된다. 운영에서 6~15강 콘텐츠 자체를 되돌려야
하는 상황이 오면, 감사기록을 보존할지·함께 정리할지를 먼저 사람이 판단하고
그에 맞는 별도 절차(예: 감사기록을 다른 테이블로 옮겨 보관한 뒤 진행)를
수립해야 한다 — 이 저장소는 그 판단을 대신 내리지 않는다.

이 저장소의 다른 콘텐츠 migration(예: 향후 챌린지 카드 추가)도 승인·게시
감사 이력을 남기게 되면 동일한 원칙(감사기록이 있으면 자동 downgrade 금지)을
따라야 한다.

## 8. 테스트

- `apps/api/tests/test_lessons_06_15.py` — seed 상태(10개 전부
  `status=READY_FOR_REVIEW`)와 게시 전 비노출(10개 전부 대상), 기존
  PUBLISHED 강의(1강 등) 노출, 퀴즈 채점·정답 비노출·오답별 설명, XP 중복
  방지, 기존 1~5강·챌린지 카드·진도 보존.
- `apps/api/tests/test_lessons_06_15_migration.py` — 이 migration 자체의
  downgrade/upgrade 재현성과 기존 데이터 보존(`test_migration_duplicate_instrument_merge.py`와
  동일한 패턴).
- `apps/api/tests/test_publish_lesson_cli.py` — 승인 CLI 자체의 안전장치와,
  실제 lesson-06~15가 여전히 미승인(READY_FOR_REVIEW) 상태로 남아 있는지
  (에이전트 자기승인 여부).
- `apps/api/tests/test_lesson_review_audit_downgrade_safety.py` — 승인
  감사기록이 있으면 시드 migration downgrade가 안전하게 막히는지.
- `apps/web/e2e/lessons-06-15.spec.ts` — 1강(기존 PUBLISHED 강의 "투자는
  무엇인가") 진입부터 완료·퀴즈·XP·새로고침 유지까지 실제 화면 흐름,
  lesson-06~15 10개 전부 게시 전 비노출(화면+API), 390px 모바일.

## 9. 교육용 정보 고지

이 강의들은 교육용 콘텐츠이며 투자 추천이나 수익 보장이 아니다. 특정
종목의 매수·매도를 지시하지 않는다. 9강은 법률·세무 자문이 아니라는
점을 본문에 명시한다. 실제 투자 결정 전에는 각 거래소·감독기관의 최신
공식 자료를 직접 확인해야 한다 — 모든 강의 상세 API 응답(`disclosure`
필드)과 화면에 이 고지가 항상 함께 표시된다.
