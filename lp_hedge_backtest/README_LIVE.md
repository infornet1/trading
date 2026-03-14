# 🚀 LP + Perps Hedge: Live Bot Guide

This directory contains the scripts to run the "Bot Aragan" (Hedge Only) strategy in real-time.

## 📋 Setup Instructions

### 1. Configure Credentials
Copy the `.env.example` file to `.env` and fill in your Hyperliquid private key and address.

```bash
cd lp_hedge_backtest
cp .env.example .env
# Edit .env and paste your credentials
```

**⚠️ SECURITY WARNING:** Never share your `.env` file or private key with anyone. The bot only needs "Trade" permissions on Hyperliquid.

### 2. Test Hyperliquid API
Before running the bot, verify your account balance and API connection.

```bash
source venv/bin/activate
python3 test_hyperliquid_api.py
```

### 3. Start the Live Hedge Bot
This bot will monitor your Uniswap NFT #5364575 and open a short on Hyperliquid if the price drops below $1,920.

```bash
python3 live_hedge_bot.py
```

## 🛠️ Bot Logic (Aragan Mode)
- **NFT Monitor:** Fetches the range ($1,919.89 - $2,232.81) directly from Arbitrum.
- **Trigger:** If price hits **$1,910.29** (0.5% below range floor) → Open **SHORT** (10x).
- **Take Profit:** If price returns to **$1,919.89** → Close **SHORT**.

## 📊 Monitoring
The bot will output its status every 30 seconds to the console:
`[HH:MM:SS] ETH: $2084.50 | 🟢 IN RANGE | ⚪ HEDGE OFF`

To stop the bot, press `Ctrl+C`.
