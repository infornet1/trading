import os
import json
from dotenv import load_dotenv
from eth_account import Account
from hyperliquid.info import Info
from hyperliquid.utils import constants

# Load environment variables
load_dotenv()

HL_SECRET_KEY = os.getenv("HYPERLIQUID_SECRET_KEY")
HL_ADDRESS = os.getenv("HYPERLIQUID_ACCOUNT_ADDRESS") # Main account

def test_api():
    print(f"🧪 Final Diagnostic: Testing for {HL_ADDRESS}...")
    
    if not HL_SECRET_KEY or not HL_ADDRESS:
        print("❌ Error: HYPERLIQUID_SECRET_KEY or HYPERLIQUID_ACCOUNT_ADDRESS not found in .env")
        return

    try:
        # Initialize Info API
        info = Info(constants.MAINNET_API_URL, skip_ws=True)
        
        # 1. Fetch live ETH price
        all_mids = info.all_mids()
        eth_price = all_mids.get("ETH")
        print(f"✅ Connection Successful! Live ETH Price: ${eth_price}")

        # 2. Check User State
        user_state = info.user_state(HL_ADDRESS)
        
        # A. Check Cross Margin Summary (standard for perps)
        cross_margin = user_state.get("crossMarginSummary", {})
        account_value = float(cross_margin.get("accountValue", "0"))
        
        # B. Check Spot State (USDC is often held as a spot asset on Hyperliquid L1)
        spot_state = info.spot_user_state(HL_ADDRESS)
        spot_balances = spot_state.get("balances", [])
        
        usdc_spot_balance = 0.0
        for asset in spot_balances:
            if asset.get('coin') == 'USDC':
                usdc_spot_balance = float(asset.get('total', '0'))

        print("-" * 50)
        print(f"📊 PERP MARGIN ACCOUNT VALUE: ${account_value:.2f} USDC")
        print(f"📊 SPOT USDC BALANCE:         ${usdc_spot_balance:.2f} USDC")

        # Decision
        total_balance = max(account_value, usdc_spot_balance)
        
        print("-" * 50)

        if total_balance >= 10:
            print(f"🚀 SUCCESS: Found total available of ${total_balance:.2f} USDC.")
            print("✅ You are ready for live trading!")
        else:
            print(f"⚠️  BALANCE TOO LOW: Found only ${total_balance:.2f} USDC.")
            print("💡 To trade, deposit at least $10 USDC into your Perp account on Hyperliquid.")

    except Exception as e:
        print(f"❌ API Diagnostic Failed: {e}")

if __name__ == "__main__":
    test_api()
