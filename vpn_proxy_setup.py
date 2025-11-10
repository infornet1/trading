#!/usr/bin/env python3
"""
Setup SOCKS proxy through ZeroTier VPN for Bybit API access
This is the easiest solution - routes Python requests through your business network
"""

import subprocess
import sys
import time
import requests

ZT_GATEWAY = "172.28.10.10"  # Your business network gateway
SOCKS_PORT = 1080

def check_zerotier():
    """Check if ZeroTier is running"""
    try:
        result = subprocess.run(['ip', 'link', 'show', 'ztjlh4w6bx'],
                              capture_output=True, text=True)
        return result.returncode == 0
    except:
        return False

def check_gateway():
    """Check if gateway is reachable"""
    try:
        result = subprocess.run(['ping', '-c', '2', '-W', '2', ZT_GATEWAY],
                              capture_output=True, text=True)
        return result.returncode == 0
    except:
        return False

def setup_ssh_tunnel():
    """Setup SSH SOCKS proxy tunnel"""
    print("\n📡 Setting up SSH tunnel to gateway...")
    print(f"   Gateway: {ZT_GATEWAY}")
    print(f"   SOCKS Port: {SOCKS_PORT}")
    print()

    print("⚠️  This requires:")
    print(f"   1. SSH server running on {ZT_GATEWAY}")
    print("   2. SSH key or password access")
    print()

    username = input(f"SSH username on {ZT_GATEWAY}: ").strip()

    if not username:
        print("❌ Username required")
        return False

    print()
    print("Creating SSH tunnel...")
    print(f"Command: ssh -D {SOCKS_PORT} -N -f {username}@{ZT_GATEWAY}")
    print()

    try:
        # Try to create SSH tunnel
        cmd = [
            'ssh',
            '-D', str(SOCKS_PORT),
            '-N',  # No command execution
            '-f',  # Background
            '-o', 'StrictHostKeyChecking=no',
            '-o', 'ConnectTimeout=10',
            f'{username}@{ZT_GATEWAY}'
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode == 0:
            print("✅ SSH tunnel created!")
            return True
        else:
            print(f"❌ Failed to create tunnel: {result.stderr}")
            print()
            print("💡 Make sure:")
            print("   1. SSH server is running on gateway")
            print("   2. You can SSH manually: ssh {username}@{ZT_GATEWAY}")
            print("   3. Firewall allows SSH connections")
            return False

    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def test_proxy():
    """Test if SOCKS proxy works"""
    print("\n🧪 Testing SOCKS proxy...")

    proxies = {
        'http': f'socks5://127.0.0.1:{SOCKS_PORT}',
        'https': f'socks5://127.0.0.1:{SOCKS_PORT}'
    }

    try:
        # Test Bybit API through proxy
        response = requests.get(
            'https://api.bybit.com/v5/market/time',
            proxies=proxies,
            timeout=10
        )

        if response.status_code == 200:
            print("✅ Proxy works! Bybit API accessible")

            # Get BTC price to confirm
            response = requests.get(
                'https://api.bybit.com/v5/market/tickers?category=linear&symbol=BTCUSDT',
                proxies=proxies,
                timeout=10
            )

            if response.status_code == 200:
                data = response.json()
                price = float(data['result']['list'][0]['lastPrice'])
                print(f"✅ BTC Price: ${price:,.2f}")

            return True
        else:
            print(f"❌ Proxy not working (status: {response.status_code})")
            return False

    except Exception as e:
        print(f"❌ Proxy test failed: {e}")
        return False

def update_env_file():
    """Update .env file with proxy settings"""
    print("\n📝 Updating .env file...")

    try:
        # Read current .env
        with open('.env', 'r') as f:
            lines = f.readlines()

        # Check if SOCKS_PROXY already exists
        proxy_exists = any('SOCKS_PROXY' in line for line in lines)

        if not proxy_exists:
            # Add proxy setting
            with open('.env', 'a') as f:
                f.write(f'\n# SOCKS Proxy for VPN routing\n')
                f.write(f'SOCKS_PROXY=socks5://127.0.0.1:{SOCKS_PORT}\n')
            print("✅ Added SOCKS_PROXY to .env")
        else:
            print("✅ SOCKS_PROXY already in .env")

        return True

    except Exception as e:
        print(f"❌ Failed to update .env: {e}")
        return False

def main():
    print("=" * 60)
    print("ZeroTier VPN SOCKS Proxy Setup")
    print("=" * 60)

    # Check ZeroTier
    print("\n1. Checking ZeroTier...")
    if check_zerotier():
        print("   ✅ ZeroTier is running")
    else:
        print("   ❌ ZeroTier not found")
        print("   Make sure ZeroTier is installed and running")
        sys.exit(1)

    # Check gateway
    print("\n2. Checking gateway connectivity...")
    if check_gateway():
        print(f"   ✅ Gateway {ZT_GATEWAY} is reachable")
    else:
        print(f"   ❌ Gateway {ZT_GATEWAY} is not reachable")
        print("   Make sure your business network is online")
        sys.exit(1)

    # Setup SSH tunnel
    print("\n3. Setting up SSH tunnel...")
    if not setup_ssh_tunnel():
        print("\n❌ Setup failed")
        print("\n💡 Alternative: Route IP addresses directly")
        print("   Run: sudo ./setup_vpn_routing.sh")
        sys.exit(1)

    # Wait for tunnel to establish
    print("\n⏳ Waiting for tunnel to establish...")
    time.sleep(2)

    # Test proxy
    if test_proxy():
        print("\n🎉 Success! Bybit API is accessible through VPN")

        # Update .env
        update_env_file()

        print("\n" + "=" * 60)
        print("Setup Complete!")
        print("=" * 60)
        print("\n✅ Your trading bot will now use VPN for Bybit API")
        print("\n📝 Next steps:")
        print("   1. Test: python3 bybit_trader.py")
        print("   2. The bot will automatically use SOCKS proxy")
        print("   3. Monitor: ps aux | grep ssh  (to see tunnel)")
        print("\n⚠️  Keep SSH tunnel running for trading!")

    else:
        print("\n❌ Proxy test failed")
        print("\n💡 Troubleshooting:")
        print("   1. Check SSH tunnel: ps aux | grep ssh")
        print("   2. Test manually: curl --socks5 127.0.0.1:1080 https://api.bybit.com/v5/market/time")
        print("   3. Check gateway firewall settings")

if __name__ == "__main__":
    main()
