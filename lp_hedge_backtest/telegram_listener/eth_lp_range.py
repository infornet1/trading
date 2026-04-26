"""
ETH LP Range Advisor — pulls latest ETH chart from Swallow Trade - Premium,
analyzes it with Claude Vision, and outputs ready-to-use VIZNAGO LP range config.

Usage:
    python eth_lp_range.py              # auto-find latest ETH chart
    python eth_lp_range.py --msg 7874   # analyze specific message ID
"""

import os
import sys
import base64
import asyncio
import argparse
import re
from datetime import datetime, timezone
from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.tl.types import PeerChannel
import anthropic

# load both .env files
load_dotenv()
load_dotenv("../api/.env", override=False)

TG_API_ID   = int(os.getenv("TG_API_ID"))
TG_API_HASH = os.getenv("TG_API_HASH")
TG_SESSION  = os.getenv("TG_SESSION", "viznago_listener")
ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY")
CHANNEL_ID          = 1951769926
BITCOIN_DAILY_THREAD = 22   # Bitcoin Daily thread — charts for LP range advisor

VISION_MODEL = "claude-sonnet-4-6"   # sonnet for vision accuracy

ANALYSIS_PROMPT = """You are a professional crypto technical analyst helping configure a Uniswap v3 ETH/USDC liquidity position.

Analyze this ETH price chart and extract the following in JSON format:

{
  "pair": "ETH/USDT or ETH/USDC",
  "timeframe": "e.g. 4h",
  "current_price": <number or null>,
  "trend": "bullish | bearish | ranging",
  "resistance_levels": [<list of price numbers, highest confidence first>],
  "support_levels": [<list of price numbers, highest confidence first>],
  "key_levels": {
    "primary_resistance": <number>,
    "primary_support": <number>,
    "secondary_support": <number or null>
  },
  "volatility": "low | medium | high",
  "analyst_bias": "bullish | bearish | neutral",
  "notes": "<one sentence summary of chart structure>"
}

Rules:
- Extract ONLY levels clearly marked or labeled on the chart (lines, boxes, price labels)
- If a level has a price label on the chart, use that exact number
- current_price = the most recent candle close or any marked current price line
- Return ONLY valid JSON, no extra text
"""


def compute_lp_ranges(levels: dict, current_price: float) -> dict:
    resistance = levels.get("primary_resistance") or current_price * 1.08
    support    = levels.get("primary_support") or current_price * 0.92
    support2   = levels.get("secondary_support") or support * 0.97

    # clamp to sensible distance from current price
    upper_a = max(resistance, current_price * 1.03)
    lower_a = min(support, current_price * 0.97)

    upper_b = current_price * 1.06
    lower_b = min(support, current_price * 0.95)

    upper_c = max(resistance * 1.02, current_price * 1.12)
    lower_c = min(support2, current_price * 0.90)

    def width(lo, hi): return round((hi - lo) / lo * 100, 1)
    def lev(w):
        if w < 8:   return "5–8x"
        if w < 15:  return "3–5x"
        return "2–3x"
    def sl(w):
        return "0.5%" if w < 10 else "0.8%"

    return {
        "current_price": round(current_price, 2),
        "options": {
            "A_standard": {
                "lower": round(lower_a, 2),
                "upper": round(upper_a, 2),
                "width_pct": width(lower_a, upper_a),
                "leverage": lev(width(lower_a, upper_a)),
                "sl_pct": sl(width(lower_a, upper_a)),
                "label": "Standard — chart levels",
            },
            "B_tight": {
                "lower": round(lower_b, 2),
                "upper": round(upper_b, 2),
                "width_pct": width(lower_b, upper_b),
                "leverage": lev(width(lower_b, upper_b)),
                "sl_pct": sl(width(lower_b, upper_b)),
                "label": "Tight — more fees, more IL risk",
            },
            "C_conservative": {
                "lower": round(lower_c, 2),
                "upper": round(upper_c, 2),
                "width_pct": width(lower_c, upper_c),
                "leverage": lev(width(lower_c, upper_c)),
                "sl_pct": sl(width(lower_c, upper_c)),
                "label": "Conservative — wider cushion",
            },
        }
    }


def print_report(analysis: dict, ranges: dict, msg_id: int, msg_date: datetime, caption: str):
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    cp  = ranges["current_price"]

    print(f"\n{'='*62}")
    print(f"  ETH LP Range Advisor — VIZNAGO DeFi")
    print(f"  Chart: msg #{msg_id} | {msg_date.strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"  Analysis run: {now}")
    print(f"{'='*62}")

    print(f"\n📊 CHART ANALYSIS")
    print(f"  Pair:       {analysis.get('pair','ETH/USDT')}  ({analysis.get('timeframe','?')})")
    print(f"  Price:      ${cp:,.2f}")
    print(f"  Trend:      {analysis.get('trend','?').upper()}")
    print(f"  Bias:       {analysis.get('analyst_bias','?').upper()}")
    print(f"  Volatility: {analysis.get('volatility','?').upper()}")
    print(f"  Notes:      {analysis.get('notes','')}")

    print(f"\n🎯 KEY LEVELS IDENTIFIED")
    res = analysis.get("resistance_levels", [])
    sup = analysis.get("support_levels", [])
    for r in res[:3]: print(f"  🔴 Resistance  ${r:,.2f}")
    for s in sup[:3]: print(f"  🟢 Support     ${s:,.2f}")

    print(f"\n{'─'*62}")
    print(f"  VIZNAGO LP RANGE OPTIONS  (ETH/USDC · Uniswap v3 · Arbitrum)")
    print(f"{'─'*62}")

    labels = {"A_standard": "A — Standard ⭐", "B_tight": "B — Tight", "C_conservative": "C — Conservative"}
    for key, opt in ranges["options"].items():
        w = opt["width_pct"]
        print(f"\n  {labels[key]}")
        print(f"    Lower bound : ${opt['lower']:,.2f}")
        print(f"    Upper bound : ${opt['upper']:,.2f}")
        print(f"    Range width : {w}%")
        print(f"    Leverage    : {opt['leverage']}")
        print(f"    SL %        : {opt['sl_pct']}")
        print(f"    Hedge ratio : {'70–80%' if w < 12 else '60–70%'}")
        print(f"    Mode        : Defensor Bajista (short-only hedge)")

    print(f"\n{'─'*62}")
    print(f"  ⚠️  Chart from {msg_date.strftime('%b %d')} — verify current ETH price before deploying.")
    print(f"     If price broke below primary support, wait for new analysis.")
    print(f"{'='*62}\n")


async def find_latest_eth_chart(client, entity):
    """Scan Bitcoin Daily thread (22) for the most recent ETH analysis chart."""
    eth_keywords = re.compile(r'\bETH\b', re.IGNORECASE)
    skip = re.compile(r'JUST IN|ETF|Deribit|options will expire', re.IGNORECASE)

    async for msg in client.iter_messages(entity, limit=500, reply_to=BITCOIN_DAILY_THREAD):
        text = msg.message or ""
        if msg.media and eth_keywords.search(text) and not skip.search(text):
            return msg
    return None


def save_cache(analysis: dict, ranges: dict, msg_id: int, msg_date: datetime):
    """Write analysis result to data_cache/lp_range_latest.json for the API to serve."""
    import json
    cache_dir = os.path.join(os.path.dirname(__file__), "..", "data_cache")
    os.makedirs(cache_dir, exist_ok=True)
    payload = {
        "saved_at": datetime.now(timezone.utc).isoformat(),
        "msg_id":   msg_id,
        "msg_date": msg_date.isoformat(),
        "analysis": analysis,
        "ranges":   ranges,
    }
    cache_path = os.path.join(cache_dir, "lp_range_latest.json")
    with open(cache_path, "w") as f:
        json.dump(payload, f, indent=2)
    print(f"💾 Saved to {cache_path}", flush=True)


async def main(msg_id: int = None, save: bool = False):
    ai = anthropic.Anthropic(api_key=ANTHROPIC_KEY)

    async with TelegramClient(TG_SESSION, TG_API_ID, TG_API_HASH) as client:
        entity = await client.get_entity(PeerChannel(CHANNEL_ID))

        if msg_id:
            msg = await client.get_messages(entity, ids=msg_id)
        else:
            print("🔍 Scanning for latest ETH chart...")
            msg = await find_latest_eth_chart(client, entity)
            if not msg:
                print("No ETH chart found in last 500 messages.")
                return

        print(f"📥 Downloading chart (msg #{msg.id}, {msg.date.strftime('%Y-%m-%d %H:%M UTC')})...")
        img_path = await client.download_media(msg, file=f"eth_chart_{msg.id}.jpg")
        caption  = msg.message or ""

        print(f"🤖 Analyzing with Claude Vision ({VISION_MODEL})...")
        with open(img_path, "rb") as f:
            img_b64 = base64.standard_b64encode(f.read()).decode("utf-8")

        response = ai.messages.create(
            model=VISION_MODEL,
            max_tokens=1024,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": img_b64}},
                    {"type": "text",  "text": ANALYSIS_PROMPT + f"\n\nChart caption from channel:\n{caption}"},
                ],
            }],
        )

        raw = response.content[0].text.strip()

        # extract JSON from response
        import json
        json_match = re.search(r'\{.*\}', raw, re.DOTALL)
        if not json_match:
            print("Could not parse Claude response:\n", raw)
            return
        analysis = json.loads(json_match.group())

        current_price = (
            analysis.get("current_price")
            or (analysis.get("key_levels") or {}).get("primary_resistance", 0) * 0.97
        )

        if not current_price or current_price == 0:
            print("⚠️  Could not determine current price from chart.")
            return

        key_levels = analysis.get("key_levels", {})
        ranges = compute_lp_ranges(key_levels, current_price)

        print_report(analysis, ranges, msg.id, msg.date, caption)

        if save:
            save_cache(analysis, ranges, msg.id, msg.date)

        # cleanup downloaded image
        os.remove(img_path)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--msg",  type=int,  default=None,  help="Specific message ID to analyze")
    parser.add_argument("--save", action="store_true",      help="Save result to data_cache/lp_range_latest.json")
    args = parser.parse_args()
    asyncio.run(main(args.msg, save=args.save))
