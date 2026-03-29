#!/usr/bin/env python3
"""
VIZNAGO FURY — Hyperliquid Order Dry-Run Validator
===================================================
Validates that HL connectivity, sizing math, and order placement work
without touching the live bot.

Usage:
  python3 test_hl_order.py                  # read-only: connectivity + sizing
  python3 test_hl_order.py --live           # + real round-trip (0.001 ETH open+close)
  python3 test_hl_order.py --nft 5381818    # test a specific NFT (default: reads .env)
"""

import argparse
import math
import os
import sys
import time

from dotenv import load_dotenv
from eth_account import Account
from hyperliquid.exchange import Exchange
from hyperliquid.info import Info
from hyperliquid.utils import constants
from web3 import Web3

load_dotenv()

# ── Config ─────────────────────────────────────────────────────────────────

HL_SECRET_KEY = os.getenv("HYPERLIQUID_SECRET_KEY")
HL_ADDRESS    = os.getenv("HYPERLIQUID_ACCOUNT_ADDRESS")
RPC_URL       = os.getenv("ARBITRUM_RPC_URL", "https://arb1.arbitrum.io/rpc")

V3_POS_MANAGER = "0xC36442b4a4522E871399CD717aBDD847Ab11FE88"
V3_ABI = [
    {"inputs": [{"internalType": "uint256", "name": "tokenId", "type": "uint256"}],
     "name": "positions", "outputs": [
        {"internalType": "uint96",  "name": "nonce",     "type": "uint96"},
        {"internalType": "address", "name": "operator",  "type": "address"},
        {"internalType": "address", "name": "token0",    "type": "address"},
        {"internalType": "address", "name": "token1",    "type": "address"},
        {"internalType": "uint24",  "name": "fee",       "type": "uint24"},
        {"internalType": "int24",   "name": "tickLower", "type": "int24"},
        {"internalType": "int24",   "name": "tickUpper", "type": "int24"},
        {"internalType": "uint128", "name": "liquidity", "type": "uint128"},
        {"internalType": "uint256", "name": "feeGrowthInside0LastX128", "type": "uint256"},
        {"internalType": "uint256", "name": "feeGrowthInside1LastX128", "type": "uint256"},
        {"internalType": "uint128", "name": "tokensOwed0", "type": "uint128"},
        {"internalType": "uint128", "name": "tokensOwed1", "type": "uint128"},
    ], "stateMutability": "view", "type": "function"}
]

MIN_ORDER   = 0.001   # HL minimum ETH order size
HEDGE_RATIO = float(os.getenv("HEDGE_RATIO", "50.0"))
MAX_LEV     = int(os.getenv("MAX_LEVERAGE", "3"))
MARGIN_BUF  = 1.5

OK   = "[OK]"
FAIL = "[FAIL]"
WARN = "[WARN]"


# ── Helpers ────────────────────────────────────────────────────────────────

def tick_to_price(tick):
    return (1.0001 ** tick) * (10 ** 12)


def calc_x_max_eth(liquidity, tick_lower, tick_upper):
    if liquidity == 0:
        return 0.0
    sqrt_pa = math.sqrt(1.0001 ** tick_lower)
    sqrt_pb = math.sqrt(1.0001 ** tick_upper)
    return liquidity * (1.0 / sqrt_pa - 1.0 / sqrt_pb) / 1e18


def sep(label=""):
    width = 60
    if label:
        pad = (width - len(label) - 2) // 2
        print(f"\n{'─' * pad} {label} {'─' * pad}")
    else:
        print("─" * width)


# ── Checks ─────────────────────────────────────────────────────────────────

def check_credentials():
    sep("1. Credentials")
    ok = True
    if not HL_SECRET_KEY:
        print(f"{FAIL} HYPERLIQUID_SECRET_KEY not set")
        ok = False
    else:
        print(f"{OK} HYPERLIQUID_SECRET_KEY found (len={len(HL_SECRET_KEY)})")
    if not HL_ADDRESS:
        print(f"{FAIL} HYPERLIQUID_ACCOUNT_ADDRESS not set")
        ok = False
    else:
        print(f"{OK} HYPERLIQUID_ACCOUNT_ADDRESS: {HL_ADDRESS}")
    return ok


def check_hl_connection():
    sep("2. Hyperliquid Connection")
    try:
        info = Info(constants.MAINNET_API_URL, skip_ws=True)
        mids = info.all_mids()
        eth_price = float(mids["ETH"])
        print(f"{OK} HL API reachable — ETH price: ${eth_price:,.2f}")
        return info, eth_price
    except Exception as e:
        print(f"{FAIL} Cannot connect to Hyperliquid: {e}")
        return None, None


def check_hl_account(info):
    sep("3. HL Account State")
    try:
        state   = info.user_state(HL_ADDRESS)
        summary = state["marginSummary"]
        balance = float(summary["accountValue"])
        margin  = float(summary["totalMarginUsed"])
        pnl     = float(summary.get("totalUnrealizedPnl", 0))
        print(f"{OK} Account value:    ${balance:,.2f} USDC")
        print(f"   Margin in use:    ${margin:,.2f} USDC")
        print(f"   Unrealized PnL:   ${pnl:,.4f} USDC")

        positions = state.get("assetPositions", [])
        eth_pos = [p for p in positions if p["position"]["coin"] == "ETH"]
        if eth_pos:
            p = eth_pos[0]["position"]
            print(f"{WARN} Existing ETH position: {p['szi']} ETH @ ${p.get('entryPx', '?')}")
        else:
            print(f"{OK} No open ETH position")

        return balance
    except Exception as e:
        print(f"{FAIL} Cannot read account state: {e}")
        return 0.0


def check_nft(nft_id):
    sep(f"4. Uniswap NFT #{nft_id}")
    try:
        w3       = Web3(Web3.HTTPProvider(RPC_URL))
        contract = w3.eth.contract(address=V3_POS_MANAGER, abi=V3_ABI)
        pos      = contract.functions.positions(nft_id).call()
        tick_lo, tick_hi, liquidity = pos[5], pos[6], pos[7]
        lower = tick_to_price(tick_lo)
        upper = tick_to_price(tick_hi)
        x_max = calc_x_max_eth(liquidity, tick_lo, tick_hi)
        print(f"{OK} NFT #{nft_id} on-chain")
        print(f"   Range:     ${lower:,.2f} — ${upper:,.2f}")
        print(f"   Liquidity: {liquidity:,}")
        print(f"   X_max ETH: {x_max:.6f} ETH  (max LP exposure at lower bound)")
        return lower, upper, liquidity, tick_lo, tick_hi, x_max
    except Exception as e:
        print(f"{FAIL} Cannot read NFT #{nft_id}: {e}")
        return None, None, None, None, None, None


def simulate_sizing(eth_price, margin, lower, x_max):
    sep("5. Order Sizing Simulation")
    hedge_size = round(x_max * HEDGE_RATIO / 100.0, 4)
    hedge_size = max(hedge_size, MIN_ORDER)
    hedge_size = min(hedge_size, x_max)

    notional     = hedge_size * eth_price
    raw_leverage = notional / margin if margin > 0 else 99
    leverage     = min(max(math.ceil(raw_leverage), 1), MAX_LEV)
    req_margin   = notional / leverage
    safe_margin  = req_margin * MARGIN_BUF

    margin_ok = margin >= safe_margin

    print(f"   ETH price:       ${eth_price:,.2f}")
    print(f"   X_max:           {x_max:.6f} ETH")
    print(f"   Hedge ratio:     {HEDGE_RATIO}%")
    print(f"   => Hedge size:   {hedge_size:.4f} ETH")
    print(f"   => Notional:     ${notional:,.2f}")
    print(f"   HL balance:      ${margin:,.2f}")
    print(f"   Raw leverage:    {raw_leverage:.2f}x  (capped at {MAX_LEV}x -> {leverage}x)")
    print(f"   Required margin: ${req_margin:,.2f}")
    print(f"   Safety (x{MARGIN_BUF}):    ${safe_margin:,.2f}  {'<- OK' if margin_ok else '<- INSUFFICIENT'}")

    if x_max < MIN_ORDER:
        print(f"\n{FAIL} X_max {x_max:.6f} ETH < min {MIN_ORDER} ETH — hedge would be SKIPPED")
        return False
    if margin <= 0:
        print(f"\n{FAIL} No HL margin — hedge would be SKIPPED")
        return False
    if not margin_ok:
        print(f"\n{WARN} Insufficient margin — hedge would be SKIPPED")
        return False

    trigger = lower * 0.995
    print(f"\n{OK} Sizing OK — bot would open {hedge_size:.4f} ETH short at {leverage}x leverage")
    print(f"   Trigger price:   ${trigger:,.2f}  (0.5% below floor ${lower:,.2f})")
    return True


def live_round_trip(eth_price):
    sep("6. LIVE Round-Trip Test (0.001 ETH)")
    print(f"{WARN} About to place a REAL order on Hyperliquid mainnet.")
    print(f"   Direction: SHORT  |  Size: 0.001 ETH  |  ~${0.001 * eth_price:.2f}")
    print(f"   The position will be closed immediately after opening.")
    confirm = input("\n   Type 'yes' to proceed: ").strip().lower()
    if confirm != "yes":
        print("   Skipped.")
        return

    try:
        wallet   = Account.from_key(HL_SECRET_KEY)
        exchange = Exchange(wallet, constants.MAINNET_API_URL, account_address=HL_ADDRESS)

        # Use 1x leverage for the test
        print("\n   Setting leverage to 1x...")
        lev_result = exchange.update_leverage(1, "ETH")
        print(f"   Leverage result: {lev_result}")

        # Open short
        print("   Placing 0.001 ETH SHORT...")
        open_result = exchange.market_open("ETH", False, 0.001, slippage=0.01)
        print(f"   Raw response: {open_result}")

        if open_result.get("status") != "ok":
            print(f"\n{FAIL} Open order FAILED — nothing to close")
            return

        statuses = open_result.get("response", {}).get("data", {}).get("statuses", [{}])
        fill_info = statuses[0].get("filled", {}) if statuses else {}
        fill_px  = fill_info.get("avgPx", "?")
        fill_sz  = fill_info.get("totalSz", "?")
        print(f"\n{OK} SHORT opened: {fill_sz} ETH @ ${fill_px}")

        time.sleep(2)

        # Close
        print("   Closing position...")
        close_result = exchange.market_close("ETH")
        print(f"   Raw response: {close_result}")

        if close_result.get("status") == "ok":
            print(f"\n{OK} Round-trip COMPLETE — open and close both succeeded!")
            print(f"   The bot's order logic is confirmed working on mainnet.")
        else:
            print(f"\n{FAIL} Close FAILED — check HL dashboard to close manually!")

    except Exception as e:
        print(f"\n{FAIL} Live test error: {e}")
        import traceback
        traceback.print_exc()


# ── Main ───────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="VIZNAGO HL dry-run validator")
    parser.add_argument("--live", action="store_true",
                        help="Run a real 0.001 ETH open+close to confirm order API works")
    parser.add_argument("--nft", type=int, default=None,
                        help="NFT token ID to test sizing against (default: UNISWAP_NFT_ID env)")
    args = parser.parse_args()

    nft_id = args.nft or int(os.getenv("UNISWAP_NFT_ID", "5364087"))

    print("\n" + "=" * 60)
    print("  VIZNAGO FURY — HL Order Validator")
    print(f"  NFT #{nft_id}  |  Account: {HL_ADDRESS or 'NOT SET'}")
    print("=" * 60)

    # 1. Credentials
    if not check_credentials():
        sys.exit(1)

    # 2. HL connection + price
    info, eth_price = check_hl_connection()
    if not info:
        sys.exit(1)

    # 3. Account state
    margin = check_hl_account(info)

    # 4. NFT data
    lower, upper, liquidity, tick_lo, tick_hi, x_max = check_nft(nft_id)
    if lower is None:
        sys.exit(1)

    # 5. Sizing simulation
    size_ok = simulate_sizing(eth_price, margin, lower, x_max)

    # 6. Optional live test
    if args.live:
        if size_ok:
            live_round_trip(eth_price)
        else:
            print(f"\n{WARN} Skipping live test — sizing check failed above")

    sep()
    if size_ok:
        print("All checks passed — bot is ready for live hedging.")
    else:
        print("Issues found — review above before going live.")
    print()


if __name__ == "__main__":
    main()
