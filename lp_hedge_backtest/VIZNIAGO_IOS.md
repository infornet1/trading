# VIZNIAGO iOS App — Build Plan
> v1.0 — 2026-03-29
> Phase 1: Capacitor wrapper · Phase 2: React Native rebuild

---

## 1. Overview

The VIZNIAGO iOS app brings the full platform to iPhone:
real-time bot monitoring, whale signals, FURY trades, and the VIZBOT assistant
— all accessible without opening a browser.

**Key principle:** Phase 1 reuses the entire existing web dashboard (HTML/JS/CSS)
with zero logic rewrite. Phase 2 replaces the web shell with a native React Native
UI for performance and UX quality worthy of the App Store.

---

## 2. Phase 1 — Capacitor Wrapper

### 2.1 What Capacitor does

Capacitor (by Ionic) packages a web app into a native iOS `.ipa` binary.
The existing `dashboard/index.html` runs in a `WKWebView` — the same engine as Safari —
while Capacitor bridges native APIs (push notifications, biometrics, Keychain) that
the browser cannot reach.

```
┌──────────────────────────────────┐
│           iOS App Bundle         │
│  ┌────────────────────────────┐  │
│  │  WKWebView (Capacitor)     │  │
│  │  ┌──────────────────────┐  │  │
│  │  │  dashboard/index.html │  │  │
│  │  │  dashboard.js         │  │  │
│  │  │  dashboard.css        │  │  │
│  │  │  chat-widget.js       │  │  │
│  │  └──────────────────────┘  │  │
│  └────────────────────────────┘  │
│  ┌───────────┐  ┌─────────────┐  │
│  │  Push     │  │  Keychain   │  │
│  │  Notif.   │  │  (JWT)      │  │
│  └───────────┘  └─────────────┘  │
└──────────────────────────────────┘
         ▼ HTTPS + WSS ▼
  FastAPI  /trading/lp-hedge/api
```

### 2.2 Prerequisites

| Requirement | Notes |
|-------------|-------|
| macOS machine with Xcode 15+ | Required for iOS build + simulator |
| Apple Developer Account | $99/yr — needed for App Store & push certs |
| Node.js 20+ | For Capacitor CLI |
| Existing VIZNIAGO dashboard | Already exists at `landing/dashboard/` |

### 2.3 Step-by-step setup

#### Step 1 — Install Capacitor

```bash
cd /var/www/dev/trading/lp_hedge_backtest/landing

npm init -y
npm install @capacitor/core @capacitor/cli
npm install @capacitor/ios
npm install @capacitor/push-notifications
npm install @capacitor/local-notifications
npm install @capacitor/status-bar
npm install @capacitor/splash-screen
```

#### Step 2 — Initialize

```bash
npx cap init "VIZNIAGO" "com.viznago.fury" --web-dir="."
```

This creates `capacitor.config.json` at `landing/`:

```json
{
  "appId": "com.viznago.fury",
  "appName": "VIZNIAGO",
  "webDir": ".",
  "server": {
    "androidScheme": "https"
  },
  "plugins": {
    "SplashScreen": {
      "launchShowDuration": 2000,
      "backgroundColor": "#0a0a0f",
      "splashFullScreen": true
    },
    "PushNotifications": {
      "presentationOptions": ["badge", "sound", "alert"]
    }
  }
}
```

#### Step 3 — Add iOS platform

```bash
npx cap add ios
npx cap sync ios
```

This generates `landing/ios/` — an Xcode project ready to open.

#### Step 4 — Open in Xcode

```bash
npx cap open ios
```

In Xcode:
- Set **Team** → your Apple Developer account
- Set **Bundle ID** → `com.viznago.fury`
- Set **Deployment Target** → iOS 16.0
- Replace the default app icon with the VIZNIAGO unicorn logo
- Set **Display Name** → `VIZNIAGO`

#### Step 5 — Point the API to production URL

The dashboard currently uses a relative path `/trading/lp-hedge/api`. For the native
app this must be an absolute URL. Create `landing/capacitor-env.js`:

```javascript
// Injected by Capacitor build — overrides API_BASE for native app
if (window.Capacitor && window.Capacitor.isNativePlatform()) {
  window.__VIZNIAGO_API_BASE__ = 'https://yourdomain.com/trading/lp-hedge/api';
  window.__VIZNIAGO_WS_BASE__  = 'wss://yourdomain.com/trading/lp-hedge/api';
}
```

In `dashboard.js` change line 123:
```javascript
// Before
const API_BASE = '/trading/lp-hedge/api';

// After
const API_BASE = window.__VIZNIAGO_API_BASE__ || '/trading/lp-hedge/api';
```

And patch WebSocket construction similarly to use `__VIZNIAGO_WS_BASE__`.

#### Step 6 — Move JWT from localStorage to iOS Keychain

`localStorage` works inside WKWebView but is cleared when the app is deleted.
The Keychain survives reinstalls and is encrypted by the Secure Enclave.

```javascript
// dashboard.js — wrap storage calls
import { SecureStoragePlugin } from 'capacitor-secure-storage-plugin';

async function saveJwt(token) {
  if (window.Capacitor?.isNativePlatform()) {
    await SecureStoragePlugin.set({ key: 'vf_jwt', value: token });
  } else {
    localStorage.setItem('vf_jwt', token);
  }
}

async function loadJwt() {
  if (window.Capacitor?.isNativePlatform()) {
    const { value } = await SecureStoragePlugin.get({ key: 'vf_jwt' });
    return value;
  }
  return localStorage.getItem('vf_jwt');
}
```

Install: `npm install capacitor-secure-storage-plugin`

#### Step 7 — Push notifications

Push notifications let the app alert users when:
- A bot stops unexpectedly
- A whale signal fires (HIGH or CRITICAL tier)
- FURY circuit breaker trips
- Daily P&L summary

**Backend side** — add APNs token registration endpoint to FastAPI:

```python
# api/routers/bots.py  (new endpoint)
@router.post("/push/register")
async def register_push_token(body: dict, user=Depends(get_current_user)):
    token = body.get("token")
    # Store token in user record (add column push_token to users table)
    await db.execute(
        "UPDATE users SET push_token = ? WHERE id = ?",
        (token, user.id)
    )
    return {"ok": True}
```

**Dashboard side** — register on app launch:

```javascript
import { PushNotifications } from '@capacitor/push-notifications';

async function registerPush() {
  if (!window.Capacitor?.isNativePlatform()) return;

  const perm = await PushNotifications.requestPermissions();
  if (perm.receive !== 'granted') return;

  await PushNotifications.register();

  PushNotifications.addListener('registration', async ({ value: token }) => {
    await apiCall('POST', '/push/register', { token });
  });
}
```

**Send from bot events** — in `api/bot_manager.py`, after writing a critical bot event,
call APNs (use `httpx` + Apple's token-based auth) to push to the user's device.

#### Step 8 — Mobile CSS fixes

The current dashboard CSS is desktop-first. Add a `mobile.css` file included only
when running in Capacitor:

```javascript
if (window.Capacitor?.isNativePlatform()) {
  const link = document.createElement('link');
  link.rel = 'stylesheet';
  link.href = '../mobile.css';
  document.head.appendChild(link);
}
```

Key overrides needed in `mobile.css`:

```css
/* Safe area insets for iPhone notch / Dynamic Island */
body { padding-top: env(safe-area-inset-top); }
.navbar { padding-top: max(12px, env(safe-area-inset-top)); }

/* Bottom tab bar spacing */
.page-content { padding-bottom: env(safe-area-inset-bottom); }

/* Whale signals panel — full-width on mobile */
.whale-signals-panel { width: 100%; }

/* Bot cards — single column */
.bots-grid { grid-template-columns: 1fr; }

/* VIZBOT chat — full screen on mobile */
.chat-widget { inset: 0; border-radius: 0; }
```

#### Step 9 — Wallet connect on mobile

The existing dashboard uses MetaMask/Rabby browser injection (`window.ethereum`).
Inside WKWebView this is NOT available. Two options:

**Option A (Phase 1 — quick):** WalletConnect v2 via `@walletconnect/modal`
- Shows a QR code or deep-link to the user's mobile wallet
- Works inside WKWebView

**Option B (Phase 2 — native):** WalletConnect + native Swift integration
- Cleaner UX, can use Face ID to approve transactions

For Phase 1, inject WalletConnect Web3Modal into `dashboard.js` as a
fallback when `window.ethereum` is not detected:

```javascript
async function connectWallet() {
  if (window.ethereum) {
    // Existing desktop MetaMask flow
    return connectMetaMask();
  }
  // Mobile: use WalletConnect
  return connectWalletConnect();
}
```

#### Step 10 — Build & Test

```bash
# After any dashboard change:
npx cap sync ios

# Run on simulator
npx cap run ios

# Run on physical device (requires Apple Developer account)
# Select your device in Xcode → Product → Run
```

#### Step 11 — App Store submission

1. In Xcode → **Product → Archive**
2. **Distribute App → App Store Connect**
3. In App Store Connect:
   - Create new app: `VIZNIAGO`
   - Category: **Finance**
   - Age rating: 17+ (financial trading)
   - Screenshots: 6.7" (iPhone 16 Pro Max) + 5.5" (iPhone 8 Plus) required
   - Privacy policy URL: required for Finance category
4. Submit for review — Apple reviews Finance apps in 2–5 days

---

### 2.4 Phase 1 deliverables summary

| Item | Status after Phase 1 |
|------|----------------------|
| Bot monitoring (all 3 modes) | ✅ via WKWebView |
| Whale signals live feed | ✅ via WKWebView + WebSocket |
| FURY trade history | ✅ |
| VIZBOT assistant chat | ✅ |
| Admin panel | ✅ |
| Push notifications (bot stop, whale alert) | ✅ via APNs |
| Biometric login (Face ID) | ✅ via Keychain + LocalAuthentication |
| JWT stored securely | ✅ iOS Keychain |
| Wallet connect | ✅ WalletConnect v2 fallback |
| Native charts / animations | ❌ (web-based, Phase 2) |
| Offline mode | ❌ Phase 2 |
| App Store listed | ✅ |

---

## 3. Phase 2 — React Native Rebuild (Post-Alpha)

Phase 2 replaces the WKWebView shell with a fully native UI.
Built with **React Native + Expo SDK** for fast iteration.

### 3.1 Screen architecture

```
Tab Bar
├── 📊  Dashboard      — bot status cards, P&L summary, LP range health
├── 🐋  Whale          — live signal feed, convergence alerts, intel scores
├── ⚡  FURY           — trade history, RSI gauge, circuit breaker status
├── 🤖  VIZBOT         — AI assistant chat (native messages UI)
└── ⚙️  Settings       — wallet, API keys, notifications, membership
```

### 3.2 Key libraries

| Purpose | Library |
|---------|---------|
| Navigation | `@react-navigation/native` + bottom tabs |
| Charts | `victory-native` or `react-native-svg-charts` |
| WebSocket | Native `WebSocket` API (built-in RN) |
| Wallet | `@walletconnect/modal-react-native` |
| Push | `expo-notifications` |
| Secure storage | `expo-secure-store` |
| Animations | `react-native-reanimated` |
| i18n | `i18next` + `react-i18next` (reuse existing keys from `i18n.js`) |

### 3.3 API reuse

The FastAPI backend requires **zero changes** for Phase 2.
All endpoints, WebSocket protocol, and JWT auth stay identical.
Only the frontend client changes.

### 3.4 What improves over Phase 1

| Feature | Phase 1 (web) | Phase 2 (native) |
|---------|--------------|-----------------|
| Whale signal row animation | CSS transition | Reanimated spring |
| Bot status card | HTML div | Native `Animated.View` |
| RSI gauge | Static number | Native SVG arc gauge |
| Chart performance | Canvas (laggy on scroll) | 60fps native rendering |
| Gesture (swipe to dismiss) | ❌ | ✅ |
| Background refresh | ❌ (app must be open) | ✅ `BackgroundFetch` |
| Face ID gate | Optional | Native prompt on open |
| App size | ~8 MB | ~25 MB |

---

## 4. Notification Strategy

| Event | Trigger | Tier |
|-------|---------|------|
| Bot stopped unexpectedly | `bot_stopped` event in `bot_events` | Critical |
| FURY circuit breaker tripped | `fury_circuit_break` event | High |
| Whale CRITICAL signal | `whale_new_position` with `alert_tier=CRITICAL` | High |
| Whale convergence alert | `convergence` pattern triggered | High |
| Daily P&L summary | Scheduled — 00:00 UTC | Low |
| Bot started / restarted | `bot_started` event | Info |

**Backend delivery:** APNs token-based auth (no certificate needed, token is a JWT
signed with your Apple Developer key — 1-year expiry).
Use `httpx` from `bot_manager.py` when writing critical events.

---

## 5. App Store Listing Plan

| Field | Content |
|-------|---------|
| **Name** | VIZNIAGO — DeFi LP Bot |
| **Subtitle** | Hedge Uniswap v3 · Track Whales |
| **Category** | Finance |
| **Secondary** | Utilities |
| **Age rating** | 17+ (Frequent/Intense Simulated Trading) |
| **Keywords** | DeFi, LP hedge, Uniswap, Hyperliquid, whale tracker, perps, impermanent loss |
| **Description** | Monitor your Uniswap v3 LP positions, run automated hedge bots on Hyperliquid, and track top whale traders — all in one app. |
| **Privacy policy** | Required — must describe data collected (wallet address, JWT) |
| **App Review notes** | "This app connects to user-owned bot infrastructure. No trades are made from within the app — all positions are managed through the user's own Hyperliquid account." |

---

## 6. Timeline Estimate

### Phase 1

| Task | Effort |
|------|--------|
| Capacitor setup + Xcode config | 1 day |
| API_BASE / WS_BASE env fix | 2 hours |
| Keychain JWT migration | 2 hours |
| Mobile CSS fixes | 2 days |
| WalletConnect v2 integration | 1 day |
| Push notification (frontend + backend) | 2 days |
| Internal TestFlight testing | 3 days |
| App Store submission + review | 2–5 days |
| **Total** | **~2 weeks** |

### Phase 2 (after Phase 1 is stable)

| Task | Effort |
|------|--------|
| Expo project setup + navigation | 3 days |
| Dashboard screen (bot cards) | 1 week |
| Whale screen (signal feed + intel) | 1 week |
| FURY screen (trades + gauge) | 3 days |
| VIZBOT screen (chat UI) | 2 days |
| Settings + wallet connect | 3 days |
| Polish + TestFlight + submission | 1 week |
| **Total** | **~5–6 weeks** |

---

## 7. Open Decisions

| Question | Options | Recommendation |
|----------|---------|---------------|
| Android support | Phase 1 only iOS vs. add Android via Capacitor | Add Android in Phase 1 — Capacitor is free, 90% same code |
| WalletConnect project ID | Need one from cloud.walletconnect.com | Register free project before Phase 1 starts |
| APNs auth method | Token-based vs. certificate | Token-based — no yearly cert renewal |
| App Store or TestFlight-only for Alpha | Both | TestFlight for alpha users, App Store for launch |
| Membership gate in-app | None vs. IAP (Apple takes 30%) | No IAP — direct web checkout only, deeplink to viznago.com |
