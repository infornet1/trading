"""
Hyperliquid Whale Tracker — Core Detection Engine

Key fix vs v1: ALL HL API calls use urllib.request directly (no SDK dex= param).
The hyperliquid-python-sdk appends "dex": "" to clearinghouseState requests which
causes HTTP 422 on the current HL API version. Direct HTTP calls avoid this.

Full position payload captured per address:
  asset, side, size_contracts, size_usd, entry_price, mark_price,
  leverage_value, leverage_type (cross/isolated), liquidation_px,
  margin_used, max_leverage, unrealized_pnl, roe, cum_funding_since_open

These are all the fields a copy-trader needs to size and place a mirrored position.
"""

import json
import time
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Optional

from hyperliquid.info import Info          # used only for WS subscriptions
from hyperliquid.utils import constants

HL_INFO_URL = "https://api.hyperliquid.xyz/info"

# ── Config defaults ────────────────────────────────────────────────────────────
DEFAULT_LEADERBOARD_TOP_N  = 50
DEFAULT_MIN_NOTIONAL_USD   = 50_000
DEFAULT_POLL_INTERVAL      = 30
DEFAULT_OI_SPIKE_THRESHOLD = 0.03


# ── HTTP helper (bypasses SDK dex= bug) ───────────────────────────────────────

def _hl_post(payload: dict, timeout: int = 12) -> dict | list:
    """Direct POST to HL Info API — no SDK, no dex= param."""
    data = json.dumps(payload).encode()
    req  = urllib.request.Request(
        HL_INFO_URL,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


# ── Data structures ────────────────────────────────────────────────────────────

@dataclass
class WhalePosition:
    """Full position state for one asset held by one address."""
    address:             str
    asset:               str
    side:                str     # "LONG" | "SHORT"

    # Size
    size_contracts:      float   # raw contracts (szi)
    size_usd:            float   # mark_price × |szi|

    # Prices
    entry_price:         float
    mark_price:          float
    liquidation_px:      float

    # Leverage
    leverage_value:      float   # e.g. 20
    leverage_type:       str     # "cross" | "isolated"
    max_leverage:        int     # max allowed for this asset

    # Risk / P&L
    margin_used:         float   # USD collateral reserved
    unrealized_pnl:      float
    roe:                 float   # return on equity (0.05 = 5%)
    cum_funding_since_open: float  # total funding paid/received since entry

    snapshot_ts: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def copy_trade_summary(self) -> dict:
        """Compact dict with everything needed to place a copy trade."""
        return {
            "asset":          self.asset,
            "side":           self.side,
            "entry_px":       round(self.entry_price, 4),
            "mark_px":        round(self.mark_price, 4),
            "size_contracts": round(self.size_contracts, 6),
            "size_usd":       round(self.size_usd, 2),
            "leverage":       self.leverage_value,
            "leverage_type":  self.leverage_type,
            "liq_px":         round(self.liquidation_px, 4),
            "margin_used":    round(self.margin_used, 4),
            "upnl":           round(self.unrealized_pnl, 4),
            "roe_pct":        round(self.roe * 100, 2),
            "funding_since_open": round(self.cum_funding_since_open, 6),
        }


@dataclass
class WhaleSignal:
    """
    Emitted on every significant position change.
    `copy_info` dict contains the full position snapshot needed for copy trading.
    """
    event_type:   str    # new_position|closed|size_increase|size_decrease|flip|oi_spike|ws_fill
    address:      str
    rank:         Optional[int]    # leaderboard rank (None = custom address)
    asset:        str
    side:         str              # LONG | SHORT | CLOSED

    # Core trade params
    size_usd:     float
    size_contracts: float
    price:        float            # entry price (or mark price for closes)
    leverage:     float
    leverage_type: str             # cross | isolated
    liq_px:       float
    margin_used:  float

    # P&L context
    pnl:          float            # unrealised PnL at signal time
    roe_pct:      float            # return on equity %
    funding_since_open: float

    # Signal metadata
    delta_usd:    Optional[float]  # size change vs prior snapshot
    fill_dir:     Optional[str]    # for ws_fill: "Open Long" etc.

    ts: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        return {
            # Identity
            "event_type":    self.event_type,
            "address":       self.address,
            "rank":          self.rank,
            # Trade params (copy-trading critical)
            "asset":         self.asset,
            "side":          self.side,
            "size_usd":      round(self.size_usd, 2),
            "size_contracts": round(self.size_contracts, 6),
            "price":         round(self.price, 4),
            "leverage":      round(self.leverage, 1),
            "leverage_type": self.leverage_type,
            "liq_px":        round(self.liq_px, 4),
            "margin_used":   round(self.margin_used, 4),
            # P&L context
            "pnl":           round(self.pnl, 4),
            "roe_pct":       round(self.roe_pct, 2),
            "funding_since_open": round(self.funding_since_open, 6),
            # Signal metadata
            "delta_usd":     round(self.delta_usd, 2) if self.delta_usd is not None else None,
            "fill_dir":      self.fill_dir,
            "ts":            self.ts.isoformat(),
        }


# ── Tracker ────────────────────────────────────────────────────────────────────

class WhaleTracker:
    def __init__(
        self,
        min_notional_usd:   float = DEFAULT_MIN_NOTIONAL_USD,
        top_n:              int   = DEFAULT_LEADERBOARD_TOP_N,
        custom_addresses:   Optional[list[str]] = None,
        use_websocket:      bool  = False,
        signal_callback:    Optional[Callable[["WhaleSignal"], None]] = None,
        oi_spike_threshold: float = DEFAULT_OI_SPIKE_THRESHOLD,
        watch_assets:       Optional[set[str]] = None,
    ):
        self.min_notional       = min_notional_usd
        self.top_n              = top_n
        self.use_websocket      = use_websocket
        self.signal_callback    = signal_callback
        self.oi_spike_threshold = oi_spike_threshold
        self.watch_assets       = watch_assets

        # WS subscriptions need the SDK Info object (skip_ws=False only when needed)
        self._ws_info: Optional[Info] = None

        self._address_ranks: dict[str, Optional[int]] = {}
        self._snapshot:      dict[str, dict[str, WhalePosition]] = {}
        self._oi_snapshot:   dict[str, float] = {}
        self._mids_cache:    dict[str, float] = {}
        self._mids_ts:       float = 0.0

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

    # ── Mark prices (cached 10s) ───────────────────────────────────────────

    def _get_mids(self) -> dict[str, float]:
        now = time.time()
        if now - self._mids_ts > 10:
            try:
                raw = _hl_post({"type": "allMids"})
                self._mids_cache = {k: float(v) for k, v in raw.items()}
                self._mids_ts = now
            except Exception as e:
                print(f"[WhaleTracker] allMids error: {e}", flush=True)
        return self._mids_cache

    # ── Leaderboard ────────────────────────────────────────────────────────

    def refresh_leaderboard(self) -> list[str]:
        """Fetch HL leaderboard. Returns list of top-N addresses."""
        # Try week window first, fall back to allTime
        for window in ("week", "allTime", "day"):
            try:
                data = _hl_post({"type": "leaderboard", "req": {"timeWindow": window}})
                rows = data.get("leaderboardRows", []) if isinstance(data, dict) else data
                if rows:
                    top = []
                    for i, row in enumerate(rows[:self.top_n]):
                        addr = (row.get("ethAddress") or row.get("user") or "").lower()
                        if addr:
                            self._address_ranks[addr] = i + 1
                            top.append(addr)
                    if top:
                        return top
            except Exception as e:
                print(f"[WhaleTracker] Leaderboard ({window}) error: {e}", flush=True)
        return []

    # ── OI spike detection ─────────────────────────────────────────────────

    def check_oi_spikes(self) -> list[WhaleSignal]:
        try:
            result = _hl_post({"type": "metaAndAssetCtxs"})
            if not result or len(result) < 2:
                return []
            meta     = result[0]
            ctxs     = result[1]
            universe = meta.get("universe", [])
            mids     = self._get_mids()
            signals  = []

            for i, ctx in enumerate(ctxs):
                if i >= len(universe):
                    break
                asset = universe[i].get("name", "")
                if self.watch_assets and asset not in self.watch_assets:
                    continue

                oi_now  = float(ctx.get("openInterest", 0) or 0)
                oi_prev = self._oi_snapshot.get(asset)

                if oi_prev and oi_prev > 0:
                    delta_pct = (oi_now - oi_prev) / oi_prev
                    if delta_pct >= self.oi_spike_threshold:
                        mark_px = float(mids.get(asset, ctx.get("markPx", 0) or 0))
                        funding = float(ctx.get("funding", 0) or 0)
                        oi_side = "LONG" if funding >= 0 else "SHORT"
                        signals.append(WhaleSignal(
                            event_type="oi_spike", address="market", rank=None,
                            asset=asset, side=oi_side,
                            size_usd=oi_now * mark_px, size_contracts=oi_now,
                            price=mark_px, leverage=0, leverage_type="",
                            liq_px=0, margin_used=0, pnl=0, roe_pct=0,
                            funding_since_open=funding,
                            delta_usd=(oi_now - oi_prev) * mark_px,
                            fill_dir=f"OI +{delta_pct:.1%} | funding {funding:.4%}",
                        ))
                self._oi_snapshot[asset] = oi_now
            return signals
        except Exception as e:
            print(f"[WhaleTracker] OI check error: {e}", flush=True)
            return {}

    # ── Position fetch (full payload) ──────────────────────────────────────

    def _fetch_positions(self, address: str) -> dict[str, WhalePosition]:
        """
        Fetch full clearinghouseState for one address.
        Uses urllib.request directly — avoids SDK dex="" param which causes HTTP 422.
        """
        try:
            state   = _hl_post({"type": "clearinghouseState", "user": address})
            mids    = self._get_mids()
            result  = {}

            for ap in state.get("assetPositions", []):
                pos   = ap.get("position", {})
                asset = pos.get("coin", "")
                szi   = float(pos.get("szi", 0))
                if szi == 0:
                    continue
                if self.watch_assets and asset not in self.watch_assets:
                    continue

                side = "LONG" if szi > 0 else "SHORT"

                # Leverage — {"type": "cross"|"isolated", "value": N}
                lev_raw      = pos.get("leverage", {})
                lev_value    = float(lev_raw.get("value", 1) if isinstance(lev_raw, dict) else lev_raw or 1)
                lev_type     = lev_raw.get("type", "cross") if isinstance(lev_raw, dict) else "cross"
                max_lev      = int(pos.get("maxLeverage", 0) or 0)

                entry_px     = float(pos.get("entryPx", 0) or 0)
                mark_px      = float(mids.get(asset, entry_px or 1))
                liq_px       = float(pos.get("liquidationPx", 0) or 0)
                upnl         = float(pos.get("unrealizedPnl", 0) or 0)
                roe          = float(pos.get("returnOnEquity", 0) or 0)
                margin_used  = float(pos.get("marginUsed", 0) or 0)

                cum_funding  = pos.get("cumFunding", {})
                funding_open = float(
                    cum_funding.get("sinceOpen", 0) if isinstance(cum_funding, dict) else 0
                )

                size_usd = abs(szi) * mark_px

                result[asset] = WhalePosition(
                    address=address, asset=asset, side=side,
                    size_contracts=abs(szi), size_usd=size_usd,
                    entry_price=entry_px, mark_price=mark_px, liquidation_px=liq_px,
                    leverage_value=lev_value, leverage_type=lev_type, max_leverage=max_lev,
                    margin_used=margin_used, unrealized_pnl=upnl, roe=roe,
                    cum_funding_since_open=funding_open,
                )
            return result

        except Exception as e:
            print(f"[WhaleTracker] _fetch_positions {address[:10]}…: {e}", flush=True)
            return {}

    # ── WebSocket fills ────────────────────────────────────────────────────

    def _get_ws_info(self) -> Info:
        if self._ws_info is None:
            self._ws_info = Info(constants.MAINNET_API_URL, skip_ws=False)
        return self._ws_info

    def _make_ws_fill_handler(self, address: str) -> Callable:
        rank = self._address_ranks.get(address)

        def on_fill(msg):
            try:
                fills = msg.get("data", {})
                if isinstance(fills, dict):
                    fills = fills.get("fills", [])
                for fill in fills:
                    direction = fill.get("dir", "")
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
                    fee  = float(fill.get("fee", 0))

                    # Do a quick follow-up position fetch to get leverage + liq_px
                    pos_data = self._fetch_positions(address)
                    pos      = pos_data.get(coin)

                    signal = WhaleSignal(
                        event_type="ws_fill", address=address, rank=rank,
                        asset=coin, side=side,
                        size_usd=notional, size_contracts=sz,
                        price=px,
                        leverage=pos.leverage_value if pos else 0,
                        leverage_type=pos.leverage_type if pos else "unknown",
                        liq_px=pos.liquidation_px if pos else 0,
                        margin_used=pos.margin_used if pos else 0,
                        pnl=0, roe_pct=0,
                        funding_since_open=0,
                        delta_usd=notional,
                        fill_dir=f"{direction} | fee ${fee:.4f}",
                    )
                    if self.signal_callback:
                        self.signal_callback(signal)
            except Exception as e:
                print(f"[WhaleTracker] WS fill handler error: {e}", flush=True)
        return on_fill

    def start_ws_subscriptions(self):
        if not self.use_websocket:
            raise RuntimeError("use_websocket=True required")
        ws = self._get_ws_info()
        for addr in self._address_ranks:
            ws.subscribe({"type": "userFills", "user": addr}, self._make_ws_fill_handler(addr))
            print(f"[WhaleTracker] WS subscribed: {addr[:10]}…", flush=True)
            time.sleep(0.1)

    # ── Position diff engine ───────────────────────────────────────────────

    def _make_signal(
        self,
        event_type: str,
        address: str,
        asset: str,
        pos: Optional[WhalePosition],
        old_pos: Optional[WhalePosition],
        rank: Optional[int],
        delta_usd: Optional[float],
    ) -> WhaleSignal:
        p = pos or old_pos
        return WhaleSignal(
            event_type=event_type, address=address, rank=rank,
            asset=asset,
            side=pos.side if pos else "CLOSED",
            size_usd=pos.size_usd if pos else 0,
            size_contracts=pos.size_contracts if pos else 0,
            price=pos.entry_price if pos else (old_pos.entry_price if old_pos else 0),
            leverage=p.leverage_value if p else 0,
            leverage_type=p.leverage_type if p else "",
            liq_px=p.liquidation_px if p else 0,
            margin_used=p.margin_used if p else 0,
            pnl=p.unrealized_pnl if p else 0,
            roe_pct=round((p.roe if p else 0) * 100, 2),
            funding_since_open=p.cum_funding_since_open if p else 0,
            delta_usd=delta_usd,
            fill_dir=None,
        )

    def _diff(
        self,
        address: str,
        old: dict[str, WhalePosition],
        new: dict[str, WhalePosition],
        rank: Optional[int],
    ) -> list[WhaleSignal]:
        signals = []
        for asset in set(old) | set(new):
            old_p = old.get(asset)
            new_p = new.get(asset)

            if old_p is None and new_p is not None:
                if new_p.size_usd >= self.min_notional:
                    signals.append(self._make_signal(
                        "new_position", address, asset, new_p, None, rank, new_p.size_usd))

            elif old_p is not None and new_p is None:
                if old_p.size_usd >= self.min_notional:
                    signals.append(self._make_signal(
                        "closed", address, asset, None, old_p, rank, -old_p.size_usd))

            elif old_p is not None and new_p is not None:
                if old_p.side != new_p.side:
                    if new_p.size_usd >= self.min_notional:
                        signals.append(self._make_signal(
                            "flip", address, asset, new_p, old_p, rank,
                            new_p.size_usd + old_p.size_usd))
                    continue

                delta     = new_p.size_usd - old_p.size_usd
                pct_chg   = abs(delta) / old_p.size_usd if old_p.size_usd > 0 else 0
                if pct_chg >= 0.10 and abs(delta) >= self.min_notional * 0.2:
                    if max(old_p.size_usd, new_p.size_usd) >= self.min_notional:
                        evt = "size_increase" if delta > 0 else "size_decrease"
                        signals.append(self._make_signal(
                            evt, address, asset, new_p, old_p, rank, delta))
        return signals

    # ── Main poll ──────────────────────────────────────────────────────────

    def poll(self) -> list[WhaleSignal]:
        self.refresh_leaderboard()
        all_signals = []
        for addr in list(self._address_ranks):
            new_pos = self._fetch_positions(addr)
            old_pos = self._snapshot.get(addr, {})
            if addr in self._snapshot:
                all_signals.extend(self._diff(addr, old_pos, new_pos, self._address_ranks.get(addr)))
            self._snapshot[addr] = new_pos
            time.sleep(0.15)
        all_signals.extend(self.check_oi_spikes())
        return all_signals

    # ── Inspection helpers ─────────────────────────────────────────────────

    def top_positions(self, top_n: int = 10, asset: Optional[str] = None) -> list[dict]:
        result = []
        for addr, positions in self._snapshot.items():
            for pos_asset, pos in positions.items():
                if asset and pos_asset != asset:
                    continue
                if pos.size_usd < self.min_notional:
                    continue
                d = pos.copy_trade_summary
                d["address"] = addr
                d["rank"]    = self._address_ranks.get(addr)
                d["snapshot_ts"] = pos.snapshot_ts.isoformat()
                result.append(d)
        result.sort(key=lambda x: x["size_usd"], reverse=True)
        return result[:top_n]

    def address_snapshot(self, address: str) -> list[dict]:
        return [
            pos.copy_trade_summary
            for pos in self._snapshot.get(address.lower(), {}).values()
        ]
