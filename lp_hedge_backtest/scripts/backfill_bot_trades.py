"""One-off backfill: populate bot_trades from historical bot_events rows.

Safe to re-run: it skips configs that already have bot_trades rows unless
--force is passed.

Usage:
    ./venv/bin/python scripts/backfill_bot_trades.py
    ./venv/bin/python scripts/backfill_bot_trades.py --force
    ./venv/bin/python scripts/backfill_bot_trades.py --config-id 17
"""

import os
import sys
import argparse
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

# Allow importing api.* from repo root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from api.models import BotConfig, BotEvent, BotTrade
from api.database import Base, DB_URL


def _sync_db_url():
    url = os.getenv("DB_URL", DB_URL)
    return url.replace("mysql+aiomysql://", "mysql+pymysql://")


OPEN_EVENTS = {"hedge_opened", "fury_entry", "whale_new_position", "orphan_recovered"}
CLOSE_EVENTS = {"tp_hit", "sl_hit", "trailing_stop", "stopped", "fury_sl", "fury_tp", "whale_closed"}


def _safe_decimal(value):
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _compute_net_pnl(realized, fees, funding, il_offset):
    try:
        return Decimal(str(realized or 0)) - Decimal(str(fees or 0)) - Decimal(str(funding or 0)) + Decimal(str(il_offset or 0))
    except Exception:
        return None


def _extract_lp_pnl_usd(pnl_pct, size_usd):
    """LP bots emit pnl as percentage; convert to USD when size is known."""
    if pnl_pct is None or size_usd is None:
        return None
    try:
        return Decimal(str(size_usd)) * Decimal(str(pnl_pct)) / Decimal("100")
    except Exception:
        return None


def backfill_config(session, config_id: int, force: bool = False) -> int:
    """Backfill a single config_id. Returns number of trades inserted/updated."""
    cfg = session.execute(select(BotConfig).where(BotConfig.id == config_id)).scalar_one_or_none()
    if cfg is None:
        print(f"[Skip] Config {config_id} not found")
        return 0

    existing = session.execute(
        select(BotTrade).where(BotTrade.config_id == config_id).limit(1)
    ).scalar_one_or_none()
    if existing and not force:
        print(f"[Skip] Config {config_id} already has bot_trades rows (use --force to override)")
        return 0

    events = session.execute(
        select(BotEvent)
        .where(BotEvent.config_id == config_id)
        .where(BotEvent.event_type.in_(list(OPEN_EVENTS | CLOSE_EVENTS)))
        .order_by(BotEvent.ts, BotEvent.id)
    ).scalars().all()

    inserted = 0
    open_trade = None

    for ev in events:
        details = ev.details or {}
        price = _safe_decimal(ev.price_at_event)
        pnl = ev.pnl
        mode = cfg.mode
        pair = cfg.pair
        user_address = cfg.user_address

        if ev.event_type in OPEN_EVENTS:
            side = details.get("side")
            size_usd = _safe_decimal(details.get("notional") or details.get("size_usd"))
            entry_price = _safe_decimal(details.get("entry") or price)

            if mode in ("aragan", "avaro") and not side:
                side = "short"

            open_trade = BotTrade(
                config_id=config_id,
                user_address=user_address,
                mode=mode,
                pair=pair,
                side=side,
                entry_price=entry_price,
                size_usd=size_usd,
                opened_at=ev.ts,
            )
            session.add(open_trade)
            session.flush()  # get open_trade.id
            inserted += 1

        elif ev.event_type in CLOSE_EVENTS:
            # Realized PnL normalization
            realized_pnl_usd = None
            if pnl is not None:
                if mode in ("aragan", "avaro"):
                    size = open_trade.size_usd if open_trade else None
                    realized_pnl_usd = _extract_lp_pnl_usd(pnl, size)
                else:
                    realized_pnl_usd = _safe_decimal(pnl)

            # For external_close stopped events, details.outcome has USD PnL
            outcome = details.get("outcome") or {}
            if not realized_pnl_usd and outcome.get("pnl_usd"):
                realized_pnl_usd = _safe_decimal(outcome.get("pnl_usd"))

            fees_usd = _safe_decimal(details.get("fees_usd"))
            funding_usd = _safe_decimal(details.get("funding_usdc_net"))
            il_offset_usd = _safe_decimal(details.get("lp_value_close"))
            exit_price = _safe_decimal(outcome.get("close_px")) or price

            if open_trade is not None:
                open_trade.exit_price = exit_price
                open_trade.realized_pnl_usd = realized_pnl_usd
                open_trade.fees_usd = fees_usd
                open_trade.funding_usd = funding_usd
                open_trade.il_offset_usd = il_offset_usd
                open_trade.net_pnl_usd = _compute_net_pnl(realized_pnl_usd, fees_usd, funding_usd, il_offset_usd)
                open_trade.exit_reason = ev.event_type
                open_trade.closed_at = ev.ts
                open_trade = None
            else:
                # Closed-only estimate
                trade = BotTrade(
                    config_id=config_id,
                    user_address=user_address,
                    mode=mode,
                    pair=pair,
                    exit_price=exit_price,
                    realized_pnl_usd=realized_pnl_usd,
                    fees_usd=fees_usd,
                    funding_usd=funding_usd,
                    il_offset_usd=il_offset_usd,
                    net_pnl_usd=_compute_net_pnl(realized_pnl_usd, fees_usd, funding_usd, il_offset_usd),
                    exit_reason=ev.event_type,
                    is_estimate=True,
                    closed_at=ev.ts,
                )
                session.add(trade)
                inserted += 1

    session.commit()
    return inserted


def main():
    parser = argparse.ArgumentParser(description="Backfill bot_trades from bot_events")
    parser.add_argument("--config-id", type=int, help="Backfill only this config_id")
    parser.add_argument("--force", action="store_true", help="Re-backfill configs that already have rows")
    parser.add_argument("--batch", type=int, default=50, help="Configs to process per batch")
    args = parser.parse_args()

    engine = create_engine(_sync_db_url())
    Session = sessionmaker(bind=engine)
    session = Session()

    try:
        if args.config_id:
            configs = [args.config_id]
        else:
            result = session.execute(select(BotConfig.id).order_by(BotConfig.id))
            configs = [r[0] for r in result.all()]

        total = 0
        for config_id in configs:
            count = backfill_config(session, config_id, force=args.force)
            if count:
                print(f"[Backfill] Config {config_id}: {count} trade(s)")
                total += count

        print(f"[Backfill] Total trades inserted/updated: {total}")
    finally:
        session.close()


if __name__ == "__main__":
    main()
