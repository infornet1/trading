# VIZNAGO.finance — Production Infrastructure Plan

> Executive overview for Digital Ocean deployment once membership and treasury wallets are live.
> Last updated: 2026-04-01

---

## Architecture at a Glance

```
GitHub (source)
     │
     │  CI/CD (GitHub Actions)
     ▼
┌─────────────────────────────────────────┐
│          DO Load Balancer  ~$12/mo      │
│         (SSL termination, nginx)        │
└────────────┬───────────────┬────────────┘
             │               │
     ┌───────▼──────┐  ┌─────▼────────┐
     │  App Droplet │  │  App Droplet │  (2x for high availability)
     │  API + nginx │  │  API + nginx │  ~$24/mo each
     │  FastAPI     │  │  FastAPI     │
     └───────┬──────┘  └──────────────┘
             │
     ┌───────▼──────────────┐
     │   Worker Droplet     │  ~$48/mo (CPU-optimized)
     │   BotManager         │
     │   live_hedge_bot × N │
     │   live_fury_bot × N  │
     │   live_whale_bot × N │
     └───────┬──────────────┘
             │
     ┌───────▼──────────────┐
     │  Managed PostgreSQL  │  ~$15/mo
     │  (replaces SQLite)   │
     │  + automated backups │
     └──────────────────────┘

     ┌──────────────────────┐
     │  DO Spaces (S3)      │  ~$5/mo
     │  Logs, DB snapshots, │
     │  trade history export│
     └──────────────────────┘
```

---

## Droplet Breakdown

| Role | Spec | Purpose | Est. Cost |
|---|---|---|---|
| **Load Balancer** | DO managed | SSL termination, routing, health checks | $12/mo |
| **App × 2** | 2 vCPU / 4 GB | FastAPI API, nginx, static frontend | $24/mo × 2 |
| **Worker** | 4 vCPU / 8 GB | BotManager + all bot subprocesses (one per user pool) | $48/mo |
| **Managed PostgreSQL** | 1 vCPU / 1 GB | Replaces SQLite, automated backups, failover | $15/mo |
| **DO Spaces** | 250 GB | Log archives, DB snapshots, trade exports | $5/mo |

---

## Docker Strategy

```
viznago-api/      ← FastAPI app container
viznago-worker/   ← BotManager + bot subprocess launcher
viznago-nginx/    ← Reverse proxy + static frontend files
postgres/         ← Managed by DO (no container needed)
```

- Docker Compose on each droplet for local orchestration
- **No Kubernetes yet** — overkill for early SaaS, revisit at 500+ concurrent bots
- Worker droplet runs containers with `--restart=always` so bots survive API deploys
- Container images stored in DO Container Registry (~$5/mo)

---

## GitHub / CI-CD Pipeline

```
Push to main branch
    │
    ├── GitHub Actions: run tests
    ├── Build Docker images → push to DO Container Registry
    ├── SSH into App droplets → pull + rolling restart (zero-downtime)
    └── SSH into Worker → pull + restart BotManager
         ⚠ Only after confirming all bots IDLE (graceful drain)
```

**GitHub Secrets (never in repo):**
- `DO_API_TOKEN`
- `ANTHROPIC_API_KEY`
- `DB_URL`
- `ADMIN_WALLETS`
- `HL_API_KEY` (per user, stored encrypted in DB)

**Branch strategy:**
- `main` → production
- `dev` → optional staging droplet (~$12/mo basic droplet)

---

## SSH / Access Model

| Who | Access | Method |
|---|---|---|
| Admin (owner) | All droplets | SSH key pair + DO Firewall IP whitelist |
| GitHub Actions | App + Worker droplets | Deploy key (scoped per repo, write-only) |
| App → Worker | Internal calls | DO private networking (no public exposure) |
| App → Database | Internal only | DO managed DB private connection string |
| End users | HTTPS only | Via Load Balancer — never direct droplet access |

---

## Treasury & Membership Wallet Layer

```
User pays
    │
    ├── Stripe (credit card) → webhook → FastAPI → unlock plan in DB
    └── USDC on-chain (Arbitrum/Base) → treasury wallet monitor → unlock plan in DB

Treasury Wallet
    └── EOA or smart contract on Arbitrum / Base
    └── Lightweight on-chain listener (runs on App droplet, minimal resources)
    └── Monitors incoming USDC transfers → maps to user address → activates plan
```

- Platform never takes custody of user LP funds or Hyperliquid balances
- Treasury wallet only receives subscription payments
- HL API keys stored encrypted in PostgreSQL (trade-only, no withdrawal permission)

---

## Cost Summary

| Item | Monthly |
|---|---|
| DO Load Balancer | $12 |
| App Droplets × 2 | $48 |
| Worker Droplet | $48 |
| Managed PostgreSQL | $15 |
| DO Spaces | $5 |
| DO Container Registry | $5 |
| **Total Digital Ocean** | **~$133** |
| Anthropic API (VIZBOT) | ~$10–20 |
| SendGrid (email notifications) | $20 |
| Domain (viznago.finance) | ~$2 |
| **Grand Total** | **~$165–175/mo** |

---

## Break-even vs Membership Revenue

| Scenario | Subscribers | MRR | Infra Cost | Margin |
|---|---|---|---|---|
| Break-even | 9 Starter or 4 Pro | ~$175 | $175 | 0% |
| Early traction | 30 Starter + 10 Pro | $1,060 | $175 | 83% |
| Year 1 target | 100 Starter + 40 Pro + 5 Enterprise | ~$4,855 | $175 | 96% |

---

## What to Defer (Not Needed at Launch)

| Item | Defer Until |
|---|---|
| Kubernetes / EKS | 1,000+ concurrent bots |
| Redis (distributed cache) | Rate limiting needs shared state across App droplets |
| CDN (Cloudflare / DO CDN) | Frontend traffic justifies it |
| Dedicated staging environment | First paying customers onboarded |
| Multi-region deployment | Regulatory or latency requirements |
| Tax reporting export | Enterprise tier launch |

---

## Current Dev Environment (Pre-Production)

For reference — what is running today on the dev server:

| Component | Current Setup |
|---|---|
| Server | Single VPS at `dev.ueipab.edu.ve` |
| API | `viznago_api.service` (systemd, FastAPI + uvicorn) |
| Bot 1 | `live_hedge_bot.service` (NFT #5364575) |
| Bot 2 | `live_hedge_bot_2.service` (NFT #5381818) |
| DB | SQLite at `api/viznago.db` |
| Frontend | Nginx serving `landing/` static files |
| Domain path | `/trading/lp-hedge/` |

Migration to production requires: SQLite → PostgreSQL, systemd services → Docker + BotManager, single server → multi-droplet topology above.

---

*Preliminary plan — costs subject to change based on user growth and DO pricing at launch date.*
