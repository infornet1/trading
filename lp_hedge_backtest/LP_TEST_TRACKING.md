# LP Hedge Bot — Live Test Tracking
**Network:** Arbitrum One  
**Bot:** FURY / LP Hedge  
**Start Date:** 2026-04-09  
**Objective:** Generate real evidence that the LP hedge bot works as expected with live wallets and minimal capital.

---

## Wallets

| Role | Address | Note |
|------|---------|------|
| LP Wallet | `0xB901326FBd97dc737F5A9D289ECDA1806705Bf7D` | Holds LP position capital |
| Protection Wallet | `0xeF0DDF18382538F31dcfa0AF40B47eE8c5A2cf2f` | Holds hedge/short capital |

---

## Initial Wallet Snapshot (2026-04-09)

### LP Wallet — `0xB901...Bf7D`
| Asset | Raw | Human Amount | USD (~$2,214/ETH) |
|-------|-----|--------------|-------------------|
| ETH | 9,029,716,220,950,337 wei | 0.009030 ETH | ~$20.00 |
| USDC | 100,000,000 (6 dec) | 100.00 USDC | ~$100.00 |
| **Total** | | | **~$120.00** |

### Protection Wallet — `0xeF0D...f2f`
| Asset | Raw | Human Amount | USD |
|-------|-----|--------------|-----|
| ETH | 571,792,856,000 wei | ~0.000000572 ETH | dust |
| USDC | 80,000,199 (6 dec) | 80.00 USDC | ~$80.00 |
| WBTC | 32,656 (8 dec) | 0.00032656 WBTC | ~$27.20 |
| UNI-V3 NFT | 1 | 1 existing LP position | ⚠️ Check range |
| **Total** | | | **~$107.20** |

> ⚠️ **Action Required:** Protection wallet holds an existing Uniswap V3 NFT position. Verify if it is in-range, what pair it is, and whether it should be closed before or kept alongside this test.

**Grand Total Available:** ~$235.79

---

## LP Position Design

### Constraints
- ETH available for LP: **0.009030 ETH** (~$20.00) — this is the binding constraint
- Must keep ETH reserve for gas on Arbitrum: **~0.002 ETH**
- Deployable ETH: **~0.007 ETH** (~$15.50)
- Uniswap V3 pair: **ETH/USDC — 0.05% fee tier** (Arbitrum One)
- Reference price at setup: **~$2,214/ETH** (confirmed via Blockscout on-chain rate)

### Recommended Range: Uniswap Default ✅

| Parameter | Value |
|-----------|-------|
| Lower bound | **$2,073.5571** |
| Upper bound | **$2,347.285** |
| Width | ~13.3% |
| ±% from center | ±6.4% |
| Center | ~$2,210 |
| In-range at open? | ✅ Yes — ETH at ~$2,214, near center |
| ETH to deposit | **0.007 ETH** (~$15.50) |
| USDC to deposit | **~17-18 USDC** |
| Total LP capital | **~$33** |
| USDC reserve (LP wallet) | **~$82** |
| ETH reserve (gas) | **0.002 ETH** |

> **Rationale:** Uniswap's suggested range is centered on actual current price. Position is in-range immediately, generating fees and allowing the bot to observe real delta. A ±6.4% move takes ETH out of range (~$150 move), creating a natural out-of-range test scenario within days.

**OOR thresholds to watch:**
- Below $2,073 → position becomes 100% ETH, fees stop → bot should detect and respond
- Above $2,347 → position becomes 100% USDC, fees stop → bot should detect and respond

### Position Setup Steps
- [ ] Verify / close existing UNI-V3 NFT in protection wallet (or document its state)
- [ ] Fund LP wallet with additional ETH for gas if needed (currently tight)
- [ ] Open UNI-V3 position from LP wallet via Uniswap interface or bot
- [ ] Record NFT token ID once minted
- [ ] Configure bot with LP wallet address + position token ID
- [ ] Configure protection wallet as hedge executor
- [ ] Start bot in paper-first mode if available, then live

---

## Hedge Capital (Protection Wallet)

| Available | Amount | USD |
|-----------|--------|-----|
| USDC | 80.00 | ~$80 |
| WBTC | 0.00032656 | ~$27 |
| ETH gas | ~0 | needs top-up |

> ⚠️ Protection wallet has **no ETH for gas**. Add a small amount (~0.005 ETH) to enable hedge transactions on Arbitrum.

**Suggested hedge allocation:**
- Use **50 USDC** as active hedge capital (short ETH via perp or hedge mechanism)
- Keep 30 USDC as buffer/reserve
- WBTC: leave untouched unless needed

---

## Success Criteria

| # | Criterion | Pass |
|---|-----------|------|
| 1 | LP position opens successfully, in-range | ☐ |
| 2 | Bot detects LP position and starts monitoring | ☐ |
| 3 | Bot logs delta exposure correctly | ☐ |
| 4 | Hedge trade executes when delta threshold breached | ☐ |
| 5 | Hedge reduces net delta toward zero | ☐ |
| 6 | Bot handles out-of-range scenario without crashing | ☐ |
| 7 | P&L tracking (fees earned vs hedge cost) is logged | ☐ |
| 8 | 24h+ continuous run without critical error | ☐ |

---

## Test Log

| Date | ETH Price | LP Range Status | LP Value | Hedge Status | Fees Earned | Notes |
|------|-----------|-----------------|----------|--------------|-------------|-------|
| 2026-04-09 | ~$2,214 | — (not open yet) | — | — | — | Initial snapshot, wallets verified. Range confirmed: $2,073.56–$2,347.29 |
| | | | | | | |
| | | | | | | |

---

## Key Decisions & Notes

- **2026-04-09:** Test designed. Minimum capital approach chosen (~$44 LP, ~$50 hedge) to validate bot logic before scaling.
- Both wallets confirmed on Arbitrum One via Blockscout explorer.
- Protection wallet already has 1 UNI-V3 NFT — must investigate before proceeding.
- **2026-04-09 (platform):** Diagnosed live log wipe-on-refresh issue. Root cause: raw bot stdout lines (`ETH $X | IN | IDLE`) are streamed via WebSocket only — they are NOT written to `bot_events` DB. Only structured `[EVENT]` lines (started, hedge_opened, tp_hit, etc.) persist. Fix implemented: localStorage cache with 72h TTL stores raw lines per bot on the client; cache is restored on every page load before WS reconnects. Events API also extended with `?hours=N` filter. Clear button added to log terminal.
- **2026-04-10 (platform):** Dashboard UX session — bot card protection section simplified: label changed from "▶ Activar Protección" to "Protección" (ES/EN i18n). Added wallet address chip on the toggle header row showing `HL: 0xeF0D…cf2f` between the label and the ACTIVO badge. Chip updates live via `_configuredWallets` map — populated from DB on load, updated on dropdown selection change, activation, and wallet removal, so it displays correctly even when `hl_wallet_addr` is null in the bot config. Added inline copy button (📋 → ✓ flash) next to chip so users can copy the full wallet address without opening the drawer. Added `margin-top: 10px` to HL Balance bar for visual breathing room below the toggle header.

---

## Risks for This Test

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| ETH moves out of range | Medium | Narrow range chosen deliberately; test out-of-range logic |
| Gas exhaustion (protection wallet) | High | **Must top up ETH** before starting |
| Existing UNI-V3 NFT conflicts with bot config | Unknown | Investigate and document the existing position |
| Capital too small to see meaningful fees | High | Acceptable for logic testing; fees not the objective |
| Bot crashes on small position amounts | Low | Edge case — monitor closely at start |
