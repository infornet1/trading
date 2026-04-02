# VIZNAGO.finance — DevOps & Zero-Downtime Infrastructure

> Zero-downtime deployment strategy for 24/7 crypto bot SaaS.
> Critical requirement: crypto markets never sleep — no maintenance windows.
> Last updated: 2026-04-01

---

## Core Principle

```
Current (single droplet):
    upgrade → restart → 30-60s downtime → bot misses price event → IL not hedged

Target:
    upgrade → bots keep running → users see nothing → done silently
```

**Key insight:** Separate the API (stateless, restartable) from the bots (stateful, never restart mid-trade).

---

## Production Architecture

```
                    Cloudflare
                    (always on, absorbs traffic during transitions)
                        │
                   DO Load Balancer  ~$12/mo
                  ┌─────┴─────┐
                  │           │
            App Droplet A  App Droplet B    ~$24/mo each
            (stateless)    (stateless)
            nginx+API      nginx+API
                  └─────┬─────┘
                        │ DO private network
                        │
                  Worker Droplet            ~$48/mo
                  BotManager
                  live_hedge_bot × N
                  live_fury_bot × N
                  live_whale_bot × N
                        │
                  Managed PostgreSQL        ~$15/mo
                        │
                  DO Spaces (backups)       ~$5/mo
```

---

## Upgrade Strategies by Component

### Frontend / Static Files (nginx)
- Hot reload: `nginx -s reload` — zero downtime, always
- Files synced via `rsync` from GitHub Actions
- Cloudflare cache purge via API after deploy

### API Changes (FastAPI)
Rolling deploy across 2 App Droplets:
```
1. Remove App B from Load Balancer rotation
2. Deploy + restart App B (users all go to App A)
3. Health check App B → passes
4. Put App B back in rotation
5. Remove App A → deploy + restart App A
6. Put App A back in rotation
Total user impact: zero
```

### Bot Logic Changes (live_hedge_bot.py / live_fury_bot.py)
Graceful drain strategy:
```
1. BotManager stops accepting new bot starts
2. Wait for all active bots to reach IDLE state (no open position)
3. Deploy new bot code to Worker Droplet
4. BotManager restarts bots
Typical wait: seconds to a few minutes (between trades)
User impact: bot paused briefly only between trades, never mid-hedge
```

### Database Migrations (schema changes)
Rules:
- Always use **backward-compatible migrations** (add nullable column first, never DROP/RENAME on live DB)
- Run migration → deploy new code → backfill old data
- DO Managed PG minor upgrades: transparent
- DO Managed PG major upgrades: automatic failover (<30s)

---

## Load Balancer Setup (Digital Ocean)

### How it works
DO Load Balancer sits in front of both App Droplets and:
- Routes incoming HTTPS traffic to whichever droplet is healthy
- Runs health checks every 10s (`GET /health` → expects 200)
- If App A fails health check → all traffic goes to App B automatically
- If App A recovers → traffic resumes to both

### App Droplet synchronization
Both droplets run **identical code** — kept in sync by CI/CD:
```
GitHub Actions deploys to App A and App B sequentially (rolling)
No real-time file mirroring needed — both pull from same git repo
```

### Shared state
Both App Droplets connect to the **same Managed PostgreSQL** — this is how they share state.
No session stickiness needed: FastAPI is stateless, JWT tokens are validated against DB.

### Health check endpoint
```python
# api/routers/health.py
@router.get("/health")
async def health():
    return {"status": "ok"}
```
Load Balancer hits this every 10s. If it fails 3x → droplet removed from rotation automatically.

---

## CI/CD Pipeline (Silent Upgrades)

```
Developer pushes to main
         │
         ▼
GitHub Actions detects what changed:
  │
  ├── landing/* only
  │     └── rsync files to App A + App B
  │         nginx -s reload (both)
  │         Cloudflare cache purge
  │         → Zero downtime, ~10 seconds total
  │
  ├── api/* changed
  │     └── Rolling restart: App B first, then App A
  │         Load Balancer handles traffic during each restart
  │         → Zero downtime, ~2 minutes total
  │
  ├── bot/* changed
  │     └── Graceful drain: wait for bots IDLE
  │         Deploy to Worker Droplet
  │         BotManager restarts bots
  │         → Near-zero downtime, seconds to minutes
  │
  └── DB migration
        └── Run Alembic migration (backward-compatible)
            Deploy API code
            → Zero downtime if migration is additive
```

Admin receives Telegram/email notification on every deploy:
```
✅ Deploy complete — api/* — App A+B rolling — 1m 42s — no errors
```

---

## Cloudflare Role in Zero Downtime

| Feature | Benefit |
|---|---|
| **Always Online** | Serves cached pages if droplet briefly unreachable |
| **Health checks** | Detects issues before users do |
| **DDoS protection** | Absorbs traffic spikes automatically |
| **Cache rules** | Static assets served from edge — droplet restart invisible |
| **SSL termination** | Handles HTTPS — droplets only need HTTP internally |

---

## Cost Comparison

| Setup | Monthly | Downtime Risk |
|---|---|---|
| Beta (1 droplet, no LB) | ~$90 | Every deploy = potential 30-60s downtime |
| Zero-downtime (2 app + worker + LB) | ~$145 | Silent upgrades always |
| Difference | **+$55/mo** | No maintenance windows ever |

---

## Launch Strategy

**Start:** Beta on minimum setup (1 droplet) but code correctly from day 1:
1. API stateless — no local session state, everything in DB
2. BotManager graceful shutdown — wait for IDLE before stopping
3. Backward-compatible DB migrations — discipline from first migration
4. `/health` endpoint — ready for Load Balancer from day 1

**Upgrade trigger:** Add second App Droplet + Load Balancer when first 10 paying users onboard.
Zero code changes needed — architecture was already right.

---

## Scaling Escalation Path

```
Beta (0-10 users)
└── 1 App Droplet + 1 Worker + Managed PG
    ~$90/mo

Early traction (10-50 users)
└── + Load Balancer + second App Droplet
    ~$145/mo

Growth (50-200 users)
└── + Upgrade Worker (4 vCPU / 8GB)
    ~$175/mo

Scale (200-500 users)
└── + Redis cache + RPC upgrade + Read replica PG
    ~$250/mo

Enterprise (500+ users / 1000+ bots)
└── Migrate to Docker + Kubernetes
    ~$400+/mo (re-evaluate at this stage)
```

---

## Key Rules (Never Break These)

| Rule | Why |
|---|---|
| Never restart Worker during open bot positions | Bot mid-hedge = unprotected LP |
| Always drain bots to IDLE before Worker deploy | Graceful shutdown prevents orphan positions |
| Never DROP/RENAME columns on live DB | Breaks running API instances mid-deploy |
| Always deploy DB migration before new API code | Old code must work with new schema |
| Never push directly to main | All deploys via GitHub Actions only |
| PROD .env never in git | Private keys, HL API keys, DB URL |

---

*Architecture designed for 24/7 crypto markets — no maintenance windows, no user notifications needed.*
