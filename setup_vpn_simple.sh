#!/bin/bash
# Simple VPN Proxy Setup for Bybit API

GATEWAY="172.28.10.10"
SOCKS_PORT=1080

echo "=========================================="
echo "Bybit API VPN Proxy Setup"
echo "=========================================="
echo ""

# Step 1: Get username
echo "Step 1: SSH Username"
echo "-------------------"
echo "What username do you use to SSH to your gateway?"
echo "Common options: root, admin, pi, or your business username"
echo ""
read -p "SSH Username: " SSH_USER

if [ -z "$SSH_USER" ]; then
    echo "❌ Username required"
    exit 1
fi

echo ""
echo "Step 2: Testing SSH connection..."
echo "-------------------"
echo "Trying to connect to $SSH_USER@$GATEWAY"
echo "(You may need to enter password)"
echo ""

# Test SSH connection
if ssh -o ConnectTimeout=10 -o StrictHostKeyChecking=no $SSH_USER@$GATEWAY "echo '✅ SSH connection works!'" 2>/dev/null; then
    echo ""
    echo "✅ SSH access confirmed!"
else
    echo ""
    echo "❌ Could not connect. Please check:"
    echo "   1. Username is correct"
    echo "   2. Password is correct"
    echo "   3. SSH server is running on gateway"
    exit 1
fi

echo ""
echo "Step 3: Creating SOCKS tunnel..."
echo "-------------------"

# Kill any existing tunnel
pkill -f "ssh -D $SOCKS_PORT"

# Create SSH tunnel in background
echo "Creating tunnel: ssh -D $SOCKS_PORT -N -f $SSH_USER@$GATEWAY"
echo "(You may need to enter password again)"
echo ""

ssh -D $SOCKS_PORT -N -f -o ServerAliveInterval=60 -o StrictHostKeyChecking=no $SSH_USER@$GATEWAY

if [ $? -eq 0 ]; then
    echo "✅ SSH tunnel created!"

    # Wait a moment for tunnel to establish
    sleep 2

    # Check if tunnel is running
    if ps aux | grep -v grep | grep -q "ssh -D $SOCKS_PORT"; then
        echo "✅ Tunnel is running (PID: $(pgrep -f "ssh -D $SOCKS_PORT"))"
    else
        echo "⚠️  Tunnel may not be running"
    fi
else
    echo "❌ Failed to create tunnel"
    exit 1
fi

echo ""
echo "Step 4: Testing Bybit API access..."
echo "-------------------"

# Test with curl through SOCKS proxy
if command -v curl &> /dev/null; then
    echo "Testing: curl --socks5 127.0.0.1:$SOCKS_PORT https://api.bybit.com/v5/market/time"

    RESPONSE=$(curl -s --socks5 127.0.0.1:$SOCKS_PORT --max-time 10 https://api.bybit.com/v5/market/time)

    if echo "$RESPONSE" | grep -q "retCode"; then
        echo "✅ Bybit API is accessible through VPN!"

        # Try to get BTC price
        BTC_RESPONSE=$(curl -s --socks5 127.0.0.1:$SOCKS_PORT --max-time 10 "https://api.bybit.com/v5/market/tickers?category=linear&symbol=BTCUSDT")

        if echo "$BTC_RESPONSE" | grep -q "lastPrice"; then
            PRICE=$(echo "$BTC_RESPONSE" | grep -o '"lastPrice":"[0-9.]*"' | head -1 | cut -d'"' -f4)
            echo "✅ BTC Price: \$$PRICE"
        fi
    else
        echo "❌ Bybit API still not accessible"
        echo "Response: $RESPONSE"
    fi
fi

echo ""
echo "Step 5: Updating .env file..."
echo "-------------------"

# Update .env file
if grep -q "SOCKS_PROXY" .env 2>/dev/null; then
    echo "✅ SOCKS_PROXY already in .env"
else
    echo "" >> .env
    echo "# SOCKS Proxy for VPN routing" >> .env
    echo "SOCKS_PROXY=socks5://127.0.0.1:$SOCKS_PORT" >> .env
    echo "✅ Added SOCKS_PROXY to .env"
fi

echo ""
echo "=========================================="
echo "✅ Setup Complete!"
echo "=========================================="
echo ""
echo "SSH Tunnel Details:"
echo "  Username: $SSH_USER"
echo "  Gateway: $GATEWAY"
echo "  SOCKS Port: $SOCKS_PORT"
echo "  Status: Running"
echo ""
echo "Next Steps:"
echo "  1. Test trading bot: python3 bybit_trader.py"
echo "  2. Check tunnel status: ps aux | grep 'ssh -D'"
echo "  3. Monitor tunnel: watch 'ps aux | grep ssh'"
echo ""
echo "To make tunnel persistent (auto-start on boot):"
echo "  sudo nano /etc/systemd/system/zerotier-proxy.service"
echo ""
echo "Tunnel will stay running until you:"
echo "  - Reboot server (need to restart)"
echo "  - Kill it: pkill -f 'ssh -D $SOCKS_PORT'"
echo ""
echo "Happy Trading! 🚀"
echo "=========================================="
