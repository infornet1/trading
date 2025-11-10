#!/bin/bash
# Setup routing for Bybit API through ZeroTier VPN
# This routes api.bybit.com traffic through your business network

echo "ZeroTier VPN Routing Setup for Bybit API"
echo "=========================================="

# ZeroTier gateway (your business router)
ZT_GATEWAY="172.28.10.10"

# Check if ZeroTier is running
if ! ip link show ztjlh4w6bx &>/dev/null; then
    echo "❌ Error: ZeroTier interface not found"
    echo "   Make sure ZeroTier is running"
    exit 1
fi

echo "✅ ZeroTier interface found"
echo "   Local IP: $(ip addr show ztjlh4w6bx | grep 'inet ' | awk '{print $2}')"
echo "   Gateway: $ZT_GATEWAY"

# Test if gateway is reachable
echo ""
echo "Testing gateway connectivity..."
if ping -c 2 -W 2 $ZT_GATEWAY &>/dev/null; then
    echo "✅ Gateway reachable"
else
    echo "❌ Gateway unreachable"
    echo "   Check if your business network is online"
    exit 1
fi

# Get Bybit API IP addresses
echo ""
echo "Resolving Bybit API addresses..."
BYBIT_IPS=$(dig +short api.bybit.com | grep -E '^[0-9]+\.' | head -5)

if [ -z "$BYBIT_IPS" ]; then
    echo "⚠️  Could not resolve api.bybit.com"
    echo "   Using DNS might be blocked"
else
    echo "Bybit API IPs:"
    echo "$BYBIT_IPS" | while read ip; do
        echo "   - $ip"
    done
fi

echo ""
echo "=========================================="
echo "Setup Options:"
echo "=========================================="
echo ""
echo "Option 1: Route only Bybit API through VPN (Recommended)"
echo "   → Other traffic uses normal internet"
echo "   → Lower latency for everything else"
echo ""
echo "Option 2: Route all traffic through VPN"
echo "   → All internet goes through business network"
echo "   → Higher latency but simpler"
echo ""
echo "Option 3: Use SOCKS proxy on gateway"
echo "   → Most flexible"
echo "   → Requires SOCKS server on $ZT_GATEWAY"
echo ""

read -p "Choose option (1/2/3): " choice

case $choice in
    1)
        echo ""
        echo "Setting up selective routing..."

        # Add route for each Bybit IP
        for ip in $BYBIT_IPS; do
            sudo ip route add $ip via $ZT_GATEWAY dev ztjlh4w6bx 2>/dev/null
            if [ $? -eq 0 ]; then
                echo "✅ Route added: $ip → $ZT_GATEWAY"
            else
                echo "⚠️  Route exists: $ip"
            fi
        done

        echo ""
        echo "✅ Selective routing configured!"
        echo "   Bybit API calls will use VPN"
        echo "   Other traffic uses normal internet"
        ;;

    2)
        echo ""
        echo "⚠️  This will route ALL traffic through VPN"
        read -p "Are you sure? (yes/no): " confirm

        if [ "$confirm" = "yes" ]; then
            echo "Adding default route via VPN..."

            # Backup current default route
            DEFAULT_GW=$(ip route | grep default | head -1)
            echo "$DEFAULT_GW" > /tmp/default_route_backup.txt

            # Add VPN as default route with higher priority
            sudo ip route add default via $ZT_GATEWAY dev ztjlh4w6bx metric 100

            echo "✅ Default route added via VPN"
            echo "   Backup saved to /tmp/default_route_backup.txt"
            echo ""
            echo "To restore: sudo ip route del default via $ZT_GATEWAY"
        else
            echo "Cancelled"
        fi
        ;;

    3)
        echo ""
        echo "SOCKS Proxy Setup"
        echo "================="
        echo ""
        echo "On your gateway ($ZT_GATEWAY), install SSH server:"
        echo "   sudo apt-get install openssh-server"
        echo ""
        echo "Then from this server, create SOCKS proxy:"
        echo "   ssh -D 1080 -N user@$ZT_GATEWAY &"
        echo ""
        echo "Update .env file:"
        echo "   SOCKS_PROXY=socks5://127.0.0.1:1080"
        echo ""
        echo "The Python script will automatically use it!"
        ;;

    *)
        echo "Invalid option"
        exit 1
        ;;
esac

echo ""
echo "=========================================="
echo "Testing Bybit API access..."
echo "=========================================="

# Test Bybit API
if curl -s --max-time 5 "https://api.bybit.com/v5/market/time" | grep -q "retCode"; then
    echo "✅ Bybit API is now accessible!"
    PRICE=$(curl -s "https://api.bybit.com/v5/market/tickers?category=linear&symbol=BTCUSDT" | grep -o '"lastPrice":"[0-9.]*"' | cut -d'"' -f4)
    if [ ! -z "$PRICE" ]; then
        echo "✅ BTC Price: \$$PRICE"
    fi
else
    echo "❌ Bybit API still blocked"
    echo ""
    echo "Troubleshooting:"
    echo "1. Check if $ZT_GATEWAY can access internet"
    echo "2. Test from gateway: curl https://api.bybit.com/v5/market/time"
    echo "3. Consider using SOCKS proxy (Option 3)"
fi

echo ""
echo "Done!"
