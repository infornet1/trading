"""
Phase 1 — Signal parser for Swallow Trade - Premium channel.

Handles two formats:
  Format A: "PAIR = Long/Short (...)\n(Nx leverage)\n◼️Entry: ...\n◼️Stoploss: ...\n◼️Target: ..."
  Format B: "📊 PAIR\nSize: ...\nLeverage: ...\nEntry: ...\nTarget: ...\nStoploss: ..."
"""

import re
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Signal:
    pair: str
    direction: str          # "long" | "short"
    leverage: Optional[int]
    entry: float
    stoploss: float
    targets: list[float]
    size_pct: Optional[float] = None
    raw: str = ""

    def __str__(self):
        tgts = " | ".join(f"${t:,.2f}" for t in self.targets)
        lev  = f"{self.leverage}x" if self.leverage else "?"
        size = f"  Size: {self.size_pct}%\n" if self.size_pct else ""
        return (
            f"{'='*50}\n"
            f"  {self.pair} — {self.direction.upper()} ({lev})\n"
            f"{size}"
            f"  Entry:    ${self.entry:,.2f}\n"
            f"  Stoploss: ${self.stoploss:,.2f}\n"
            f"  Targets:  {tgts}\n"
            f"{'='*50}"
        )


def _clean_price(raw: str) -> float:
    return float(raw.replace(",", "").replace("$", "").strip())


def _parse_targets(raw: str) -> list[float]:
    parts = re.split(r"[&|,]", raw)
    results = []
    for p in parts:
        p = p.strip()
        m = re.search(r"[\d,]+\.?\d*", p)
        if m:
            results.append(_clean_price(m.group()))
    return results


def parse_format_a(text: str) -> Optional[Signal]:
    """
    BCH/USDT = Short ( 📊)
           (20x leverage)
    ◼️Entry: $459.08 (activated)
    ◼️Stoploss is at $466.94 (-56%)
    ◼️Target: $442.16 & $430.00
    """
    pair_dir = re.search(
        r"([A-Z]{2,10}/[A-Z]{2,10})\s*=\s*(Long|Short)", text, re.IGNORECASE
    )
    if not pair_dir:
        return None

    pair      = pair_dir.group(1).upper()
    direction = pair_dir.group(2).lower()

    lev_m = re.search(r"\((\d+)x\s*leverage\)", text, re.IGNORECASE)
    leverage = int(lev_m.group(1)) if lev_m else None

    entry_m = re.search(r"Entry[:\s]+\$?([\d,]+\.?\d*)", text, re.IGNORECASE)
    if not entry_m:
        return None
    entry = _clean_price(entry_m.group(1))

    sl_m = re.search(r"Stoploss\s+is\s+at\s+\$?([\d,]+\.?\d*)", text, re.IGNORECASE)
    if not sl_m:
        sl_m = re.search(r"Stoploss[:\s]+\$?([\d,]+\.?\d*)", text, re.IGNORECASE)
    if not sl_m:
        return None
    stoploss = _clean_price(sl_m.group(1))

    tgt_m = re.search(r"Target[:\s]+(.+?)(?:\n|$)", text, re.IGNORECASE)
    targets = _parse_targets(tgt_m.group(1)) if tgt_m else []

    return Signal(pair=pair, direction=direction, leverage=leverage,
                  entry=entry, stoploss=stoploss, targets=targets, raw=text)


def parse_format_b(text: str) -> Optional[Signal]:
    """
    📊 BCH/USDT
    Size: 3%
    Leverage: 20x
    Entry: $436.16 (market price entry)
    Target: $429 (+33%)
    Stoploss: $439 (-13%)
    """
    pair_m = re.search(r"([A-Z]{2,10}/[A-Z]{2,10})", text)
    if not pair_m:
        return None

    # Format B has no explicit direction — infer from entry vs target
    pair = pair_m.group(1).upper()

    lev_m   = re.search(r"Leverage[:\s]+(\d+)x", text, re.IGNORECASE)
    leverage = int(lev_m.group(1)) if lev_m else None

    size_m   = re.search(r"Size[:\s]+([\d.]+)%", text, re.IGNORECASE)
    size_pct = float(size_m.group(1)) if size_m else None

    entry_m = re.search(r"Entry[:\s]+\$?([\d,]+\.?\d*)", text, re.IGNORECASE)
    if not entry_m:
        return None
    entry = _clean_price(entry_m.group(1))

    sl_m = re.search(r"Stoploss[:\s]+\$?([\d,]+\.?\d*)", text, re.IGNORECASE)
    if not sl_m:
        return None
    stoploss = _clean_price(sl_m.group(1))

    tgt_m   = re.search(r"Target[:\s]+(.+?)(?:\n|$)", text, re.IGNORECASE)
    targets = _parse_targets(tgt_m.group(1)) if tgt_m else []

    direction = "short" if (targets and targets[0] < entry) else "long"

    return Signal(pair=pair, direction=direction, leverage=leverage,
                  entry=entry, stoploss=stoploss, targets=targets,
                  size_pct=size_pct, raw=text)


def parse_signal(text: str) -> Optional[Signal]:
    """Try all known formats, return first match."""
    return parse_format_a(text) or parse_format_b(text)


# ── Reply/status detection ───────────────────────────────────────────────────

SIGNAL_UPDATES = {
    "stopped":    re.compile(r"(stopped|sl hit|stop loss hit|🚫)", re.IGNORECASE),
    "target_hit": re.compile(r"(target\s*(hit|reached)|tp\d?\s*(hit|reached)|✅|🎯)", re.IGNORECASE),
    "partial":    re.compile(r"(tp\d|partial|50%|took\s*profit)", re.IGNORECASE),
    "cancelled":  re.compile(r"(cancel|void|invalid|ignore)", re.IGNORECASE),
}


def parse_update(text: str) -> Optional[str]:
    """
    Detect reply messages that update signal status.
    Returns one of: 'stopped' | 'target_hit' | 'partial' | 'cancelled' | None
    """
    for status, pattern in SIGNAL_UPDATES.items():
        if pattern.search(text):
            return status
    return None


# ── quick self-test ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    samples = [
        """BCH/USDT = Short ( 📊)
       (20x leverage)

◼️Entry: $459.08 (activated)
◼️Stoploss is at $466.94 (-56%)
◼️Target: $442.16

💻Looks good for further move here!""",

        """ETH/USDT = Short ( 📊)
       (20x leverage)

◼️Entry: $3,356.09 (activated)
◼️Stoploss is at $2399.49 (-56%)
◼️Target: $2283.19 & $2248.86 & $2207.48

💻slightly went from entry away but still solid entry!""",

        """📊 BCH/USDT

Size: 3%
Leverage: 20x
Entry: $436.16 (market price entry)
Target: $429 (+33%)
Stoploss: $439 (-13%)

🌩 Formed MSB""",

        """LTC/USDT = Short ( 📊)
       (15x leverage)

◼️Entry: $3.209 (activated)
◼️Stoploss is at $3.33 (-58%)
◼️Target: $3.088 & $3.013

💻Strong MSB could give a good dip here!""",
    ]

    for s in samples:
        result = parse_signal(s)
        if result:
            print(result)
        else:
            print("NOT PARSED:", s[:60])
        print()

    print("\n── Reply/update detection ──")
    updates = [
        "🚫Got Stopped",
        "✅ Target reached! Great trade everyone",
        "Took 50% profits at TP1",
        "Cancel this signal, setup invalidated",
        "Markets are looking interesting today",  # should return None
    ]
    for u in updates:
        status = parse_update(u)
        print(f"  '{u[:40]}' → {status}")
