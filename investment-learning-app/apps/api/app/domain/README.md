# 도메인 모델

명세서 8장 기준 SQLAlchemy 모델.

- `base.py` — 공통 베이스, UUID PK, UTC 타임스탬프 믹스인
- `user.py` — users, profiles, consents, devices, sessions (Phase 1 인증, 구현 완료)
- `market.py` — instruments, bars (as_of/source/delay_seconds 필수; ticker+exchange는
  심볼 재사용을 고려해 DB unique 제약 없이 valid_to로 "현재 유효" 여부를 구분한다)
- `portfolio.py` — portfolios, orders, fills, positions, ledger_entries (Phase 3, 구현 완료)
- `policy.py` — fee_policies (KR/US 수수료·세금), fx_rates (Phase 3, 구현 완료 — fx_rates는
  market-data-worker가 없어 seed 플레이스홀더 값 사용 중)
- `journal.py` — journal_entries(user_id 포함), journal_versions (Phase 4, 구현 완료)
- `ai.py` — ai_conversations, ai_messages (모델·프롬프트버전·출처를 메시지에 직접 기록,
  Phase 4, 구현 완료)
- `learning.py` — learning_paths, courses, modules, lessons, content_blocks, quizzes,
  questions, choices, lesson_progress, quiz_attempts, xp_ledger (Phase 2, 구현 완료)
- `services/execution.py` — 모의 체결 엔진 (6.7): 시장가·지정가 체결가 근사, 비용·환전
  계산, 평단가·실현손익 갱신을 담당하는 순수 도메인 서비스 (API 레이어와 분리)
- `services/market_data.py` — 시장 데이터 provider 추상화(Stooq 어댑터 포함, 라이브
  미검증)·검증(결측·이상치)·upsert (6.4). 실제로 지금 서빙되는 데이터는 시드 샘플이다
  (services/market-data-worker/README.md 참고)
- `services/gamification.py` — XP 산정 (6.3): 이벤트당 1회 지급, 일일 상한, 연속 학습일 계산
- `services/coaching.py` — 과정 점수 규칙 엔진(7.3)과 행동편향 탐지(7.4, 7종 전부: 확증편향·
  처분효과·집중위험·추격매수·손실회피·물타기 집착·과잉매매)
- `challenge.py` / `services/challenge.py` — 7일 학습 챌린지·과정 중심 배지(Day/미션/
  배지 정의, 사용자 진행상황, XP·배지 지급). 자세한 내용은
  `docs/features/seven-day-challenge.md` 참고
- `services/ai_coach.py` — AI 코치 파이프라인(7.5-7.7): 검색→정량엔진→LLM(Claude API,
  Haiku/Sonnet 라우팅)→출력 정책 필터→출처 표시. `ANTHROPIC_API_KEY` 미설정 시 규칙
  기반 폴백으로 항상 graceful degradation (이 개발 세션은 키가 없어 폴백 경로만 검증됨)
- `constants.py` — 계정코드·원장 entry_type·주문 상태·거래소→시장 매핑 등 공용 상수

Alembic 마이그레이션(`alembic/versions/`)은 위 모델 전체를 포함한다.

## 아직 없는 것 (다음 Phase)

- 28일 챌린지, 스트릭 보상 등 7일 챌린지 이후의 확장 (7일 챌린지 자체는
  challenges/challenge_days/challenge_missions/user_challenges/
  user_challenge_days/user_mission_progress/badge_definitions/user_badges로
  이미 구현됨)
- corporate_actions, fundamentals, market_sessions (Phase 3 확장 — 기업행사·장운영시간)
- cash_accounts, portfolio_snapshots (Phase 3 확장 — 현재는 ledger_entries에서 직접 계산)
- bias_events, coaching_reports를 별도 테이블로 정규화 (지금은 온디맨드 계산 +
  ai_messages.sources/safety_flags에 JSONB로 기록 — 이력 추적·리포트 수요가 커지면 분리)
- retrieval_sources, model_runs, safety_events를 별도 테이블로 분리 (지금은
  ai_messages 컬럼에 직접 기록)
- subscriptions, support_tickets, audit_logs, feature_flags (Phase 5). 인앱
  알림(스텁, 실제 푸시 아님)은 `services/notifications.py`로 이미 있음
