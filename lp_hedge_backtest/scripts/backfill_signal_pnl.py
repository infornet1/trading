"""One-off backfill: populate realized_pnl_usd/fees_usd/closed_at/exit_reason
for old closed Signal Lab executions.

Stores gross P&L (price return only) in realized_pnl_usd, and fees separately
in fees_usd, so api/routers/performance.py can compute net consistently.

Safe to re-run: only touches rows where close_price IS NOT NULL and
realized_pnl_usd IS NULL.

Usage:
    ./venv/bin/python scripts/backfill_signal_pnl.py
    ./venv/bin/python scripts/backfill_signal_pnl.py --dry-run
    ./venv/bin/python scripts/backfill_signal_pnl.py --limit 10
"""

import os
import sys
import argparse
from decimal import Decimal

# Allow importing api.* from repo root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, select, update
from sqlalchemy.orm import sessionmaker

from api.database import DB_URL
from api.models import SignalExecution, SignalEvent

FEES_PCT = Decimal("0.0009")  # 0.045% taker × 2 sides
DEFAULT_NOTIONAL = Decimal("10.0")  # SIGNAL_TEST_NOTIONAL_USDC fallback


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


def backfill(session, dry_run: bool = False, limit: int | None = None) -> int:
    """Backfill closed signal executions. Returns number of rows updated."""
    stmt = (
        select(SignalExecution, SignalEvent)
        .join(SignalEvent, SignalExecution.signal_id == SignalEvent.id)
        .where(SignalExecution.close_price.isnot(None))
        .where(SignalExecution.realized_pnl_usd.is_(None))
    )
    if limit:
        stmt = stmt.limit(limit)

    rows = session.execute(stmt).all()
    updated = 0

    for execution, signal in rows:
        fill = _safe_decimal(execution.fill_price)
        close = _safe_decimal(execution.close_price)
        direction = (signal.direction or "long").lower()
        leverage = _safe_decimal(execution.exec_leverage) or _safe_decimal(signal.leverage) or Decimal("1")
        notional = _safe_decimal(execution.exec_size_usdt) or DEFAULT_NOTIONAL

        if not fill or not close or fill == 0:
            print(f"[Skip] Execution {execution.id}: missing/invalid fill or close price")
            continue

        if direction == "short":
            raw_return = (fill - close) / fill
        else:
            raw_return = (close - fill) / fill

        realized = notional * leverage * raw_return
        fees = notional * leverage * FEES_PCT

        # Infer exit reason from P&L sign; old signal_events.status can be stale.
        if realized > 0:
            exit_reason = "tp1"
        elif realized < 0:
            exit_reason = "sl"
        elif signal.status == "tp_hit":
            exit_reason = "tp1"
        elif signal.status == "stopped":
            exit_reason = "sl"
        else:
            exit_reason = "unknown"

        closed_at = signal.updated_at

        print(
            f"[Update] exec {execution.id} ({direction}, lev={leverage}, "
            f"notional=${notional:.2f}): realized={realized:.4f} fees={fees:.4f} "
            f"reason={exit_reason} closed_at={closed_at}"
        )

        if not dry_run:
            session.execute(
                update(SignalExecution)
                .where(SignalExecution.id == execution.id)
                .values(
                    realized_pnl_usd=realized,
                    fees_usd=fees,
                    closed_at=closed_at,
                    exit_reason=exit_reason,
                )
            )
            updated += 1

    if not dry_run:
        session.commit()
    return updated


def main():
    parser = argparse.ArgumentParser(description="Backfill Signal Lab P&L")
    parser.add_argument("--dry-run", action="store_true", help="Print changes without writing")
    parser.add_argument("--limit", type=int, default=None, help="Process at most N rows")
    args = parser.parse_args()

    engine = create_engine(_sync_db_url())
    Session = sessionmaker(bind=engine)
    session = Session()

    try:
        updated = backfill(session, dry_run=args.dry_run, limit=args.limit)
        mode = "Dry-run" if args.dry_run else "Updated"
        print(f"{mode}: {updated} rows")
    finally:
        session.close()


if __name__ == "__main__":
    main()
