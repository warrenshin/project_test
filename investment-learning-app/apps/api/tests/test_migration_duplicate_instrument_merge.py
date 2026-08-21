"""alembic/versions/94b30d15c128 (중복 Instrument 병합 + unique constraint)을
실제로 downgrade/upgrade 하며 검증한다 — 일반 애플리케이션 코드 테스트가 아니라
migration 자체의 데이터 보존·충돌 처리를 확인하는 전용 테스트다.

시나리오(item 13 요구사항):
1. 중복 없음 — no-op으로 안전하게 constraint만 생성
2. 중복 Instrument만 존재(참조 없음) — canonical만 남고 나머지는 valid_to 기록
3. 각 중복에 bars 존재(충돌 없음) — 모두 canonical로 재지정
4. 각 중복에 orders/positions 존재 — 모두 canonical로 재지정
5. 동일 timestamp/interval bar 충돌 — migration이 실패하고 롤백되어야 함(부분 반영 금지)
6. downgrade -> 다시 upgrade 반복 후에도 데이터·참조 무결성 유지

각 시나리오는 고유하게 태그된 ticker만 써서 서로 겹치지 않는다. 테스트 데이터만
쓰고 실제 사용자 데이터는 건드리지 않는다.
"""

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text

from tests.conftest import signup_user

DOWN_REVISION = "d9719e5a287e"  # 이 migration 바로 이전
TARGET_REVISION = "94b30d15c128"  # 이 migration 자체
HEAD_REVISION = "d5d5285c1108"  # 이 파일의 테스트가 끝난 뒤 반드시 복귀해야 하는 최종 head


def _alembic_config() -> Config:
    api_root = Path(__file__).resolve().parents[1]
    return Config(str(api_root / "alembic.ini"))


@pytest.fixture
def migration_cycle():
    """각 테스트 전후로 정확히 DOWN_REVISION <-> TARGET_REVISION을 오가고,
    테스트가 끝나면(성공/실패 무관) 항상 head로 복귀시켜 이후 다른 테스트
    파일에 영향을 주지 않는다."""
    cfg = _alembic_config()
    command.downgrade(cfg, DOWN_REVISION)
    yield cfg
    command.upgrade(cfg, HEAD_REVISION)


def _insert_instrument(db, ticker: str, exchange: str, valid_to=None) -> str:
    instrument_id = str(uuid.uuid4())
    db.execute(
        text(
            "INSERT INTO instruments (id, ticker, exchange, currency, name, is_tradable, valid_to, created_at) "
            "VALUES (:id, :ticker, :exchange, 'USD', :ticker, true, :valid_to, now())"
        ),
        {"id": instrument_id, "ticker": ticker, "exchange": exchange, "valid_to": valid_to},
    )
    return instrument_id


def _insert_bar(db, instrument_id: str, bar_start, close: str, source: str) -> str:
    bar_id = str(uuid.uuid4())
    db.execute(
        text(
            "INSERT INTO bars (id, instrument_id, interval, open, high, low, close, volume, bar_start, source, as_of, delay_seconds) "
            "VALUES (:id, :iid, '1d', :close, :close, :close, :close, 1000, :bar_start, :source, now(), 0)"
        ),
        {"id": bar_id, "iid": instrument_id, "close": close, "bar_start": bar_start, "source": source},
    )
    return bar_id


def test_upgrade_is_noop_when_no_duplicates_exist(db, migration_cycle):
    tag = uuid.uuid4().hex[:8].upper()
    ticker = f"MIGNODUP{tag}"
    instrument_id = _insert_instrument(db, ticker, "NASDAQ")
    db.commit()

    command.upgrade(migration_cycle, TARGET_REVISION)

    row = db.execute(
        text("SELECT valid_to FROM instruments WHERE id = :id"), {"id": instrument_id}
    ).first()
    assert row.valid_to is None  # 손대지 않았다

    index_exists = db.execute(
        text("SELECT 1 FROM pg_indexes WHERE indexname = 'uq_instruments_active_exchange_ticker'")
    ).first()
    assert index_exists is not None
    # 읽기만 했어도 세션에 트랜잭션이 열린 채로 남는다 — 이후(픽스처 teardown
    # 포함) alembic이 별도 커넥션에서 DDL을 실행할 때 이 트랜잭션이 lock을
    # 잡고 있으면 서로 영원히 기다리는 déadlock이 된다. 매 읽기 뒤 반드시
    # commit()으로 비워둔다.
    db.commit()


def test_duplicates_with_no_references_are_merged_and_invalidated(db, migration_cycle):
    tag = uuid.uuid4().hex[:8].upper()
    ticker = f"MIGDUP{tag}"
    older_id = _insert_instrument(db, ticker, "NASDAQ")
    db.execute(text("UPDATE instruments SET created_at = now() - interval '1 day' WHERE id = :id"), {"id": older_id})
    newer_id = _insert_instrument(db, ticker, "NASDAQ")
    db.commit()

    command.upgrade(migration_cycle, TARGET_REVISION)

    rows = db.execute(
        text("SELECT id, valid_to FROM instruments WHERE ticker = :t AND exchange = 'NASDAQ'"), {"t": ticker}
    ).fetchall()
    assert len(rows) == 2
    active = [r for r in rows if r.valid_to is None]
    invalidated = [r for r in rows if r.valid_to is not None]
    assert len(active) == 1
    assert len(invalidated) == 1
    # 참조가 둘 다 0개로 동률이므로 tie-break 규칙(더 오래된 created_at)에 따라
    # older_id가 canonical로 남아야 한다 — 임의 선택이 아니다.
    assert str(active[0].id) == older_id
    assert str(invalidated[0].id) == newer_id
    db.commit()  # 읽기로 열린 트랜잭션을 비운다(픽스처 teardown DDL과의 deadlock 방지)


def test_duplicates_with_non_conflicting_bars_are_repointed_to_canonical(db, migration_cycle):
    tag = uuid.uuid4().hex[:8].upper()
    ticker = f"MIGBARS{tag}"
    canonical_id = _insert_instrument(db, ticker, "NASDAQ")
    dup_id = _insert_instrument(db, ticker, "NASDAQ")
    now = datetime.now(timezone.utc)
    # canonical 쪽이 참조(bar)가 하나 더 많으므로 참조 개수 규칙상 canonical로 선택된다.
    _insert_bar(db, canonical_id, now - timedelta(days=2), "100", "demo")
    _insert_bar(db, canonical_id, now - timedelta(days=1), "101", "demo")
    dup_bar_start = now - timedelta(days=3)  # canonical과 겹치지 않는 시각 -> 충돌 없음
    _insert_bar(db, dup_id, dup_bar_start, "99", "stooq")
    db.commit()

    command.upgrade(migration_cycle, TARGET_REVISION)

    bars = db.execute(text("SELECT instrument_id FROM bars WHERE bar_start = :bs"), {"bs": dup_bar_start}).fetchall()
    assert len(bars) == 1
    assert str(bars[0].instrument_id) == canonical_id  # 중복 쪽 bar가 canonical로 옮겨졌다

    dup_row = db.execute(text("SELECT valid_to FROM instruments WHERE id = :id"), {"id": dup_id}).first()
    assert dup_row.valid_to is not None
    db.commit()


def test_duplicates_with_orders_and_positions_are_repointed_to_canonical(db, migration_cycle):
    tag = uuid.uuid4().hex[:8].upper()
    ticker = f"MIGREFS{tag}"
    canonical_id = _insert_instrument(db, ticker, "NASDAQ")
    dup_id = _insert_instrument(db, ticker, "NASDAQ")
    # dup 쪽에는 order 1개 + position 1개(참조 2개)가 붙을 예정이므로, canonical
    # 쪽에는 bar를 3개 붙여 참조 개수 규칙상 확실히 canonical로 선택되게 한다.
    now = datetime.now(timezone.utc)
    _insert_bar(db, canonical_id, now - timedelta(days=1), "100", "demo")
    _insert_bar(db, canonical_id, now - timedelta(days=2), "101", "demo")
    _insert_bar(db, canonical_id, now - timedelta(days=3), "102", "demo")
    db.commit()

    cookies, portfolio_id = signup_user(f"migrefs{tag.lower()}")

    order_id = str(uuid.uuid4())
    db.execute(
        text(
            "INSERT INTO orders (id, portfolio_id, instrument_id, side, order_type, quantity, "
            "time_in_force, status, submitted_at, policy_version, idempotency_key, created_at) "
            "VALUES (:id, :pid, :iid, 'BUY', 'MARKET', 1, 'DAY', 'FILLED', now(), 'US:v1', :idem, now())"
        ),
        {"id": order_id, "pid": portfolio_id, "iid": dup_id, "idem": str(uuid.uuid4())},
    )
    position_id = str(uuid.uuid4())
    db.execute(
        text(
            "INSERT INTO positions (id, portfolio_id, instrument_id, quantity, average_cost, created_at) "
            "VALUES (:id, :pid, :iid, 1, 100, now())"
        ),
        {"id": position_id, "pid": portfolio_id, "iid": dup_id},
    )
    db.commit()

    command.upgrade(migration_cycle, TARGET_REVISION)

    order_row = db.execute(text("SELECT instrument_id FROM orders WHERE id = :id"), {"id": order_id}).first()
    position_row = db.execute(text("SELECT instrument_id FROM positions WHERE id = :id"), {"id": position_id}).first()
    assert str(order_row.instrument_id) == canonical_id
    assert str(position_row.instrument_id) == canonical_id
    db.commit()


def test_conflicting_bars_abort_migration_without_partial_changes(db, migration_cycle):
    """같은 interval+bar_start인데 값이 다른 bar가 두 중복 종목에 각각 있으면,
    migration은 이를 조용히 아무 쪽이나 골라 병합하지 않고 실패해야 한다 —
    실패 시 이 그룹뿐 아니라 트랜잭션 전체가 롤백되어 부분 반영도 없어야 한다."""
    tag = uuid.uuid4().hex[:8].upper()
    ticker = f"MIGCONFLICT{tag}"
    # 충돌 시나리오와는 무관한, 정상적으로 병합됐어야 할 다른 그룹도 함께 넣어
    # "이 그룹 실패가 트랜잭션 전체를 롤백시키는지"까지 확인한다.
    other_ticker = f"MIGOK{tag}"
    other_canonical = _insert_instrument(db, other_ticker, "NASDAQ")
    other_dup = _insert_instrument(db, other_ticker, "NASDAQ")

    canonical_id = _insert_instrument(db, ticker, "NASDAQ")
    dup_id = _insert_instrument(db, ticker, "NASDAQ")
    same_bar_start = datetime.now(timezone.utc) - timedelta(days=1)
    _insert_bar(db, canonical_id, same_bar_start, "100", "demo")
    _insert_bar(db, dup_id, same_bar_start, "999", "stooq")  # 같은 시각, 다른 값 -> 충돌
    db.commit()

    with pytest.raises(Exception):
        command.upgrade(migration_cycle, TARGET_REVISION)

    # 실패했으므로 unique index도 생성되지 않았고, 충돌난 그룹도 그대로 남아
    # 있어야 한다(둘 다 여전히 활성 상태 — 부분적으로 병합되지 않았다).
    index_exists = db.execute(
        text("SELECT 1 FROM pg_indexes WHERE indexname = 'uq_instruments_active_exchange_ticker'")
    ).first()
    assert index_exists is None
    db.commit()

    conflict_rows = db.execute(
        text("SELECT valid_to FROM instruments WHERE ticker = :t"), {"t": ticker}
    ).fetchall()
    assert all(r.valid_to is None for r in conflict_rows)  # 둘 다 그대로 활성
    db.commit()

    # 트랜잭션 전체 롤백 확인: 충돌과 무관했던 other_ticker 그룹도 병합되지
    # 않은 채(즉 이번 실패한 upgrade 시도에서는 손대지 않은 채) 남아 있어야 한다.
    other_rows = db.execute(
        text("SELECT valid_to FROM instruments WHERE ticker = :t"), {"t": other_ticker}
    ).fetchall()
    assert all(r.valid_to is None for r in other_rows)
    db.commit()

    # 충돌 데이터를 정리한 뒤에는 정상적으로 병합·constraint 생성이 가능함을 확인한다
    # (migration_cycle fixture가 테스트 종료 시 head로 복귀시키려면 이 upgrade가
    # 성공해야 한다).
    db.execute(text("DELETE FROM bars WHERE instrument_id IN (:a, :b)"), {"a": canonical_id, "b": dup_id})
    db.execute(text("DELETE FROM instruments WHERE id IN (:a, :b)"), {"a": canonical_id, "b": dup_id})
    db.commit()

    command.upgrade(migration_cycle, TARGET_REVISION)
    other_rows_after = db.execute(
        text("SELECT valid_to FROM instruments WHERE ticker = :t"), {"t": other_ticker}
    ).fetchall()
    assert sum(1 for r in other_rows_after if r.valid_to is None) == 1  # 이번엔 정상 병합됨
    db.commit()


def test_downgrade_then_upgrade_again_preserves_integrity(db, migration_cycle):
    """downgrade(constraint 제거) 후 다시 upgrade해도 — 이미 이전 upgrade에서
    병합이 끝난 데이터라 새로운 중복 그룹이 없으므로 — 참조 무결성이 그대로
    유지되어야 한다(재실행해도 안전)."""
    tag = uuid.uuid4().hex[:8].upper()
    ticker = f"MIGCYCLE{tag}"
    older_id = _insert_instrument(db, ticker, "NASDAQ")
    db.execute(text("UPDATE instruments SET created_at = now() - interval '1 day' WHERE id = :id"), {"id": older_id})
    newer_id = _insert_instrument(db, ticker, "NASDAQ")
    db.commit()

    command.upgrade(migration_cycle, TARGET_REVISION)
    first_pass = db.execute(
        text("SELECT id, valid_to FROM instruments WHERE ticker = :t"), {"t": ticker}
    ).fetchall()
    assert sum(1 for r in first_pass if r.valid_to is None) == 1
    db.commit()

    command.downgrade(migration_cycle, DOWN_REVISION)
    command.upgrade(migration_cycle, TARGET_REVISION)

    second_pass = db.execute(
        text("SELECT id, valid_to FROM instruments WHERE ticker = :t"), {"t": ticker}
    ).fetchall()
    # 재실행 후에도 여전히 활성 행은 정확히 1개, 그리고 같은 id(older_id)여야
    # 한다 — 재실행이 데이터를 더 망가뜨리지 않는다.
    active_second = [r for r in second_pass if r.valid_to is None]
    assert len(active_second) == 1
    assert str(active_second[0].id) == older_id
    db.commit()
