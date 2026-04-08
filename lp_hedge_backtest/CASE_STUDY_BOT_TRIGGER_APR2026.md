# VIZNIAGO DeFi Bot — Case Study: Live Trigger Event
**Wallet:** `0xe84f181541072c14a6a28224a33b078a44cc343c`
**Date:** April 2, 2026
**Strategy:** LP Hedge — Uniswap v3 (Arbitrum) + Hyperliquid SHORT

---

## What is VIZNIAGO?

VIZNIAGO is an automated DeFi strategy combining two revenue streams:

1. **Passive LP Yield** — Concentrated liquidity on Uniswap v3 (Arbitrum), earning trading fees from the ETH/USDC pool
2. **Automated Hedge Protection** — When ETH price drops, the bot automatically opens a SHORT on Hyperliquid perps, offsetting impermanent loss from the LP

```
Market goes DOWN  →  SHORT hedge profits  →  offsets LP impermanent loss
Market goes UP    →  Short SL exits fast  →  LP earns all the upside + fees
Market sideways   →  LP collects fees     →  hedge dormant (no cost)
```

---

## Live Trigger Event — April 1–2, 2026

### Market Context

ETH was trading quietly at **$2,140–$2,157** through midnight. At **01:00 UTC April 2**, a sharp sell-off began — $65 drop in a single hour. The bot detected the breakdown and automatically fired a SHORT hedge.

### Price Timeline

| Time (UTC) | ETH Price | Event |
|---|---|---|
| Apr 1, 23:00 | $2,140 | Quiet — no signal |
| Apr 2, 01:00 | $2,155 → $2,090 | Sharp drop begins (-$65 in 1h) |
| Apr 2, **02:09:14** | **$2,086.30** | **BOT TRIGGERS — SHORT opened automatically** |
| Apr 2, 03:00 | $2,073 → $2,056 | Continued sell-off |
| Apr 2, 12:49 | **$2,027.30** | Snapshot price |

ETH intraday range on April 2: **$2,024 – $2,158** ($134 total swing)

---

## Hedge Trade Results

| Metric | Value |
|---|---|
| Trade opened | 2026-04-02 at 02:09:14 UTC |
| Direction | SHORT ETH |
| Entry price | **$2,086.30** |
| Size | 0.1233 ETH (~$250 notional) |
| Mark price (snapshot) | **$2,027.30** |
| ETH decline captured | **-$59.00 (-2.83%)** |
| Unrealized PnL | +$7.27 USDC |
| Entry fee paid | -$0.12 USDC |
| **Net PnL** | **+$7.16 USDC** |
| **Return on margin** | **+29.09%** |
| Leverage | 10x cross |
| Margin deployed | $25.01 USDC |
| Funding income | +$0.02 USDC (longs paying shorts) |

### Risk Profile

| Metric | Value | Assessment |
|---|---|---|
| Liquidation price | $2,281.26 | ETH would need to rally **+12.5%** from entry |
| Distance to liquidation | +$194.96 | Comfortable buffer maintained |
| Status at snapshot | Open, profitable | No stop-loss triggered |

---

## En Español — Protección Activada

ETH cotizaba tranquilo entre **$2,140–$2,157** hasta medianoche. A la **01:00 UTC** del 2 de abril comenzó una caída brusca:

| Hora (UTC) | Precio ETH | Evento |
|---|---|---|
| Abr 1, 23:00 | $2,140 | Sin señal — mercado quieto |
| Abr 2, 01:00 | $2,155 → $2,090 | **Caída fuerte comienza** (-$65 en 1 hora) |
| Abr 2, **02:09:14** | **$2,086.30** | **BOT ACTIVA PROTECCIÓN — SHORT abierto** |
| Abr 2, 03:00 | $2,073 → $2,056 | Continuación bajista |
| Abr 2, 12:49 | **$2,027.30** | Precio al momento del reporte |

| Métrica | Valor |
|---|---|
| Dirección | SHORT ETH |
| Precio de entrada | **$2,086.30** |
| Precio actual | **$2,027.30** |
| Caída capturada | **-$59 (-2.83%)** |
| **Ganancia neta** | **+$7.16 USDC** |
| **Retorno sobre margen** | **+29.09%** |
| Precio de liquidación | $2,281 — ETH tendría que subir +12.5% para llegar ahí |

El bot detectó la ruptura, abrió la protección automáticamente en segundos, y capturó la mayor parte del movimiento bajista — sin intervención manual.

---

## Bot Execution Quality

- **Timing:** Entered at $2,086 during the second hour of the sell-off, well before the continuation leg to $2,024 — capturing the bulk of the move
- **Precision:** Single clean market fill at 02:09:14 UTC, no partial fills, no slippage issues
- **Risk management:** 10x leverage with 12.5% liquidation buffer, trailing stop-loss active to lock in profits
- **Autonomy:** Zero manual intervention required — bot monitored, detected, and executed in real time

---

## Infrastructure

| Component | Detail |
|---|---|
| LP Network | Arbitrum (L2 — low gas costs) |
| Perps Venue | Hyperliquid (top-5 DEX perps, fully on-chain) |
| Monitoring interval | Every 30 seconds, 24/7 |
| Alerts | Email on every trigger, SL, TP, and error event |
| Custody model | Non-custodial — bot uses API key only, cannot withdraw funds |
| Dashboard | Real-time web UI with bot status, LP value, margin calculator |

---

## Why Support VIZNIAGO?

- **Proven automation:** Bot triggered, entered, and managed risk without human input during a live market event
- **Dual revenue model:** LP fees (passive) + hedge profits (active protection) — both sides of the market covered
- **Non-custodial & transparent:** All positions verifiable on-chain at any time
- **SaaS roadmap:** Platform built to onboard multiple users — one dashboard, multiple pools, subscription model
- **Early stage:** Opportunity to support the project at ground level and shape its direction

---

## Follow-Up

For questions, access to the live dashboard, or to discuss supporting the project:

- Dashboard: [VIZNIAGO Trading Dashboard](https://dev.ueipab.edu.ve/trading/lp-hedge/dashboard/)
- Wallet to verify: `0xe84f181541072c14a6a28224a33b078a44cc343c`
- All trades verifiable on [Arbiscan](https://arbiscan.io/address/0xe84f181541072c14a6a28224a33b078a44cc343c) and [Hyperliquid](https://app.hyperliquid.xyz/)

---

*This document is for informational purposes only. DeFi strategies carry risk. Past performance of individual events does not guarantee future results.*
