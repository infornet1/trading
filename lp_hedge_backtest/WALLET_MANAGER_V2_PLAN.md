# Wallet Manager v2 — Enhancement Plan
**Page:** `landing/wallet/index.html`  
**Status:** Planning — not started  
**Created:** 2026-04-10  

---

## Objective

Transform the current static Wallet Guardian page into a fully live, authenticated wallet management interface. Single source of truth for all LP ↔ HL wallet relationships. Full CRUD for HL wallet address and API private key.

---

## Stage Roadmap

| Stage | Scope | Status |
|-------|-------|--------|
| **Stage 1** | Build Wallet Manager v2 — auth, live cards, CRUD, lock on active bots | 🔲 Pending |
| **Stage 2** | Decommission credential inputs from LP Defensor Bot Card — replace with wizard popup | 🔲 Pending (after Stage 1) |
| **Stage 3** | Deep link `?focus=tokenId` — Wallet Manager card auto-expands on arrival | 🔲 Future |

---

## Stage 1 — Full Specification

### Authentication Gate

- Same JWT flow as LP Defensor (`POST /auth/...`)
- If not signed in:
  ```
  🔐  Connect your wallet to manage your protection wallets
      [ Sign in with Wallet ]
  ```
- Once signed in, bot configs load from `GET /bots`
- Signed-in state persists via same `saas.jwt` mechanism

---

### LP ↔ HL Relationship Cards

One card per bot config returned by `GET /bots`.

#### Card — Bot INACTIVE (editable)
```
┌─────────────────────────────────────────────────┐
│  NFT #5413901  ·  WETH/USDC  ·  0.05%  ·  ARB  │
│  LP Wallet:  0xB901326FBd97dc737F5A9D289ECDA…   │
│                         ⬇ protected by           │
│  HL Wallet:  0xeF0DDF18382538F31dcfa0AF40B47…   │
│  HL Balance: $39.80  (green ≥$20 / amber <$20 / │
│              red ≤$0 / — if not set)             │
│  API Key:    ••••••••••••  (set)                 │
│                                                  │
│  [ ✏ Edit ]    [ 🗑 Remove ]                     │
└─────────────────────────────────────────────────┘
```

#### Card — Bot ACTIVE / RUNNING (locked)
```
┌─────────────────────────────────────────────────┐
│  NFT #5413901  ·  WETH/USDC  ·  0.05%  ·  ARB  │
│  🟢 RUNNING                                      │
│  LP Wallet:  0xB901326FBd97dc737F5A9D289ECDA…   │
│                         ⬇ protected by           │
│  HL Wallet:  0xeF0DDF18382538F31dcfa0AF40B47…   │
│  HL Balance: $39.80                              │
│  API Key:    ••••••••••••  (set)                 │
│                                                  │
│  🔒 Stop the bot in LP Defensor to edit          │
└─────────────────────────────────────────────────┘
```

#### Card — Bot ACTIVE but CRASHED (locked)
```
│  🔴 BOT CAÍDO  (active=true, process dead)       │
│  🔒 Stop the bot in LP Defensor to edit          │
```

#### Card — No HL wallet linked
```
┌─────────────────────────────────────────────────┐
│  NFT #7291044  ·  WBTC/USDC  ·  0.3%  ·  ARB   │
│  LP Wallet:  0xB901326FBd97dc737F5A9D289ECDA…   │
│                                                  │
│  ⚠ No HL protection linked                      │
│                                                  │
│  [ ➕ Link HL Wallet ]                           │
└─────────────────────────────────────────────────┘
```

---

### HL Balance Color Thresholds (matching Admin panel)

| Value | Color | Meaning |
|-------|-------|---------|
| ≥ $20 | 🟢 Green | Healthy hedge capital |
| $1 – $19.99 | 🟡 Amber | Low — consider topping up |
| ≤ $0 | 🔴 Red | Empty — bot cannot hedge |
| null / not set | — | No wallet configured |

---

### Edit Flow (inactive bot only)

Clicking **✏ Edit** expands an inline form on the card — no modal, no navigation:

```
  HL Wallet Address  [ 0xeF0DDF18382538F31dcfa0… ]
  API Private Key    [ _________________________ ]  👁
                       Leave blank to keep current
  [ Save ]  [ Cancel ]
```

- Address pre-filled with current value
- Key always blank (write-only) — placeholder: *"Leave blank to keep current"*
- 👁 toggle shows/hides the key field while typing
- Save calls `PUT /bots/{id}` with only changed fields
- On success: form collapses, card refreshes, HL balance re-fetches
- On error (409 = bot became active): show inline error, re-lock card

---

### Link Flow (no wallet configured)

Clicking **➕ Link HL Wallet** expands inline form (same fields as Edit):

```
  HL Wallet Address  [ 0x…_______________________ ]
  API Private Key    [ 0x…_______________________ ]  👁
  [ Save ]  [ Cancel ]
```

- Both fields required
- Calls `PUT /bots/{id}` with `hl_wallet_addr` + `hl_api_key`

---

### Remove Flow (inactive bot only)

Clicking **🗑 Remove** shows a small inline confirm strip — no modal:

```
  Remove HL wallet from this position?
  [ Yes, remove ]  [ Cancel ]
```

- Calls `DELETE /bots/hl-wallet?wallet=...`
- On success: card updates to "No HL protection linked" state

---

### Lock Rules (Option A — hard block)

| `bot.active` | UI state |
|-------------|----------|
| `false` | ✏ Edit + 🗑 Remove buttons visible and enabled |
| `true` (running or crashed) | Buttons replaced by 🔒 lock hint |

- Lock hint text: *"Stop the bot in LP Defensor to edit"*
- No disabled buttons — lock hint replaces them entirely
- Backend `PUT /bots/{id}` also enforces this (409 if `cfg.active = true`) as safety net

---

### Auto-refresh Interaction (reviewed & confirmed safe)

- Wallet Manager v2 is a **separate page** — no auto-refresh timer from LP Defensor
- Has its own manual **⟳ Refresh** button per card (re-fetches HL balance)
- No stale state conflict with LP Defensor while both are open simultaneously
  - LP Defensor credential inputs still exist in Stage 1 (decommissioned in Stage 2)
  - Last writer wins on `PUT /bots/{id}` — both check `active=false` first

---

## Stage 2 — LP Defensor Decommission (after Stage 1)

### What gets removed from LP Defensor Bot Card protection drawer

- HL Wallet Address input field + dropdown selector
- API Private Key input field
- Wallet remove (🗑) button inside drawer
- "Activar Protección" credential-saving logic (start bot flow simplified to params only)

### What stays in LP Defensor Bot Card

- Toggle header: `▶ Protección  HL: 0xeF0D…cf2f  📋  🟢 ACTIVO`
- HL Balance bar inside drawer
- Bot mode, trigger %, leverage, SL/TP, trailing stop, auto-rearm
- Stop Bot button

### Replacement — Wallet Wizard Popup (Option B)

Clicking the `HL: 0xeF0D…cf2f` chip or a new `⚙` icon on the toggle header opens a lightweight popup:

**Bot RUNNING state:**
```
┌──────────────────────────────────────────────┐
│  🛡️  HL Protection Wallet                    │
│                                              │
│  0xeF0DDF18382538F31dcfa0AF40B47eE8c5A2cf2f  │
│  💰 HL Balance: $39.80                       │
│                                              │
│  🟢 Bot is running — credentials locked      │
│                                              │
│  [ ↗ Open Wallet Manager ]                  │
└──────────────────────────────────────────────┘
```

**Bot INACTIVE state:**
```
┌──────────────────────────────────────────────┐
│  🛡️  HL Protection Wallet                    │
│                                              │
│  0xeF0DDF18382538F31dcfa0AF40B47eE8c5A2cf2f  │
│  💰 HL Balance: $39.80                       │
│                                              │
│  [ ↗ Open Wallet Manager ]  [ ✏ Edit here ] │
└──────────────────────────────────────────────┘
```

- "Edit here" navigates to Wallet Manager with `?focus=5413901` URL param
- Popup is a fixed overlay — auto-refresh rebuilds card behind it invisibly (safe, confirmed)
- Closing popup returns user to dashboard with card in default state (acceptable, Option A)

---

## Stage 3 — Deep Link (future)

- `landing/wallet/index.html?focus=5413901` auto-expands the matching card on load
- Enables direct navigation from LP Defensor wizard popup to the right card
- No backend changes needed — pure frontend URL param handling

---

## API Surface — Zero New Endpoints Required (Stage 1)

| Action | Endpoint | Exists |
|--------|----------|--------|
| Load cards | `GET /bots` | ✅ |
| JWT sign-in | `POST /auth/...` | ✅ |
| HL balance | `GET /bots/hl-balance?wallet=` | ✅ |
| Link / Edit wallet | `PUT /bots/{id}` | ✅ |
| Remove wallet | `DELETE /bots/hl-wallet` | ✅ |
| Bot running state | `bot.active` from GET /bots | ✅ |

---

## Key Design Decisions Locked In

| Decision | Choice | Reason |
|----------|--------|--------|
| Lock on active bot | Hard block (Option A) | Mirrors backend 409, no silent inconsistency |
| Auto-refresh conflict | Do nothing (Option A) | Popup is fixed overlay, card reset behind it is invisible |
| Edit flow | Inline expand, no modal | Keeps context, no navigation loss |
| Remove flow | Inline confirm strip, no modal | Lightweight, consistent with edit |
| Stage 2 popup | Option B (wizard popup) | Context-first, shows balance before navigating away |
| Stage 2 refresh | Stage 1 ships first, decommission after | Safe incremental rollout |

---

## Risks

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| User edits wallet in LP Defensor + Wallet Manager simultaneously | Low | Both blocked by `active=true` check; last writer wins when inactive |
| HL balance stale if user leaves page open for hours | Low | Per-card ⟳ Refresh button; balance re-fetches on any save |
| `PUT /bots/{id}` 409 race (bot starts between lock check and save) | Very low | Backend returns 409 — show inline error "Bot started, reload to see lock" |
| Stage 2 decommission breaks existing activation flows | Medium | Stage 1 fully tested first; Stage 2 is a separate PR |

---

## Notes

- **2026-04-10:** Plan created. All three stages reviewed and approved in principle.
- Auto-refresh interaction analyzed — confirmed safe (popup is fixed overlay outside grid DOM).
- `active` vs `running` distinction noted: lock triggers on `active=true` which matches `PUT /bots/{id}` server-side guard exactly.
- Admin panel HL balance color thresholds adopted (≥$20 green, <$20 amber, ≤$0 red).
- Stage 2 decommission explicitly deferred until Stage 1 is fully live and tested.
