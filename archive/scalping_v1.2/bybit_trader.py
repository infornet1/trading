#!/usr/bin/env python3
"""
Bybit Futures Trading API Wrapper
Handles all interactions with Bybit API for automated trading
"""

import os
import time
import hmac
import hashlib
import requests
import json
import logging
from datetime import datetime
from typing import Optional, Dict, Any
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

logger = logging.getLogger('BybitTrader')


class BybitTrader:
    """Bybit API wrapper for futures trading with 5x leverage"""

    def __init__(self, testnet=False, paper_trading=False):
        """
        Initialize Bybit trader

        Args:
            testnet: Use testnet (default: False, use from .env)
            paper_trading: Simulate trades without API calls (default: False)
        """
        self.api_key = os.getenv('BYBIT_API_KEY')
        self.api_secret = os.getenv('BYBIT_API_SECRET')
        self.leverage = int(os.getenv('BYBIT_LEVERAGE', '5'))
        self.paper_trading = paper_trading

        # SOCKS proxy support for VPN routing
        self.socks_proxy = os.getenv('SOCKS_PROXY')
        self.proxies = None
        if self.socks_proxy:
            self.proxies = {
                'http': self.socks_proxy,
                'https': self.socks_proxy
            }
            logger.info(f"Using SOCKS proxy: {self.socks_proxy}")

        # Use testnet setting from env if not explicitly set
        if os.getenv('BYBIT_TESTNET', 'false').lower() == 'true':
            testnet = True

        # Set base URL
        if testnet:
            self.base_url = "https://api-testnet.bybit.com"
            logger.info("Using Bybit TESTNET")
        else:
            self.base_url = "https://api.bybit.com"
            logger.info("Using Bybit MAINNET")

        # Validate credentials
        if not self.api_key or not self.api_secret:
            raise ValueError("API credentials not found in .env file")

        # Track daily P&L for risk management
        self.daily_pnl = 0.0
        self.max_daily_loss = float(os.getenv('MAX_DAILY_LOSS_USD', '50'))

        logger.info(f"BybitTrader initialized (Paper Trading: {paper_trading})")

    def _generate_signature(self, method: str, params: Dict[str, Any], timestamp: str) -> str:
        """
        Generate HMAC SHA256 signature for API request

        Args:
            method: HTTP method (GET or POST)
            params: Request parameters
            timestamp: Request timestamp

        Returns:
            str: Hex signature
        """
        recv_window = '5000'

        if method == 'GET':
            # For GET: timestamp + api_key + recv_window + queryString
            param_str = timestamp + self.api_key + recv_window
            if params:
                query_string = '&'.join([f"{k}={v}" for k, v in sorted(params.items())])
                param_str += query_string
        else:
            # For POST: timestamp + api_key + recv_window + jsonBodyString
            param_str = timestamp + self.api_key + recv_window
            if params:
                param_str += json.dumps(params, separators=(',', ':'))

        # Generate HMAC SHA256 signature
        signature = hmac.new(
            self.api_secret.encode('utf-8'),
            param_str.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()

        return signature

    def _make_request(self, method: str, endpoint: str, params: Dict = None) -> Dict:
        """
        Make authenticated request to Bybit API

        Args:
            method: HTTP method (GET, POST)
            endpoint: API endpoint
            params: Request parameters

        Returns:
            API response as dict
        """
        if self.paper_trading:
            logger.info(f"[PAPER TRADE] {method} {endpoint} - params: {params}")
            return {"retCode": 0, "retMsg": "OK (paper trade)", "result": {}}

        if params is None:
            params = {}

        timestamp = str(int(time.time() * 1000))
        signature = self._generate_signature(method, params, timestamp)

        headers = {
            'X-BAPI-API-KEY': self.api_key,
            'X-BAPI-SIGN': signature,
            'X-BAPI-TIMESTAMP': timestamp,
            'X-BAPI-RECV-WINDOW': '5000',
            'Content-Type': 'application/json'
        }

        url = f"{self.base_url}{endpoint}"

        try:
            if method == 'GET':
                response = requests.get(url, params=params, headers=headers, proxies=self.proxies)
            else:  # POST
                response = requests.post(url, json=params, headers=headers, proxies=self.proxies)

            response.raise_for_status()
            data = response.json()

            if data.get('retCode') != 0:
                logger.error(f"API Error: {data.get('retMsg')}")

            return data

        except Exception as e:
            logger.error(f"API Request failed: {e}")
            return {"retCode": -1, "retMsg": str(e), "result": {}}

    def set_leverage(self, symbol: str = "BTCUSDT") -> bool:
        """
        Set leverage for trading pair

        Args:
            symbol: Trading symbol (default: BTCUSDT)

        Returns:
            bool: True if successful
        """
        endpoint = "/v5/position/set-leverage"
        params = {
            "category": "linear",
            "symbol": symbol,
            "buyLeverage": str(self.leverage),
            "sellLeverage": str(self.leverage)
        }

        logger.info(f"Setting {self.leverage}x leverage for {symbol}")
        response = self._make_request("POST", endpoint, params)

        if response.get('retCode') == 0:
            logger.info(f"✅ Leverage set to {self.leverage}x")
            return True
        else:
            logger.error(f"❌ Failed to set leverage: {response.get('retMsg')}")
            return False

    def get_balance(self) -> Optional[float]:
        """
        Get USDT balance

        Returns:
            float: Available USDT balance
        """
        endpoint = "/v5/account/wallet-balance"
        params = {
            "accountType": "UNIFIED"
        }

        response = self._make_request("GET", endpoint, params)

        if response.get('retCode') == 0:
            try:
                coins = response['result']['list'][0]['coin']
                for coin in coins:
                    if coin['coin'] == 'USDT':
                        balance = float(coin['walletBalance'])
                        logger.info(f"💰 USDT Balance: ${balance:.2f}")
                        return balance
            except (KeyError, IndexError) as e:
                logger.error(f"Failed to parse balance: {e}")

        return None

    def get_current_price(self, symbol: str = "BTCUSDT") -> Optional[float]:
        """
        Get current market price

        Args:
            symbol: Trading symbol

        Returns:
            float: Current price
        """
        endpoint = "/v5/market/tickers"
        params = {
            "category": "linear",
            "symbol": symbol
        }

        response = self._make_request("GET", endpoint, params)

        if response.get('retCode') == 0:
            try:
                price = float(response['result']['list'][0]['lastPrice'])
                return price
            except (KeyError, IndexError):
                pass

        return None

    def place_order(self, side: str, qty: float, symbol: str = "BTCUSDT",
                   order_type: str = "Market", stop_loss: float = None,
                   take_profit: float = None) -> Optional[str]:
        """
        Place a futures order

        Args:
            side: "Buy" for long, "Sell" for short
            qty: Position size in BTC (e.g., 0.001)
            symbol: Trading symbol (default: BTCUSDT)
            order_type: "Market" or "Limit"
            stop_loss: Stop loss price
            take_profit: Take profit price

        Returns:
            str: Order ID if successful
        """
        # Check daily loss limit
        if self.daily_pnl <= -self.max_daily_loss:
            logger.error(f"🛑 Daily loss limit reached (${self.daily_pnl:.2f})")
            return None

        endpoint = "/v5/order/create"
        params = {
            "category": "linear",
            "symbol": symbol,
            "side": side,
            "orderType": order_type,
            "qty": str(qty),
            "timeInForce": "GTC",
            "positionIdx": 0
        }

        # Add stop loss and take profit if provided
        if stop_loss:
            params['stopLoss'] = str(stop_loss)
        if take_profit:
            params['takeProfit'] = str(take_profit)

        direction = "LONG" if side == "Buy" else "SHORT"
        logger.info(f"📝 Placing {direction} order: {qty} BTC @ Market")

        if self.paper_trading:
            logger.info(f"[PAPER TRADE] Order placed: {direction} {qty} BTC")
            return f"PAPER-{int(time.time())}"

        response = self._make_request("POST", endpoint, params)

        if response.get('retCode') == 0:
            order_id = response['result'].get('orderId')
            logger.info(f"✅ Order placed: {order_id}")
            return order_id
        else:
            logger.error(f"❌ Order failed: {response.get('retMsg')}")
            return None

    def close_position(self, symbol: str = "BTCUSDT") -> bool:
        """
        Close all positions for a symbol

        Args:
            symbol: Trading symbol

        Returns:
            bool: True if successful
        """
        # Get current position
        position = self.get_position(symbol)

        if not position or position['size'] == 0:
            logger.info("No open position to close")
            return True

        # Determine opposite side
        current_side = position['side']
        close_side = "Sell" if current_side == "Buy" else "Buy"
        qty = position['size']

        logger.info(f"🔄 Closing {current_side} position: {qty} BTC")

        # Place closing order
        endpoint = "/v5/order/create"
        params = {
            "category": "linear",
            "symbol": symbol,
            "side": close_side,
            "orderType": "Market",
            "qty": str(qty),
            "reduceOnly": True,
            "positionIdx": 0
        }

        response = self._make_request("POST", endpoint, params)

        if response.get('retCode') == 0:
            logger.info(f"✅ Position closed")
            return True
        else:
            logger.error(f"❌ Failed to close position: {response.get('retMsg')}")
            return False

    def get_position(self, symbol: str = "BTCUSDT") -> Optional[Dict]:
        """
        Get current position info

        Args:
            symbol: Trading symbol

        Returns:
            dict: Position info (size, side, entry_price, pnl)
        """
        endpoint = "/v5/position/list"
        params = {
            "category": "linear",
            "symbol": symbol
        }

        response = self._make_request("GET", endpoint, params)

        if response.get('retCode') == 0:
            try:
                positions = response['result']['list']
                if positions:
                    pos = positions[0]
                    return {
                        'size': float(pos.get('size', 0)),
                        'side': pos.get('side'),
                        'entry_price': float(pos.get('avgPrice', 0)),
                        'unrealized_pnl': float(pos.get('unrealisedPnl', 0)),
                        'leverage': pos.get('leverage')
                    }
            except (KeyError, IndexError) as e:
                logger.error(f"Failed to parse position: {e}")

        return None

    def update_daily_pnl(self, pnl: float):
        """Update daily P&L tracker"""
        self.daily_pnl += pnl
        logger.info(f"📊 Daily P&L: ${self.daily_pnl:.2f}")

    def reset_daily_pnl(self):
        """Reset daily P&L (call at start of new trading day)"""
        self.daily_pnl = 0.0
        logger.info("🔄 Daily P&L reset")


if __name__ == "__main__":
    # Test connection
    logging.basicConfig(level=logging.INFO)

    print("Testing Bybit API Connection...\n")

    # Test in paper trading mode first
    trader = BybitTrader(paper_trading=True)

    print("\n1. Testing paper trading mode...")
    trader.set_leverage()
    trader.place_order("Buy", 0.001)

    print("\n2. To test real API connection, set paper_trading=False")
    print("   trader = BybitTrader(paper_trading=False)")
    print("   balance = trader.get_balance()")
    print("   price = trader.get_current_price()")

    print("\n⚠️  IMPORTANT: Start with paper_trading=True for testing!")
