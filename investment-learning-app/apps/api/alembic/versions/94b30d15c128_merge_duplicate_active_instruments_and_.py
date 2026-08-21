"""merge duplicate active instruments and add unique constraint

Revision ID: 94b30d15c128
Revises: d9719e5a287e
Create Date: 2026-08-21 22:10:00.000000

배경: instruments 테이블에는 (ticker, exchange) DB unique 제약이 의도적으로
없었다(심볼 재사용 대비, market.py의 Instrument 모델 docstring 참고). 하지만
이는 "같은 티커가 시간이 지나 다른 종목에 재배정될 수 있다"는 뜻이지 "동시에
활성(valid_to IS NULL)인 행이 여러 개 있어도 된다"는 뜻이 아니었다. 실제로는
시드 마이그레이션(0f12a06bce94)과 테스트 fixture가 존재 여부를 확인하지 않고
매번 새 행을 raw INSERT해, 같은 (exchange, ticker)에 대해 동시에 활성인 행이
여러 개 쌓였다.

이 migration은:
1. 활성 행을 (exchange, 정규화된 ticker) 기준으로 정규화(trim+upper)한다.
2. 정규화 후에도 같은 그룹에 활성 행이 2개 이상이면, 결정 규칙에 따라
   canonical을 고르고 나머지(중복) 행이 참조되는 모든 곳(bars/orders/
   positions/journal_entries)을 canonical로 안전하게 재지정한 뒤에만 중복
   행을 비활성화(valid_to 기록, 하드 DELETE 아님)한다.
3. bar 충돌(같은 interval+bar_start인데 값이 다름)이나 position 충돌(같은
   포트폴리오가 중복 종목과 canonical 종목 양쪽에 이미 포지션을 보유)처럼
   안전하게 자동 병합할 수 없는 경우, 값을 조용히 버리지 않고 migration
   자체를 실패시켜 수동 검토를 요구한다.
4. 정리가 끝난 뒤에만 (exchange, ticker) partial unique index(활성 행에만
   적용)를 추가해 앞으로 같은 문제가 재발하지 않게 한다.

주의: downgrade()는 unique index만 제거한다 — 데이터 병합(참조 재지정,
valid_to 기록)은 되돌리지 않는다. 병합 이후 새로 생성된 참조가 이미 canonical
행을 가리키고 있어, 이를 "원래 어느 중복 행을 가리켰는지" 되짚어 복원할
근거가 없기 때문이다(안전하게 되돌릴 수 없는 것을 억지로 되돌리지 않는다).
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision = '94b30d15c128'
down_revision = 'd9719e5a287e'
branch_labels = None
depends_on = None

UNIQUE_INDEX_NAME = "uq_instruments_active_exchange_ticker"


class DuplicateInstrumentMergeError(RuntimeError):
    """중복 Instrument를 안전하게 병합할 수 없을 때 migration을 중단시킨다.

    이 예외가 발생하면 Alembic이 트랜잭션을 롤백하므로 데이터는 이 migration
    실행 이전 상태 그대로 남는다 — 부분적으로만 병합된 상태가 되지 않는다.
    """


def upgrade() -> None:
    conn = op.get_bind()

    # 0. 활성 행의 ticker/exchange를 정규화한다(공백 제거 + 대문자). 이미
    #    정규화된 값(대부분의 기존 데이터)은 그대로 유지된다.
    conn.execute(text(
        "UPDATE instruments "
        "SET ticker = upper(trim(ticker)), exchange = upper(trim(exchange)) "
        "WHERE valid_to IS NULL "
        "AND (ticker <> upper(trim(ticker)) OR exchange <> upper(trim(exchange)))"
    ))

    # 1. 정규화 후에도 남아있는 중복 그룹을 찾는다.
    groups = conn.execute(text(
        "SELECT exchange, ticker, array_agg(id) AS ids "
        "FROM instruments WHERE valid_to IS NULL "
        "GROUP BY exchange, ticker HAVING count(*) > 1"
    )).fetchall()

    if groups:
        now = conn.execute(text("SELECT now()")).scalar()
        for group in groups:
            _merge_group(conn, group.exchange, group.ticker, list(group.ids), now)

    # 2. 정리가 끝난 뒤에만 unique index를 추가한다 — 병합이 실패했다면(예외로
    #    중단됐다면) 이 지점에 도달하지 않고, 트랜잭션 전체가 롤백된다.
    op.create_index(
        UNIQUE_INDEX_NAME,
        "instruments",
        ["exchange", "ticker"],
        unique=True,
        postgresql_where=sa.text("valid_to IS NULL"),
    )


def _merge_group(conn, exchange: str, ticker: str, ids: list, now) -> None:
    # canonical 결정 규칙(임의 선택 금지 — 순서대로 적용):
    #   1) 참조(bars+orders+positions+journal_entries) 개수가 가장 많은 id
    #   2) 동률이면 created_at이 가장 이른(오래된) id
    #   3) 그래도 동률이면 UUID 문자열이 가장 작은 id(안정적 tie-breaker)
    ref_counts = {iid: _reference_count(conn, iid) for iid in ids}
    created_ats = {
        iid: conn.execute(
            text("SELECT created_at FROM instruments WHERE id = :id"), {"id": iid}
        ).scalar()
        for iid in ids
    }
    canonical_id = sorted(ids, key=lambda i: (-ref_counts[i], created_ats[i], str(i)))[0]
    duplicate_ids = [i for i in ids if i != canonical_id]

    for dup_id in duplicate_ids:
        _merge_bars(conn, dup_id, canonical_id, exchange, ticker)
        _merge_positions(conn, dup_id, canonical_id, exchange, ticker)
        # orders/journal_entries에는 instrument_id 관련 unique 제약이 없으므로
        # 충돌 걱정 없이 그대로 재지정한다.
        conn.execute(
            text("UPDATE orders SET instrument_id = :canonical WHERE instrument_id = :dup"),
            {"canonical": canonical_id, "dup": dup_id},
        )
        conn.execute(
            text("UPDATE journal_entries SET instrument_id = :canonical WHERE instrument_id = :dup"),
            {"canonical": canonical_id, "dup": dup_id},
        )
        # 모든 참조를 canonical로 옮긴 뒤에만 중복 행을 비활성화한다. 하드
        # DELETE 대신 valid_to를 채워, 이력을 남기고 필요하면 수동으로 다시
        # 조사할 수 있게 한다.
        conn.execute(
            text("UPDATE instruments SET valid_to = :now WHERE id = :dup"),
            {"now": now, "dup": dup_id},
        )


def _reference_count(conn, instrument_id) -> int:
    total = 0
    for table in ("bars", "orders", "positions", "journal_entries"):
        total += conn.execute(
            text(f"SELECT count(*) FROM {table} WHERE instrument_id = :id"),
            {"id": instrument_id},
        ).scalar()
    return total


def _merge_bars(conn, dup_id, canonical_id, exchange: str, ticker: str) -> None:
    dup_bars = conn.execute(
        text(
            "SELECT id, interval, bar_start, open, high, low, close, volume, source "
            "FROM bars WHERE instrument_id = :dup"
        ),
        {"dup": dup_id},
    ).fetchall()

    for bar in dup_bars:
        existing = conn.execute(
            text(
                "SELECT id, open, high, low, close, volume, source FROM bars "
                "WHERE instrument_id = :canonical AND interval = :interval AND bar_start = :bar_start"
            ),
            {"canonical": canonical_id, "interval": bar.interval, "bar_start": bar.bar_start},
        ).fetchone()

        if existing is None:
            conn.execute(
                text("UPDATE bars SET instrument_id = :canonical WHERE id = :bar_id"),
                {"canonical": canonical_id, "bar_id": bar.id},
            )
            continue

        identical = (
            existing.open == bar.open
            and existing.high == bar.high
            and existing.low == bar.low
            and existing.close == bar.close
            and existing.volume == bar.volume
            and existing.source == bar.source
        )
        if identical:
            # 완전히 같은 값의 중복 bar 행 — canonical 쪽을 유지하고 중복은 버린다.
            conn.execute(text("DELETE FROM bars WHERE id = :bar_id"), {"bar_id": bar.id})
        else:
            raise DuplicateInstrumentMergeError(
                f"{exchange}/{ticker} 중복 종목 병합 실패: bar 충돌 "
                f"(dup instrument={dup_id} bar={bar.id} vs canonical instrument={canonical_id} "
                f"bar={existing.id}, interval={bar.interval!r}, bar_start={bar.bar_start}) — "
                "같은 interval+bar_start인데 값(가격/거래량/source)이 서로 달라 자동으로 "
                "병합할 수 없습니다. 수동 검토가 필요합니다."
            )


def _merge_positions(conn, dup_id, canonical_id, exchange: str, ticker: str) -> None:
    dup_positions = conn.execute(
        text("SELECT id, portfolio_id FROM positions WHERE instrument_id = :dup"),
        {"dup": dup_id},
    ).fetchall()

    for pos in dup_positions:
        conflict = conn.execute(
            text(
                "SELECT id FROM positions WHERE instrument_id = :canonical AND portfolio_id = :portfolio_id"
            ),
            {"canonical": canonical_id, "portfolio_id": pos.portfolio_id},
        ).fetchone()
        if conflict is not None:
            raise DuplicateInstrumentMergeError(
                f"{exchange}/{ticker} 중복 종목 병합 실패: 포트폴리오 {pos.portfolio_id}가 "
                f"중복 종목({dup_id})과 canonical 종목({canonical_id}) 양쪽에 이미 포지션을 "
                f"보유하고 있습니다(position={pos.id} vs {conflict.id}) — 수량/평단가를 자동으로 "
                "합치면 사용자 보유 내역이 왜곡될 수 있어 수동 검토가 필요합니다."
            )
        conn.execute(
            text("UPDATE positions SET instrument_id = :canonical WHERE id = :pos_id"),
            {"canonical": canonical_id, "pos_id": pos.id},
        )


def downgrade() -> None:
    op.drop_index(UNIQUE_INDEX_NAME, table_name="instruments")
    # 데이터 병합(참조 재지정, valid_to 기록)은 되돌리지 않는다 — 자세한 이유는
    # 모듈 docstring 참고.
