"""시장 데이터 수동 수집 CLI.

    python -m scripts.ingest_market_data --ticker 005930 --exchange KRX --currency KRW --name 삼성전자

주의: 이 저장소를 개발한 샌드박스에서는 stooq.com 아웃바운드가 조직 egress
정책으로 차단되어 있어 이 스크립트를 라이브로 검증하지 못했다. egress가
허용된 환경(로컬 개발 PC, 배포 서버 등)에서 먼저 소규모로 검증한 뒤 사용할 것.
"""

import argparse

from app.core.db import SessionLocal
from app.domain.services.market_data import ProviderFetchError, StooqProvider, upsert_bars, upsert_instrument


def main() -> None:
    parser = argparse.ArgumentParser(description="stooq.com에서 일봉 데이터를 가져와 DB에 반영한다.")
    parser.add_argument("--ticker", required=True, help="예: 005930, AAPL")
    parser.add_argument("--exchange", required=True, help="KRX / NASDAQ / NYSE 등")
    parser.add_argument("--currency", required=True, help="KRW / USD 등 ISO 4217 코드")
    parser.add_argument("--name", required=True, help="종목명")
    args = parser.parse_args()

    provider = StooqProvider()
    try:
        raw_bars = provider.fetch_daily_bars(args.ticker, args.exchange)
    except ProviderFetchError as exc:
        raise SystemExit(f"조회 실패: {exc}")

    if not raw_bars:
        raise SystemExit("가져온 bar가 없습니다. 티커·거래소를 확인하세요.")

    db = SessionLocal()
    try:
        instrument = upsert_instrument(db, args.ticker, args.exchange, args.currency, args.name)
        written = upsert_bars(db, instrument, raw_bars, source=provider.name)
        db.commit()
        print(f"{args.ticker}.{args.exchange}: {written}개 bar 반영 (instrument_id={instrument.id})")
    finally:
        db.close()


if __name__ == "__main__":
    main()
