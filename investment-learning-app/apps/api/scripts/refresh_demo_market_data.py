"""데모 종목(005930/000660/AAPL/MSFT) 시드 시세의 as_of를 현재 시각으로 갱신한다.

market_data_staleness_threshold_seconds(기본 900초)를 넘긴 시세는 주문이
거부된다(6.7, 12.3). 라이브 시세 공급자 아웃바운드가 차단된 이 환경에서는
시드 bar가 한 번 오래되면 모의 매수/매도 자체가 막히므로, 로컬 개발·E2E
테스트 실행 전에 이 스크립트로 각 종목의 최신 bar 시각만 새로고침한다.
가격(OHLCV)이나 source는 바꾸지 않는다 — "seed-sample"이라는 표시는 유지한다.

    python -m scripts.refresh_demo_market_data
"""

from datetime import datetime, timezone

from sqlalchemy import func

from app.core.db import SessionLocal
from app.domain.market import Bar, Instrument


def main() -> None:
    db = SessionLocal()
    try:
        latest_bar_start_subq = (
            db.query(Bar.instrument_id, func.max(Bar.bar_start).label("max_bar_start"))
            .group_by(Bar.instrument_id)
            .subquery()
        )
        latest_bars = (
            db.query(Bar)
            .join(
                latest_bar_start_subq,
                (Bar.instrument_id == latest_bar_start_subq.c.instrument_id)
                & (Bar.bar_start == latest_bar_start_subq.c.max_bar_start),
            )
            .all()
        )

        now = datetime.now(timezone.utc)
        updated = 0
        for bar in latest_bars:
            bar.as_of = now
            bar.delay_seconds = 0
            updated += 1
        db.commit()

        tickers = [i.ticker for i in db.query(Instrument).filter(Instrument.valid_to.is_(None)).all()]
        print(f"{updated}개 종목의 최신 시세 as_of를 {now.isoformat()}로 갱신했습니다. (대상: {', '.join(tickers)})")
    finally:
        db.close()


if __name__ == "__main__":
    main()
