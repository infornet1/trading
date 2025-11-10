#!/bin/bash
# Test Direct IP Routing to Bybit through ZeroTier VPN

GATEWAY="172.28.10.10"
ZT_INTERFACE="ztjlh4w6bx"

echo "=========================================="
echo "Testing Direct IP Routing to Bybit"
echo "=========================================="
echo ""

# Step 1: Check ZeroTier
echo "Step 1: Checking ZeroTier connection..."
echo "-------------------"
if ip link show $ZT_INTERFACE &>/dev/null; then
    ZT_IP=$(ip addr show $ZT_INTERFACE | grep 'inet ' | awk '{print $2}')
    echo "✅ ZeroTier interface: $ZT_INTERFACE"
    echo "   Local IP: $ZT_IP"
else
    echo "❌ ZeroTier interface not found"
    exit 1
fi

# Step 2: Test gateway
echo ""
echo "Step 2: Testing gateway connectivity..."
echo "-------------------"
if ping -c 2 -W 2 $GATEWAY &>/dev/null; then
    PING_TIME=$(ping -c 1 -W 2 $GATEWAY | grep 'time=' | awk -F'time=' '{print $2}' | awk '{print $1}')
    echo "✅ Gateway reachable: $GATEWAY"
    echo "   Latency: ${PING_TIME}ms"
else
    echo "❌ Gateway not reachable"
    exit 1
fi

# Step 3: Get Bybit IPs
echo ""
echo "Step 3: Resolving Bybit API addresses..."
echo "-------------------"
BYBIT_IPS=$(dig +short api.bybit.com | grep -E '^[0-9]+\.' | head -5)

if [ -z "$BYBIT_IPS" ]; then
    echo "❌ Could not resolve api.bybit.com"
    echo "   Trying alternative DNS..."
    BYBIT_IPS=$(host api.bybit.com 8.8.8.8 | grep 'has address' | awk '{print $4}' | head -5)
fi

if [ -z "$BYBIT_IPS" ]; then
    echo "❌ Still cannot resolve Bybit IPs"
    exit 1
fi

echo "Found Bybit IPs:"
echo "$BYBIT_IPS" | while read ip; do
    echo "   - $ip"
done

# Step 4: Test current access (should fail)
echo ""
echo "Step 4: Testing current Bybit access (before routing)..."
echo "-------------------"
if curl -s --max-time 5 https://api.bybit.com/v5/market/time | grep -q "retCode"; then
    echo "⚠️  Bybit API already accessible (no routing needed!)"
    echo "   You can use Bybit API directly"
    exit 0
else
    echo "✅ Confirmed: Bybit is blocked (as expected)"
fi

# Step 5: Add test route
echo ""
echo "Step 5: Adding test route for ONE Bybit IP..."
echo "-------------------"
TEST_IP=$(echo "$BYBIT_IPS" | head -1)
echo "Test IP: $TEST_IP"
echo "Command: sudo ip route add $TEST_IP via $GATEWAY dev $ZT_INTERFACE"

# Check if route already exists
if ip route show | grep -q "$TEST_IP"; then
    echo "⚠️  Route already exists, removing old route..."
    sudo ip route del $TEST_IP 2>/dev/null
fi

# Add route
if sudo ip route add $TEST_IP via $GATEWAY dev $ZT_INTERFACE 2>/dev/null; then
    echo "✅ Route added successfully"
else
    echo "❌ Failed to add route (already exists or permission issue)"
fi

# Verify route
if ip route show | grep -q "$TEST_IP"; then
    echo "✅ Route confirmed in routing table"
    ip route show | grep "$TEST_IP"
else
    echo "❌ Route not in routing table"
fi

# Step 6: Test Bybit access through route
echo ""
echo "Step 6: Testing Bybit API through VPN route..."
echo "-------------------"
echo "Waiting 2 seconds for route to activate..."
sleep 2

echo "Testing: curl https://api.bybit.com/v5/market/time"
RESPONSE=$(curl -s --max-time 10 https://api.bybit.com/v5/market/time)

if echo "$RESPONSE" | grep -q "retCode"; then
    echo "✅ SUCCESS! Bybit API is accessible through VPN!"
    echo ""
    echo "Response: $RESPONSE" | head -c 100
    echo "..."
    
    # Try to get BTC price
    echo ""
    echo "Testing BTC price fetch..."
    BTC_RESPONSE=$(curl -s --max-time 10 "https://api.bybit.com/v5/market/tickers?category=linear&symbol=BTCUSDT")
    
    if echo "$BTC_RESPONSE" | grep -q "lastPrice"; then
        PRICE=$(echo "$BTC_RESPONSE" | grep -o '"lastPrice":"[0-9.]*"' | head -1 | cut -d'"' -f4)
        echo "✅ BTC Price: \$$PRICE"
    fi
    
    # Success - ask about adding all routes
    echo ""
    echo "=========================================="
    echo "✅ DIRECT ROUTING WORKS!"
    echo "=========================================="
    echo ""
    echo "Would you like to add routes for ALL Bybit IPs?"
    echo "This will make Bybit API fully accessible."
    echo ""
    read -p "Add all routes? (yes/no): " ADD_ALL
    
    if [ "$ADD_ALL" = "yes" ]; then
        echo ""
        echo "Adding routes for all Bybit IPs..."
        for ip in $BYBIT_IPS; do
            if ! ip route show | grep -q "^$ip"; then
                sudo ip route add $ip via $GATEWAY dev $ZT_INTERFACE 2>/dev/null
                if [ $? -eq 0 ]; then
                    echo "✅ Added: $ip → $GATEWAY"
                else
                    echo "⚠️  Skipped: $ip (already exists)"
                fi
            else
                echo "⚠️  Exists: $ip"
            fi
        done
        
        echo ""
        echo "✅ All routes added!"
        echo ""
        echo "Current Bybit routes:"
        ip route show | grep ztjlh4w6bx | grep -v "172.28.0.0"
        
        echo ""
        echo "⚠️  NOTE: These routes will disappear on reboot"
        echo "To make permanent, add to /etc/rc.local or systemd"
    else
        echo "Skipped adding all routes"
    fi
    
else
    echo "❌ FAILED: Bybit API still not accessible"
    echo ""
    echo "Response: $RESPONSE"
    echo ""
    echo "Possible issues:"
    echo "1. Gateway doesn't have IP forwarding enabled"
    echo "2. Gateway firewall blocking traffic"
    echo "3. Gateway cannot access Bybit either"
    echo ""
    echo "To check gateway IP forwarding:"
    echo "  ssh root@$GATEWAY 'cat /proc/sys/net/ipv4/ip_forward'"
    echo "  (Should return '1', if '0' run:)"
    echo "  ssh root@$GATEWAY 'echo 1 > /proc/sys/net/ipv4/ip_forward'"
    
    # Clean up test route
    echo ""
    echo "Removing test route..."
    sudo ip route del $TEST_IP 2>/dev/null
    
    echo ""
    echo "=========================================="
    echo "❌ Direct routing doesn't work"
    echo "Recommendation: Use SSH SOCKS method instead"
    echo "Run: ./setup_vpn_simple.sh"
    echo "=========================================="
fi

echo ""
echo "Test complete!"
