# 도메인 모델

명세서 8장 기준 SQLAlchemy 모델.

- `base.py` — 공통 베이스, UUID PK, UTC 타임스탬프 믹스인
- `user.py` — users, profiles, consents, devices, sessions (Phase 1 인증, 구현 완료)
- `market.py` — instruments, bars (as_of/source/delay_seconds 필수; ticker+exchange는
  심볼 재사용을 고려해 DB unique 제약 없이 valid_to로 "현재 유효" 여부를 구분한다)
- `portfolio.py` — portfolios, orders, fills, positions, ledger_entries (Phase 3, 구현 완료)
- `policy.py` — fee_policies (KR/US 수수료·세금), fx_rates (Phase 3, 구현 완료 — fx_rates는
  market-data-worker가 없어 seed 플레이스홀더 값 사용 중)
- `journal.py` — journal_entries, journal_versions
- `learning.py` — learning_paths, courses, modules, lessons, content_blocks, quizzes,
  questions, choices, lesson_progress, quiz_attempts, xp_ledger (Phase 2, 구현 완료)
- `services/execution.py` — 모의 체결 엔진 (6.7): 시장가·지정가 체결가 근사, 비용·환전
  계산, 평단가·실현손익 갱신을 담당하는 순수 도메인 서비스 (API 레이어와 분리)
- `services/market_data.py` — 시장 데이터 provider 추상화(Stooq 어댑터 포함, 라이브
  미검증)·검증(결측·이상치)·upsert (6.4). 실제로 지금 서빙되는 데이터는 시드 샘플이다
  (services/market-data-worker/README.md 참고)
- `services/gamification.py` — XP 산정 (6.3): 이벤트당 1회 지급, 일일 상한, 연속 학습일 계산
- `constants.py` — 계정코드·원장 entry_type·주문 상태·거래소→시장 매핑 등 공용 상수

Alembic 마이그레이션(`alembic/versions/`)은 위 모델 전체를 포함한다.

## 아직 없는 것 (다음 Phase)

- challenges/missions/badges/streaks (Phase 2 확장 — 지금은 xp_ledger·lesson_progress
  기반의 최소 학습 요약만 있고, 7일/28일 챌린지 미션 구성과 배지는 없음)
- corporate_actions, fundamentals, market_sessions (Phase 3 확장 — 기업행사·장운영시간)
- cash_accounts, portfolio_snapshots (Phase 3 확장 — 현재는 ledger_entries에서 직접 계산)
- bias_events, coaching_reports (Phase 4)
- ai_conversations, ai_messages, retrieval_sources, model_runs, safety_events (Phase 4)
- notifications, subscriptions, support_tickets, audit_logs, feature_flags (Phase 5)
