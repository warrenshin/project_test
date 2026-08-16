# 도메인 모델

명세서 8장 기준 SQLAlchemy 모델. 이번 Phase에서는 금융 핵심 경로(원장이 진실의
원천이어야 하는 부분)를 우선 구현했다.

- `base.py` — 공통 베이스, UUID PK, UTC 타임스탬프 믹스인
- `market.py` — instruments, bars (as_of/source/delay_seconds 필수)
- `portfolio.py` — portfolios, orders, fills, positions, ledger_entries
- `journal.py` — journal_entries, journal_versions

## 아직 없는 것 (다음 Phase)

- users/profiles/consents/devices/sessions (Phase 1 인증)
- learning_paths ~ progress (Phase 2 학습 엔진)
- challenges/missions/xp_ledger/badges (Phase 2 게임화)
- fx_rates, corporate_actions, fundamentals, market_sessions (Phase 3 확장)
- fee_policies, cash_accounts, portfolio_snapshots (Phase 3 확장)
- bias_events, coaching_reports (Phase 4)
- ai_conversations, ai_messages, retrieval_sources, model_runs, safety_events (Phase 4)
- notifications, subscriptions, support_tickets, audit_logs, feature_flags (Phase 5)

Alembic 마이그레이션은 인증 모델까지 포함해 Phase 1에서 함께 초기화할 예정이다.
