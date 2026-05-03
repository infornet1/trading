"""
LP Signal Lab — Dry Run Test
=============================
Tests the full copy-trading pipeline without placing real HL orders.

Checks:
  1. Signal parser (Format A + B + update detection)
  2. Database connection + registered wallet lookup
  3. HL balance fetch (perp + spot unified account)
  4. Size calculation
  5. Full auto-execute pipeline in dry_run mode (DB write → executor → email)
  6. Cleanup

Usage:
    cd /var/www/dev/trading/lp_hedge_backtest
    source venv/bin/activate
    python -m telegram_listener.test_signal_lab
"""

import asyncio
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "../api/.env"))

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from telegram_listener.signal_parser import parse_signal, parse_update
from api.models import SignalEvent, SignalExecution, SignalWallet
from api.signal_executor import place_hl_order
from api.signal_email import send_signal_email

DB_URL = os.getenv("DB_URL", "mysql+aiomysql://viznago:90GSxYu0GdSe6fzGowBA4hNOlsBK@localhost/viznago_dev")

_PASS = "✅"
_FAIL = "❌"
_WARN = "⚠️ "

_passed = 0
_failed = 0

def _ok(msg):
    global _passed
    _passed += 1
    print(f"  {_PASS} {msg}")

def _err(msg):
    global _failed
    _failed += 1
    print(f"  {_FAIL} {msg}")

def _warn(msg):
    print(f"  {_WARN} {msg}")

def _header(n, title):
    print(f"\n[{n}] {title}")
    print(f"  {'─' * 50}")


# ── Test signals ──────────────────────────────────────────────────────────────

FORMAT_A = """ETH/USDT = Short ( 📊)
       (20x leverage)

◼️Entry: $2350.00 (activated)
◼️Stoploss is at $2399.00 (-2.1%)
◼️Target: $2283.19 & $2248.86

💻Strong BOS on 15m — clean short setup."""

FORMAT_B = """📊 BCH/USDT

Size: 2%
Leverage: 20x
Entry: $459.08 (market price entry)
Target: $442.16 (+3.7%)
Stoploss: $466.94 (-1.7%)

🌩 MSB confirmed."""

UPDATE_SAMPLES = [
    ("🚫Got Stopped",                              "stopped"),
    ("✅ Target reached! Great trade everyone",    "target_hit"),
    ("Took 50% profits at TP1",                   "partial"),
    ("Cancel this signal, setup invalidated",      "cancelled"),
    ("Markets are looking interesting today",      None),
]


async def run_tests():
    engine        = create_async_engine(DB_URL, pool_pre_ping=True, echo=False)
    AsyncSession_ = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    inserted_signal_id    = None
    inserted_execution_id = None

    # ── 1. Signal Parser ──────────────────────────────────────────────────────
    _header("1/6", "Signal Parser")

    sig_a = parse_signal(FORMAT_A)
    if sig_a and sig_a.pair == "ETH/USDT" and sig_a.direction == "short" and sig_a.leverage == 20:
        _ok(f"Format A → {sig_a.pair} {sig_a.direction.upper()} {sig_a.leverage}x | entry ${sig_a.entry:,.2f} | SL ${sig_a.stoploss:,.2f}")
    else:
        _err(f"Format A parse failed: {sig_a}")

    sig_b = parse_signal(FORMAT_B)
    if sig_b and sig_b.pair == "BCH/USDT" and sig_b.direction == "short" and sig_b.leverage == 20:
        _ok(f"Format B → {sig_b.pair} {sig_b.direction.upper()} {sig_b.leverage}x | entry ${sig_b.entry:,.2f} | SL ${sig_b.stoploss:,.2f}")
    else:
        _err(f"Format B parse failed: {sig_b}")

    all_updates_ok = True
    for text, expected in UPDATE_SAMPLES:
        got = parse_update(text)
        if got != expected:
            _err(f"Update '{text[:35]}' → expected {expected}, got {got}")
            all_updates_ok = False
    if all_updates_ok:
        _ok(f"Update detection: all {len(UPDATE_SAMPLES)} samples correct")

    # ── 2. Database + Wallet ──────────────────────────────────────────────────
    _header("2/6", "Database + Registered Wallet")

    async with AsyncSession_() as db:
        try:
            result = await db.execute(
                select(SignalWallet).where(
                    SignalWallet.active       == True,
                    SignalWallet.auto_execute == True,
                )
            )
            wallet = result.scalar_one_or_none()
            if wallet:
                _ok(f"DB connected to viznago_dev")
                _ok(f"Signal wallet: '{wallet.label}' | {wallet.hl_wallet_addr[:10]}…{wallet.hl_wallet_addr[-4:]} | auto_execute=True")
            else:
                _err("No active auto_execute wallet found in signal_wallets — register one first")
                wallet = None
        except Exception as e:
            _err(f"DB connection failed: {e}")
            wallet = None

    if not wallet:
        print(f"\n{'='*60}")
        print(f"  Aborted — no signal wallet registered.")
        print(f"{'='*60}")
        return

    # ── 3. HL Balance ─────────────────────────────────────────────────────────
    _header("3/6", "HL Balance (unified account)")

    from hyperliquid.info import Info
    from hyperliquid.utils import constants as hl_constants

    try:
        info  = Info(hl_constants.MAINNET_API_URL, skip_ws=True)
        state = info.user_state(wallet.hl_wallet_addr)
        perp  = float(state["marginSummary"]["accountValue"])
        spot  = 0.0
        spot_usable = False
        spot_state  = info.spot_user_state(wallet.hl_wallet_addr)
        for b in spot_state.get("balances", []):
            if b["coin"] == "USDC":
                spot = float(b["total"])
                break
        for entry in spot_state.get("tokenToAvailableAfterMaintenance", []):
            if entry[0] == 0 and float(entry[1]) > 0:
                spot_usable = True
                break
        total = perp + spot
        _ok(f"Perp: ${perp:.2f} | Spot: ${spot:.2f} | spot_usable={spot_usable}")
        if total >= 10:
            _ok(f"Effective tradeable balance: ${total:.2f} USDC ✓")
        else:
            _warn(f"Effective balance ${total:.2f} < $10 minimum — orders would fail")
    except Exception as e:
        _err(f"HL balance fetch failed: {e}")
        total = 0.0

    # ── 4. Size Calculation ───────────────────────────────────────────────────
    _header("4/6", "Size Calculation (no orders)")

    if sig_a and total > 0:
        size_pct = float(sig_a.size_pct) if sig_a.size_pct else 2.0
        lev      = sig_a.leverage or 10
        entry_px = sig_a.entry
        margin   = total * size_pct / 100
        size     = (margin * lev) / entry_px
        notional = size * entry_px
        _ok(f"Signal: {sig_a.pair} {sig_a.direction.upper()} {lev}x @ ${entry_px:,.2f}")
        _ok(f"Margin ({size_pct}% of ${total:.2f}): ${margin:.4f} USDC")
        _ok(f"Size: {size:.6f} {sig_a.pair.split('/')[0]} | Notional: ${notional:.2f}")
        if notional >= 10:
            _ok(f"Notional ${notional:.2f} ≥ $10 minimum ✓")
        else:
            _warn(f"Notional ${notional:.2f} < $10 — balance too low for this leverage/size combo")

    # ── 5. Full Pipeline Dry Run ──────────────────────────────────────────────
    _header("5/6", "Full Pipeline Dry Run (DB write → executor → record)")

    async with AsyncSession_() as db:
        # Insert test signal
        test_signal = SignalEvent(
            source_id   = 1,
            pair        = sig_a.pair,
            direction   = sig_a.direction,
            leverage    = sig_a.leverage,
            entry       = sig_a.entry,
            stoploss    = sig_a.stoploss,
            targets     = sig_a.targets,
            size_pct    = sig_a.size_pct,
            raw_text    = "[DRY RUN TEST] " + FORMAT_A[:50],
            status      = "pending",
            msg_id      = 999999999,
            received_at = datetime.now(timezone.utc),
        )
        db.add(test_signal)
        await db.commit()
        await db.refresh(test_signal)
        inserted_signal_id = test_signal.id
        _ok(f"Test signal inserted → id={inserted_signal_id} ({sig_a.pair} {sig_a.direction.upper()} {sig_a.leverage}x)")

        # Run executor in dry_run mode
        result = await asyncio.to_thread(
            place_hl_order,
            wallet.hl_wallet_addr,
            wallet.hl_secret_key,
            test_signal,
            True,   # dry_run=True
        )

        if result["success"] and result.get("dry_run"):
            _ok(f"[DRY RUN] Would open: {result['symbol']} {sig_a.direction.upper()} {result['leverage']}x")
            _ok(f"[DRY RUN] Fill @ ${result['fill_price']:,.4f} | Size {result['size']} {result['symbol']}")
            _ok(f"[DRY RUN] Margin: ${result['margin_used']:.2f} | Notional: ${result['notional']:.2f}")
            _ok(f"[DRY RUN] Would place SL trigger @ ${result['sl_price']:,.4f}")
            if result.get("tp_price"):
                _ok(f"[DRY RUN] Would place TP trigger @ ${result['tp_price']:,.4f}")
        else:
            _err(f"Executor returned failure: {result.get('error')}")

        # Insert execution record
        execution = SignalExecution(
            signal_id      = test_signal.id,
            user_address   = wallet.hl_wallet_addr,
            hl_wallet_addr = wallet.hl_wallet_addr,
            hl_order_id    = result.get("hl_order_id"),
            fill_price     = result.get("fill_price"),
            outcome        = "filled" if result["success"] else "failed",
        )
        db.add(execution)
        test_signal.status = "executed"
        await db.commit()
        await db.refresh(execution)
        inserted_execution_id = execution.id
        _ok(f"Execution record saved → id={inserted_execution_id} | outcome={execution.outcome}")

    # ── 6. Email ──────────────────────────────────────────────────────────────
    _header("6/6", "Email Notification")

    try:
        send_signal_email(
            "🧪 Dry Run Test — pipeline OK",
            f"LP Signal Lab dry run test completed successfully.\n\n"
            f"Signal:    {sig_a.pair} {sig_a.direction.upper()} {sig_a.leverage}x\n"
            f"Entry:     ${sig_a.entry:,.4f}\n"
            f"SL:        ${sig_a.stoploss:,.4f}\n"
            f"Balance:   ${result.get('balance', 0):.2f} USDC\n"
            f"Margin:    ${result.get('margin_used', 0):.4f} USDC\n"
            f"Size:      {result.get('size', 0)} {result.get('symbol', '')}\n"
            f"Notional:  ${result.get('notional', 0):.2f}\n\n"
            f"[DRY RUN — no real orders were placed]",
        )
        _ok("Test email sent to admin")
    except Exception as e:
        _err(f"Email failed: {e}")

    # ── Cleanup ───────────────────────────────────────────────────────────────
    print(f"\n  {'─' * 50}")
    print(f"  [Cleanup]")
    async with AsyncSession_() as db:
        if inserted_execution_id:
            await db.execute(delete(SignalExecution).where(SignalExecution.id == inserted_execution_id))
            print(f"  🗑  Execution record deleted (id={inserted_execution_id})")
        if inserted_signal_id:
            await db.execute(delete(SignalEvent).where(SignalEvent.id == inserted_signal_id))
            print(f"  🗑  Test signal deleted (id={inserted_signal_id})")
        await db.commit()

    await engine.dispose()

    # ── Summary ───────────────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    total_checks = _passed + _failed
    if _failed == 0:
        print(f"  All {total_checks} checks passed ✅  — pipeline ready to fire")
    else:
        print(f"  {_passed}/{total_checks} passed | {_failed} failed ❌")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    print(f"\n{'='*60}")
    print(f"  LP Signal Lab — Dry Run Test")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print(f"{'='*60}")
    asyncio.run(run_tests())
