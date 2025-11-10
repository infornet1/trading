#!/usr/bin/env python3
"""
BingX Futures Trading API Wrapper
Handles all interactions with BingX API for automated trading
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

logger = logging.getLogger('BingXTrader')


class BingXTrader:
    """BingX API wrapper for futures trading with 5x leverage"""

    def __init__(self, paper_trading=False):
        """
        Initialize BingX trader

        Args:
            paper_trading: Simulate trades without API calls (default: False)
        """
        self.api_key = os.getenv('BINGX_API_KEY')
        self.api_secret = os.getenv('BINGX_API_SECRET')
        self.leverage = int(os.getenv('BINGX_LEVERAGE', '5'))
        self.paper_trading = paper_trading
        self.base_url = "https://open-api.bingx.com"

        # Validate credentials
        if not self.api_key or not self.api_secret:
            raise ValueError("BingX API credentials not found in .env file")

        # Track daily P&L for risk management
        self.daily_pnl = 0.0
        self.max_daily_loss = float(os.getenv('MAX_DAILY_LOSS_USD', '50'))

        logger.info(f"BingXTrader initialized (Paper Trading: {paper_trading})")

    def _generate_signature(self, params: Dict[str, Any]) -> str:
        """
        Generate HMAC SHA256 signature for BingX API

        Args:
            params: Request parameters

        Returns:
            str: Hex signature
        """
        # Create params copy without signature
        sign_params = {k: v for k, v in params.items() if k != 'signature'}

        # Sort parameters and create query string
        query_string = '&'.join([f"{k}={v}" for k, v in sorted(sign_params.items())])

        # Generate HMAC SHA256 signature
        signature = hmac.new(
            self.api_secret.encode('utf-8'),
            query_string.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()

        return signature

    def _make_request(self, method: str, endpoint: str, params: Dict = None) -> Dict:
        """
        Make authenticated request to BingX API

        Args:
            method: HTTP method (GET, POST)
            endpoint: API endpoint
            params: Request parameters

        Returns:
            API response as dict
        """
        if self.paper_trading:
            logger.info(f"[PAPER TRADE] {method} {endpoint} - params: {params}")
            return {"code": 0, "msg": "success (paper trade)", "data": {}}

        if params is None:
            params = {}

        # Get BingX server time for accurate timestamp
        try:
            time_response = requests.get(f"{self.base_url}/openApi/swap/v2/server/time", timeout=5)
            if time_response.status_code == 200:
                params['timestamp'] = time_response.json()['data']['serverTime']
            else:
                params['timestamp'] = int(time.time() * 1000)
        except:
            params['timestamp'] = int(time.time() * 1000)

        # Generate signature
        signature = self._generate_signature(params)
        params['signature'] = signature

        headers = {
            'X-BX-APIKEY': self.api_key,
            'Content-Type': 'application/json'
        }

        url = f"{self.base_url}{endpoint}"

        try:
            if method == 'GET':
                response = requests.get(url, params=params, headers=headers)
            else:  # POST
                response = requests.post(url, json=params, headers=headers)

            response.raise_for_status()
            data = response.json()

            if data.get('code') != 0:
                logger.error(f"API Error: {data.get('msg')}")

            return data

        except Exception as e:
            logger.error(f"API Request failed: {e}")
            return {"code": -1, "msg": str(e), "data": {}}

    def set_leverage(self, symbol: str = "BTC-USDT", side: str = "LONG") -> bool:
        """
        Set leverage for trading pair

        Args:
            symbol: Trading symbol (default: BTC-USDT)
            side: LONG or SHORT

        Returns:
            bool: True if successful
        """
        endpoint = "/openApi/swap/v2/trade/leverage"
        params = {
            "symbol": symbol,
            "side": side,
            "leverage": self.leverage
        }

        logger.info(f"Setting {self.leverage}x leverage for {symbol} {side}")
        response = self._make_request("POST", endpoint, params)

        if response.get('code') == 0:
            logger.info(f"✅ Leverage set to {self.leverage}x")
            return True
        else:
            logger.error(f"❌ Failed to set leverage: {response.get('msg')}")
            return False

    def get_balance(self) -> Optional[float]:
        """
        Get USDT balance

        Returns:
            float: Available USDT balance
        """
        endpoint = "/openApi/swap/v2/user/balance"
        params = {}

        response = self._make_request("GET", endpoint, params)

        if response.get('code') == 0:
            try:
                balance_data = response['data']['balance']
                # Find USDT balance
                usdt_balance = balance_data.get('balance', 0)
                balance = float(usdt_balance)
                logger.info(f"💰 USDT Balance: ${balance:.2f}")
                return balance
            except (KeyError, ValueError) as e:
                logger.error(f"Failed to parse balance: {e}")

        return None

    def get_current_price(self, symbol: str = "BTC-USDT") -> Optional[float]:
        """
        Get current market price

        Args:
            symbol: Trading symbol

        Returns:
            float: Current price
        """
        endpoint = "/openApi/swap/v2/quote/ticker"
        params = {"symbol": symbol}

        response = self._make_request("GET", endpoint, params)

        if response.get('code') == 0:
            try:
                price = float(response['data']['lastPrice'])
                return price
            except (KeyError, ValueError):
                pass

        return None

    def place_order(self, side: str, position_side: str, qty: float,
                   symbol: str = "BTC-USDT", order_type: str = "MARKET",
                   stop_loss: float = None, take_profit: float = None) -> Optional[str]:
        """
        Place a futures order

        Args:
            side: "BUY" for open long/close short, "SELL" for open short/close long
            position_side: "LONG" or "SHORT" (which position type)
            qty: Position size in BTC (e.g., 0.001)
            symbol: Trading symbol (default: BTC-USDT)
            order_type: "MARKET" or "LIMIT"
            stop_loss: Stop loss price
            take_profit: Take profit price

        Returns:
            str: Order ID if successful
        """
        # Check daily loss limit
        if self.daily_pnl <= -self.max_daily_loss:
            logger.error(f"🛑 Daily loss limit reached (${self.daily_pnl:.2f})")
            return None

        endpoint = "/openApi/swap/v2/trade/order"
        params = {
            "symbol": symbol,
            "side": side,
            "positionSide": position_side,
            "type": order_type,
            "quantity": qty
        }

        # Add stop loss and take profit if provided
        if stop_loss:
            params['stopPrice'] = stop_loss
        if take_profit:
            params['takeProfit'] = take_profit

        action = f"{side} {position_side}"
        logger.info(f"📝 Placing order: {action} {qty} BTC @ {order_type}")

        if self.paper_trading:
            logger.info(f"[PAPER TRADE] Order placed: {action} {qty} BTC")
            return f"PAPER-{int(time.time())}"

        response = self._make_request("POST", endpoint, params)

        if response.get('code') == 0:
            order_id = response['data'].get('orderId')
            logger.info(f"✅ Order placed: {order_id}")
            return str(order_id)
        else:
            logger.error(f"❌ Order failed: {response.get('msg')}")
            return None

    def close_position(self, symbol: str = "BTC-USDT", position_side: str = "LONG") -> bool:
        """
        Close position for a symbol

        Args:
            symbol: Trading symbol
            position_side: "LONG" or "SHORT"

        Returns:
            bool: True if successful
        """
        # Get current position
        position = self.get_position(symbol, position_side)

        if not position or position['size'] == 0:
            logger.info(f"No open {position_side} position to close")
            return True

        # Determine closing side (opposite of position)
        close_side = "SELL" if position_side == "LONG" else "BUY"
        qty = position['size']

        logger.info(f"🔄 Closing {position_side} position: {qty} BTC")

        # Place closing order
        order_id = self.place_order(
            side=close_side,
            position_side=position_side,
            qty=qty,
            symbol=symbol,
            order_type="MARKET"
        )

        if order_id:
            logger.info(f"✅ Position closed")
            return True
        else:
            logger.error(f"❌ Failed to close position")
            return False

    def get_position(self, symbol: str = "BTC-USDT", position_side: str = "LONG") -> Optional[Dict]:
        """
        Get current position info

        Args:
            symbol: Trading symbol
            position_side: "LONG" or "SHORT"

        Returns:
            dict: Position info (size, entry_price, pnl)
        """
        endpoint = "/openApi/swap/v2/user/positions"
        params = {"symbol": symbol}

        response = self._make_request("GET", endpoint, params)

        if response.get('code') == 0:
            try:
                positions = response['data']
                # Find the position with matching side
                for pos in positions:
                    if pos.get('positionSide') == position_side:
                        return {
                            'size': float(pos.get('positionAmt', 0)),
                            'side': pos.get('positionSide'),
                            'entry_price': float(pos.get('avgPrice', 0)),
                            'unrealized_pnl': float(pos.get('unrealizedProfit', 0)),
                            'leverage': pos.get('leverage')
                        }
            except (KeyError, ValueError) as e:
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

    print("Testing BingX API Connection...\n")

    # Test in paper trading mode first
    print("1. Testing paper trading mode...")
    trader = BingXTrader(paper_trading=True)
    trader.set_leverage()
    trader.place_order("BUY", "LONG", 0.001)

    print("\n2. Testing real API connection...")
    trader = BingXTrader(paper_trading=False)

    balance = trader.get_balance()
    if balance is not None:
        print(f"   ✅ Balance: ${balance:.2f}")

    price = trader.get_current_price()
    if price:
        print(f"   ✅ BTC Price: ${price:,.2f}")

    if balance is not None and price:
        print("\n   ✅ BingX API is working!")
    else:
        print("\n   ❌ API connection issues")

    print("\n⚠️  IMPORTANT: Start with paper_trading=True for testing!")
