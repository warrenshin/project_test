# 도메인 모델

명세서 8장 기준 SQLAlchemy 모델.

- `base.py` — 공통 베이스, UUID PK, UTC 타임스탬프 믹스인
- `user.py` — users, profiles, consents, devices, sessions (Phase 1 인증, 구현 완료)
- `market.py` — instruments, bars (as_of/source/delay_seconds 필수)
- `portfolio.py` — portfolios, orders, fills, positions, ledger_entries (Phase 3, 구현 완료)
- `policy.py` — fee_policies (KR/US 수수료·세금), fx_rates (Phase 3, 구현 완료 — fx_rates는
  market-data-worker가 없어 seed 플레이스홀더 값 사용 중)
- `journal.py` — journal_entries, journal_versions
- `services/execution.py` — 모의 체결 엔진 (6.7): 시장가·지정가 체결가 근사, 비용·환전
  계산, 평단가·실현손익 갱신을 담당하는 순수 도메인 서비스 (API 레이어와 분리)
- `constants.py` — 계정코드·원장 entry_type·주문 상태·거래소→시장 매핑 등 공용 상수

Alembic 마이그레이션(`alembic/versions/`)은 위 모델 전체를 포함한다.

## 아직 없는 것 (다음 Phase)

- learning_paths ~ progress (Phase 2 학습 엔진)
- challenges/missions/xp_ledger/badges (Phase 2 게임화)
- corporate_actions, fundamentals, market_sessions (Phase 3 확장 — 기업행사·장운영시간)
- cash_accounts, portfolio_snapshots (Phase 3 확장 — 현재는 ledger_entries에서 직접 계산)
- bias_events, coaching_reports (Phase 4)
- ai_conversations, ai_messages, retrieval_sources, model_runs, safety_events (Phase 4)
- notifications, subscriptions, support_tickets, audit_logs, feature_flags (Phase 5)
