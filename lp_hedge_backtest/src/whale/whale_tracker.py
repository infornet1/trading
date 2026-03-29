"""
Hyperliquid Whale Tracker — Core Detection Engine

Polls the Hyperliquid leaderboard and tracked addresses to detect large
position opens/closes/flips. Emits structured signals for copy-trade use.

Detection approach:
  1. Pull HL leaderboard (raw POST — not in SDK) → top N traders by PnL
  2. For each address, fetch clearinghouseState → open positions
  3. Diff against prior snapshot → detect:
       - NEW position opened (new asset entry)
       - POSITION CLOSED (asset disappeared)
       - SIZE INCREASED  (adding to a position)
       - SIZE DECREASED  (partial close or reduce)
       - SIDE FLIP       (long → short or vice versa)
  4. Filter events by notional threshold (MIN_NOTIONAL_USD)
  5. Emit structured signal dicts ready for copy-trade execution

Real-time mode (use_websocket=True):
  - Subscribes to userFills WS feed for each tracked address
  - Latency: ~100–500ms from whale fill to signal (vs. POLL_INTERVAL for polling)
  - Requires skip_ws=False on the Info instance

OI monitoring:
  - Polls metaAndAssetCtxs for open interest spikes as a leading signal
  - OI delta > OI_SPIKE_THRESHOLD triggers a whale_oi_spike event

All HL Info API calls are read-only — no private keys required.
"""

import time
import requests
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Optional

from hyperliquid.info import Info
from hyperliquid.utils import constants

HL_API_URL = constants.MAINNET_API_URL


# ── Config ─────────────────────────────────────────────────────────────────────

DEFAULT_LEADERBOARD_TOP_N  = 50
DEFAULT_MIN_NOTIONAL_USD   = 50_000
DEFAULT_POLL_INTERVAL      = 30       # seconds between snapshot polls
DEFAULT_OI_SPIKE_THRESHOLD = 0.03     # 3% OI increase in one interval = whale signal


# ── Data structures ────────────────────────────────────────────────────────────

@dataclass
class WhalePosition:
    address:        str
    asset:          str
    side:           str           # "LONG" | "SHORT"
    size_usd:       float
    entry_price:    float
    leverage:       float
    unrealized_pnl: float
    liquidation_px: float = 0.0
    snapshot_ts:    datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class WhaleSignal:
    """Emitted whenever a significant position change is detected."""
    event_type:  str           # "new_position"|"closed"|"size_increase"|"size_decrease"|"flip"|"oi_spike"|"ws_fill"
    address:     str
    asset:       str
    side:        str           # "LONG" | "SHORT" | "CLOSED"
    size_usd:    float
    price:       float
    leverage:    float
    pnl:         float
    rank:        Optional[int]   # leaderboard rank (None if custom address)
    delta_usd:   Optional[float] # size change vs prior snapshot
    fill_dir:    Optional[str]   # for ws_fill events: "Open Long"|"Close Long" etc.
    ts:          datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        return {
            "event_type": self.event_type,
            "address":    self.address,
            "asset":      self.asset,
            "side":       self.side,
            "size_usd":   round(self.size_usd, 2),
            "price":      round(self.price, 4),
            "leverage":   round(self.leverage, 1),
            "pnl":        round(self.pnl, 2),
            "rank":       self.rank,
            "delta_usd":  round(self.delta_usd, 2) if self.delta_usd is not None else None,
            "fill_dir":   self.fill_dir,
            "ts":         self.ts.isoformat(),
        }


# ── Tracker ────────────────────────────────────────────────────────────────────

class WhaleTracker:
    """
    Stateful whale position tracker.

    Polling mode (default):
        tracker = WhaleTracker(min_notional=100_000, top_n=30)
        tracker.add_address("0xabc...")
        for signal in tracker.poll():
            print(signal.to_dict())

    WebSocket mode (real-time, ~100-500ms latency):
        tracker = WhaleTracker(use_websocket=True, signal_callback=my_handler)
        tracker.add_address("0xabc...")
        tracker.start_ws_subscriptions()   # subscribes to userFills for all addresses
        # signals fire via signal_callback as they arrive
    """

    def __init__(
        self,
        min_notional_usd:   float    = DEFAULT_MIN_NOTIONAL_USD,
        top_n:              int      = DEFAULT_LEADERBOARD_TOP_N,
        custom_addresses:   Optional[list[str]] = None,
        use_websocket:      bool     = False,
        signal_callback:    Optional[Callable[[WhaleSignal], None]] = None,
        oi_spike_threshold: float    = DEFAULT_OI_SPIKE_THRESHOLD,
        watch_assets:       Optional[set[str]] = None,
    ):
        self.min_notional      = min_notional_usd
        self.top_n             = top_n
        self.use_websocket     = use_websocket
        self.signal_callback   = signal_callback
        self.oi_spike_threshold = oi_spike_threshold
        self.watch_assets      = watch_assets  # None = all assets

        # skip_ws=False only when we need the WS manager
        self.info = Info(HL_API_URL, skip_ws=(not use_websocket))

        # address → rank (1-indexed), None if custom
        self._address_ranks: dict[str, Optional[int]] = {}

        # address → {asset → WhalePosition}
        self._snapshot: dict[str, dict[str, WhalePosition]] = {}

        # OI tracking: asset → last_oi float
        self._oi_snapshot: dict[str, float] = {}

        if custom_addresses:
            for addr in custom_addresses:
                self.add_address(addr)

    # ── Address management ─────────────────────────────────────────────────

    def add_address(self, address: str, rank: Optional[int] = None):
        self._address_ranks[address.lower()] = rank

    def remove_address(self, address: str):
        addr = address.lower()
        self._address_ranks.pop(addr, None)
        self._snapshot.pop(addr, None)

    @property
    def watched_addresses(self) -> list[str]:
        return list(self._address_ranks.keys())

    # ── Leaderboard fetch ──────────────────────────────────────────────────

    def refresh_leaderboard(self) -> list[str]:
        """
        Fetch HL leaderboard via raw POST (not wrapped by SDK).
        Returns list of top-N addresses.
        """
        try:
            resp = requests.post(
                f"{HL_API_URL}/info",
                json={"type": "leaderboard"},
                headers={"Content-Type": "application/json"},
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()

            # Response: {"leaderboardRows": [{ethAddress, accountValue, pnl, vlm, ...}]}
            rows = data.get("leaderboardRows", []) if isinstance(data, dict) else data
            top_addresses = []
            for i, row in enumerate(rows[:self.top_n]):
                addr = row.get("ethAddress", "").lower()
                if addr:
                    self._address_ranks[addr] = i + 1
                    top_addresses.append(addr)
            return top_addresses
        except Exception as e:
            print(f"[WhaleTracker] Leaderboard fetch error: {e}", flush=True)
            return []

    # ── OI monitoring ──────────────────────────────────────────────────────

    def check_oi_spikes(self) -> list[WhaleSignal]:
        """
        Poll metaAndAssetCtxs for open interest spikes.
        Returns signals for assets where OI increased > oi_spike_threshold.
        """
        try:
            result = self.info.meta_and_asset_ctxs()
            # result: [meta_dict, [ctx_per_asset, ...]]
            if not result or len(result) < 2:
                return []
            meta  = result[0]
            ctxs  = result[1]
            universe = meta.get("universe", [])

            signals = []
            for i, ctx in enumerate(ctxs):
                if i >= len(universe):
                    break
                asset = universe[i].get("name", "")
                if self.watch_assets and asset not in self.watch_assets:
                    continue

                oi_now = float(ctx.get("openInterest", 0) or 0)
                oi_prev = self._oi_snapshot.get(asset)

                if oi_prev is not None and oi_prev > 0:
                    delta_pct = (oi_now - oi_prev) / oi_prev
                    if delta_pct >= self.oi_spike_threshold:
                        mark_px = float(ctx.get("markPx", 0) or 0)
                        funding  = float(ctx.get("funding", 0) or 0)
                        # Infer direction from funding: positive = longs paying = net long bias
                        oi_side = "LONG" if funding >= 0 else "SHORT"
                        signals.append(WhaleSignal(
                            event_type="oi_spike",
                            address="market",
                            asset=asset,
                            side=oi_side,
                            size_usd=oi_now * mark_px,
                            price=mark_px,
                            leverage=0,
                            pnl=0,
                            rank=None,
                            delta_usd=(oi_now - oi_prev) * mark_px,
                            fill_dir=f"OI +{delta_pct:.1%} | funding {funding:.4%}",
                        ))

                self._oi_snapshot[asset] = oi_now

            return signals
        except Exception as e:
            print(f"[WhaleTracker] OI check error: {e}", flush=True)
            return []

    # ── Position snapshot ──────────────────────────────────────────────────

    def _fetch_positions(self, address: str) -> dict[str, WhalePosition]:
        """Fetch current open perp positions for one address."""
        try:
            state = self.info.user_state(address)
            positions = {}
            mids = self.info.all_mids()

            for ap in state.get("assetPositions", []):
                pos   = ap.get("position", {})
                asset = pos.get("coin", "")
                szi   = float(pos.get("szi", 0))
                if szi == 0:
                    continue
                if self.watch_assets and asset not in self.watch_assets:
                    continue

                side        = "LONG" if szi > 0 else "SHORT"
                entry_px    = float(pos.get("entryPx", 0) or 0)
                lev_raw     = pos.get("leverage", {})
                leverage    = float(lev_raw.get("value", 1) if isinstance(lev_raw, dict) else lev_raw or 1)
                upnl        = float(pos.get("unrealizedPnl", 0) or 0)
                liq_px      = float(pos.get("liquidationPx", 0) or 0)
                mark_price  = float(mids.get(asset, entry_px or 1))
                size_usd    = abs(szi) * mark_price

                positions[asset] = WhalePosition(
                    address=address,
                    asset=asset,
                    side=side,
                    size_usd=size_usd,
                    entry_price=entry_px,
                    leverage=leverage,
                    unrealized_pnl=upnl,
                    liquidation_px=liq_px,
                )
            return positions

        except Exception as e:
            print(f"[WhaleTracker] Position fetch error for {address[:10]}…: {e}", flush=True)
            return {}

    # ── WebSocket real-time fills ──────────────────────────────────────────

    def _make_ws_fill_handler(self, address: str) -> Callable:
        """Return a WS callback that fires on this address's fills."""
        rank = self._address_ranks.get(address)

        def on_fill(msg):
            try:
                fills = msg.get("data", {})
                if isinstance(fills, dict):
                    fills = fills.get("fills", [])
                for fill in fills:
                    direction = fill.get("dir", "")
                    # Only act on opening fills; ignore closes
                    if "Open" not in direction:
                        continue

                    coin     = fill.get("coin", "")
                    if self.watch_assets and coin not in self.watch_assets:
                        continue

                    sz       = float(fill.get("sz", 0))
                    px       = float(fill.get("px", 0))
                    notional = sz * px

                    if notional < self.min_notional:
                        continue

                    side = "LONG" if "Long" in direction else "SHORT"
                    signal = WhaleSignal(
                        event_type="ws_fill",
                        address=address,
                        asset=coin,
                        side=side,
                        size_usd=notional,
                        price=px,
                        leverage=0,   # not in fill payload; fetch separately if needed
                        pnl=0,
                        rank=rank,
                        delta_usd=notional,
                        fill_dir=direction,
                    )
                    if self.signal_callback:
                        self.signal_callback(signal)
            except Exception as e:
                print(f"[WhaleTracker] WS fill handler error: {e}", flush=True)

        return on_fill

    def start_ws_subscriptions(self):
        """
        Subscribe to userFills WebSocket feed for all tracked addresses.
        Signals fire via signal_callback as fills arrive (~100–500ms latency).
        Must be called after addresses are added via add_address() or refresh_leaderboard().
        """
        if not self.use_websocket:
            raise RuntimeError("use_websocket=True required to call start_ws_subscriptions()")
        for addr in self._address_ranks:
            handler = self._make_ws_fill_handler(addr)
            self.info.subscribe(
                {"type": "userFills", "user": addr},
                handler,
            )
            print(f"[WhaleTracker] Subscribed to userFills for {addr[:10]}…", flush=True)
            time.sleep(0.1)  # stagger subscriptions

    # ── Diff engine ────────────────────────────────────────────────────────

    def _diff(
        self,
        address: str,
        old:     dict[str, WhalePosition],
        new:     dict[str, WhalePosition],
        rank:    Optional[int],
    ) -> list[WhaleSignal]:
        signals = []

        for asset in set(old.keys()) | set(new.keys()):
            old_pos = old.get(asset)
            new_pos = new.get(asset)
            price   = new_pos.entry_price if new_pos else (old_pos.entry_price if old_pos else 0)
            pnl     = new_pos.unrealized_pnl if new_pos else 0

            if old_pos is None and new_pos is not None:
                if new_pos.size_usd >= self.min_notional:
                    signals.append(WhaleSignal(
                        event_type="new_position", address=address, asset=asset,
                        side=new_pos.side, size_usd=new_pos.size_usd, price=price,
                        leverage=new_pos.leverage, pnl=pnl, rank=rank,
                        delta_usd=new_pos.size_usd, fill_dir=None,
                    ))

            elif old_pos is not None and new_pos is None:
                if old_pos.size_usd >= self.min_notional:
                    signals.append(WhaleSignal(
                        event_type="closed", address=address, asset=asset,
                        side="CLOSED", size_usd=0, price=price,
                        leverage=old_pos.leverage, pnl=pnl, rank=rank,
                        delta_usd=-old_pos.size_usd, fill_dir=None,
                    ))

            elif old_pos is not None and new_pos is not None:
                if old_pos.side != new_pos.side:
                    if new_pos.size_usd >= self.min_notional:
                        signals.append(WhaleSignal(
                            event_type="flip", address=address, asset=asset,
                            side=new_pos.side, size_usd=new_pos.size_usd, price=price,
                            leverage=new_pos.leverage, pnl=pnl, rank=rank,
                            delta_usd=new_pos.size_usd + old_pos.size_usd, fill_dir=None,
                        ))
                    continue

                delta     = new_pos.size_usd - old_pos.size_usd
                pct_change = abs(delta) / old_pos.size_usd if old_pos.size_usd > 0 else 0
                if pct_change >= 0.10 and abs(delta) >= self.min_notional * 0.2:
                    event_type = "size_increase" if delta > 0 else "size_decrease"
                    if max(old_pos.size_usd, new_pos.size_usd) >= self.min_notional:
                        signals.append(WhaleSignal(
                            event_type=event_type, address=address, asset=asset,
                            side=new_pos.side, size_usd=new_pos.size_usd, price=price,
                            leverage=new_pos.leverage, pnl=pnl, rank=rank,
                            delta_usd=delta, fill_dir=None,
                        ))

        return signals

    # ── Main poll ──────────────────────────────────────────────────────────

    def poll(self) -> list[WhaleSignal]:
        """
        Single poll cycle:
          1. Refresh leaderboard
          2. Fetch positions for all watched addresses
          3. Diff against prior snapshot
          4. Check OI spikes
          5. Return combined list of signals
        """
        self.refresh_leaderboard()

        all_signals = []
        for addr in list(self._address_ranks.keys()):
            new_positions = self._fetch_positions(addr)
            old_positions = self._snapshot.get(addr, {})

            if addr in self._snapshot:
                rank    = self._address_ranks.get(addr)
                signals = self._diff(addr, old_positions, new_positions, rank)
                all_signals.extend(signals)

            self._snapshot[addr] = new_positions
            time.sleep(0.15)  # courtesy delay

        oi_signals = self.check_oi_spikes()
        all_signals.extend(oi_signals)

        return all_signals

    # ── Inspection helpers ─────────────────────────────────────────────────

    def top_positions(self, top_n: int = 10, asset: Optional[str] = None) -> list[dict]:
        """Return largest current positions across all tracked addresses."""
        all_positions = []
        for addr, positions in self._snapshot.items():
            for pos_asset, pos in positions.items():
                if asset and pos_asset != asset:
                    continue
                if pos.size_usd < self.min_notional:
                    continue
                all_positions.append({
                    "address":     addr,
                    "rank":        self._address_ranks.get(addr),
                    "asset":       pos_asset,
                    "side":        pos.side,
                    "size_usd":    round(pos.size_usd, 2),
                    "entry_px":    round(pos.entry_price, 4),
                    "leverage":    round(pos.leverage, 1),
                    "upnl":        round(pos.unrealized_pnl, 2),
                    "liq_px":      round(pos.liquidation_px, 4),
                    "snapshot_ts": pos.snapshot_ts.isoformat(),
                })
        all_positions.sort(key=lambda x: x["size_usd"], reverse=True)
        return all_positions[:top_n]

    def address_snapshot(self, address: str) -> list[dict]:
        addr = address.lower()
        return [
            {
                "asset":    a,
                "side":     p.side,
                "size_usd": round(p.size_usd, 2),
                "entry_px": round(p.entry_price, 4),
                "leverage": round(p.leverage, 1),
                "upnl":     round(p.unrealized_pnl, 2),
                "liq_px":   round(p.liquidation_px, 4),
            }
            for a, p in self._snapshot.get(addr, {}).items()
        ]
