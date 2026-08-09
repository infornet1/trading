"""One-off backfill: populate the profitability-dashboard columns on
signal_executions that were closed by the Telegram listener.

Why these rows exist: until 2026-08-09, `_auto_close_signal` in
telegram_listener/listener.py wrote only `close_price`. `realized_pnl_usd`,
`fees_usd`, `closed_at` and `exit_reason` were written exclusively by
api/signal_reconciler.py, so every close driven by a channel update
(target_hit / stopped / "close it here") stayed invisible to /performance/*
— api/routers/performance.py filters signal executions on `closed_at`, so a
NULL there drops the row from every date-ranged query.

P&L uses the same convention as the reconciler and the listener:
realized_pnl_usd is GROSS (price return only) and fees_usd is separate,
because performance.py subtracts fees itself.

`closed_at` is not recorded anywhere for these rows, so it is approximated
from signal_events.updated_at — the moment the channel update flipped the
signal's status. exit_reason is set to 'backfill' rather than a guessed
'sl'/'tp' so the value is never mistaken for an observed fill reason.

Safe to re-run: only touches rows where close_price IS NOT NULL AND
closed_at IS NULL. Dry-run by default.

Usage:
    ./venv/bin/python scripts/backfill_signal_close_pnl.py           # preview
    ./venv/bin/python scripts/backfill_signal_close_pnl.py --apply   # write
"""

import os
import sys
import argparse
from decimal import Decimal

# Allow importing api.* from repo root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from api.models import SignalEvent, SignalExecution
from api.database import DB_URL

#: HL taker fee, both sides of the round trip (0.045% x 2).
HL_ROUND_TRIP_FEE_PCT = Decimal("0.0009")


def _sync_db_url():
    url = os.getenv("DB_URL", DB_URL)
    return url.replace("mysql+aiomysql://", "mysql+pymysql://")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true",
                    help="write the changes (default is a dry run)")
    args = ap.parse_args()

    engine = create_engine(_sync_db_url(), pool_pre_ping=True)
    Session = sessionmaker(bind=engine)

    with Session() as db:
        rows = db.execute(
            select(SignalExecution, SignalEvent)
            .join(SignalEvent, SignalExecution.signal_id == SignalEvent.id)
            .where(
                SignalExecution.close_price.isnot(None),
                SignalExecution.closed_at.is_(None),
            )
            .order_by(SignalExecution.id)
        ).all()

        if not rows:
            print("Nothing to backfill — no closed executions are missing P&L.")
            return

        print(f"{len(rows)} execution(s) to backfill"
              f"{'' if args.apply else ' (DRY RUN — nothing written)'}\n")
        header = f"{'exec':>5} {'sig':>4} {'pair':<10} {'gross P&L':>10} {'fees':>7} {'closed_at':<19} note"
        print(header)
        print("-" * len(header))

        updated = skipped = 0
        total_pnl = total_fees = Decimal("0")

        for execution, signal in rows:
            entry = execution.fill_price
            close = execution.close_price
            size  = execution.exec_size_usdt
            lev   = execution.exec_leverage or signal.leverage or 1

            if not (entry and close and size):
                print(f"{execution.id:>5} {signal.id:>4} {signal.pair:<10} "
                      f"{'—':>10} {'—':>7} {'—':<19} skipped: missing entry/close/size")
                skipped += 1
                continue

            is_short = signal.direction != "long"
            raw_pct  = ((entry - close) / entry) if is_short else ((close - entry) / entry)
            pnl      = size * raw_pct * Decimal(lev)
            fees     = size * HL_ROUND_TRIP_FEE_PCT * Decimal(lev)
            closed_at = signal.updated_at or execution.executed_at

            print(f"{execution.id:>5} {signal.id:>4} {signal.pair:<10} "
                  f"{pnl:>10.4f} {fees:>7.4f} {str(closed_at):<19} "
                  f"{'approx from signal.updated_at' if signal.updated_at else 'fallback: executed_at'}")

            if args.apply:
                execution.realized_pnl_usd = pnl
                execution.fees_usd         = fees
                execution.closed_at        = closed_at
                execution.exit_reason      = "backfill"

            updated += 1
            total_pnl  += pnl
            total_fees += fees

        if args.apply:
            db.commit()

        print("-" * len(header))
        print(f"{updated} backfilled, {skipped} skipped")
        print(f"Gross P&L {total_pnl:+.4f} USD | fees {total_fees:.4f} USD "
              f"| net {total_pnl - total_fees:+.4f} USD")
        if not args.apply:
            print("\nDry run only. Re-run with --apply to write.")


if __name__ == "__main__":
    main()
