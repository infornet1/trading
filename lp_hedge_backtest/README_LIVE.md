# LP + Perps Hedge: Live Bot Guide

**Bot Defensor Bajista v2.0** — dual-trigger hedge bot for Uniswap v3 LP positions.

---

## Setup

### 1. Configure Credentials

```bash
cd lp_hedge_backtest
cp .env.example .env   # fill in HL private key + address
```

**⚠️ SECURITY:** Never share your `.env`. Bot only needs "Trade" permissions on Hyperliquid.

### 2. Validate before running

```bash
source venv/bin/activate
python3 test_hl_order.py              # read-only: connectivity + sizing check
python3 test_hl_order.py --live       # + real 0.001 ETH round-trip
python3 test_hl_order.py --nft 12345  # test a specific NFT
```

### 3. Run via systemd (recommended)

```bash
sudo systemctl start live_hedge_bot
sudo systemctl status live_hedge_bot
journalctl -u live_hedge_bot -f
```

---

## Bot Logic (v2.0)

### Two entry triggers

| Trigger | Condition | Description |
|---------|-----------|-------------|
| **FROM ABOVE** | Price crosses `upper_bound × (1 - UPPER_BUFFER_PCT)` downward | Armed when price was above range, fires on re-entry |
| **BELOW RANGE** | Price drops below `lower_bound × (1 - TRIGGER_OFFSET_PCT)` | Classic IL protection |

### Position sizing

- `X_max` ETH = max LP exposure at lower bound (computed from on-chain liquidity)
- Hedge size = `X_max × HEDGE_RATIO / 100`
- Leverage = auto-calculated to fit available margin, capped at `MAX_LEVERAGE`

### Exit logic (unified trailing SL)

1. **Initial SL**: `entry × (1 + SL_PCT)` — fires if price spikes immediately after entry
2. **Breakeven activation**: once profit ≥ `BREAKEVEN_PCT`, trailing SL activates
3. **Trail**: `SL = min(entry, short_min × (1 + TRAIL_PCT))` — moves down as price falls, never up
4. **No fixed TP** — trailing SL locks in profits dynamically

### Re-entry guard

After a short closes, the below-range trigger is blocked until price recovers
`close_price × (1 + REENTRY_BUFFER_PCT)`. Prevents immediately re-shorting a choppy bottom.

### Bounds refresh

Every `BOUNDS_REFRESH_HOURS` hours (when idle, no open position), the bot re-reads the
Uniswap NFT from Arbitrum to pick up any LP range changes.

---

## Key Parameters

| Variable | Default | Description |
|----------|---------|-------------|
| `UNISWAP_NFT_ID` | `5364087` | Uniswap v3 NFT token ID |
| `CHECK_INTERVAL` | `30` | Price polling interval (seconds) |
| `TRIGGER_OFFSET_PCT` | `0.5` | % below lower bound to trigger short |
| `UPPER_BUFFER_PCT` | `2.0` | % inside upper bound for from-above trigger |
| `HEDGE_RATIO` | `50.0` | % of X_max ETH to short |
| `MAX_LEVERAGE` | `10` | Hard leverage cap |
| `SL_PCT` | `0.5` | Initial SL % above entry |
| `BREAKEVEN_PCT` | `1.0` | Profit % to activate trailing SL |
| `TRAIL_PCT` | `1.5` | Trail % above running min price |
| `REENTRY_BUFFER_PCT` | `0.5` | Recovery % before re-entry guard clears |
| `BOUNDS_REFRESH_HOURS` | `4` | Hours between idle LP range refreshes |

---

## Monitoring

### Terminal status line (every 30s)

```
[10:30:00] ETH $2,085.25 | 🟢 IN    | ⚪ IDLE (ready)
[10:30:30] ETH $1,908.10 | 🔴 BELOW | 🛡️ SHORT below_range | min $1905.00 | SL $1923.45 | BE✗
```

### Admin dashboard

- Pool health cards with live ETH price position bar
- **Heartbeat badge** — last stdout received from bot (green < 2min, yellow < 5min, red > 5min)
- **Native SL Order panel** — shows if a native stop-loss order exists on Hyperliquid or warns if protection is software-only
- **SL distance** — real-time % distance from current price to SL trigger
- **Trail status** — whether breakeven has activated and trailing SL is running
- Event history with PnL tracking

---

## Changelog

### 2026-03-27 — SL floor + margin failure guard + stop confirmation modal

**4. SL hard floor (0.3% minimum)**
A new `_SL_FLOOR_PCT = 0.003` constant prevents the bot from operating with a stop-loss
smaller than 0.3% above entry. Users who set `SL_PCT` below this value have it silently
raised to 0.3%. The default `SL_PCT` was also changed from 0.1% → 0.5%.
This eliminates whipsaw losses caused by tiny SL gaps (e.g. NFT #5374616 had 0.05%,
producing a $0.99 gap — smaller than normal Hyperliquid price noise).

**5. Margin failure guard (5 retries → 5-minute backoff + email)**
If sizing/margin checks fail 5 consecutive times, the bot pauses for 5 minutes and
sends an email alert instead of retrying every 30 seconds. The counter resets on any
successful order. Prevents flooding Hyperliquid with 269-error requests when the wallet
is empty.

**6. Stop confirmation modal with live position query**
The dashboard "Stop Bot" button now shows a confirmation modal that queries the live
Hyperliquid position before the user confirms. The modal shows: coin, side (SHORT/LONG),
size, entry price, mark price, and unrealized PnL. If no open position exists, the modal
still requires confirmation but shows a "no open position" message. New API endpoint:
`GET /bots/{config_id}/hl-position`.

**7. Bot renamed to VIZNIAGO Defensor Bajista**
All references in email subjects, email bodies, console output, and file docstrings
updated from "Haragán v2.0" to "VIZNIAGO Defensor Bajista".

---

### 2026-03-27 — Three order-placement bugs fixed

**1. Unified account balance (`get_hl_margin_balance`)**
Hyperliquid's `clearinghouseState` API returns `accountValue: 0` for unified accounts
where USDC sits in the spot wallet. The bot now also queries `spotClearinghouseState`
and sums `perp + spot USDC` as the effective margin, so unified accounts work correctly.

**2. Leverage auto-adjustment loop (wrong direction)**
When `TARGET_LEVERAGE` didn't fit the available margin, the bot looped downward
(`range(lev-1, 0, -1)`) — lower leverage requires *more* margin, so the loop always
failed. Fixed to loop upward to `MAX_LEVERAGE` (15x) instead, reducing the margin
requirement until it fits.

**3. Float precision — `float_to_wire` rejection**
`min(size, x_max)` could return the raw unrounded `x_max` float
(e.g. `0.06939895769911981`) bypassing the earlier `round(..., 4)`. Hyperliquid's SDK
rejects sizes with > 4 decimal places. Fixed with `round(min(size, x_max), 4)`.

---

## Known Limitations

### SL is software-managed (no native HL stop order yet)

The stop-loss is a **Python variable checked every 30 seconds**, not a native order placed on
Hyperliquid. Risks:

- 30s polling gap: exit may be worse than SL price during fast spikes
- If the bot crashes, there is no protection until it restarts (systemd restarts in ~10s)

**Planned fix:** Option A — place a native HL stop-market order after opening each short,
and `modify_order()` it as the trailing SL moves. See `SAAS_PLAN.md` for implementation plan.

---

## DB Migration Required (trailing_stop event type)

If upgrading from a version before this one, run this migration on MariaDB:

```sql
ALTER TABLE bot_events
  MODIFY COLUMN event_type
  ENUM('started','hedge_opened','breakeven','tp_hit','sl_hit','trailing_stop','stopped','error')
  NOT NULL;
```

This adds `trailing_stop` as a proper event type (previously fell back to `error`).

---

## Telegram Bot — @vizniago_bot

VIZNAGO provides real-time alerts via Telegram. No email or personal data required — only your wallet address.

### How to link your wallet

1. Open Telegram and search for **@vizniago_bot**
2. Tap **START** — the bot sends a welcome message in Spanish
3. Send: `/start 0xYourWalletAddress`
4. The bot replies with full status of all **active** bots on that wallet

### Commands

| Command | Description |
|---|---|
| `/start` | Show welcome message and instructions |
| `/start 0xWallet` | Link wallet and display active bot status |
| `/status` | Show bots across all linked wallets |
| `/unlink 0xWallet` | Remove a specific wallet from alerts |
| `/unlink all` | Remove all linked wallets |
| `/help` | List all commands |

### What the bot shows after /start 0xWallet

For each **active** bot on the wallet:
- NFT token ID, trading pair, LP price range
- Estimated pool size (in ETH)
- All active parameters: hedge ratio, leverage, stop loss %, trailing stop, auto-rearm, take profit, trigger offset
- FURY mode: RSI thresholds, max leverage, risk % per trade, stop loss type
- WHALE mode: top-N traders, min notional, watched assets
- Most recent bot event (e.g. HEDGE OPENED @ $2,086.30)

Stopped bots and historical positions are intentionally omitted — only live, active bots are shown.

### Alert events (push notifications)

The bot sends instant alerts for:
- `HEDGE OPENED` — short hedge entry
- `SL HIT` — stop loss executed
- `TP HIT` — take profit executed
- `TRAILING STOP` — trailing stop closed position
- `FURY ENTRY` — FURY RSI bot opened a trade
- `FURY SL / FURY TP` — FURY trade closed
- `FURY CIRCUIT BREAKER` — FURY bot paused (daily drawdown or consecutive losses)
- `ERROR` — bot error requiring attention
- `LP REMOVED / LP BURNED` — LP position events

### Multi-wallet support

One Telegram account can link multiple wallets. Each wallet fires alerts independently. Example:
```
/start 0xWalletA   ← link first wallet
/start 0xWalletB   ← link second wallet
/status            ← shows bots from both wallets
/unlink 0xWalletA  ← remove only wallet A
```

### Privacy

VIZNAGO stores only: wallet address (public on-chain) + Telegram chat ID (a number). No name, email, phone number, or username is ever stored.
