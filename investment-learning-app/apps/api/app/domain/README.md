# 도메인 모델

명세서 8장 기준 SQLAlchemy 모델.

- `base.py` — 공통 베이스, UUID PK, UTC 타임스탬프 믹스인
- `user.py` — users, profiles, consents, devices, sessions (Phase 1 인증, 구현 완료)
- `market.py` — instruments, bars (as_of/source/delay_seconds 필수)
- `portfolio.py` — portfolios, orders, fills, positions, ledger_entries
- `journal.py` — journal_entries, journal_versions

Alembic 마이그레이션(`alembic/versions/`)은 위 모델 전체를 초기 revision으로 포함한다.

## 아직 없는 것 (다음 Phase)

- learning_paths ~ progress (Phase 2 학습 엔진)
- challenges/missions/xp_ledger/badges (Phase 2 게임화)
- fx_rates, corporate_actions, fundamentals, market_sessions (Phase 3 확장)
- fee_policies, cash_accounts, portfolio_snapshots (Phase 3 확장)
- bias_events, coaching_reports (Phase 4)
- ai_conversations, ai_messages, retrieval_sources, model_runs, safety_events (Phase 4)
- notifications, subscriptions, support_tickets, audit_logs, feature_flags (Phase 5)
