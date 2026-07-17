"""One-off enrichment for whale closed-only estimates.

Populates:
  - fees_usd = 0 (whale tracker is read-only, no HL taker fees)
  - funding_usd from bot_events.details.funding_since_open
  - net_pnl_usd = realized_pnl_usd - fees_usd - funding_usd + il_offset_usd
  - pair from bot_events.details.asset (if currently 'WHALE')

Safe to re-run: only touches rows where mode = 'whale', is_estimate = TRUE,
and funding_usd IS NULL.

Usage:
    ./venv/bin/python scripts/enrich_whale_estimates.py
    ./venv/bin/python scripts/enrich_whale_estimates.py --dry-run
"""

import os
import sys
import argparse
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, select, update
from sqlalchemy.orm import sessionmaker

from api.database import DB_URL
from api.models import BotTrade, BotEvent


def _sync_db_url():
    url = os.getenv("DB_URL", DB_URL)
    return url.replace("mysql+aiomysql://", "mysql+pymysql://")


def _safe_decimal(value):
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


def enrich(session, dry_run: bool = False) -> int:
    stmt = (
        select(BotTrade)
        .where(BotTrade.is_estimate.is_(True))
        .where(BotTrade.mode == "whale")
        .where(BotTrade.exit_reason == "whale_closed")
        .where(BotTrade.funding_usd.is_(None))
    )
    trades = session.execute(stmt).scalars().all()
    updated = 0

    for trade in trades:
        # Match the corresponding bot_event by config, timestamp, and exit price.
        event = session.execute(
            select(BotEvent)
            .where(BotEvent.config_id == trade.config_id)
            .where(BotEvent.event_type == "whale_closed")
            .where(BotEvent.ts == trade.closed_at)
            .where(BotEvent.price_at_event == trade.exit_price)
            .limit(1)
        ).scalar_one_or_none()

        if not event or not event.details:
            print(f"[Skip] trade {trade.id}: no matching whale_closed event")
            continue

        details = event.details
        funding = _safe_decimal(details.get("funding_since_open"))
        asset = details.get("asset")

        if funding is None:
            print(f"[Skip] trade {trade.id}: no funding_since_open in event details")
            continue

        realized = _safe_decimal(trade.realized_pnl_usd) or Decimal("0")
        fees = _safe_decimal(trade.fees_usd) or Decimal("0")
        il = _safe_decimal(trade.il_offset_usd) or Decimal("0")
        net = realized - fees - funding + il

        new_pair = asset if asset and trade.pair == "WHALE" else trade.pair

        print(
            f"[Update] trade {trade.id} ({new_pair}): "
            f"funding={funding:.4f} net={net:.4f}"
        )

        if not dry_run:
            session.execute(
                update(BotTrade)
                .where(BotTrade.id == trade.id)
                .values(
                    fees_usd=Decimal("0"),
                    funding_usd=funding,
                    net_pnl_usd=net,
                    pair=new_pair,
                )
            )
            updated += 1

    if not dry_run:
        session.commit()
    return updated


def main():
    parser = argparse.ArgumentParser(description="Enrich whale estimate rows")
    parser.add_argument("--dry-run", action="store_true", help="Print changes without writing")
    args = parser.parse_args()

    engine = create_engine(_sync_db_url())
    Session = sessionmaker(bind=engine)
    session = Session()

    try:
        updated = enrich(session, dry_run=args.dry_run)
        mode = "Dry-run" if args.dry_run else "Updated"
        print(f"{mode}: {updated} rows")
    finally:
        session.close()


if __name__ == "__main__":
    main()
