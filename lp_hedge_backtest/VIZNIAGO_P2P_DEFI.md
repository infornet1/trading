# Vizniago DeFi P2P — Specification & Implementation Plan
**Version:** 4.0 | **Date:** 2026-03-23 | **Status:** Planning
**Concept:** Fiat ↔ Crypto OTC marketplace with smart contract escrow (Binance P2P model, fully DeFi)

---

## 1. What This Is

A **peer-to-peer fiat↔crypto trading marketplace** where:

- **Sellers** lock crypto in a smart contract escrow and post an ad
- **Buyers** initiate a trade, send fiat off-chain (Zelle, Wise, bank transfer)
- **Smart contract releases** crypto to buyer once seller confirms receipt
- **AI agent (L1)** triages disputes instantly — auto-resolves ~60% of cases
- **Vizniago arbiters (L2)** resolve edge cases via multisig — AI pre-analysis included

> Binance P2P replaces Binance custody with a smart contract. The fiat leg is always off-chain — unavoidable in any fiat↔crypto system — but the crypto custody is fully trustless.

### What Vizniago Adds on Top of Binance P2P

- Wallet-native identity (EIP-191 auth — no email/password, no KYC required)
- On-chain reputation (trade history immutable, sybil-resistant via wallet age)
- LP position holders as natural sellers (they already hold USDC from LP fees)
- Arbitrum One (sub-cent gas per escrow tx vs. Ethereum mainnet)
- **AI-powered dispute resolution** — instant triage, no waiting hours for a human

---

## 2. Trade Flow

### Sell Side (crypto → fiat)

```
1. Seller creates ad
   └── "Selling 500 USDC | Price: $1.02/USDC | Min: $50 | Max: $500
        Payment: Wise, Zelle | Response time: < 15 min"

2. Buyer clicks "Buy" → selects amount (e.g. $200 = 196.08 USDC)
   └── Platform fee: 0.5% = $1.00 → buyer receives 195.10 USDC net

3. Smart contract locks 196.08 USDC in escrow
   └── Seller's wallet signs lockFunds() tx → funds move to VizniagoEscrow.sol

4. Buyer sees payment instructions (seller's Wise ID / Zelle phone)
   └── Trade room opens (real-time chat via WebSocket)

5. Buyer sends $200 fiat → clicks "I've Paid"
   └── 30-minute countdown starts for seller to confirm

6a. Seller verifies payment received → clicks "Release Funds"
    └── escrow.release() → 195.10 USDC to buyer + 0.98 USDC to treasury
    └── Reputation updated: +1 completed trade for both parties

6b. Seller does NOT confirm in 30 min → Buyer opens dispute
    └── AI agent triages immediately (< 2 min)
    └── If confidence ≥ 90% → auto-resolve
    └── Otherwise → human arbiter queue with AI pre-analysis
```

### Buy Side (fiat → crypto, buyer posts ad)

```
1. Buyer posts ad
   └── "Buying 500 USDC | Offering: $1.01/USDC | Min: $100 | Max: $500
        Payment: Wise only"

2. Seller sees ad → initiates trade
   └── Seller locks USDC in escrow (same flow as above, roles swapped)

3. Same escrow + confirmation flow
```

---

## 3. Architecture

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                        USER (Browser + Wallet)                               │
│                                                                              │
│  Marketplace UI  →  Trade Room  →  Profile / Reputation                     │
└──────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│              FastAPI Backend (existing, extended)                             │
│                                                                              │
│  /p2p/ads           — CRUD for buy/sell listings                            │
│  /p2p/trades        — trade lifecycle state machine                         │
│  /p2p/chat          — WebSocket encrypted trade room                        │
│  /p2p/disputes      — arbiter queue + evidence upload                       │
│  /p2p/reputation    — on-chain trade history aggregation                    │
│  /p2p/notifications — email + Telegram alerts per trade event               │
└──────────────────────────────────────────────────────────────────────────────┘
                │                       │                      │
                ▼                       ▼                      ▼
┌──────────────────────┐  ┌─────────────────────┐  ┌──────────────────────────┐
│  MariaDB             │  │  Arbitrum One        │  │  AI Dispute Agent        │
│  (off-chain state)   │  │  (on-chain escrow)   │  │  (Claude Opus 4.6)       │
│                      │  │                      │  │                          │
│  ads, trades,        │  │  VizniagoEscrow.sol   │  │  Vision: screenshot      │
│  messages,           │  │  VizniagoReputation   │  │  analysis                │
│  disputes,           │  │  .sol                │  │  NLP: chat history       │
│  ai_analyses         │  │                      │  │  Output: structured      │
│                      │  │                      │  │  verdict + reasoning     │
└──────────────────────┘  └─────────────────────┘  └──────────────────────────┘
```

---

## 4. Smart Contracts (Arbitrum One)

### 4.1 VizniagoEscrow.sol

The most critical contract. Holds seller's crypto during a trade.

**Chain:** Arbitrum One (mainnet, Chain ID 42161) | Testnet: Arbitrum Sepolia (421614)
**Gas cost per tx:** ~$0.02–$0.05 (vs $5–$20 on Ethereum L1)
**Token:** Native USDC only — `0xaf88d065e77c8cC2239327C5EDb3A432268e5831`

```
States per trade:
  EMPTY → LOCKED → RELEASED
                 → CANCELLED   (buyer cancels before paying)
                 → DISPUTED    → RESOLVED
```

```solidity
struct Trade {
    uint256 tradeId;
    address seller;
    address buyer;
    address token;          // USDC, USDT, WETH — native only
    uint256 amount;         // crypto amount locked (gross, includes fee)
    uint256 fiatAmount;     // informational (2 decimals)
    string  fiatCurrency;   // "USD", "EUR", "VES", etc.
    uint16  feeBps;         // taker fee in basis points (e.g. 50 = 0.5%)
    uint8   status;         // 0=locked,1=released,2=cancelled,3=disputed,4=resolved
    uint256 lockedAt;
    uint256 releasedAt;
    uint256 expiresAt;      // lockedAt + 30 min (auto-cancel if buyer never pays)
}

function lockFunds(
    uint256 tradeId,
    address buyer,
    address token,
    uint256 amount,
    uint256 fiatAmount,
    string calldata fiatCurrency
) external;

// Deducts fee at release: buyer receives (amount - fee), treasury receives fee
function release(uint256 tradeId) external onlySeller;
function cancel(uint256 tradeId) external onlyBuyer;   // only before "I've Paid"
function openDispute(uint256 tradeId) external;         // buyer or seller
function arbitrate(uint256 tradeId, address winner) external onlyArbiter;
```

**Security:**
- `onlyArbiter` = Vizniago Gnosis Safe multisig (3-of-5) initially
- No admin can move funds without `arbitrate()` — never an owner backdoor
- Emergency pause (OpenZeppelin Pausable) for critical exploits only
- Reentrancy guard on all state-changing functions
- No native ETH — ERC-20 tokens only (avoids ETH transfer edge cases)

---

### 4.2 VizniagoReputation.sol

Immutable on-chain trade record. Cannot be gamed — only the escrow contract writes to it.

```solidity
struct TraderStats {
    uint32 completedTrades;
    uint32 disputesLost;
    uint32 disputesWon;
    uint32 cancellations;
    uint256 totalVolumeUSD; // cumulative fiat value traded (6 decimals)
    uint256 firstTradeAt;
    uint256 lastTradeAt;
}

// only callable by VizniagoEscrow
function recordCompletion(address seller, address buyer, uint256 fiatAmount) external onlyEscrow;
function recordDispute(address loser, address winner) external onlyEscrow;

// public view
function getStats(address trader) external view returns (TraderStats memory);
function getCompletionRate(address trader) external view returns (uint256 bps); // 0–10000
```

---

## 5. Fee Model

### Base Structure: Maker 0% / Taker 0.5%

```
Trade: $200 fiat → 196.08 USDC

  Buyer initiates (taker) → 0.5% fee = 0.98 USDC
  Seller posts ad (maker)  → 0% fee

  Buyer receives:   195.10 USDC
  Vizniago treasury:   0.98 USDC  ← deducted inside release() on-chain
```

Fee is **collected automatically inside `release()`** — trustless, cannot be bypassed.

```solidity
function release(uint256 tradeId) external onlySeller {
    Trade storage t = trades[tradeId];
    require(t.status == Status.PAYMENT_SENT);

    uint256 fee = (t.amount * t.feeBps) / 10000;
    uint256 buyerReceives = t.amount - fee;

    IERC20(t.token).transfer(t.buyer, buyerReceives);
    IERC20(t.token).transfer(treasury, fee);          // Gnosis Safe

    t.status = Status.COMPLETED;
    reputation.recordCompletion(t.seller, t.buyer, t.fiatAmount);
    emit TradeReleased(tradeId, buyerReceives, fee);
}
```

### Subscription Tiers (Unlock Protocol NFT Integration)

| Tier | NFT Key | Taker Fee | Monthly Trade Limit |
|------|---------|-----------|---------------------|
| **Free** | None | 0.5% | $5,000 |
| **Starter** | $19/mo | 0.3% | $20,000 |
| **Pro** | $49/mo | 0.2% | $100,000 |
| **Enterprise** | $199/mo | 0.1% | Unlimited |

`feeBps` is resolved at trade creation by checking the buyer's Unlock Protocol NFT key on Arbitrum One. Heavy traders have a strong incentive to upgrade — cross-selling the existing subscription model.

### Additional Revenue Streams

| Stream | Rate | Trigger |
|--------|------|---------|
| Featured ads | $2–$5 USDC flat | Seller pins ad to top for 24h |
| Dispute fee | $2 USDC flat | Paid by the **losing** party — deters frivolous disputes |
| Verification badge | $10 USDC one-time | ID-doc check, no data stored |
| API access | Included in Enterprise | High-volume market makers |

### Revenue Projections

| Daily GMV | Avg Fee | Daily Revenue | Monthly Revenue |
|-----------|---------|---------------|-----------------|
| $10,000 | 0.5% | $50 | $1,500 |
| $50,000 | 0.4% | $200 | $6,000 |
| $200,000 | 0.35% | $700 | $21,000 |
| $1,000,000 | 0.3% | $3,000 | $90,000 |

---

## 6. Off-Chain Components

### 6.1 Trade State Machine (Backend)

The backend is the source of truth for off-chain trade state (chat, payment instructions, timers). The smart contract is the source of truth for money.

```
AD_ACTIVE
    │
    ▼ buyer initiates
TRADE_CREATED   ← backend creates trade record
    │
    ▼ seller calls lockFunds() tx confirmed
FUNDS_LOCKED
    │
    ▼ buyer clicks "I've Paid"
PAYMENT_SENT    ← 30-min countdown starts
    │
    ├──▶ seller clicks "Release" → escrow.release() confirmed
    │                                       ▼
    │                               COMPLETED  → reputation updated
    │
    └──▶ timer expires OR dispute opened
                    ▼
              DISPUTED
                    │
                    ▼ AI agent runs immediately (< 2 min)
              AI_TRIAGED
                    │
                    ├──▶ confidence ≥ 90% → auto-resolve
                    │         ▼
                    │    escrow.arbitrate() called by backend
                    │         ▼
                    │      RESOLVED
                    │
                    └──▶ confidence < 90% → human arbiter queue
                              ▼
                         UNDER_REVIEW  (AI pre-analysis attached)
                              │
                              ▼ arbiter submits decision
                           RESOLVED
```

### 6.2 Trade Chat (WebSocket)

Real-time encrypted messaging between buyer and seller during a trade.

- Same WebSocket hub as existing bot events (`/api/ws/`)
- Messages stored in MariaDB `p2p_messages` table (not on-chain)
- E2E encryption: client-side AES, shared secret = `keccak256(tradeId + sellerAddr + buyerAddr)`
- File attachment support (payment screenshots for dispute evidence)
- Auto-deletes after 90 days (GDPR / privacy)

### 6.3 Notifications

Reuses existing email (Brevo SMTP) + Telegram webhook infrastructure.

| Event | Notify |
|-------|--------|
| Trade initiated | Seller (email + Telegram) |
| Funds locked on-chain | Buyer (email + Telegram) |
| Buyer clicks "I've Paid" | Seller (email + Telegram) |
| 5 min before timer expires | Both parties |
| Dispute opened | Both parties + arbiter queue |
| AI verdict issued | Both parties (verdict + reasoning) |
| Human arbiter requested | Arbiter Telegram alert |
| Trade completed / resolved | Both parties |

### 6.4 AI Dispute Agent

Powered by **Claude Opus 4.6** with vision. Runs automatically when a dispute is opened.

#### Dispute Type Taxonomy

| Type | Frequency | AI Resolvable? |
|------|-----------|----------------|
| Seller ghost (locked funds, won't respond) | 30% | Yes — timer rule auto-triggers |
| Payment not received (buyer claims sent, denied) | 40% | Partially — vision analyzes screenshot |
| Wrong amount sent | 10% | Yes — screenshot + chat analysis |
| Wrong payment method | 8% | Yes — AI reads chat history |
| Chargeback attempt (reversible payment) | 7% | No — escalate to human |
| Account freeze (bank issue) | 5% | No — escalate to human |

#### Triage Flow

```
ALL DISPUTES
      │
      ▼
L0 — Automatic rules (no AI needed)
  ├── Timer expired, buyer never clicked "I've Paid"
  │   → auto-cancel, funds return to seller
  └── Seller didn't respond 30 min after "I've Paid"
      → auto-escalate to AI triage
      │
      ▼
L1 — AI Agent (Claude Opus 4.6)    ~resolves 50–60% of disputes
  ├── Vision: analyze payment screenshot
  │   (amount, reference, date, tampering signs)
  ├── NLP: read full trade chat history
  ├── Check: amount + reference match trade metadata
  ├── Check: screenshot timestamp vs trade timeline
  ├── Detect: bad-faith patterns in chat
  ├── Lookup: buyer/seller reputation score
  └── Output structured verdict:
      RECOMMEND_RELEASE | RECOMMEND_CANCEL | ESCALATE_TO_HUMAN
      + confidence (0–100) + reasoning + red_flags
      │
      ├── confidence ≥ 90% → auto-resolve on-chain
      │
      └── confidence < 90% → human arbiter queue
                │
                ▼
L2 — Human Arbiter (Vizniago multisig 3-of-5)
  ├── Sees AI pre-analysis (verdict, reasoning, red flags)
  ├── Reduces arbiter time by ~65%
  └── Executes escrow.arbitrate(winner) on-chain
```

#### What AI Checks Per Dispute

| Check | Method |
|-------|--------|
| Screenshot fiat amount matches trade | Vision — reads amount in receipt |
| Payment reference present (`VZP-XXXXXX`) | Vision — looks for trade ref code |
| Screenshot timestamp plausible | Vision — date on receipt vs locked_at |
| Screenshot not obviously edited | Vision — font/layout inconsistencies |
| Buyer acknowledged sending in chat | NLP — reads chat |
| Seller provided counter-evidence | NLP — reads chat |
| Buyer completion rate ≥ 90% | Structured data — on-chain reputation |
| No chat at all (ghost pattern) | Rule — flag as high fraud risk |

#### Operational Impact

| Metric | Without AI | With AI Agent |
|--------|-----------|---------------|
| Disputes/day at 500 trades | ~10 | ~10 |
| Human arbiter hours/day | 2.5–5 hrs | ~1 hr |
| User wait time for triage | 2–8 hours | < 2 minutes |
| Cost per resolved dispute | $15–25 | ~$0.15–0.30 (API call) |
| Auto-resolved (no human) | 0% | ~60% |

---

## 7. Database Schema (New Tables)

```sql
CREATE TABLE p2p_ads (
    id              BIGINT PRIMARY KEY AUTO_INCREMENT,
    owner_address   VARCHAR(42) NOT NULL,
    ad_type         ENUM('sell','buy') NOT NULL,
    token           VARCHAR(10) NOT NULL,           -- 'USDC', 'USDT', 'WETH'
    fiat_currency   VARCHAR(5) NOT NULL,            -- 'USD', 'EUR', 'VES'
    price_per_unit  DECIMAL(18,6) NOT NULL,         -- fiat per 1 token
    min_amount_fiat DECIMAL(18,2) NOT NULL,
    max_amount_fiat DECIMAL(18,2) NOT NULL,
    payment_methods JSON NOT NULL,                  -- ["Wise","Zelle","BankTransfer"]
    payment_details TEXT,                           -- AES-256 encrypted, shown to counterparty only
    terms           TEXT,
    status          ENUM('active','paused','completed','cancelled') DEFAULT 'active',
    available_amount DECIMAL(18,6) NOT NULL,
    created_at      TIMESTAMP DEFAULT NOW(),
    INDEX idx_type_token_status (ad_type, token, status)
);

CREATE TABLE p2p_trades (
    id              BIGINT PRIMARY KEY AUTO_INCREMENT,
    ad_id           BIGINT REFERENCES p2p_ads(id),
    trade_ref       VARCHAR(16) UNIQUE,             -- human-readable: VZP-XXXXXX
    seller_address  VARCHAR(42) NOT NULL,
    buyer_address   VARCHAR(42) NOT NULL,
    token           VARCHAR(10) NOT NULL,
    token_amount    DECIMAL(18,6) NOT NULL,         -- gross (includes fee)
    fee_bps         SMALLINT NOT NULL DEFAULT 50,   -- buyer's tier fee at trade time
    fiat_currency   VARCHAR(5) NOT NULL,
    fiat_amount     DECIMAL(18,2) NOT NULL,
    payment_method  VARCHAR(50) NOT NULL,
    status          ENUM('created','locked','payment_sent','completed',
                         'cancelled','disputed','ai_triaged',
                         'under_review','resolved') DEFAULT 'created',
    escrow_tx_hash  VARCHAR(66),                    -- lockFunds() tx
    release_tx_hash VARCHAR(66),                    -- release() or arbitrate() tx
    arbiter_address VARCHAR(42),
    resolution      ENUM('seller_wins','buyer_wins'),
    expires_at      TIMESTAMP,                      -- 30 min after locked
    created_at      TIMESTAMP DEFAULT NOW(),
    updated_at      TIMESTAMP ON UPDATE NOW(),
    INDEX idx_seller (seller_address),
    INDEX idx_buyer (buyer_address)
);

CREATE TABLE p2p_messages (
    id              BIGINT PRIMARY KEY AUTO_INCREMENT,
    trade_id        BIGINT REFERENCES p2p_trades(id),
    sender_address  VARCHAR(42) NOT NULL,
    content         TEXT NOT NULL,                  -- AES encrypted
    attachment_url  VARCHAR(512),                   -- S3/IPFS for dispute evidence
    is_system       BOOLEAN DEFAULT FALSE,
    created_at      TIMESTAMP DEFAULT NOW(),
    INDEX idx_trade (trade_id)
);

CREATE TABLE p2p_disputes (
    id              BIGINT PRIMARY KEY AUTO_INCREMENT,
    trade_id        BIGINT REFERENCES p2p_trades(id),
    opened_by       VARCHAR(42) NOT NULL,
    reason          TEXT NOT NULL,
    evidence_urls   JSON,                           -- uploaded payment screenshots
    -- AI triage fields
    ai_verdict      ENUM('recommend_release','recommend_cancel','escalate_to_human'),
    ai_confidence   TINYINT UNSIGNED,               -- 0–100
    ai_reasoning    TEXT,                           -- shown to both parties
    ai_red_flags    JSON,                           -- internal fraud signals
    ai_missing_evidence JSON,                       -- what would change the verdict
    ai_arbiter_notes TEXT,                          -- shown to human arbiter only
    ai_analyzed_at  TIMESTAMP,
    -- human review fields
    arbiter_notes   TEXT,
    status          ENUM('open','ai_triaged','under_review','resolved') DEFAULT 'open',
    opened_at       TIMESTAMP DEFAULT NOW(),
    resolved_at     TIMESTAMP
);
```

---

## 8. API Endpoints

```
ADS
  GET  /p2p/ads                         — marketplace list (filter: type/token/currency/payment)
  POST /p2p/ads                         — create new ad (JWT required)
  GET  /p2p/ads/{id}                    — ad details
  PUT  /p2p/ads/{id}                    — update/pause/reactivate (owner only)
  DELETE /p2p/ads/{id}                  — cancel ad (no active trades)

TRADES
  POST /p2p/trades                      — initiate trade from ad (JWT required)
  GET  /p2p/trades/{ref}                — trade detail (buyer or seller only)
  POST /p2p/trades/{ref}/confirm-payment — buyer: "I've Paid"
  POST /p2p/trades/{ref}/release        — seller: release escrow
  POST /p2p/trades/{ref}/cancel         — buyer: cancel before paying
  POST /p2p/trades/{ref}/dispute        — open dispute → triggers AI triage

CHAT
  WS   /p2p/chat/{trade_ref}            — real-time trade room (JWT required)
  GET  /p2p/chat/{trade_ref}/history    — message history

DISPUTES
  GET  /p2p/disputes                    — open dispute queue (arbiter only)
  GET  /p2p/disputes/{id}              — dispute detail + AI analysis + evidence
  POST /p2p/disputes/{id}/analyze      — manually re-trigger AI triage (arbiter only)
  POST /p2p/disputes/{id}/resolve      — submit human arbiter decision

REPUTATION
  GET  /p2p/profile/{address}           — public trader profile + on-chain stats
  GET  /p2p/profile/me                  — own profile (JWT required)
```

---

## 9. Frontend Pages

### 9.1 Marketplace (`/p2p/`)

```
┌──────────────────────────────────────────────────────────────────────┐
│  VIZNIAGO P2P                                       [Connect Wallet]  │
│                                                                      │
│  [Buy USDC]  [Sell USDC]       Filter: [USD ▾] [All Methods ▾]     │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │  0xABCD...1234   ★4.9  (234 trades)   ⚡ Avg 8 min          │   │
│  │  Price: $1.02/USDC   Limits: $50 – $500   Fee: 0.5%         │   │
│  │  Methods: Wise · Zelle                                       │   │
│  │  Available: 800 USDC                        [Buy USDC →]    │   │
│  └──────────────────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │  0xDEF0...5678   ★4.7  (89 trades)    ⚡ Avg 12 min         │   │
│  │  Price: $1.015/USDC  Limits: $100 – $1,000   Fee: 0.3%      │   │
│  │  Methods: Bank Transfer                                      │   │
│  │  Available: 2,500 USDC                      [Buy USDC →]    │   │
│  └──────────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────────┘
```
Fee shown reflects buyer's current subscription tier.

### 9.2 Trade Room (`/p2p/trade/{ref}`)

```
┌────────────────────────────────────────────────────────────────────┐
│  Trade VZP-A3K9PX          Status: WAITING FOR PAYMENT   ⏱ 24:31  │
│                                                                    │
│  You are buying  195.10 USDC  for  $200.00 USD via Wise           │
│  (Fee: 0.98 USDC · Your tier: Free)                               │
│                                                                    │
│  ┌── Payment Instructions ──────────────────────────────────────┐ │
│  │  Send $200 via Wise to:  carlos@example.com                  │ │
│  │  Reference: VZP-A3K9PX  ← include this or dispute may fail  │ │
│  └──────────────────────────────────────────────────────────────┘ │
│                                                                    │
│  ┌── Chat ──────────────────────────────────────────────────────┐ │
│  │  [Seller] Hi, send payment to the Wise email above           │ │
│  │  [Buyer]  Payment sent! Screenshot attached                  │ │
│  │  📎 [payment_proof.png]                                      │ │
│  │                                                              │ │
│  │  Type a message...                         [Send]           │ │
│  └──────────────────────────────────────────────────────────────┘ │
│                                                                    │
│  [I've Sent Payment]              [Cancel Trade]                   │
└────────────────────────────────────────────────────────────────────┘
```

### 9.3 Dispute Room (`/p2p/dispute/{id}`)

When a dispute is opened, both parties see the AI triage result within 2 minutes:

```
┌────────────────────────────────────────────────────────────────────┐
│  Dispute — Trade VZP-A3K9PX                                        │
│                                                                    │
│  ┌── AI Triage Result (Vizniago Arbiter Bot) ──────────────────┐   │
│  │  Verdict:     RECOMMEND RELEASE TO BUYER                   │   │
│  │  Confidence:  87%  → Escalating to human review            │   │
│  │  Reasoning:   Screenshot shows $200.00 via Wise on         │   │
│  │               2026-03-23 14:32 UTC. Reference VZP-A3K9PX  │   │
│  │               is visible. Amount matches trade exactly.     │   │
│  │  Red flags:   None detected.                               │   │
│  │  Missing:     Transaction ID not provided — arbiter may     │   │
│  │               request this to confirm on Wise dashboard.   │   │
│  └────────────────────────────────────────────────────────────┘   │
│                                                                    │
│  Status: Under human review — decision within 4 hours             │
└────────────────────────────────────────────────────────────────────┘
```

### 9.4 Create Ad (`/p2p/create-ad/`)
- Token selector (USDC, USDT, WETH)
- Fiat currency selector
- Price input (manual or % above/below market reference)
- Min/max limits
- Payment methods checklist (Wise, Zelle, Bank Transfer — no PayPal)
- Payment details (encrypted, shown only to counterparty during trade)
- Terms textarea
- Preview → sign tx to lock available amount (sell ads) or just publish (buy ads)

### 9.5 Profile (`/p2p/profile/{address}`)
- Completion rate (%), total trades, average release time
- Positive / negative feedback count
- Active ads
- Trade history (on-chain, paginated)
- Subscription tier badge (Free / Starter / Pro / Enterprise)

---

## 10. Implementation Phases

### Phase 1 — Escrow Contract + Basic Marketplace (Weeks 1–5)

| Task | Output |
|------|--------|
| `VizniagoEscrow.sol` + Foundry fuzz tests | Deployed on Arbitrum Sepolia testnet |
| `VizniagoReputation.sol` | Linked to escrow, testnet |
| Fee logic inside `release()` (feeBps per trade) | On-chain fee collection |
| MariaDB schema (ads, trades, messages, disputes) | Migrations ready |
| `/p2p/ads` GET + POST endpoints | Ads list + create working |
| `/p2p/trades` POST + state machine | Trade creation + status tracking |
| Marketplace page (list + filter) | Browse ads with fee displayed |

### Phase 2 — Trade Room + Chat (Weeks 6–9)

| Task | Output |
|------|--------|
| WebSocket trade room (`/p2p/chat/{ref}`) | Real-time chat |
| Escrow tx confirmation listener (`p2p_escrow_listener.py`) | Backend detects lockFunds, release events |
| Trade room UI (instructions + chat + timers) | Full trade flow E2E |
| "I've Paid" → dispute trigger flow | Complete state machine |
| Notification system (email + Telegram per event) | Alerts working |
| Unlock Protocol fee tier lookup at trade creation | Subscription-based fee bps |

### Phase 3 — AI Dispute Agent + Reputation (Weeks 10–13)

| Task | Output |
|------|--------|
| `dispute_agent.py` — Claude Opus 4.6 + vision | AI triage on dispute open |
| Auto-resolve path (confidence ≥ 90% → on-chain tx) | Trustless AI resolution |
| Dispute room UI (AI verdict card + evidence) | Users see triage result < 2 min |
| Arbiter dashboard (AI pre-analysis attached) | Human review accelerated |
| Evidence upload (S3 or IPFS) | Screenshot attachments |
| Arbiter Gnosis Safe multisig setup (3-of-5) | Production dispute resolution |
| Reputation page + profile UI | Trader stats visible |
| Foundry invariant tests on escrow | Security baseline |

### Phase 4 — Security Audit + Mainnet (Weeks 14–17)

| Task | Output |
|------|--------|
| Smart contract audit (`VizniagoEscrow.sol` priority) | Audit report + remediations |
| Mainnet deploy on Arbitrum One | Live escrow contract |
| AI agent red-team testing (adversarial screenshots) | Robustness baseline |
| Seed liquidity: Vizniago team posts first sell ads | First real trades |
| Market maker program: incentivize high-volume sellers | GMV growth |

---

## 11. Key Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|-----------|
| **Chargeback fraud** (reversible payments) | Seller loses crypto + fiat reversed | Restrict to non-reversible methods (Wise, Zelle, bank transfer) — no PayPal |
| **Fake payment screenshot** | Buyer claims paid, didn't | AI vision detects common edits; arbiter requests Wise/Zelle transaction ID |
| **Seller ghost** | Buyer's trade stuck | 30-min auto-cancel if seller never confirms lock; 30-min timer after "I've Paid" |
| **AI false positive** (wrong auto-resolution) | Innocent party loses funds | Auto-resolve only at confidence ≥ 90%; losing party can appeal to human (costs $2 dispute fee) |
| **AI adversarial attack** (crafted screenshots) | Manipulate AI verdict | AI flags uncertainty → escalates; final on-chain tx always requires arbiter or seller signature |
| **Smart contract exploit** | Funds drained | Foundry fuzz + invariant tests + external audit before mainnet; Pausable emergency stop |
| **Regulatory exposure** (fiat↔crypto facilitation) | Legal risk | Pseudonymous (no KYC); geo-blocking for restricted jurisdictions; legal review pre-mainnet |
| **Sybil reputation gaming** | Fake positive trades | On-chain reputation only counts trades with unique counterparties; $50 minimum fiat threshold |

---

## 12. File Structure (New)

```
lp_hedge_backtest/
├── contracts/                          ← NEW
│   ├── src/
│   │   ├── VizniagoEscrow.sol           ← escrow + fee deduction
│   │   └── VizniagoReputation.sol       ← immutable on-chain trade record
│   ├── test/
│   │   ├── VizniagoEscrow.t.sol         ← fuzz + invariant tests
│   │   └── VizniagoReputation.t.sol
│   ├── script/
│   │   └── Deploy.s.sol
│   └── foundry.toml
│
├── api/
│   └── routers/
│       ├── p2p_ads.py                  ← NEW
│       ├── p2p_trades.py               ← NEW
│       ├── p2p_chat.py                 ← NEW (WebSocket)
│       ├── p2p_disputes.py             ← NEW (triggers AI agent)
│       └── p2p_reputation.py           ← NEW
│
├── dispute_agent.py                    ← NEW (Claude Opus 4.6 triage)
├── p2p_escrow_listener.py              ← NEW (on-chain event watcher)
│
└── landing/
    └── p2p/
        ├── index.html                  ← Marketplace
        ├── trade.html                  ← Trade room
        ├── dispute.html                ← Dispute room (AI verdict card)
        ├── create-ad.html              ← Post ad
        ├── profile.html                ← Trader profile
        └── p2p.js                      ← ethers.js + escrow ABI
```

---

## 13. Vizniago Fury Bot Automation Architecture

All LP hedge bot lifecycle is managed automatically through the API — no manual `.env` files, no standalone systemd services per pool.

### Design Principle

> Any user who connects an LP pool to Vizniago must get protection immediately and permanently, without any manual operator step.

### How It Works

```
viznago_api.service  (single systemd unit)
        │
        ▼
  FastAPI lifespan
        │
        ├─ startup: _auto_restart_bots()
        │       reads bot_configs WHERE active=True
        │       spawns one live_hedge_bot.py subprocess per pool
        │
        └─ BotManager (singleton)
                │
                ├─ start(config_id, config)   → Popen subprocess
                ├─ stop(config_id)            → SIGTERM + DB active=False
                ├─ _tail(config_id, proc)     → stdout→DB events + WebSocket
                └─ subscribe/unsubscribe      → real-time dashboard
```

### Environment Isolation

Each bot subprocess receives **only** explicit per-pool variables — never a blanket `**os.environ` which would bleed `.env` secrets across pools:

| Variable | Source |
|----------|--------|
| `HYPERLIQUID_SECRET_KEY` | DB (AES-256 encrypted) → decrypted at spawn |
| `HYPERLIQUID_ACCOUNT_ADDRESS` | DB |
| `UNISWAP_NFT_ID` | DB |
| `TRIGGER_OFFSET_PCT` / `HEDGE_RATIO` | DB |
| `BOT_MODE` / `CONFIG_ID` | DB |
| `ARBITRUM_RPC_URL` | `api/.env` (global infra) |
| `PATH`, `HOME`, `LANG` | OS defaults only |

### What Was Decommissioned

| Removed | Replaced By |
|---------|-------------|
| `.env` (root) — pool-specific secrets | DB `bot_configs` table |
| `.env.pool2` — second pool override | DB row for pool 2 |
| `live_hedge_bot.service` systemd unit | BotManager subprocess |
| `live_hedge_bot_2.service` systemd unit | BotManager subprocess |
| `load_dotenv()` in `live_hedge_bot.py` | BotManager-injected env vars |
| Manual `UNISWAP_NFT_ID=xxx` exports | DB `nft_token_id` column |

### Pool Registration

New pools are registered via:
1. **Dashboard UI** — `/dashboard` → Add Pool form → POST `/bots`
2. **API** — `POST /bots` with `nft_token_id`, `pair`, `trigger_pct`, `hedge_ratio`
3. **Migration script** — `scripts/seed_pools.py` (one-time, idempotent)

On `active=True`, BotManager starts the bot immediately. On API restart, `_auto_restart_bots()` re-launches all active configs automatically.

### Currently Monitored Pools (as of 2026-03-23)

| Config ID | NFT | Pair | Range | Status |
|-----------|-----|------|-------|--------|
| 2 | #5381818 | ETH/USDC | $1,919–$2,344 | Active (IN range) |
| 3 | #5364575 | ETH/USDC | $1,919–$2,232 | Active (IN range) |
| 4 | #5374616 | ETH/USDC | $2,030–$2,300 | Active (IN range) |

---

## 14. What Reuses Existing Vizniago Infrastructure

| Existing Piece | Reused As-Is |
|----------------|-------------|
| `api/auth.py` EIP-191 wallet login | All P2P pages use same JWT auth |
| `api/ws.py` WebSocket hub | Trade chat rooms use same hub pattern |
| Brevo SMTP email | Trade event + dispute notifications |
| Telegram webhook | Trade alerts + arbiter dispute pings |
| MariaDB + SQLAlchemy | Same DB, new tables |
| Arbitrum One (Unlock Protocol) | Same chain for escrow contracts + fee tiers |
| Vanilla JS + CSS design system | Same UI kit, new pages |
| `anthropic` Python SDK | Already installed → `dispute_agent.py` |

---

## 15. Key Design Decisions

| Decision | Choice | Reason |
|----------|--------|--------|
| Fiat direction | Buyer always the taker (pays fee) | Sellers post clean round numbers — simpler UX |
| Allowed payment methods | Wise, Zelle, bank transfer only | No PayPal/credit card — chargeback risk too high |
| AI confidence threshold | 90% for auto-resolve | Erring on the side of human review; appeal available |
| AI model | Claude Opus 4.6 (adaptive thinking) | Vision + reasoning for screenshot analysis |
| Dispute appeal | Loser pays $2 flat fee | Deters frivolous appeals without blocking legitimate ones |
| Chain | Arbitrum One only (Phase 1) | Lowest gas, same chain as Unlock Protocol |
| Token | Native USDC only | Avoid bridged USDC.e confusion and liquidity fragmentation |

---

*v4.0 — Adds Section 13: bot automation architecture, decommission of manual .env approach.*
*v3.0 — Incorporates fee model, AI dispute agent, and Arbitrum One contract details.*
*v2.0 — Core P2P design (Binance P2P model, DeFi escrow).*
*v1.0 (deprecated) — Copy-trading vault concept. Replaced by P2P OTC design.*
