import os
import time
from dotenv import load_dotenv
from eth_account import Account
from hyperliquid.exchange import Exchange
from hyperliquid.info import Info
from hyperliquid.utils import constants

# Load environment variables
load_dotenv()

HL_SECRET_KEY = os.getenv("HYPERLIQUID_SECRET_KEY")
HL_ADDRESS = os.getenv("HYPERLIQUID_ACCOUNT_ADDRESS")

def run_order_test():
    print(f"🧪 Testing Live Order Management for: {HL_ADDRESS}...")
    
    if not HL_SECRET_KEY or not HL_ADDRESS:
        print("❌ Error: Credentials not found in .env")
        return

    try:
        # 1. Initialize
        info = Info(constants.MAINNET_API_URL, skip_ws=True)
        exchange = Exchange(Account.from_key(HL_SECRET_KEY), constants.MAINNET_API_URL, account_address=HL_ADDRESS)
        
        # 2. Update Leverage (Proves Write Access)
        print("⚙️  Step 1: Updating Leverage to 10x...")
        lev_result = exchange.update_leverage(10, "ETH")
        if lev_result["status"] == "ok":
            print("✅ Leverage update successful!")
        else:
            print(f"❌ Leverage update failed: {lev_result}")
            return

        # 3. Open a tiny position (0.01 ETH)
        print("🚀 Step 2: Opening a test 0.01 ETH Long...")
        # market_open(coin, is_buy, sz, px, slippage)
        order_result = exchange.market_open("ETH", True, 0.01, slippage=0.01)
        
        if order_result["status"] == "ok":
            print("✅ Order placed successfully!")
            tx_hash = order_result["response"]["data"]["statuses"][0]["resting"]["oid"]
            print(f"📜 Transaction OID: {tx_hash}")
            
            # 4. Wait and Close
            print("⏳ Waiting 3 seconds before closing...")
            time.sleep(3)
            
            print("🏁 Step 3: Closing test position...")
            close_result = exchange.market_close("ETH")
            if close_result["status"] == "ok":
                print("✅ Position closed successfully!")
                print("\n🎉 ALL TESTS PASSED! Your API is fully capable of managing orders.")
            else:
                print(f"❌ Failed to close: {close_result}")
        else:
            print(f"❌ Failed to open order: {order_result}")
            if "not authorized" in str(order_result):
                print("💡 Suggestion: Ensure the Agent address is authorized in Hyperliquid settings.")

    except Exception as e:
        print(f"❌ Test Failed with Error: {e}")

if __name__ == "__main__":
    run_order_test()
