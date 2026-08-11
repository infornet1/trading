"""One-off correction: remove the double-counted leverage factor from
signal_executions.realized_pnl_usd and .fees_usd.

The bug: `exec_size_usdt` is the NOTIONAL (size × fill_price — see
api/signal_executor.place_hl_order), so leverage is already embedded in it.
Every writer of these columns multiplied by leverage a second time:

    realized_pnl_usd = size * raw_pnl_pct * leverage    # wrong

so each stored value is inflated by exactly its leverage multiple (3× … 60×).
Confirmed against Hyperliquid's own `closedPnl` on 2026-08-11: exec 137 (DOT,
10×) was stored as +2.6560 while HL reported +0.2657.

Affected writers, all fixed 2026-08-11:
  * api/signal_reconciler.py            (since the dashboard shipped 2026-07-16)
  * telegram_listener/listener.py       (_close_pnl_usd)
  * scripts/backfill_signal_close_pnl.py

Two groups of rows need different treatment:

  A. exec_size_usdt IS NOT NULL — recompute from first principles:
         pnl  = notional × price_return
         fees = notional × 0.0009
     Exact, and it re-derives rather than trusting the stored number.

  B. exec_size_usdt IS NULL — pre-M5 rows, written by the 2026-07-16 dashboard
     backfill using a hardcoded $10 notional × leverage. The notional is not
     recorded anywhere, so these can only be divided by the leverage that
     inflated them (signal_events.leverage, the value that backfill used).
     Verified against the stored values before dividing; any row that does not
     reproduce is reported and skipped rather than guessed at.

Safe to re-run: group A is idempotent by construction, and group B is skipped
once its stored value no longer matches the inflated formula. Dry-run default.

Usage:
    ./venv/bin/python scripts/fix_signal_pnl_leverage.py           # preview
    ./venv/bin/python scripts/fix_signal_pnl_leverage.py --apply   # write
"""

import os
import sys
import argparse
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from api.models import SignalEvent, SignalExecution
from api.database import DB_URL

#: HL taker fee, both sides of the round trip (0.045% × 2), on notional.
HL_ROUND_TRIP_FEE_PCT = Decimal("0.0009")

#: Notional assumed by the 2026-07-16 dashboard backfill for pre-M5 rows.
LEGACY_ASSUMED_NOTIONAL = Decimal("10")

#: Tolerance when checking that a legacy row reproduces the inflated formula.
LEGACY_MATCH_TOLERANCE = Decimal("0.01")


def _sync_db_url():
    return os.getenv("DB_URL", DB_URL).replace("mysql+aiomysql://", "mysql+pymysql://")


def _price_return(entry: Decimal, close: Decimal, is_short: bool) -> Decimal:
    return ((entry - close) / entry) if is_short else ((close - entry) / entry)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="write the changes (default is a dry run)")
    args = ap.parse_args()

    engine  = create_engine(_sync_db_url(), pool_pre_ping=True)
    Session = sessionmaker(bind=engine)

    with Session() as db:
        rows = db.execute(
            select(SignalExecution, SignalEvent)
            .join(SignalEvent, SignalExecution.signal_id == SignalEvent.id)
            .where(SignalExecution.realized_pnl_usd.isnot(None))
            .order_by(SignalExecution.id)
        ).all()

        if not rows:
            print("Nothing to correct — no execution carries a realized P&L.")
            return

        print(f"{len(rows)} execution(s) with stored P&L"
              f"{'' if args.apply else '  (DRY RUN — nothing written)'}\n")
        header = (f"{'exec':>5} {'pair':<11} {'lev':>4} {'grp':>3} "
                  f"{'old gross':>10} {'new gross':>10} {'old fees':>9} {'new fees':>9}  note")
        print(header)
        print("-" * len(header))

        fixed = skipped = 0
        old_net = new_net = Decimal("0")

        for execution, signal in rows:
            lev      = Decimal(str(execution.exec_leverage or signal.leverage or 1))
            is_short = signal.direction != "long"
            old_pnl  = execution.realized_pnl_usd
            old_fee  = execution.fees_usd or Decimal("0")

            if execution.exec_size_usdt is not None:
                # ── Group A: recompute exactly from the recorded notional ──
                group    = "A"
                notional = execution.exec_size_usdt
                if not (execution.fill_price and execution.close_price):
                    print(f"{execution.id:>5} {signal.pair:<11} {lev:>4} {group:>3} "
                          f"{'—':>10} {'—':>10} {'—':>9} {'—':>9}  skipped: no fill/close price")
                    skipped += 1
                    continue
                pct     = _price_return(execution.fill_price, execution.close_price, is_short)
                new_pnl = notional * pct
                new_fee = notional * HL_ROUND_TRIP_FEE_PCT
                note    = "recomputed from notional"
            else:
                # ── Group B: divide out the leverage the backfill applied ──
                group = "B"
                if lev == 1:
                    print(f"{execution.id:>5} {signal.pair:<11} {lev:>4} {group:>3} "
                          f"{old_pnl:>10.4f} {'—':>10} {old_fee:>9.4f} {'—':>9}  "
                          f"skipped: leverage 1, nothing to divide")
                    skipped += 1
                    continue
                # Confirm the row really was produced by $10 × pct × leverage.
                if not (execution.fill_price and execution.close_price):
                    print(f"{execution.id:>5} {signal.pair:<11} {lev:>4} {group:>3} "
                          f"{old_pnl:>10.4f} {'—':>10} {old_fee:>9.4f} {'—':>9}  "
                          f"skipped: no fill/close price to verify against")
                    skipped += 1
                    continue
                pct      = _price_return(execution.fill_price, execution.close_price, is_short)
                expected = LEGACY_ASSUMED_NOTIONAL * pct * lev
                if abs(expected - old_pnl) > LEGACY_MATCH_TOLERANCE:
                    print(f"{execution.id:>5} {signal.pair:<11} {lev:>4} {group:>3} "
                          f"{old_pnl:>10.4f} {'—':>10} {old_fee:>9.4f} {'—':>9}  "
                          f"SKIPPED: does not match $10×pct×lev (expected {expected:.4f}) "
                          f"— provenance unknown, left alone")
                    skipped += 1
                    continue
                new_pnl = old_pnl / lev
                new_fee = old_fee / lev
                note    = f"÷{lev} (est. $10 notional)"

            print(f"{execution.id:>5} {signal.pair:<11} {lev:>4} {group:>3} "
                  f"{old_pnl:>10.4f} {new_pnl:>10.4f} {old_fee:>9.4f} {new_fee:>9.4f}  {note}")

            if args.apply:
                execution.realized_pnl_usd = new_pnl
                execution.fees_usd         = new_fee

            fixed   += 1
            old_net += old_pnl - old_fee
            new_net += new_pnl - new_fee

        if args.apply:
            db.commit()

        print("-" * len(header))
        print(f"{fixed} corrected, {skipped} skipped")
        print(f"Net P&L  before {old_net:+.4f} USD   →   after {new_net:+.4f} USD "
              f"(overstated by {old_net - new_net:+.4f})")
        if not args.apply:
            print("\nDry run only. Re-run with --apply to write.")


if __name__ == "__main__":
    main()
