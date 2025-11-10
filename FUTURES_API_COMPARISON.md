# Bybit vs BingX Futures Trading API Comparison

## ✅ Quick Answer

**YES, both Bybit and BingX support placing buy/sell futures orders with 5x leverage via API!**

Both exchanges offer robust APIs for automated futures trading with customizable leverage settings.

---

## 📊 Feature Comparison

| Feature | Bybit | BingX |
|---------|-------|-------|
| **Futures Trading API** | ✅ Yes (V5 API) | ✅ Yes (V2 API) |
| **5x Leverage Support** | ✅ Yes (1-125x) | ✅ Yes (1-150x) |
| **Set Leverage via API** | ✅ Yes | ✅ Yes (default 5x) |
| **Place Market Orders** | ✅ Yes | ✅ Yes |
| **Place Limit Orders** | ✅ Yes | ✅ Yes |
| **Stop Loss / Take Profit** | ✅ Yes | ✅ Yes |
| **API Documentation Quality** | ⭐⭐⭐⭐⭐ Excellent | ⭐⭐⭐⭐ Good |
| **Code Examples** | ✅ Multiple languages | ⚠️ Limited |
| **Max Leverage** | 125x | 150x |
| **Default Leverage** | User set | 5x |
| **KYC Required for 5x** | ✅ Yes | ✅ Yes |

---

## 🔷 Bybit API (Recommended)

### Why Bybit?
- ✅ Better documentation
- ✅ More mature API (V5)
- ✅ Unified API for all products
- ✅ Better code examples
- ✅ Larger trading community
- ✅ More reliable uptime

### API Endpoints

**Base URL:**
```
https://api.bybit.com
```

**1. Set Leverage**
```
POST /v5/position/set-leverage
```

**Parameters:**
```json
{
  "category": "linear",        // USDT perpetual
  "symbol": "BTCUSDT",         // Trading pair
  "buyLeverage": "5",          // Long leverage (5x)
  "sellLeverage": "5"          // Short leverage (5x)
}
```

**2. Place Order**
```
POST /v5/order/create
```

**Parameters (Long Position):**
```json
{
  "category": "linear",
  "symbol": "BTCUSDT",
  "side": "Buy",               // Buy = Long
  "orderType": "Market",       // or "Limit"
  "qty": "0.01",              // Position size in BTC
  "timeInForce": "GTC",
  "positionIdx": 0            // 0 = one-way mode
}
```

**Parameters (Short Position):**
```json
{
  "category": "linear",
  "symbol": "BTCUSDT",
  "side": "Sell",             // Sell = Short
  "orderType": "Market",
  "qty": "0.01",
  "timeInForce": "GTC",
  "positionIdx": 0
}
```

**3. Close Position**
```
POST /v5/order/create
```

**Close Long (same as opening short):**
```json
{
  "category": "linear",
  "symbol": "BTCUSDT",
  "side": "Sell",             // Opposite side to close
  "orderType": "Market",
  "qty": "0.01",
  "reduceOnly": true          // Important: only close, don't open opposite
}
```

### Python Example

```python
import hmac
import time
import requests
import json

class BybitAPI:
    def __init__(self, api_key, api_secret):
        self.api_key = api_key
        self.api_secret = api_secret
        self.base_url = "https://api.bybit.com"

    def _sign(self, params):
        """Generate signature for authentication"""
        timestamp = str(int(time.time() * 1000))
        params['api_key'] = self.api_key
        params['timestamp'] = timestamp

        param_str = '&'.join([f"{k}={params[k]}" for k in sorted(params.keys())])
        signature = hmac.new(
            self.api_secret.encode('utf-8'),
            param_str.encode('utf-8'),
            'sha256'
        ).hexdigest()

        params['sign'] = signature
        return params

    def set_leverage(self, symbol, leverage):
        """Set leverage for a trading pair"""
        endpoint = "/v5/position/set-leverage"
        params = {
            'category': 'linear',
            'symbol': symbol,
            'buyLeverage': str(leverage),
            'sellLeverage': str(leverage)
        }

        signed_params = self._sign(params)
        response = requests.post(
            f"{self.base_url}{endpoint}",
            json=signed_params
        )
        return response.json()

    def place_order(self, symbol, side, qty, order_type='Market'):
        """
        Place a futures order
        side: 'Buy' for long, 'Sell' for short
        """
        endpoint = "/v5/order/create"
        params = {
            'category': 'linear',
            'symbol': symbol,
            'side': side,
            'orderType': order_type,
            'qty': str(qty),
            'timeInForce': 'GTC',
            'positionIdx': 0
        }

        signed_params = self._sign(params)
        response = requests.post(
            f"{self.base_url}{endpoint}",
            json=signed_params
        )
        return response.json()

# Usage Example
api = BybitAPI('YOUR_API_KEY', 'YOUR_API_SECRET')

# Set 5x leverage
api.set_leverage('BTCUSDT', 5)

# Open long position (buy)
api.place_order('BTCUSDT', 'Buy', 0.01)

# Close long position (sell)
api.place_order('BTCUSDT', 'Sell', 0.01)
```

### Documentation
- **Official Docs**: https://bybit-exchange.github.io/docs/v5/intro
- **Set Leverage**: https://bybit-exchange.github.io/docs/v5/position/leverage
- **Place Order**: https://bybit-exchange.github.io/docs/v5/order/create-order

---

## 🔶 BingX API (Alternative)

### Why BingX?
- ✅ Higher max leverage (150x)
- ✅ Default 5x leverage (no need to set)
- ⚠️ Less documentation
- ⚠️ Smaller community

### API Endpoints

**Base URL:**
```
https://open-api.bingx.com
```

**1. Set Leverage**
```
POST /openApi/swap/v2/trade/leverage
```

**Parameters:**
```json
{
  "symbol": "BTC-USDT",        // Note: Different format than Bybit
  "side": "LONG",              // LONG or SHORT
  "leverage": 5                // 1-150x
}
```

**2. Place Order**
```
POST /openApi/swap/v2/trade/order
```

**Parameters (Long Position):**
```json
{
  "symbol": "BTC-USDT",
  "side": "BUY",               // BUY = Open Long
  "positionSide": "LONG",      // Position direction
  "type": "MARKET",            // or "LIMIT"
  "quantity": 0.01             // Position size
}
```

**Parameters (Short Position):**
```json
{
  "symbol": "BTC-USDT",
  "side": "SELL",              // SELL = Open Short
  "positionSide": "SHORT",
  "type": "MARKET",
  "quantity": 0.01
}
```

**3. Close Position**

**Close Long:**
```json
{
  "symbol": "BTC-USDT",
  "side": "SELL",              // Opposite to close
  "positionSide": "LONG",      // Which position to close
  "type": "MARKET",
  "quantity": 0.01
}
```

### Python Example

```python
import hmac
import time
import requests

class BingXAPI:
    def __init__(self, api_key, api_secret):
        self.api_key = api_key
        self.api_secret = api_secret
        self.base_url = "https://open-api.bingx.com"

    def _sign(self, params):
        """Generate signature"""
        timestamp = str(int(time.time() * 1000))
        params['timestamp'] = timestamp

        param_str = '&'.join([f"{k}={params[k]}" for k in sorted(params.keys())])
        signature = hmac.new(
            self.api_secret.encode('utf-8'),
            param_str.encode('utf-8'),
            'sha256'
        ).hexdigest()

        return signature, timestamp

    def set_leverage(self, symbol, leverage, side='LONG'):
        """Set leverage"""
        endpoint = "/openApi/swap/v2/trade/leverage"
        params = {
            'symbol': symbol,
            'side': side,
            'leverage': leverage
        }

        signature, timestamp = self._sign(params)

        headers = {
            'X-BX-APIKEY': self.api_key,
        }

        params['signature'] = signature

        response = requests.post(
            f"{self.base_url}{endpoint}",
            params=params,
            headers=headers
        )
        return response.json()

    def place_order(self, symbol, side, position_side, quantity):
        """
        Place order
        side: 'BUY' or 'SELL'
        position_side: 'LONG' or 'SHORT'
        """
        endpoint = "/openApi/swap/v2/trade/order"
        params = {
            'symbol': symbol,
            'side': side,
            'positionSide': position_side,
            'type': 'MARKET',
            'quantity': quantity
        }

        signature, timestamp = self._sign(params)

        headers = {
            'X-BX-APIKEY': self.api_key,
        }

        params['signature'] = signature

        response = requests.post(
            f"{self.base_url}{endpoint}",
            params=params,
            headers=headers
        )
        return response.json()

# Usage Example
api = BingXAPI('YOUR_API_KEY', 'YOUR_API_SECRET')

# Set 5x leverage
api.set_leverage('BTC-USDT', 5, 'LONG')

# Open long position
api.place_order('BTC-USDT', 'BUY', 'LONG', 0.01)

# Close long position
api.place_order('BTC-USDT', 'SELL', 'LONG', 0.01)
```

### Documentation
- **Official Docs**: https://bingx-api.github.io/docs/
- **GitHub Issues**: https://github.com/BingX-API/BingX-swap-api-doc/issues

---

## 🎯 Which Should You Choose?

### Choose Bybit If:
- ✅ You want better documentation
- ✅ You need reliable code examples
- ✅ You value API stability
- ✅ You want larger community support
- ✅ You plan to scale your trading bot
- ✅ You're a beginner with APIs

**Recommendation: Start with Bybit** - Better developer experience

### Choose BingX If:
- ✅ You want higher max leverage (150x vs 125x)
- ✅ You prefer default 5x leverage
- ✅ You have experience with exchange APIs
- ✅ You want lower fees (check current rates)

---

## ⚠️ Important Considerations

### Risk Management

**With 5x Leverage:**
- A 20% move against you = liquidation
- A 1% price move = 5% gain or loss
- **Always use stop losses!**

**Position Sizing:**
```
Example with $1,000 capital at 5x leverage:

Max position value: $5,000
Safe position: $1,000 (1x effectively)
Risk per trade: $100 (10% of capital)

If BTC is $50,000:
- Max position: 0.1 BTC ($5,000)
- Safe position: 0.02 BTC ($1,000)
- Conservative: 0.002 BTC ($100)
```

### API Keys Security

**Both Exchanges:**
1. Enable IP whitelist
2. Disable withdrawals for trading API keys
3. Store keys in environment variables (never in code)
4. Use separate keys for testing

**Example .env file:**
```bash
BYBIT_API_KEY=your_key_here
BYBIT_API_SECRET=your_secret_here

BINGX_API_KEY=your_key_here
BINGX_API_SECRET=your_secret_here
```

### Testing

**Always test on testnet first:**

**Bybit Testnet:**
- URL: https://api-testnet.bybit.com
- Get testnet funds: https://testnet.bybit.com/

**BingX:**
- Use minimal position sizes in production
- Test with $10-20 worth first

---

## 🚀 Integration with Your BTC Monitor

You can integrate either API with your existing BTC scalping monitor!

### Integration Example

```python
# In btc_monitor.py, add automated trading:

from bybit_api import BybitAPI  # Your API wrapper

class BTCMonitor:
    def __init__(self, config_file='config.json', enable_trading=False):
        # ... existing code ...

        # Initialize trading API
        self.trading_enabled = enable_trading
        if enable_trading:
            self.api = BybitAPI(
                os.getenv('BYBIT_API_KEY'),
                os.getenv('BYBIT_API_SECRET')
            )
            self.api.set_leverage('BTCUSDT', 5)

    def execute_trade(self, signal_type, price):
        """Execute trade based on signal"""
        if not self.trading_enabled:
            return

        position_size = 0.001  # Start small!

        if signal_type == 'RSI_OVERSOLD':
            # Open long position
            self.api.place_order('BTCUSDT', 'Buy', position_size)
            print(f"🟢 Opened LONG at ${price}")

        elif signal_type == 'RSI_OVERBOUGHT':
            # Open short position
            self.api.place_order('BTCUSDT', 'Sell', position_size)
            print(f"🔴 Opened SHORT at ${price}")
```

**⚠️ WARNING**: Automated trading is extremely risky. Only enable after:
1. 100+ successful paper trades
2. Win rate >60% proven over weeks
3. Risk capital you can afford to lose
4. Testing with minimum position sizes

---

## 📚 Next Steps

### 1. Choose Your Exchange
- **Recommended**: Start with Bybit (better docs)

### 2. Create API Keys
- Enable trading permissions
- Restrict to your IP
- Disable withdrawals

### 3. Test Connection
```python
# test_connection.py
from your_api_wrapper import BybitAPI

api = BybitAPI('key', 'secret')
print(api.get_balance())  # Check if connected
```

### 4. Paper Trade First
- Log signals from monitor
- Manually "execute" trades
- Track hypothetical results
- **Don't use real API until proven profitable**

### 5. Start Tiny
- Use 0.001 BTC positions ($50-100)
- Maximum 1% risk per trade
- Stop after 2% daily loss

---

## ✅ Summary

**Both Bybit and BingX support 5x leverage futures trading via API!**

| Aspect | Winner |
|--------|--------|
| Documentation | 🏆 Bybit |
| Max Leverage | 🏆 BingX (150x) |
| API Stability | 🏆 Bybit |
| Beginner Friendly | 🏆 Bybit |
| Overall Recommendation | 🏆 **Bybit** |

**Start with Bybit for the best developer experience and more reliable API.**

---

**Ready to implement?** Let me know if you want me to create a complete trading bot integration with your existing BTC monitor system!

**⚠️ Remember**: Leverage trading is extremely risky. Only trade with money you can afford to lose completely. Start with paper trading and tiny positions.
