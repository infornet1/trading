import os
import time
import json
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from decimal import Decimal
from dotenv import load_dotenv
from web3 import Web3
from eth_account import Account
from hyperliquid.exchange import Exchange
from hyperliquid.info import Info
from hyperliquid.utils import constants

# Load environment variables
load_dotenv()

# Configuration
RPC_URL = os.getenv("ARBITRUM_RPC_URL", "https://arb1.arbitrum.io/rpc")
NFT_ID = int(os.getenv("UNISWAP_NFT_ID", 5364087))
HL_SECRET_KEY = os.getenv("HYPERLIQUID_SECRET_KEY")
HL_ADDRESS = os.getenv("HYPERLIQUID_ACCOUNT_ADDRESS")
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", 30))
TRIGGER_OFFSET = float(os.getenv("TRIGGER_OFFSET_PCT", 0.5)) / 100.0

# Strategy Parameters (DeFi Suite / Raúl Martín Specs)
LEVERAGE = 10
DEFAULT_SL_PCT = 0.005 # 0.5%
BREAKEVEN_PROFIT_PCT = 0.01 # 1.0%
HEDGE_SIZE_ETH = 0.05

# Email Configuration
EMAIL_CONFIG_PATH = "/var/www/dev/trading/email_config.json"
RECIPIENTS = ["perdomo.gustavo@gmail.com", "carlosam81@gmail.com"]

# Uniswap v3 Position Manager
V3_POS_MANAGER = "0xC36442b4a4522E871399CD717aBDD847Ab11FE88"
V3_ABI = [
    {"inputs": [{"internalType": "uint256", "name": "tokenId", "type": "uint256"}], "name": "positions", "outputs": [
        {"internalType": "uint96", "name": "nonce", "type": "uint96"}, {"internalType": "address", "name": "operator", "type": "address"},
        {"internalType": "address", "name": "token0", "type": "address"}, {"internalType": "address", "name": "token1", "type": "address"},
        {"internalType": "uint24", "name": "fee", "type": "uint24"}, {"internalType": "int24", "name": "tickLower", "type": "int24"},
        {"internalType": "int24", "name": "tickUpper", "type": "int24"}, {"internalType": "uint128", "name": "liquidity", "type": "uint128"},
        {"internalType": "uint256", "name": "feeGrowthInside0LastX128", "type": "uint256"}, {"internalType": "uint256", "name": "feeGrowthInside1LastX128", "type": "uint256"},
        {"internalType": "uint128", "name": "tokensOwed0", "type": "uint128"}, {"internalType": "uint128", "name": "tokensOwed1", "type": "uint128"}
    ], "stateMutability": "view", "type": "function"}
]

def tick_to_price(tick):
    return (1.0001 ** tick) * (10 ** 12)

class LiveHedgeBot:
    def __init__(self):
        print(f"⚙️  Initializing Bot Aragan v1.2 for {HL_ADDRESS}...")
        self.w3 = Web3(Web3.HTTPProvider(RPC_URL))
        self.contract = self.w3.eth.contract(address=V3_POS_MANAGER, abi=V3_ABI)
        self.info = Info(constants.MAINNET_API_URL, skip_ws=True)
        self.exchange = Exchange(Account.from_key(HL_SECRET_KEY), constants.MAINNET_API_URL, account_address=HL_ADDRESS)
        self.hedge_active = False
        self.entry_price = None
        self.current_sl_price = None
        self.breakeven_reached = False
        self.lower_bound = None
        self.upper_bound = None
        self.email_config = self._load_email_config()

    def _load_email_config(self):
        try:
            with open(EMAIL_CONFIG_PATH, "r") as f:
                return json.load(f)
        except Exception as e:
            print(f"⚠️  Could not load email config: {e}")
            return None

    def send_email_alert(self, subject, body):
        if not self.email_config: return
        try:
            msg = MIMEMultipart()
            msg['From'] = self.email_config['sender_email']
            msg['To'] = ", ".join(RECIPIENTS)
            msg['Subject'] = f"🛡️ [Hedge Bot v1.2] {subject}"
            msg.attach(MIMEText(body, 'plain'))
            server = smtplib.SMTP(self.email_config['smtp_server'], self.email_config['smtp_port'])
            server.starttls()
            server.login(self.email_config['smtp_username'], self.email_config['smtp_password'])
            server.send_message(msg)
            server.quit()
            print(f"📧 Email alert sent to {len(RECIPIENTS)} recipients")
        except Exception as e:
            print(f"❌ Failed to send email: {e}")

    def get_position_bounds(self):
        try:
            pos = self.contract.functions.positions(NFT_ID).call()
            self.lower_bound = tick_to_price(pos[5])
            self.upper_bound = tick_to_price(pos[6])
            print(f"✅ Range Verified: ${self.lower_bound:.2f} - ${self.upper_bound:.2f}")
            return self.lower_bound, self.upper_bound
        except Exception as e:
            print(f"❌ Error fetching position: {e}")
            return None, None

    def get_eth_price(self):
        try:
            return float(self.info.all_mids()["ETH"])
        except Exception as e:
            return None

    def open_hedge(self, price):
        print(f"🚨 TRIGGERED: ETH ${price:.2f} is below range floor.")
        try:
            # 1. Update Leverage to 10x
            self.exchange.update_leverage(LEVERAGE, "ETH")
            
            # 2. Open Market Short
            order_result = self.exchange.market_open("ETH", False, HEDGE_SIZE_ETH, slippage=0.01)
            
            if order_result["status"] == "ok":
                self.entry_price = price
                self.hedge_active = True
                self.breakeven_reached = False
                
                # 3. Calculate Stop Loss (0.5% or Lower Bound if bounce protection needed)
                # If we are already deep out of range, SL is the lower bound.
                self.current_sl_price = max(self.entry_price * (1 + DEFAULT_SL_PCT), self.lower_bound)
                
                print(f"✅ Hedge OPENED. Entry: ${self.entry_price:.2f} | SL: ${self.current_sl_price:.2f}")
                self.send_email_alert(
                    "Hedge OPENED 🚨",
                    f"Action: 10x SHORT Opened\nEntry Price: ${self.entry_price:.2f}\nStop Loss: ${self.current_sl_price:.2f} (0.5%)\nGoal: Protect Uniswap NFT #{NFT_ID}"
                )
            else:
                print(f"❌ Order Failed: {order_result}")
        except Exception as e:
            print(f"❌ Execution Error: {e}")

    def manage_active_hedge(self, price):
        """Handle SL, Breakeven, and Take Profit logic"""
        # A. Stop Loss Hit
        if price >= self.current_sl_price:
            print(f"🛑 STOP LOSS HIT at ${price:.2f}. Closing hedge.")
            self.close_hedge(price, reason="Stop Loss Hit")
            return

        # B. Breakeven Trigger (1% Profit)
        # For a short, 1% profit means price dropped 1% below entry
        if not self.breakeven_reached and price <= self.entry_price * (1 - BREAKEVEN_PROFIT_PCT):
            self.current_sl_price = self.entry_price # Move SL to Entry
            self.breakeven_reached = True
            print(f"🛡️  BREAKEVEN REACHED. SL moved to entry: ${self.current_sl_price:.2f}")
            self.send_email_alert("Hedge Protected 🛡️", f"Short profit reached 1%. SL moved to entry (${self.entry_price:.2f}). Trade is now risk-free.")

        # C. Take Profit (Price returns to Lower Bound)
        if price >= self.lower_bound:
            print(f"🎉 TAKE PROFIT: Price back in range at ${price:.2f}.")
            self.close_hedge(price, reason="Price Returned to Range (TP)")

    def close_hedge(self, price, reason):
        try:
            order_result = self.exchange.market_close("ETH")
            if order_result["status"] == "ok":
                print(f"✅ Hedge CLOSED. Reason: {reason}")
                self.hedge_active = False
                self.send_email_alert(f"Hedge CLOSED ✅", f"Reason: {reason}\nExit Price: ${price:.2f}\nYour Uniswap position is now active/protected.")
            else:
                print(f"❌ Close failed: {order_result}")
        except Exception as e:
            print(f"❌ Order error: {e}")

    def run(self):
        print("🚀 Bot Aragan v1.2 - Live with DeFi Suite Logic")
        self.get_position_bounds()
        # Initial status check
        price = self.get_eth_price()
        trigger_price = self.lower_bound * (1 - TRIGGER_OFFSET)
        
        self.send_email_alert("Bot v1.2 Started 🚀", f"Monitoring NFT #{NFT_ID}\nRange: ${self.lower_bound:.2f} - ${self.upper_bound:.2f}\nTrigger: ${trigger_price:.2f}\nRecipients: {', '.join(RECIPIENTS)}")

        while True:
            price = self.get_eth_price()
            if price:
                if not self.hedge_active:
                    if price <= trigger_price:
                        self.open_hedge(price)
                else:
                    self.manage_active_hedge(price)
                
                status = "🟢 IN RANGE" if price >= self.lower_bound else "🔴 OUT OF RANGE"
                hedge = "🛡️ ON" if self.hedge_active else "⚪ OFF"
                print(f"[{time.strftime('%H:%M:%S')}] ETH: ${price:.2f} | {status} | Hedge: {hedge}", end="\r")
            
            time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    bot = LiveHedgeBot()
    bot.run()
