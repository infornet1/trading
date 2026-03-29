"""
VIZNAGO WHALE — Hyperliquid Whale Position Tracker Bot

Monitors top HL leaderboard traders + custom addresses for large position
changes. Emits structured events for dashboard display and optional
copy-trade signal forwarding.

Two detection modes:
  POLL mode (default): snapshots every POLL_INTERVAL seconds — simple, reliable
  WS mode (USE_WEBSOCKET=1): subscribes to userFills per address — ~100-500ms latency

Additional signals:
  OI spikes: detects open interest jumps via metaAndAssetCtxs (leading whale indicator)

Required env vars:
    None — HL Info API is fully public / read-only

Optional env vars (defaults shown):
    CONFIG_ID             — SaaS bot_config row ID          (optional)
    LEADERBOARD_TOP_N     — Number of leaderboard addresses  (default: 50)
    MIN_NOTIONAL_USD      — Minimum position size to alert   (default: 50000)
    POLL_INTERVAL         — Seconds between polls            (default: 30)
    CUSTOM_ADDRESSES      — Comma-separated extra addresses  (optional)
    WATCH_ASSETS          — Comma-separated asset filter     (optional, e.g. BTC,ETH)
    USE_WEBSOCKET         — '1' = real-time WS fills mode    (default: 0)
    OI_SPIKE_THRESHOLD    — OI delta % to trigger oi_spike   (default: 0.03)
    PAPER_TRADE           — Set to '1' to run in dry mode    (default: 0)
"""

import json
import os
import sys
import time
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.whale.whale_tracker import WhaleTracker

# ── Config ─────────────────────────────────────────────────────────────────────
CONFIG_ID          = os.getenv("CONFIG_ID")
PAPER_TRADE        = os.getenv("PAPER_TRADE", "0") == "1"
POLL_INTERVAL      = int(os.getenv("POLL_INTERVAL", "30"))
TOP_N              = int(os.getenv("LEADERBOARD_TOP_N", "50"))
MIN_NOTIONAL       = float(os.getenv("MIN_NOTIONAL_USD", "50000"))
USE_WEBSOCKET      = os.getenv("USE_WEBSOCKET", "0") == "1"
OI_SPIKE_THRESHOLD = float(os.getenv("OI_SPIKE_THRESHOLD", "0.03"))

_custom_raw        = os.getenv("CUSTOM_ADDRESSES", "")
CUSTOM_ADDRESSES   = [a.strip() for a in _custom_raw.split(",") if a.strip()]

_assets_raw        = os.getenv("WATCH_ASSETS", "")
WATCH_ASSETS       = set(a.strip().upper() for a in _assets_raw.split(",") if a.strip()) or None


# ── Helpers ────────────────────────────────────────────────────────────────────

def emit(event: str, price=None, pnl=None, details=None):
    """Emit structured event line — BotManager parses [EVENT] prefix."""
    record = {"event": event, "config_id": CONFIG_ID, "ts": datetime.now(timezone.utc).isoformat()}
    if price   is not None: record["price"]   = price
    if pnl     is not None: record["pnl"]     = pnl
    if details is not None: record["details"] = details
    print(f"[EVENT] {json.dumps(record)}", flush=True)


def log(msg: str):
    print(f"[WHALE] {msg}", flush=True)


def signal_passes_filter(signal_dict: dict) -> bool:
    """Return True if this signal should be emitted (asset filter)."""
    if not WATCH_ASSETS:
        return True
    return signal_dict.get("asset", "") in WATCH_ASSETS


# ── Main loop ──────────────────────────────────────────────────────────────────

def handle_signal(signal):
    """Shared handler for both poll and WS signals."""
    sd = signal.to_dict()
    if not signal_passes_filter(sd):
        return

    event_label = _signal_event_label(signal.event_type)
    emoji       = _signal_emoji(signal.event_type, signal.side)

    if signal.event_type == "oi_spike":
        log(f"{emoji} OI SPIKE {signal.asset} | {signal.fill_dir} | notional ${signal.size_usd:,.0f}")
    elif signal.event_type == "ws_fill":
        log(
            f"{emoji} WS FILL | {signal.asset} {signal.side} ${signal.size_usd:,.0f} "
            f"@ {signal.price:.2f} | dir: {signal.fill_dir}"
        )
    else:
        rank_str  = f"Rank #{signal.rank}" if signal.rank else "Custom"
        delta_str = f" (Δ ${signal.delta_usd:+,.0f})" if signal.delta_usd else ""
        log(
            f"{emoji} [{rank_str}] {signal.address[:10]}… | "
            f"{signal.asset} {signal.side} ${signal.size_usd:,.0f}{delta_str} "
            f"@ {signal.price:.2f} | {signal.leverage:.0f}x | uPnL ${signal.pnl:+,.0f}"
        )

    emit(event_label, price=signal.price, pnl=signal.pnl, details=sd)


def main():
    paper_tag = " [PAPER / READ-ONLY]" if PAPER_TRADE else ""
    mode_tag  = " [WS MODE]" if USE_WEBSOCKET else " [POLL MODE]"
    log(f"Starting WHALE Tracker{paper_tag}{mode_tag} | Top-N: {TOP_N} | Min notional: ${MIN_NOTIONAL:,.0f}")
    log(f"Custom addresses: {CUSTOM_ADDRESSES or 'none'}")
    log(f"Asset filter: {list(WATCH_ASSETS) if WATCH_ASSETS else 'all assets'}")
    if not USE_WEBSOCKET:
        log(f"Poll interval: {POLL_INTERVAL}s")

    tracker = WhaleTracker(
        min_notional_usd=MIN_NOTIONAL,
        top_n=TOP_N,
        custom_addresses=CUSTOM_ADDRESSES,
        use_websocket=USE_WEBSOCKET,
        signal_callback=handle_signal if USE_WEBSOCKET else None,
        oi_spike_threshold=OI_SPIKE_THRESHOLD,
        watch_assets=WATCH_ASSETS,
    )

    emit("started", details={
        "top_n":               TOP_N,
        "min_notional_usd":    MIN_NOTIONAL,
        "poll_interval":       POLL_INTERVAL,
        "use_websocket":       USE_WEBSOCKET,
        "oi_spike_threshold":  OI_SPIKE_THRESHOLD,
        "custom_addresses":    CUSTOM_ADDRESSES,
        "watch_assets":        list(WATCH_ASSETS) if WATCH_ASSETS else [],
        "paper_trade":         PAPER_TRADE,
    })

    if USE_WEBSOCKET:
        # WS mode: refresh leaderboard once, subscribe, then keep alive with periodic OI checks
        log("Refreshing leaderboard and starting WS subscriptions...")
        tracker.refresh_leaderboard()
        tracker.start_ws_subscriptions()
        log(f"Subscribed to {len(tracker.watched_addresses)} addresses via WebSocket")

        poll_count = 0
        while True:
            try:
                poll_count += 1
                # OI check still runs on poll cadence as a leading indicator
                oi_signals = tracker.check_oi_spikes()
                for sig in oi_signals:
                    handle_signal(sig)

                # Refresh leaderboard + re-subscribe every 100 cycles (~50 min at 30s)
                if poll_count % 100 == 0:
                    log("Refreshing leaderboard...")
                    tracker.refresh_leaderboard()
                    tracker.start_ws_subscriptions()

                if poll_count % 20 == 0:
                    top = tracker.top_positions(top_n=5)
                    emit("whale_snapshot", details={"top_positions": top, "poll_count": poll_count})

            except Exception as e:
                log(f"Loop error: {e}")
                emit("error", details={"msg": str(e)})
            time.sleep(POLL_INTERVAL)

    else:
        # Poll mode: full snapshot diff every POLL_INTERVAL seconds
        poll_count = 0
        while True:
            try:
                poll_count += 1
                log(f"Poll #{poll_count} — watching {len(tracker.watched_addresses)} addresses")

                signals = tracker.poll()

                if not signals:
                    log("No significant position changes detected")
                else:
                    for signal in signals:
                        handle_signal(signal)

                if poll_count % 10 == 0:
                    top = tracker.top_positions(top_n=5)
                    log(f"Top 5 positions: {json.dumps(top, default=str)}")
                    emit("whale_snapshot", details={"top_positions": top, "poll_count": poll_count})

            except Exception as e:
                log(f"Loop error: {e}")
                emit("error", details={"msg": str(e)})
            time.sleep(POLL_INTERVAL)


def _signal_event_label(event_type: str) -> str:
    return {
        "new_position":  "whale_new_position",
        "closed":        "whale_closed",
        "size_increase": "whale_size_increase",
        "size_decrease": "whale_size_decrease",
        "flip":          "whale_flip",
    }.get(event_type, "whale_event")


def _signal_emoji(event_type: str, side: str) -> str:
    if event_type == "new_position":
        return "🐋 NEW" if side == "LONG" else "🐋 NEW SHORT"
    if event_type == "closed":
        return "📤 CLOSED"
    if event_type == "flip":
        return "🔄 FLIP"
    if event_type == "size_increase":
        return "📈 ADDING"
    if event_type == "size_decrease":
        return "📉 REDUCING"
    return "🔔"


if __name__ == "__main__":
    main()
