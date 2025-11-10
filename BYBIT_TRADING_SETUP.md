# Bybit Automated Trading Setup

## ✅ API Credentials Configured

Your Bybit API is ready for automated trading with the following setup:

**API Name:** Scalping
**Permissions:**
- ✅ Contracts - Orders & Positions
- ✅ Unified Trading - Trade
- ✅ SPOT - Trade

**Leverage:** 5x (configured)
**Trading Mode:** Paper Trading (safe testing mode)

---

## 🔐 Security Setup

### **Credentials Storage**

Your API credentials are securely stored in `.env` file:

```bash
/var/www/dev/trading/.env
```

**File permissions:** `600` (only owner can read)
**⚠️ NEVER share or commit this file to git!**

### **API Key Restrictions (Recommended)**

For maximum security, configure these restrictions in Bybit:

1. **IP Whitelist:**
   ```
   Go to Bybit → API Management → Edit API
   → Add your server IP to whitelist
   ```

2. **Withdrawal Disabled:**
   - Your API should NOT have withdrawal permissions
   - Only trading permissions are needed

3. **Two-Factor Authentication:**
   - Enable 2FA on your Bybit account
   - API modifications require 2FA code

---

## 🎯 Trading Modes

### **1. Paper Trading Mode** (Current - SAFE)

Simulates all trades WITHOUT making real API calls.

```python
from bybit_trader import BybitTrader

# Paper trading - no real money
trader = BybitTrader(paper_trading=True)
```

**Use this to:**
- ✅ Test your strategy logic
- ✅ Verify signal integration
- ✅ Debug without risk
- ✅ Learn the system

### **2. Testnet Mode** (Practice with fake money)

Uses Bybit testnet with fake USDT.

**Setup:**
1. Create testnet account: https://testnet.bybit.com/
2. Get testnet API keys
3. Get free testnet USDT from faucet
4. Update `.env`:
   ```bash
   BYBIT_TESTNET=true
   ```

```python
# Testnet trading
trader = BybitTrader(testnet=True, paper_trading=False)
```

**Use this to:**
- ✅ Test with real API calls (fake money)
- ✅ Verify API signature works
- ✅ Practice order execution
- ✅ Test error handling

### **3. Live Trading Mode** (REAL MONEY - DANGEROUS!)

Uses real Bybit account with real USDT.

```python
# LIVE trading - REAL MONEY!
trader = BybitTrader(paper_trading=False)
```

**⚠️ Only use after:**
1. ✅ 100+ successful paper trades
2. ✅ Proven win rate >60% over weeks
3. ✅ Tested on testnet successfully
4. ✅ Understanding all risks
5. ✅ Starting with TINY positions (0.001 BTC)

---

## 📊 Risk Management Settings

Your current safety limits (in `.env`):

```bash
TRADING_ENABLED=false           # Master kill switch
POSITION_SIZE_BTC=0.001         # Tiny positions ($110 @ $110k BTC)
MAX_DAILY_LOSS_USD=50           # Stop trading after $50 loss
BYBIT_LEVERAGE=5                # 5x leverage (conservative)
```

### **Understanding Position Sizes**

```
BTC Price: $110,000
Position Size: 0.001 BTC

Position Value: 0.001 × $110,000 = $110
With 5x Leverage: $110 × 5 = $550 buying power
Margin Required: $110

If price moves 1%:
- Your position moves: 1% × 5 = 5%
- On $110 position: ±$5.50 P&L

Stop Loss at 0.3%:
- Position loss: 0.3% × 5 = 1.5%
- Dollar loss: $110 × 1.5% = $1.65
```

### **Recommended Starting Sizes**

| Account Size | Position Size | Max Loss Per Trade |
|--------------|---------------|-------------------|
| $500 | 0.0005 BTC (~$55) | $0.83 (0.3% stop) |
| $1,000 | 0.001 BTC (~$110) | $1.65 (0.3% stop) |
| $2,000 | 0.002 BTC (~$220) | $3.30 (0.3% stop) |
| $5,000 | 0.005 BTC (~$550) | $8.25 (0.3% stop) |

**Rule: Never risk more than 1% of account per trade**

---

## 🚀 Quick Start Guide

### **Step 1: Test Paper Trading**

```bash
cd /var/www/dev/trading
source venv/bin/activate
python3 bybit_trader.py
```

**Expected output:**
```
Testing Bybit API Connection...
✅ Leverage set to 5x
[PAPER TRADE] Order placed: LONG 0.001 BTC
```

### **Step 2: Test Real API Connection**

```python
from bybit_trader import BybitTrader

# Create trader (paper mode)
trader = BybitTrader(paper_trading=False)

# Test basic calls
balance = trader.get_balance()
print(f"Balance: ${balance:.2f}")

price = trader.get_current_price()
print(f"BTC Price: ${price:.2f}")

# Set leverage
trader.set_leverage()
```

### **Step 3: Test Manual Trade (Paper)**

```python
from bybit_trader import BybitTrader

trader = BybitTrader(paper_trading=True)

# Set leverage
trader.set_leverage()

# Place a long order
order_id = trader.place_order(
    side="Buy",
    qty=0.001,
    stop_loss=111000,  # $111k
    take_profit=113000  # $113k
)

print(f"Order ID: {order_id}")
```

### **Step 4: Integrate with Signal Monitor**

Coming next - automated signal execution!

---

## 📋 API Methods Reference

### **Account Methods**

```python
# Get USDT balance
balance = trader.get_balance()

# Get current BTC price
price = trader.get_current_price("BTCUSDT")

# Set leverage
trader.set_leverage("BTCUSDT")
```

### **Trading Methods**

```python
# Open LONG position
order_id = trader.place_order(
    side="Buy",
    qty=0.001,
    order_type="Market",
    stop_loss=111000,
    take_profit=113000
)

# Open SHORT position
order_id = trader.place_order(
    side="Sell",
    qty=0.001,
    order_type="Market",
    stop_loss=113000,
    take_profit=111000
)

# Close all positions
trader.close_position("BTCUSDT")
```

### **Position Management**

```python
# Get current position info
position = trader.get_position("BTCUSDT")

if position:
    print(f"Size: {position['size']} BTC")
    print(f"Side: {position['side']}")
    print(f"Entry: ${position['entry_price']:.2f}")
    print(f"P&L: ${position['unrealized_pnl']:.2f}")
```

### **Risk Management**

```python
# Update daily P&L
trader.update_daily_pnl(pnl=5.25)  # Made $5.25

# Reset at start of day
trader.reset_daily_pnl()

# Check if daily limit reached
if trader.daily_pnl <= -trader.max_daily_loss:
    print("Daily loss limit reached - stop trading")
```

---

## ⚠️ Important Safety Rules

### **Before Going Live:**

1. **✅ Test Everything in Paper Mode**
   - Run for at least 1 week
   - Verify signals are correct
   - Check win rate >60%

2. **✅ Use Testnet First**
   - Practice with fake money
   - Verify API calls work
   - Test error handling

3. **✅ Start Microscopic**
   - Use 0.001 BTC ($110) positions
   - Trade for 1 month at this size
   - Only increase if profitable

4. **✅ Set Stop Losses ALWAYS**
   - Every position must have stop loss
   - Never trade without protection
   - Honor your stops (don't move them)

5. **✅ Respect Daily Loss Limit**
   - Stop trading after $50 loss
   - Don't revenge trade
   - Review what went wrong

### **Common Mistakes to Avoid:**

❌ **Don't:** Start with large positions
✅ **Do:** Start with 0.001 BTC

❌ **Don't:** Skip paper trading
✅ **Do:** Test for weeks before live

❌ **Don't:** Trade on emotions
✅ **Do:** Follow your system mechanically

❌ **Don't:** Override stop losses
✅ **Do:** Honor every stop, no exceptions

❌ **Don't:** Revenge trade after losses
✅ **Do:** Stop for the day after daily limit

---

## 🔍 Monitoring Your Trades

### **Check Balance:**

```bash
python3 << 'EOF'
from bybit_trader import BybitTrader
trader = BybitTrader(paper_trading=False)
balance = trader.get_balance()
print(f"💰 Balance: ${balance:.2f} USDT")
EOF
```

### **Check Position:**

```bash
python3 << 'EOF'
from bybit_trader import BybitTrader
trader = BybitTrader(paper_trading=False)
pos = trader.get_position()
if pos and pos['size'] > 0:
    print(f"📊 Position: {pos['side']} {pos['size']} BTC")
    print(f"💵 Entry: ${pos['entry_price']:.2f}")
    print(f"📈 P&L: ${pos['unrealized_pnl']:.2f}")
else:
    print("No open positions")
EOF
```

### **Close Emergency Position:**

```bash
python3 << 'EOF'
from bybit_trader import BybitTrader
trader = BybitTrader(paper_trading=False)
trader.close_position()
EOF
```

---

## 📚 Next Steps

### **1. Test Connection (Do Now)**

```bash
cd /var/www/dev/trading
source venv/bin/activate
python3 << 'EOF'
from bybit_trader import BybitTrader

# Test with real API (but paper trading mode)
trader = BybitTrader(paper_trading=False)

print("Testing API connection...")
balance = trader.get_balance()
price = trader.get_current_price()

if balance is not None:
    print(f"✅ API Connected!")
    print(f"💰 Balance: ${balance:.2f}")
    print(f"💵 BTC Price: ${price:.2f}")
else:
    print("❌ API Connection failed")
EOF
```

### **2. Paper Trade for 1 Week**
- Let monitor generate signals
- See which ones would win
- Track hypothetical P&L

### **3. Integrate with Monitor** (Coming Next)
- Automatic signal execution
- Risk management built-in
- Email notifications

### **4. Go Live (Only After Success)**
- Proven strategy (>60% win rate)
- Tested on testnet
- Starting tiny (0.001 BTC)

---

## 🆘 Troubleshooting

### **"API credentials not found"**

Check `.env` file exists and has credentials:
```bash
cat .env | grep BYBIT
```

### **"Invalid signature" error**

- Check API key and secret are correct
- Ensure no extra spaces in `.env`
- Verify API permissions in Bybit dashboard

### **"Insufficient balance" error**

- Check your USDT balance in Bybit
- Ensure you have enough margin
- Reduce position size

### **Position not opening**

- Check leverage is set: `trader.set_leverage()`
- Verify sufficient balance
- Check daily loss limit not reached
- Review Bybit API logs

---

## 📞 Support

**Bybit API Documentation:**
https://bybit-exchange.github.io/docs/v5/intro

**Bybit Support:**
https://www.bybit.com/en-US/help-center/

**Your files:**
- API Wrapper: `bybit_trader.py`
- Credentials: `.env`
- This Guide: `BYBIT_TRADING_SETUP.md`

---

## ✅ Summary

**Status:** API configured and ready
**Mode:** Paper trading (safe)
**Leverage:** 5x
**Position Size:** 0.001 BTC (~$110)
**Daily Loss Limit:** $50

**Next:** Test API connection, then paper trade for 1 week before going live!

**⚠️ CRITICAL: Never skip paper trading. Start tiny. Use stop losses always.**
